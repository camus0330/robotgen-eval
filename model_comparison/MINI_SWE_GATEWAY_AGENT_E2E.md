IMPLEMENTATION: PASS (final repair)
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

## Final repair: failure evidence and credential-injection checks

Repair baseline: `198468f587afd1ad363f962e25f7c3657a8f728c`
Interpreter: Python `3.13.13` from the reviewed venv
Dependencies: `mini-swe-agent 2.4.6`, upstream SHA
`04d809ceab9df28f9adaed044884180159172930`, `litellm 1.102.0`,
`tiktoken 0.14.0`
Prepared cache:
`C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-_683fx7j`
Cache SHA-256:
`223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`

The exact final validation commands and exit codes were:

```powershell
& $py -B -u model_comparison/spikes/mini_swe_gateway_probe.py --audit-self-test
# exit 0
& $py -B -u model_comparison/spikes/mini_swe_offline_import_preflight.py
# exit 0; cache path above came from this run
& $py -B -u model_comparison/spikes/mini_swe_gateway_agent_e2e.py `
  --self-test --cache C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-_683fx7j
# exit 0
```

The self-test dispatches each audited integration case in its own child
process. The measured cases were:

| Case | Query calls | Shell launches | Classification | Evidence |
|---|---:|---:|---|---|
| success | 2 | 2 | `PASS` | native `Submitted` |
| first format error | 1 | 0 | `FORMAT_MISMATCH` | `FormatMismatch` |
| second completion endpoint fixture failure | 2 | 1 | `ENDPOINT_FAILED` | `EndpointFailed` |
| first command boundary rejection | 1 | 0 | `ENVIRONMENT_BLOCKED` | `BoundaryAbort` |

The aggregate was fixture calls `6`, cost-fixture calls `5`, model query calls
`6`, real shell launches `3`, gateway queries `0`, and real LLM API calls `0`.
Each child emitted its own allowlisted evidence, including stage, agent calls,
query count, shell count, network target lists, IPC target list, observed native
tools state, and safe exception class. No count was padded after a failure.

The separate synthetic-injection process wrote the synthetic credential to
stdout, stderr, logging, an ordinary exception message, and a `BoundaryAbort`
message. The captured buffers positively contained the injections, while the
final child stdout/stderr and parent summary were clean. Logging state, stdout,
stderr, and profile state were restored; raw capture buffers and traceback data
were discarded. The formal configuration, real key, live route, and real
gateway remain unread and unexecuted.

## Current repair: parent verdict and count semantics

IMPLEMENTATION: PASS
OFFLINE_SELF_TEST: PASS (exit code 0)
REAL GATEWAY E2E: NOT RUN

Baseline: `2c47a1d1dd45e820552b2a2b7b33fa876950f8cb`
Interpreter: Python `3.13.13` from the reviewed venv
Dependencies: `mini-swe-agent 2.4.6`, upstream SHA
`04d809ceab9df28f9adaed044884180159172930`, `litellm 1.102.0`,
`tiktoken 0.14.0`
Cache: `C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-569bm_v2`
Cache SHA-256:
`223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`

The reviewed interpreter existed. The commands and exit codes were:

```powershell
& $py -B -u model_comparison/spikes/mini_swe_gateway_probe.py --audit-self-test
# exit 0
& $py -B -u model_comparison/spikes/mini_swe_offline_import_preflight.py
# exit 0; cache path above came from this run
& $py -B -u model_comparison/spikes/mini_swe_gateway_agent_e2e.py `
  --self-test --cache C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-569bm_v2
# exit 0
```

The four independent Agent processes returned these parent-validated results:

| Case | Query calls | Shell launches | Child exit | Classification |
|---|---:|---:|---:|---|
| success | 2 | 2 | 0 | `PASS` |
| first format error | 1 | 0 | 4 | `FORMAT_MISMATCH` |
| second completion endpoint fixture failure | 2 | 1 | 5 | `ENDPOINT_FAILED` |
| first command boundary rejection | 1 | 0 | 2 | `ENVIRONMENT_BLOCKED` |

Every case also passed the required `exit_code == child_exit_code`, clean
stdout/stderr, credential-leak, profile-restored, and
`real_llm_api_calls == 0` checks. The parent accepts the expected non-zero
failure exits and returns `OFFLINE_SELF_TEST` only after all evidence passes.

The six pure-data rejection regressions all returned `REJECTED`:

| Mutation | Result |
|---|---|
| `external_output_clean=False` | `REJECTED` |
| `child_stdout_clean=False` | `REJECTED` |
| `child_stderr_clean=False` | `REJECTED` |
| success `child_exit_code=9` | `REJECTED` |
| `profile_restored=False` | `REJECTED` |
| missing required safety field | `REJECTED` |

The unified count semantics are: `model_query_calls` is the observed client
model-query attempt count; `gateway_queries` is `0` for offline and the same
observed client count for live, without claiming server completion; and live
`real_llm_api_calls` is `null` with source `not_observed` because no independent
server counter exists. Offline uses `real_llm_api_calls=0` with source
`offline_fixture`. Pure state checks for offline/live at query counts 0, 1, and
2 all passed, for both success and failure classifications.

The four-case totals remain fixture calls `6`, cost-fixture calls `5`, model
queries `6`, real shell launches `3`, gateway queries `0`, and real LLM API
calls `0`. No additional Agent, fixture, shell, or network process was started
for the pure-data regressions. Formal configuration, real keys, live gateway
execution, and `--live` remain unexecuted by design.

## Current live execution: reviewed tiny E2E

IMPLEMENTATION: PASS (existing implementation unchanged)
OFFLINE_SELF_TEST: PASS (reused reviewed result; not rerun)
REAL GATEWAY E2E: ENVIRONMENT_BLOCKED (single live attempt, exit code 2)

Baseline: `c192403d0e6e30c25b03dbf970ff649a9650a387`
Interpreter: `C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe`
Cache: `C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-569bm_v2`
Cache SHA-256:
`223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`
Temporary config: `C:\Users\hp\AppData\Local\Temp\robotgen-live-e2e-36293e17b5e64255a4fbbcb9bb7839b8\gateway_agent_live.json`
Key source: environment variable `SMART_AGI_API_KEY`; presence was checked without
printing its value. The temporary config contained an empty `api_key`.

The only live command was:

```powershell
& $py -B -u model_comparison/spikes/mini_swe_gateway_agent_e2e.py `
  --live --config $cfg --cache $cache
# exit 2
```

Execution window: `2026-09-22T21:43:33.6367185+08:00` to
`2026-09-22T21:43:40.4740751+08:00`; timezone: `China Standard Time` (`+08:00`).
The redacted stdout was saved outside the repository at
`C:\Users\hp\AppData\Local\Temp\robotgen-live-e2e-36293e17b5e64255a4fbbcb9bb7839b8\live-stdout.txt`;
stderr was saved separately at the corresponding `live-stderr.txt`. No SDK
raw dump was saved.

The live path started with route `gpt-5.6-sol` and routed model
`openai/gpt-5.6-sol`, passed the existing provenance and cache checks, and
stopped at the existing audit boundary. It did not reach a shell action or
the submit sentinel, so `Submitted` was not obtained. The actual summary was:

| Field | Value |
|---|---|
| classification | `ENVIRONMENT_BLOCKED` |
| exit code | `2` |
| stage | `agent_run` |
| safe exception | `BoundaryAbort` |
| agent calls | `1` |
| model query calls | `1` |
| gateway queries | `1` client attempt (not a server completion count) |
| real shell launches | `0` |
| fixture calls / cost fixture calls | `0 / 0` |
| real LLM API calls | `null`, source `not_observed` |
| exit status / submission | not observed |

`gateway_network_targets` retained the attempted DNS target
`big-model.smart-agi.com:443`. `unrelated_network_attempts` retained the
local proxy DNS target `127.0.0.1:7897`, which caused the fail-closed boundary
stop. `local_runtime_ipc_targets` retained the CPython cleanup socketpair
target `127.0.0.1:11437`. No retry, fallback route, `/v1/models` probe,
fixture patch, parser patch, or provider retry was used. The backend identity
behind the `gpt-5.6-sol` gateway route was not confirmed.

The formal `model_A` configuration was not read or modified. No Prompt or
frozen input, dependency, upstream file, Python implementation, benchmark, or
RobotGen generation was changed. This single live attempt is an execution
record, not a robot-generation metric or formal model comparison.

## Proxy bypass repair and one restricted live attempt

Baseline: `154c4aeb20e23b1351e0a19fd68315df7add9c6d`.
Local branch, local/remote HEAD and clean working tree matched before edits.
Python changed only at the two authorized settings: `NO_PROXY` was added to
`SAFE_ENV_NAMES`, and `scrub_environment()` forces `NO_PROXY="*"` before
third-party imports and client initialization. No audit or action rule changed.

The interpreter, cache and temporary configuration below existed:

```powershell
$py = 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe'
$cache = 'C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-569bm_v2'
$cfg = 'C:\Users\hp\AppData\Local\Temp\robotgen-live-e2e-36293e17b5e64255a4fbbcb9bb7839b8\gateway_agent_live.json'
```

Cache file `9b5ad71b2ce5302211f9c61530b329a4922fc6a4` had SHA-256
`223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`.
Key source was `SMART_AGI_API_KEY` in the environment; the precheck only
tested nonempty presence. The script retained its configuration/provenance
checks. A separate read-only configuration field comparison was performed
after the run and passed: reviewed route/HTTPS endpoint, empty inline key,
designated key variable, stream false, timeout 600, retries 0, null generation
parameters and empty extra body. The config was not modified; its recorded
last-write time remained `2026-09-22T21:42:51.2093461+08:00`.

Commands and results, in execution order:

```powershell
& $py -B -c "import sys, os, urllib.request; sys.path.insert(0, 'model_comparison/spikes'); import mini_swe_gateway_agent_e2e as m; m.scrub_environment(); p=urllib.request.getproxies(); assert os.environ.get('NO_PROXY')=='*'; assert p.get('no')=='*'; assert not any(k in p for k in ('http','https','all')); print('PROCESS_PROXY_BYPASS: PASS')"
# PROCESS_PROXY_BYPASS: PASS; actual LASTEXITCODE=0
& $py -B -u model_comparison/spikes/mini_swe_gateway_agent_e2e.py --self-test --cache $cache
# OFFLINE_SELF_TEST PASS; actual LASTEXITCODE=0; executed once
& $py -B -u model_comparison/spikes/mini_swe_gateway_agent_e2e.py --live --config $cfg --cache $cache
# Executed once; JSON exit_code=4; FINAL: FORMAT_MISMATCH
```

The existing self-test retained fixture/cost-fixture/query/shell totals
`6/5/6/3`, gateway queries `0`, and real LLM API calls `0`. All four Agent
cases, injection checks, six rejection regressions and six count-state checks
passed. No new tests, downloads or installations were added.

The live command assigned LASTEXITCODE immediately after execution, but the
tool yielded before completion and its final outer-shell status/timestamps
were not recovered. Therefore the process exit code is not independently
observed; `4` is the saved script summary value, not a recovered shell status.
The approximate window, based on the new output directory creation and stdout
last-write times, was `2026-09-22T21:54:38.7114852+08:00` through
`2026-09-22T21:55:41.7042758+08:00` (China Standard Time, UTC+08:00).

New external stdout/stderr files, preserving the previous logs, are under
`C:\Users\hp\AppData\Local\Temp\robotgen-live-e2e-repair-dca88532ccc7453d9832a3c8d289990f`.
Only the script's external output was saved; stderr was empty. The live
summary reported:

| Field | Observed value |
|---|---|
| classification / stage | `FORMAT_MISMATCH` / `agent_run` |
| safe exception class | `FormatMismatch` |
| summary exit_code | `4` |
| agent_calls / model_query_calls / gateway_queries | `1 / 1 / 1` |
| real_shell_launches | `0` |
| fixture_calls / cost_fixture_calls | `0 / 0` |
| real_llm_api_calls / source | `null` / `not_observed` |
| native_tools / usage / cost / returned_model | `not_observed` |
| exit_status / submission | `not_observed`; no `Submitted` |

Gateway records were two `socket.getaddrinfo` observations for
`big-model.smart-agi.com:443` and one `socket.connect` to `198.18.0.68:443`.
`unrelated_network_attempts=[]`; `127.0.0.1:7897` did not reappear.
The local IPC record was `socket.connect` to `127.0.0.1:10733`, reason
`cpython_socketpair`, stdlib file `C:\ProgramData\miniconda3\Lib\socket.py`,
function `_fallback_socketpair`, `asyncio_self_pipe=true`.

The real query path started and the existing format check stopped it before
any shell action. No request was added after failure. Gateway queries remain
client attempts, not independently confirmed server completions. The gateway
route was `gpt-5.6-sol`, routed as `openai/gpt-5.6-sol`; backend identity remains
unconfirmed. No live fixture/parser/provider patch, retry, fallback route,
availability probe or further repair was performed. System proxy, registry,
persistent environment and formal model_A configuration were not modified;
the formal configuration was not read. This is not a robot-generation metric
or formal model comparison.
