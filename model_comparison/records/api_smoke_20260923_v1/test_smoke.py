"""Synthetic HTTP transport only; these are not gateway/model observations."""
import base64
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx2 as httpx
from openai import OpenAI, DefaultHttpxClient
import smoke


KEY = "SYNTHETIC_TEST_KEY_ONLY"


def completion(text="OK", finish="stop"):
    return {"id": "synthetic", "object": "chat.completion", "created": 0,
            "model": "synthetic-returned-model", "choices": [{"index": 0,
            "finish_reason": finish, "message": {"role": "assistant", "content": text,
            "reasoning_content": "DO_NOT_SAVE_HIDDEN_REASONING"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


class SmokeTests(unittest.TestCase):
    def exercise(self, handler):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            transport = DefaultHttpxClient(transport=httpx.MockTransport(handler), follow_redirects=False)
            with OpenAI(api_key=KEY, base_url=smoke.BASE_URL, max_retries=0,
                        timeout=120.0, http_client=transport) as client, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                status = smoke.run_checks(client, KEY, run)
            files = {p.name: json.loads(p.read_text()) for p in run.iterdir()}
            self.assertNotIn(KEY, output.getvalue())
            self.assertNotIn("DO_NOT_SAVE_HIDDEN_REASONING", json.dumps(files))
            return status, files

    def test_exact_two_payloads_and_original_image_bytes(self):
        sent = []
        def handler(request):
            self.assertEqual(str(request.url), smoke.TARGET)
            self.assertEqual(request.method, "POST")
            sent.append(json.loads(request.content))
            return httpx.Response(200, json=completion(), headers={"x-request-id": "synthetic-id"})
        status, files = self.exercise(handler)
        self.assertEqual(status, 0)
        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[0], {"model": "glm-5.3", "messages": [
            {"role": "user", "content": "Reply with exactly: OK"}],
            "temperature": 0, "max_tokens": 256, "stream": False})
        self.assertEqual(set(sent[1]), set(sent[0]))
        self.assertEqual(sent[1]["model"], "deepseek-v4-pro")
        self.assertEqual(sent[1]["max_tokens"], 1024)
        self.assertEqual(sent[1]["temperature"], 0)
        self.assertIs(sent[1]["stream"], False)
        parts = sent[1]["messages"][0]["content"]
        self.assertEqual(parts[0]["text"], smoke.IMAGE_PROMPT)
        uri = parts[1]["image_url"]["url"]
        self.assertTrue(uri.startswith("data:image/png;base64,"))
        self.assertEqual(base64.b64decode(uri.split(",", 1)[1]), smoke.IMAGE.read_bytes())
        second = files["2_deepseek-v4-pro.json"]
        self.assertEqual(second["image_sha256"], hashlib.sha256(smoke.IMAGE.read_bytes()).hexdigest())
        self.assertTrue(second["image_send_attempted"])
        self.assertTrue(second["image_server_accepted"])
        self.assertIsNone(second["answer_matches_image"])

    def test_502_stops_after_one_and_redacts_key(self):
        sent = []
        def handler(request):
            sent.append(True)
            return httpx.Response(502, json={"error": {"message": "synthetic " + KEY}},
                                  headers={"x-request-id": "synthetic-id"})
        status, files = self.exercise(handler)
        self.assertEqual((status, len(sent), len(files)), (2, 1, 1))
        record = files["1_glm-5.3.json"]
        self.assertEqual(record["http_status"], 502)
        self.assertEqual(record["outcome"], "HTTP_ERROR_OUTCOME_UNKNOWN")

    def test_timeout_no_replay_unknown_status(self):
        sent = []
        def handler(request):
            sent.append(True)
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        status, files = self.exercise(handler)
        self.assertEqual((status, len(sent), len(files)), (2, 1, 1))
        self.assertIsNone(files["1_glm-5.3.json"]["http_status"])
        self.assertEqual(files["1_glm-5.3.json"]["outcome"], "OUTCOME_UNKNOWN")

    def test_empty_or_length_never_start_image_request(self):
        for content, finish, outcome in (("", "stop", "EMPTY_CONTENT"), ("OK", "length", "LENGTH_LIMIT")):
            with self.subTest(outcome=outcome):
                sent = []
                def handler(request):
                    sent.append(True)
                    return httpx.Response(200, json=completion(content, finish))
                status, files = self.exercise(handler)
                self.assertEqual((status, len(sent)), (2, 1))
                self.assertEqual(files["1_glm-5.3.json"]["outcome"], outcome)

    def test_existing_run_cannot_be_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "live").mkdir()
            with patch.object(smoke, "BATCH", root), \
                 patch.dict(smoke.os.environ, {"SMART_AGI_API_KEY": KEY}), \
                 patch.object(smoke, "OpenAI") as client:
                with self.assertRaises(FileExistsError):
                    smoke.main()
                client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
