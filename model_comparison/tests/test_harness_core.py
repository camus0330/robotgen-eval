"""Deterministic lifecycle tests; no network, files, real tools or sleep."""

import unittest

from model_comparison.tools.harness_core import (
    ModelError, ModelReply, MockModel, MockToolHandler, ToolCall, ToolResult,
    run_agent,
)


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class HarnessCoreTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.tool = MockToolHandler()
        self.call = ToolCall("call-1", "echo", {"text": "hello"})
        self.final = ModelReply(content="done", final=True)

    def run_loop(self, model, tool=None, turns=3, wall=10):
        return run_agent(model, self.tool if tool is None else tool,
                         turns, wall, clock=self.clock)

    def assert_terminal(self, result, status, reason, turns, kinds):
        self.assertEqual(result.status, status)
        self.assertEqual(result.termination_reason, reason)
        self.assertEqual(result.model_turns, turns)
        self.assertEqual([event.kind for event in result.events], kinds)
        self.assertEqual(kinds.count("TERMINATION"), 1)
        self.assertEqual(result.events[-1].kind, "TERMINATION")
        self.assertEqual(result.events[-1].data, reason)

    def test_direct_final(self):
        model = MockModel([self.final])
        result = self.run_loop(model, turns=1)
        self.assert_terminal(result, "COMPLETED", "final", 1,
                             ["MODEL_REQUEST", "MODEL_RESPONSE", "TERMINATION"])
        self.assertEqual(len(model.histories), 1)
        self.assertEqual(result.events[1].data.content, "done")

    def test_tool_cycle_order_and_history(self):
        reply = ModelReply(tool_calls=(self.call,))
        model = MockModel([reply, self.final])
        result = self.run_loop(model, turns=2)
        self.assert_terminal(result, "COMPLETED", "final", 2, [
            "MODEL_REQUEST", "MODEL_RESPONSE", "TOOL_CALL", "TOOL_RESULT",
            "MODEL_REQUEST", "MODEL_RESPONSE", "TERMINATION",
        ])
        self.assertEqual(result.events[3].data,
                         ToolResult("call-1", True, {"text": "hello"}))
        self.assertEqual(model.histories[1], result.events[:5])
        self.assertEqual(len(model.histories[0]), 1)

    def test_failed_tool_result_reaches_next_model_turn(self):
        call = ToolCall("bad", "forced_failure", {})
        model = MockModel([ModelReply(tool_calls=(call,)), self.final])
        result = self.run_loop(model)
        self.assertEqual(result.status, "COMPLETED")
        failure = model.histories[1][3].data
        self.assertEqual(failure, ToolResult("bad", False, "forced_failure"))
        self.assertEqual(result.model_turns, 2)

    def test_tool_exception_becomes_failure_without_traceback(self):
        def broken_tool(call):
            raise RuntimeError("synthetic internal detail")

        model = MockModel([ModelReply(tool_calls=(self.call,)), self.final])
        result = self.run_loop(model, tool=broken_tool)
        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(model.histories[1][3].data,
                         ToolResult("call-1", False, "tool_exception"))
        self.assertNotIn("Traceback", repr(result.events))
        self.assertNotIn("synthetic internal detail", repr(result.events))

    def test_model_error_is_terminal_and_not_retried(self):
        class BrokenModel:
            calls = 0

            def respond(self, history):
                self.calls += 1
                raise ModelError("synthetic model failure")

        model = BrokenModel()
        result = self.run_loop(model)
        self.assert_terminal(result, "GENERATION_FAILED", "model_error", 1,
                             ["MODEL_REQUEST", "TERMINATION"])
        self.assertEqual(model.calls, 1)

    def test_mock_exhaustion_is_model_error(self):
        model = MockModel([])
        result = self.run_loop(model)
        self.assertEqual((result.status, result.termination_reason),
                         ("GENERATION_FAILED", "model_error"))
        self.assertEqual(len(model.histories), 1)

    def test_turn_limit_never_calls_model_n_plus_one(self):
        reply = ModelReply(tool_calls=(self.call,))
        model = MockModel([reply, reply, self.final])
        result = self.run_loop(model, turns=2)
        self.assert_terminal(result, "GENERATION_FAILED", "model_turn_limit", 2,
                             ["MODEL_REQUEST", "MODEL_RESPONSE", "TOOL_CALL",
                              "TOOL_RESULT"] * 2 + ["TERMINATION"])
        self.assertEqual(len(model.histories), 2)

    def test_invalid_model_replies_do_not_execute_tools(self):
        replies = [ModelReply(tool_calls=(self.call,), final=True), ModelReply(),
                   ModelReply(final="yes"), ModelReply(tool_calls=("bad",)), None]
        for reply in replies:
            with self.subTest(reply=reply):
                calls = []
                result = self.run_loop(MockModel([reply]), tool=calls.append)
                self.assert_terminal(result, "GENERATION_FAILED", "invalid_model_reply", 1,
                                     ["MODEL_REQUEST", "MODEL_RESPONSE", "TERMINATION"])
                self.assertEqual(calls, [])

    def test_tool_arguments_must_be_dict(self):
        for arguments in (None, [], "text"):
            with self.subTest(arguments=arguments), self.assertRaises(TypeError):
                ToolCall("id", "echo", arguments)

    def test_multiple_tools_keep_order_and_failure_context(self):
        calls = (self.call, ToolCall("bad", "forced_failure", {}),
                 ToolCall("last", "echo", {"value": 2}))
        model = MockModel([ModelReply(tool_calls=calls), self.final])
        result = self.run_loop(model)
        self.assert_terminal(result, "COMPLETED", "final", 2,
                             ["MODEL_REQUEST", "MODEL_RESPONSE"]
                             + ["TOOL_CALL", "TOOL_RESULT"] * 3
                             + ["MODEL_REQUEST", "MODEL_RESPONSE", "TERMINATION"])
        results = [e.data for e in model.histories[1] if e.kind == "TOOL_RESULT"]
        self.assertEqual([r.call_id for r in results], ["call-1", "bad", "last"])
        self.assertEqual([r.ok for r in results], [True, False, True])

    def test_timeout_before_first_request(self):
        model = MockModel([self.final])
        result = self.run_loop(model, wall=0)
        self.assert_terminal(result, "TIMEOUT", "wall_time_exceeded", 0,
                             ["TERMINATION"])
        self.assertEqual(model.histories, [])

    def test_timeout_after_model_return_prevents_tools_or_completion(self):
        for reply in (ModelReply(tool_calls=(self.call,)), self.final):
            with self.subTest(reply=reply):
                clock = self.clock

                class SlowModel:
                    def respond(self, history):
                        clock.advance(10)
                        return reply

                calls = []
                result = self.run_loop(SlowModel(), tool=calls.append)
                self.assert_terminal(result, "TIMEOUT", "wall_time_exceeded", 1,
                                     ["MODEL_REQUEST", "MODEL_RESPONSE", "TERMINATION"])
                self.assertEqual(calls, [])

    def test_timeout_after_tool_prevents_next_tool_and_model(self):
        calls = []

        def slow_tool(call):
            calls.append(call.call_id)
            self.clock.advance(10)
            return self.tool(call)

        for tool_calls in ((self.call,), (self.call, ToolCall("second", "echo", {}))):
            with self.subTest(tool_calls=tool_calls):
                calls.clear()
                model = MockModel([ModelReply(tool_calls=tool_calls), self.final])
                result = self.run_loop(model, tool=slow_tool)
                self.assert_terminal(result, "TIMEOUT", "wall_time_exceeded", 1, [
                    "MODEL_REQUEST", "MODEL_RESPONSE", "TOOL_CALL", "TOOL_RESULT",
                    "TERMINATION",
                ])
                self.assertEqual(calls, ["call-1"])
                self.assertEqual(len(model.histories), 1)

    def test_zero_turn_budget_does_not_call_model(self):
        model = MockModel([self.final])
        result = self.run_loop(model, turns=0)
        self.assert_terminal(result, "GENERATION_FAILED", "model_turn_limit", 0,
                             ["TERMINATION"])
        self.assertEqual(model.histories, [])

    def test_invalid_limits_fail_before_model_call(self):
        model = MockModel([self.final])
        for turns, wall in [(-1, 10), (True, 10), (1.5, 10), (1, -1),
                            (1, True), (1, float("nan")), (1, float("inf"))]:
            with self.subTest(turns=turns, wall=wall), self.assertRaises(ValueError):
                self.run_loop(model, turns=turns, wall=wall)
        self.assertEqual(model.histories, [])

    def test_invalid_tool_result_becomes_failure(self):
        for response in (None, ToolResult("wrong-id", True, "bad"),
                         ToolResult("call-1", "yes", "bad")):
            with self.subTest(response=response):
                model = MockModel([ModelReply(tool_calls=(self.call,)), self.final])
                result = self.run_loop(model, tool=lambda call: response)
                self.assertEqual(result.status, "COMPLETED")
                self.assertEqual(model.histories[1][3].data,
                                 ToolResult("call-1", False, "invalid_tool_result"))

    def test_unknown_mock_tool_returns_failure(self):
        self.assertEqual(self.tool(ToolCall("id", "unknown", {})),
                         ToolResult("id", False, "unknown_tool"))

    def test_identical_scripts_produce_identical_results(self):
        replies = [ModelReply(tool_calls=(self.call,)), self.final]
        first = self.run_loop(MockModel(replies))
        second = self.run_loop(MockModel(replies))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
