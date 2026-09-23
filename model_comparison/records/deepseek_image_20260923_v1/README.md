# Newly authorized single DeepSeek image request

Preparation status: **NOT_STARTED_MISSING_KEY; actual requests = 0**.
This is a new one-request authorization and directory, not recovery or replay of
`api_smoke_20260923_v1`. The old GLM and interrupted image journals stay unchanged.

Run locally; enter the Key only into the hidden terminal prompt:

```bash
cd /home/camus/robotgen-eval-v2
env -u ALL_PROXY -u all_proxy .tools/api-smoke/bin/python -B \
  model_comparison/records/api_smoke_20260923_v1/smoke.py --image-only
```

Only `run_image_only()` is used; it never calls the old `run_checks()`.
It requests `deepseek-v4-pro` once, temperature 0, max_tokens 1024, stream false,
zero retries, timeout 120 seconds. The exact endpoint is
`https://big-model.smart-agi.com/v1/chat/completions`. No GLM, model catalogue,
alias fallback, Agent, tool or robot generation request is made.

The PNG bytes from `model_comparison/inputs/assets/reference.png` are placed in
the same user message as the specified Chinese text, using a base64 image_url
data URI. New request/environment journals will be under this directory's
`live/`. The request-start journal is flushed before sending; the image hash,
actual target, send-attempt count, HTTP status, visible reply, usage, finish reason
and request ID are preserved. Unknowns stay null. No hidden reasoning, Key or
request headers are recorded; returned code is never executed.

Allow the SDK its full waiting time; absence of immediate output is not failure.
The operator does not interrupt the request. A user's Ctrl+C is respected and
recorded as INTERRUPTED_OUTCOME_UNKNOWN, without replay. A subsequent launch
refuses the existing live directory. There is no image-only resume option.

After a response exists, compare its specific posture, colors and visible
structures against the actual reference PNG. Service acceptance and HTTP 200 do
not prove visual correctness. A refusal, truncation, timeout or interruption stays
in the record and consumes this authorization. `answer_matches_image` remains
null until that content review. Identity is gateway_declared, not independently
attested. This result does not open the robot Harness admission gate.
