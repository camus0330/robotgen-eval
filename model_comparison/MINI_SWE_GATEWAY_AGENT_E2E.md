IMPLEMENTATION: PASS
OFFLINE_SELF_TEST: PASS (exit code 0)
REAL GATEWAY E2E: NOT RUN

# Guarded mini-swe gateway agent E2E spike

Repair baseline: `d1f99d94919d8d45c1890d73930fec9652383925`<br>
Previous PASS baseline: `69a3b39b046b0579832317ce9651c042b647f214`<br>
Pinned upstream: `mini-swe-agent 2.4.6`, SHA
`04d809ceab9df28f9adaed044884180159172930`<br>
Reviewed dependencies: `litellm 1.102.0`, `tiktoken 0.14.0`<br>
Prepared cache used for the recorded run:
`C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-_683fx7j`<br>
Cache SHA-256:
`223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`

This spike adds a small, bounded integration path around the pinned
`mini-swe-agent` 2.4.6 upstream implementation. It is not RobotGen Harness,
generation, benchmark, or a general-purpose sandbox.

The command line has two explicit modes:

```powershell
& $py -B -u model_comparison/spikes/mini_swe_gateway_agent_e2e.py `
  --self-test --cache <prepared-cache>

& $py -B -u model_comparison/spikes/mini_swe_gateway_agent_e2e.py `
  --live --config <temporary-reviewed-config> --cache <prepared-cache>
```

`--self-test` never reads the formal `api_config.json`, a real API key, or a
gateway. It uses raw assistant-content fixtures only at the
`litellm.completion` and `completion_cost` boundaries; the upstream
`DefaultAgent`, text parser, `LocalEnvironment`, observation formatter, and
submit sentinel still run. The fixture must produce exactly two completions and
the real environment must execute these commands, in order:

```text
echo robotgen_gateway_agent_e2e
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT&&echo robotgen_gateway_agent_submission
```

The self-test verifies the first real observation is present in the second
completion, no native-tool arguments are passed, the native exit status is
`Submitted`, the submission is `robotgen_gateway_agent_submission\n`, and no
trajectory is persisted. A synthetic credential is kept only in memory for the
leak check and is excluded from summaries and child environments. The result is
always labelled `OFFLINE_SELF_TEST`; it does not claim a real gateway E2E.

The live branch accepts only the reviewed Smart AGI route: model
`gpt-5.6-sol`, routed model `openai/gpt-5.6-sol`, an empty inline key, and the
`SMART_AGI_API_KEY` environment variable. It rejects unsupported request
overrides, does not query `/v1/models`, and uses the real LiteLLM model query.
The agent is limited to two steps, one format error, cost 1.0, and a five
second local environment timeout; provider and mini-swe retries are zero.

Both modes install a fail-closed audit policy. Only the two exact shell launches
above may occur, in a new system temporary directory. Executable, command, cwd,
and child-environment boundaries are checked before launch. Gateway DNS/connect
events are permitted only in live mode for the configured host; ordinary
localhost and unrelated network/configuration access are rejected. A boundary
rejection aborts the run and prevents retries. Output is a short allowlisted,
redacted summary; SDK request dumps, raw third-party logs, tracebacks, and
credentials are not emitted.

The recorded validation used these exact commands:

```powershell
& $py -B -u model_comparison/spikes/mini_swe_gateway_probe.py --audit-self-test
# exit 0
& $py -B -u model_comparison/spikes/mini_swe_offline_import_preflight.py
# exit 0; prepared cache path recorded above
& $py -B -u model_comparison/spikes/mini_swe_gateway_agent_e2e.py `
  --self-test --cache C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-_683fx7j
# exit 0
```

The self-test observed two fixture completions, two model query calls, two real
bounded `LocalEnvironment` shell launches, zero gateway queries, no native-tool
arguments in the observed completion kwargs, native `Submitted`, and the exact
submission `robotgen_gateway_agent_submission\n`. Regression cases rejected an
illegal command before OS launch, a legal first command after rejection, the
configured gateway address after rejection, ordinary loopback after rejection,
wrong executable, `child_env=None`, wrong cwd, wrong order, a third execution,
and a synthetic credential in the child environment. Synthetic wrong-model,
inline-key, and request-override configs were rejected before key access. The
real third-party stdout/stderr and logging capture passed without writing raw
content to a report or temporary output file.

Startup provenance is checked at runtime before LiteLLM or mini-swe-agent
imports. Runtime failures are classified as `CONFIG_BLOCKED`,
`ENVIRONMENT_BLOCKED`, `FORMAT_MISMATCH`, `ENDPOINT_FAILED`, or `FAIL`; the
successful path records the observed model query count rather than assuming a
gateway request count. Live native-tool observation remains
`not_observed` because live mode is intentionally not run.

The run was offline only: **REAL GATEWAY E2E: NOT RUN** and real LLM API calls
were `0`. The formal `api_config.json` and real API key were not read, modified,
or staged. Live endpoint behavior, real model output stability, and endpoint
failure counts remain skipped by design.
