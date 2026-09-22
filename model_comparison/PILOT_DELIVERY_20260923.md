# PARTIAL — three-model robot pilot delivery

This delivery is `PARTIAL`, not `DELIVERED_PILOT`. The selected gateway account did not admit any of the three documented candidate routes, so no model query was used to generate a robot design and no engineering score is claimed.

## Frozen conditions

Baseline `f1d77516e35d7191a942d842b83f7ae23bb0710b`; branch `deadline/three-model-pilot-20260923`. The public route evidence supplied for the mapping is [Smart AGI Model Plaza](https://big-model.smart-agi.com/model-plaza?embedded=1). The frozen candidate IDs were `deepseek-v4-pro`, `kimi-k3`, and `glm-5.3`, all sent to the Smart AGI HTTPS chat-completions endpoint. This catalogue is route evidence only; it does not establish backend identity or account entitlement.

Inputs were bound from baseline Git blobs and hashed against `model_comparison/records/input_manifest.json`. The checked-out text files have a CRLF representation discrepancy; originals were not modified. The common scaffold is the existing mini-swe `DefaultAgent`, `LitellmTextbasedModel`, and `LocalEnvironment` at upstream SHA `04d809ceab9df28f9adaed044884180159172930`, version 2.4.6, with LiteLLM 1.102.0 and tiktoken 0.14.0. The common text protocol is one literal `mswea_bash_command` action per turn followed by the native submit sentinel. The reference PNG was bound in the plan as the identical future data-URI input for each model, but no model received it because admission failed.

The plan fixes one pilot per model, maximum 48 client queries per attempt, provider retries zero, at most two consecutive native format recoveries, 3600 seconds wall time, zero operator design edits, and serial order model_A/model_B/model_C. The setup/admission budget is 12; three requests were used.

## Admission and pilot results

| slot | declared model | request model ID | admission | HTTP | generation | queries | shell | engineering |
|---|---|---|---|---:|---|---:|---:|---|
| model_A | DeepSeek | deepseek-v4-pro | ACCESS_BLOCKED | 404 | NOT_STARTED | 0 | 0 | NOT_RUN |
| model_B | Kimi | kimi-k3 | ACCESS_BLOCKED | 404 | NOT_STARTED | 0 | 0 | NOT_RUN |
| model_C | GLM | glm-5.3 | ACCESS_BLOCKED | 404 | NOT_STARTED | 0 | 0 | NOT_RUN |

Each admission request was made once with `provider retries=0`; there was no robot prompt, no shell action, no format recovery, no fallback route, and no `/v1/models` probe in this batch. The 404 response was classified from status only; its service-side reason and any completion count are `not_observed`. The gateway key was read only from the selected `SMART_AGI_API_KEY` environment variable and was never written to config, logs, or a child environment.

## Verification commands

The reviewed interpreter was `C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe` (Python 3.13.13). The prepared tokenizer cache filename was `9b5ad71b2ce5302211f9c61530b329a4922fc6a4` and SHA-256 `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`; preflight passed both cache and client provenance checks.

| command | result |
|---|---|
| `pilot_access.py --output results/pilot_20260923/admission.json` | exit 2; three 404 access blocks |
| `pilot_run.py preflight` | exit 2; `ACCESS_BLOCKED`, generation gate closed |
| `test_pilot_delivery.py` | exit 0; 5 tests passed |
| `pilot_run.py run --slot model_A/B/C` | exit 2 each; `NOT_STARTED` and `ACCESS_BLOCKED` |
| `pilot_evaluate.py --slot model_A/B/C` | exit 2 each; `NOT_RUN` and `ACCESS_BLOCKED` |
| original `experiment.py verify-inputs` | exit 2 on the Windows checkout representation; canonical Git-blob kit passed the unchanged verifier in the isolated test |

The isolation checks used WSL Ubuntu-24.04 and bubblewrap with a temporary read-only canonical input kit, cleared environment, no model credential, no home mount, no external network, a timeout that returned 124, and a separate actual-exit-code check. Full generation lifecycle, CAD kernel, dynamics simulator, and a model worker were not started because the admission gate failed. No robot artifact exists; the engineering metrics remain `NOT_RUN` rather than zero.

## Evidence and boundaries

Tracked evidence is in `records/pilot_20260923/`; safe full logs and the canonical kit are under ignored `results/pilot_20260923/` and `outputs/pilot_20260923/`. The artifact manifest contains no generated design. No formal model_A configuration, frozen prompt/input source, benchmark, dependency, system proxy, or credential store was modified. The existing gateway E2E received only the visible-message evidence addition and common protocol wording; its parser, Agent, Environment, audit, and shell policy were not replaced.

There is no backend identity confirmation, no `returned_model`, usage, billing, hidden reasoning, or server completion fact. Those fields are `not_observed`. This report is not a RobotGen generation metric or formal model comparison, and external review has not been performed.

## Continuation: executable offline integration path

At `2026-09-22T15:15:00Z`, a separate run ID `offline_integration_20260922_v4` exercised the newly implemented path. It used the real pinned `DefaultAgent`, `LitellmTextbasedModel`, upstream parser, and the same literal text action protocol. The only model boundary replacement was an explicit `OFFLINE_INTEGRATION` completion/cost fixture; no model query or gateway request occurred.

The fixture produced a clearly synthetic, non-robot submission. The first action wrote the files through the WSL/bubblewrap output mount; the second action ran its declared rebuild entrypoint and returned the native `Submitted` sentinel. Observed counts were exactly `agent_calls=2`, `model_query_calls=2`, `real_shell_launches=2`, `fixture_calls=2`, `real_llm_api_calls=0`, and OS exit `0`. First and final snapshots are under `outputs/pilot_20260923/offline_integration_20260922_v4/first` and `final`.

Independent evaluation used the unchanged `experiment.py` file contract, then ran the rebuild in a fresh no-credential, no-external-network sandbox. `clean_rebuild` passed with OS exit `0`; the synthetic STL had an observed 10×10×10 mm envelope and positive measured proxy volume, and the 220×220×250 mm envelope check passed. URDF and MJCF XML parsing and the declared joint tree passed. The current interpreter has neither OCP nor cadquery, so `step_kernel_readback` is `NA/ADAPTER_UNSUPPORTED`; dynamics and motion replay remain `NA` for the same reason. No total score was produced. Detailed values and hashes are in `results/pilot_20260923/offline_integration_20260922_v4/metrics.json`.

This fixture is validation evidence only and is not inserted into the three-model result table. The invalid STL negative check returned `FAIL`, while missing submissions and path traversal remained rejected. The continuation plan and boundaries are recorded in `records/pilot_20260923/continuation_20260922.json`.

Continuation command record:

```text
python model_comparison/tools/experiment.py verify-inputs                         exit 2 (known Windows CRLF checkout mismatch)
python -m unittest discover -s model_comparison/tests -p "test_pilot_*.py" -v   exit 0 (6 tests)
python model_comparison/tools/pilot_run.py preflight                              exit 2 (ACCESS_BLOCKED; generation_ready=false from admission evidence)
python model_comparison/tools/pilot_run.py run --offline-integration              exit 0 (PASS; 2 queries, 2 shell launches, Submitted)
python model_comparison/tools/pilot_evaluate.py --integration --submission ...   exit 0 (FILE_CONTRACT_ACCEPTED; rebuild exit 0)
```

The offline run used only a completion/cost fixture and produced no real LLM API call. The three model admission attempts remain the earlier single attempts with HTTP 404; no new model request was made during this continuation.

## Continuation from execution baseline `9d9d839`

The real generation branch is now reachable at `pilot_run.py run --integration-only-config`. It validates the temporary HTTPS gateway configuration, reads only its selected environment credential, binds the frozen task files and reference PNG as an image data URI, uses the pinned `DefaultAgent`/`LitellmTextbasedModel`, counts queries, and executes model actions through the isolated command environment. The command environment has no credential mount, no external network, a writable `/work` output mount, timeout and shell resource limits, and returns the same observation to the Agent before its next action. It is fail-closed when no admitted candidate is present.

The historical gpt-5.6-sol live E2E records were echo/probe activity only and did not consume a robot-generation attempt. Under the current execution baseline, one explicitly authorized robot attempt was therefore run as `integration_only_20260923_v2`. It made one client model query, launched zero shell actions, and ended with a safe `Timeout` before a submission was produced. Provider retries were zero; no retry, fallback route, or second live attempt was made. The three national-model admission attempts were not repeated. The saved 404 bodies do not exist; their detailed reason remains `not_observed`.

The updated preflight was run once after this implementation and returned exit `2` with `ACCESS_BLOCKED`, provenance PASS, cache PASS, and `generation_ready=false` because no admission record contains a successful completion. No real model generation was started.

The evaluator now executes the manifest's declared rebuild command in the isolated workspace, measures every manifest-listed STL part, performs actual STEP-kernel probing inside the WSL sandbox (otherwise records `NA/ADAPTER_UNSUPPORTED`), separates XML parsing from dynamics loading, and requires the full eight-role/joint contract before reporting PASS. The new evaluation run is `offline_integration_eval_20260922_v3`; it does not rerun or overwrite the historical fixture execution. It recorded rebuild exit `0`, positive proxy STL envelope measurements with solid validity `NA`, XML parse PASS, dynamics/STEP kernel NA, and the synthetic one-joint contract as FAIL rather than silently accepting it.


## Real integration-only robot attempt (execution baseline `6204f7e07c71a2e3c3297ddde30a9106b6e38d37`)

The executable live path was invoked once with the reviewed temporary Smart AGI configuration `C:\Users\hp\AppData\Local\Temp\robotgen-live-e2e-36293e17b5e64255a4fbbcb9bb7839b8\gateway_agent_live.json` and the pinned interpreter. The recorded interval was `2026-09-23 00:15:12` to `00:16:45` Asia/Shanghai (`2026-09-22T16:15:12Z` to `2026-09-22T16:16:45Z`). The route was `gpt-5.6-sol`; backend identity was not confirmed. The task included the frozen text inputs and the reference PNG data URI. No formal `model_A` configuration or real key file was read. The child environment retained no credential mount and used the existing network-deny isolated action executor.

```text
C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe -B -u -c "import sys;sys.path.insert(0, 'model_comparison/tools');from pilot_run import run_real_integration;raise SystemExit(run_real_integration(r'C:\\Users\\hp\\AppData\\Local\\Temp\\robotgen-live-e2e-36293e17b5e64255a4fbbcb9bb7839b8\\gateway_agent_live.json', run_id='integration_only_20260923_v2'))"
OS exit: 1
provider retries: 0
model_query_calls: 1
real_shell_launches: 0
fixture_calls: 0
classification: FAILED
stage: agent_run
safe_exception_class: Timeout
Submitted: false
real_llm_api_calls: null (source: not_observed)
final snapshot: empty (0 files)
```

The safe evidence is `results/pilot_20260923/integration_only_20260923_v2/run.json`; it contains no raw SDK response, credential, or traceback. The call was a real route attempt, but it did not reach an action or native submission. No retry, format recovery, fallback route, `/v1/models` request, or availability probe followed it.

The empty final directory was then evaluated independently, without rerunning generation, as `integration_only_eval_20260923_v1` (OS exit `2`). Intake was `INVALID` because `submission.json` was missing or empty; `rebuild_attempted=false`, `rebuild_os_exit_code=null`, and all engineering metrics were `NOT_RUN` with `FILE_CONTRACT`. Consequently there is no design artifact, no independent geometry/dynamics score, and no three-model result row.

This outcome is an external model/gateway timeout, not a fixture endpoint failure. The offline fixture remains separate validation evidence only. The three-model delivery therefore remains `PARTIAL`; no additional live work is performed in this run.
