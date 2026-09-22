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
