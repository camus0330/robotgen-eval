# Guarded mini-swe gateway agent E2E spike

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

This spike has no live result in the repository run: **REAL GATEWAY E2E: NOT
RUN**. The self-test is the only intended validation for this change.
