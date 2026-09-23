# SDK-only channel smoke test

Status at handoff: **NOT_STARTED_MISSING_KEY; actual model requests = 0**.
This is not a successful channel admission, a robot attempt, a visual capability
result, or an independent review. See `preparation.json` for local setup evidence.

Run in a local interactive terminal:

```bash
cd /home/camus/robotgen-eval-v2
.tools/api-smoke/bin/python -B model_comparison/records/api_smoke_20260923_v1/smoke.py
```

The script uses `SMART_AGI_API_KEY` if already present. Otherwise `getpass`
prompts without echo or shell-history storage. Do not paste a Key into chat,
command arguments or a committed file. No credential files are searched/read.

It reserves `live/` once, then sends at most one `glm-5.3` Chat Completions
request. The administrator's message and generation parameters are unchanged.
Only a nonempty completion with `finish_reason=stop` enables the one
`deepseek-v4-pro` image request. Exact `OK` compliance is recorded separately.
Empty content, length truncation, HTTP failure and timeout stop progression.
Both use the official OpenAI SDK, zero retries, 120-second timeout and exactly
`https://big-model.smart-agi.com/v1/chat/completions`. Redirects and repeat HTTP
sends are rejected. No `/models`, other model, tool, response format, reasoning
parameter, Agent, LiteLLM or generated-code execution is used. Proxy settings
are inherited unchanged, without recording their values.

Each result is printed immediately and saved under `live/`; HTTP status, timing,
visible reply or redacted error, returned model, finish reason, usage totals and
request ID are retained. Unknowns remain null. SDK responses are not serialized
wholesale; hidden reasoning, Key and request headers are not saved.
The guard records an HTTP send *attempt*, not proof of remote receipt or billing.
An interrupted process leaves `STARTED_OUTCOME_UNKNOWN`; HTTP 502/timeouts do not
establish that the server did nothing or incurred no charge. Do not delete
`live/` or rerun to obtain missing logs. A second launch refuses an existing run.

The second request uses the original public reference PNG, encoded unchanged as
an `image_url` data URI in the same user message as the required Chinese text.
Its SHA-256 is recorded. HTTP acceptance and visual correctness are separate:
`answer_matches_image` stays null pending manual comparison of the saved reply
against that actual PNG. Do not infer vision success from HTTP 200 or self-report.
Even successful testing establishes neither stability nor upstream identity and
does not open the Harness generation gate.

Local setup: Python 3.12.3; openai 3.19.0 in `.tools/api-smoke/` only. System
`ensurepip` was unavailable (initial venv command exit 1). The created venv's
interpreter ran PyPA's `pip.pyz` to install `openai` and dependencies (exit 0);
the bootstrap hash and installed versions are in `preparation.json`. No system
packages, CAD runtime, mini-swe environment or proxy settings were changed.

Five local synthetic HTTP tests validate exact payloads/image bytes, redaction,
502/timeout stopping, empty/length stopping and prevention of replay. They do not
contact the gateway and are not live model results. The no-Key startup check
exited 3 without creating `live/`. `paper/` is unrelated work and remains untouched.

After actual terminal execution, review and commit only these safe `live/`
records and a manual visual comparison; no extra requests to fill logging gaps.
Full robot generation remains unauthorized. CAD/pinned client restoration is
still outstanding; do not repeat the text OK test during that restoration.

## Startup-only recovery after the reported FileExistsError

The inspected `live/` contains only `environment.json`, originally timestamped
2026-09-23T14:12:51.215688+00:00. No request journal exists. The reported second
launch stopped at mkdir before constructing the client or entering a request.
A separate constructor-only test reproduced a ValueError from inherited
`ALL_PROXY`/`all_proxy` with the unsupported `socks://` scheme. Existing HTTPS
proxy variables use `http://`; no proxy values or credentials are recorded.
The exact reason the first terminal launch exited was not captured, so the
constructor diagnosis is a reproduction, not a recovered traceback.

For this inspected environment-only state, run:

```bash
cd /home/camus/robotgen-eval-v2
env -u ALL_PROXY -u all_proxy .tools/api-smoke/bin/python -B \
  model_comparison/records/api_smoke_20260923_v1/smoke.py --resume-unstarted
```

This command removes only the unsupported generic proxy variables from that
child process, retaining HTTPS/HTTP/NO_PROXY and system settings unchanged.
Constructor-only validation with this environment passed, with zero HTTP calls.

The recovery flag accepts exactly a regular `environment.json` with the expected
scope, with no other entries. It rejects any existing request journal, including
STARTED_OUTCOME_UNKNOWN, and does not delete, rename or overwrite old evidence.
The old environment file remains unchanged; the recovery creates a separate
`startup_recovery.json`. Recovery is not permitted again after that file exists
without separate inspection. A batch lock and legacy-process check prevent
concurrent launches. Existing-state and SDK transport checks run before getpass.
If an older terminal invocation is still active, end it with Ctrl+C before using
the command. No increase to the two-request budget or zero-retry policy occurs.

Seven synthetic tests passed after this repair. They include environment-only
recovery, original-record preservation and refusal to recover after any request
journal exists. `startup_repair.json` records the author-local checks and original
environment hash. No model request or vision assessment occurred during repair.
