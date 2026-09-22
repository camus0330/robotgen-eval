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

A preliminary CLI launch (`integration_only_20260922_v1`) exited `1` before the model client request because the temporary JSON contained a UTF-8 BOM; its safe evidence recorded `model_query_calls=0` and `real_shell_launches=0`. The reader was corrected to accept the reviewed UTF-8 configuration. That startup-only failure did not consume a model request.

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


## Safe snapshots and independent CAD rebuild ? 2026-09-23

```text
CAD_ENVIRONMENT: PASS
SAFE_SNAPSHOT: PASS (Windows host / stopped tool output)
SOURCE_ONLY_REBUILD: PASS (CAD environment cube, not a robot result)
REAL_MODEL_CALLS: 0
THREE_MODEL_RESULTS: INCOMPLETE
```

Execution baseline: `aeea2f217cdb168efb678981a63b7eebce119ce1`; local and fetched remote matched on branch `deadline/three-model-pilot-20260923`, with a clean starting worktree. Clock at start: `2026-09-22 17:34:49 UTC` / `2026-09-23 01:34:49 +08:00`, before the 12:00 +08:00 closure deadline. The original frozen input SHA and every historical run remain unchanged. The prior gpt-5.6-sol generation authorization remains consumed; no model request, admission request, or old fixture execution occurred here.

### Runtime actually used

Reused `/home/camus/robotgen-pilot-runtime-20260922` read-only in WSL Ubuntu-24.04, mounted at `/cad`. The actual bubblewrap interpreter was `/cad/bin/python`, Python 3.12.3, CadQuery **2.6.1**, cadquery-ocp **7.8.1.1.post1**. This existing environment differs from the frozen input lock's CadQuery 2.7.0; the lock was not changed and this test makes no same-environment model-comparison claim. No package installation or global environment change was made; the pinned Windows model-client venv was untouched.

The first actual sandbox CAD import exited **1**: ezdxf could not determine a home directory in the cleared environment. This was a runtime configuration failure, not a missing CAD package. The safe traceback is retained in `results/pilot_20260923/cad_acceptance_20260923_v1/environment_probe.json`. Assigning HOME=`/tmp` and XDG_CONFIG_HOME=`/tmp/config` inside the sandbox resolved it; the second import/solid-volume check exited **0**. No host home is mounted. Separate checks from this same CAD interpreter confirmed the credential was absent, external networking unavailable and `/cad` read-only (exit **0**). Actual dependency versions and logs are bound in `environment_versions.json` and the tracked acceptance record.

### Snapshot and rebuild rules

`pilot_snapshot.safe_snapshot` inventories all entries before reading content. On this Windows host, ancestor/directory/file handles reject reparse points and prevent replacement/write while the inventory is read. It rejects symbolic links, directory junctions/reparse points, hard links, special files and device names; permits at most 2,048 files / 256 MiB (also bounds directory entries); and binds relative path, byte size and content SHA-256. Copying goes into a private incomplete directory and is published only on success. Failed copies do not leave a complete destination. First/final snapshots and evaluator intake/rebuild copies use this entrypoint. Exit 0, ordinary exception exit 1, and tool timeout exit 124 all preserved their partial files through it. An unconfirmed tool stop is rejected rather than publishing possibly changing output; that hard-stop condition is not advertised as a captured snapshot.

The new rules are `pilot-cad-20260923.2`; previous result definitions are retained in history. A manifest must explicitly declare `rebuild_inputs`, `rebuild_outputs`, optional `rebuild_excluded`, and `rebuild_command`. Unclassified files or unsupported entrypoints are contract failures, not guessed inputs or deletion candidates. This implementation supports a declared Python source entrypoint, invoked with `/cad/bin/python -B <entrypoint>` in the existing no-credential/no-network sandbox. The fresh `/work` contains only declared source/data and checked manifest; STEP/STL intended for acceptance are excluded. Rebuilt outputs are frozen after process exit and measured from that new snapshot. Source changes, missing/empty outputs, unreadable STEP/STL or nonzero exits cannot pass clean rebuild.

STEP readback reports kernel solid count, validity, volume and bounding box. Bad data is `FAIL/STEP_READBACK_FAILED`; import/mount/runtime failure is a distinct unavailable-environment result. STL is read per declared part (ASCII or binary); a missing part stays in the result and fails the all-parts envelope check. STL triangle-volume values are explicitly proxies and solid validity remains NA. XML parsing and joint counts are separate from the full topology/actuator contract, which remains NA. Dynamics, motion and robustness are not implemented here; no total or normalized subset score is computed.

### Commands, results and evidence

Host command (actual pinned interpreter):

```powershell
$py = 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe'
& $py -B -m unittest discover -s model_comparison/tests -p 'test_pilot_*.py' -v
```

Final run: **OS exit 0, 14 tests passed**, `2026-09-23 01:50:04?01:50:24 +08:00`. Log: `results/pilot_20260923/cad_acceptance_20260923_v1/unittest_03.log`; exact argv/timestamps/exit code: `validation_03.json`. Earlier development passes also exited 0 and are retained as logs 01/02. The historical four-triangle fixture test now only reads old JSON evidence; it does not copy, rebuild or remeasure old geometry.

New test run: `cad_source_acceptance_3c1514c9614c`, mode **CAD_ENVIRONMENT_TEST_NOT_ROBOT**. Its positive source snapshot contains only `build.py` and `design_manifest.json`; there is no old STEP/STL. Actual build command inside `/work`:

```text
/cad/bin/python -B build.py
OS exit: 0
```

A separate sandbox interpreter then imports the new STEP with `cadquery.importers.importStep('/submission/assembly.step')`; OS exit **0**. Measured: **1 solid**, valid **true**, **999.9999999999998 mm?**, bounding box **10 ? 10 ? 10 mm**. Binary STL: **12 triangles**, bounding box **10 ? 10 ? 10 mm**, absolute volume proxy **1000.0000000000001 mm?** (mesh solid validity not claimed).

| Acceptance case | Actual result |
|---|---|
| Source-only closed cube | New STEP/STL produced; independent CAD readback PASS |
| Same Python entrypoint exits 0 but writes nothing | Rebuild process exit 0; both expected outputs missing, acceptance FAIL; even preexisting synthetic STEP/STL were excluded |
| Corrupt STEP after export | Build exit 0; CAD readback FAIL/STEP_READBACK_FAILED, environment still PASS |
| Missing second printed STL | Build exit 0; missing output and all-parts envelope FAIL, missing part retained as null |
| Escape junction and file symlink | Both rejected before any file content read; read count 0; no published or incomplete snapshot |
| Snapshot quota / uncertain contract / tool not stopped | Rejected, no complete snapshot |
| Stopped normal / exception / timeout tools | Actual OS exits 0 / 1 / 124; each partial snapshot COMPLETE |

Source and generated files are under `outputs/pilot_20260923/cad_source_acceptance_3c1514c9614c/cube/`; final measurement input is `cube/rebuilt/`. The original source snapshot was hash-checked unchanged. Full safe measurements are in `results/pilot_20260923/cad_source_acceptance_3c1514c9614c/acceptance.json`. Tracked, per-case evidence plus dependency versions and artifact hashes are in `model_comparison/records/pilot_20260923/cad_acceptance_20260923_v1.json`.

SHA-256:

- `build.py`: `ee2e5929cded4eda1ca108d57053a135748a8c33697c2daab4bd58152aede2f3`
- `assembly.step`: `80765833d2a156c7982fe91effb13abbaaf0a6bd3c242510d803c70b30f60916`
- `cube.stl`: `d10f1b3ac9bac4e0c5825a58515cb9a030577927be3d309bc12e067de97a6b06`

Remaining: no actual robot design was supplied by the earlier timed-out model attempt, so no real-model robot CAD acceptance or three-model result can be claimed. Full joint/actuator, dynamics, motion and robustness checks remain NA. This newly generated cube is only CAD-environment acceptance evidence, never a three-model result. No formal configuration, input source, upstream code, benchmark threshold, system proxy or credential store was modified.


## Restored gateway batch `restored_20260923_v1` ? actual new requests

STATUS: PARTIAL ? current account-group route rejection after six new admission queries.

Execution baseline `1acfc0823bc35007adbe4a0131e2958885070289`, branch `deadline/three-model-pilot-20260923`. At start, local/fetched remote matched and the worktree was clean. The customer-support statements (????????, ???????, ???????, ?????????) are recorded as `source=user_provided_support_screenshot`. No original screenshot file was supplied, so no screenshot path/hash is claimed. The support statement is distinct from the actual account-specific observations below.

### Frozen conditions and local wiring

The shared addendum, original per-file input hashes, endpoint, candidates, selection policy, interpreter and code hashes are recorded under `records/pilot_20260923/restored_20260923_v1/`. `plan.json` preserves the initial freeze; the active execution plan is **`plan_revision_2.json`**. It retains the identical public prompt, runtime, model selection policy and budgets; only pre-request config serialization was corrected. `PROMPT_ADDENDUM.md` documents the common CadQuery-version override and source/output rebuild contract without changing original inputs or providing a robot design.

Common generation conditions: `PILOT_RESTORED`, 3600 seconds / 48 queries per selected model, provider retries 0, native maximum 2 consecutive format errors, cost_limit 1.0 (library estimate guard, not a billing guarantee), human design edits 0, no operator design feedback, serial order A ? B ? C. All six candidate IDs were fixed before any possible generation result. Admission uses the same pinned `LitellmTextbasedModel`, native text parser and reference PNG expansion, 600-second request timeout and no artificial max_tokens cap. No gpt alias, `/v1/models`, availability probe or old fixture was invoked.

The generation `execute_command(cad=True)` path was checked once with a CAD import, without making a cube: OS exit **0**, actual `/cad/bin/python`, Python 3.12.3, CadQuery 2.6.1, cadquery-ocp 7.8.1.1.post1. The existing CAD venv is read-only, `/kit/inputs` read-only, `/work` model-specific, HOME `/tmp`, no credential or external network in the tool namespace. The source-rebuild evaluator remains `pilot-cad-20260923.2` and receives the actual rebuilt snapshots when a real submission exists.

A local startup error preceded the actual admission batch: the evidence sanitizer removed mandatory empty `api_key` and `request` fields while writing temporary configurations. All six of those startup records had **0 client queries** and failed before credential/network use. They remain in `admission.json`; their generic initial `ENDPOINT_FAILED` label is a local pre-request serialization failure, not a gateway response. Configuration writing was separated from evidence sanitization, a file round-trip regression was added, and the corrected plan/admission were saved separately. No real request was repeated by this correction.

### New admission observations

Actual new requests ran from **2026-09-23 02:20:25 to 02:21:02 +08:00** (2026-09-22 18:20:25?18:21:02 UTC). Three preferred IDs were tried first, followed by one predeclared backup for each family. Each worker made exactly one client query, each returned actual OS exit **2**, and the batch returned OS exit **2**. Total new client queries **6**, provider retries **0**, shell launches in admission **0**.

| Slot/family | Preferred | Result | Backup | Result | Selected |
|---|---|---|---|---|---|
| model_A / DeepSeek | deepseek-v4-pro | HTTP 404 | deepseek-v4.1-flash | HTTP 404 | none |
| model_B / Kimi | kimi-k3 | HTTP 404 | kimi-k2.7 | HTTP 404 | none |
| model_C / GLM | glm-5.3 | HTTP 404 | glm-5.3-flash | HTTP 404 | none |

For each exact ID, the current response said: `Model "<ID>" is not supported by any configured account in this group`. The full length-bounded, key-sanitized message is preserved in `admission_v2.json` and `admission_diagnostics.json`. This establishes current account-group route rejection; it does not establish that the IDs do not exist globally. Old 404 error bodies remain not_observed and were not backfilled.

All six actual final LiteLLM completion-message structures contained the PNG `image_url` content item (read-only profile observation). No nonempty completion arrived, so the parser was not invoked and image acceptance by a completing model remains `not_observed`. `returned_model`, finish_reason, usage, request ID, server error.type/code and billing are also `not_observed` where the client did not expose them. No raw header, SDK dump or hidden-reasoning field was persisted. Route identities remain only `gateway_declared`, independent backend attestation `not_observed`.

### Actual commands and exit codes

Working directory: `D:\Robotics Engineer\SEALab\robotgen-eval-swe`.

```powershell
$py = 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe'
$plan = 'D:\Robotics Engineer\SEALab\robotgen-eval-swe\model_comparison\records\pilot_20260923\restored_20260923_v1\plan_revision_2.json'
$admission = 'D:\Robotics Engineer\SEALab\robotgen-eval-swe\model_comparison\records\pilot_20260923\restored_20260923_v1\admission_v2.json'
& $py -B -u model_comparison/tools/pilot_restored.py prepare
# OS exit 0; one no-model CAD import check
& $py -B -u model_comparison/tools/pilot_restored.py admission --plan 'D:\Robotics Engineer\SEALab\robotgen-eval-swe\model_comparison\records\pilot_20260923\restored_20260923_v1\plan.json'
# OS exit 2; local startup/config failure, 0 actual queries, retained separately
& $py -B -u model_comparison/tools/pilot_restored.py admission --plan $plan --admission $admission
# OS exit 2; six actual new queries, six HTTP 404 account-group rejections
& $py -B -u model_comparison/tools/pilot_restored.py preflight --plan $plan --admission $admission
# OS exit 2; ACCESS_BLOCKED from new evidence, not from old admission state
& $py -B -m unittest discover -s model_comparison/tests -p 'test_pilot_restored.py' -v
# OS exit 0; final 5 directed tests, no real queries
& $py -B -u model_comparison/tools/pilot_restored.py summary --plan $plan --admission $admission
# OS exit 0; three explicit NOT_STARTED rows, no invented engineering results
```

The directed checks cover exact endpoint/model/config round-trip validation before credential access, preferred/backup selection, rejection of old-batch evidence, query budget clipping, common contract text, actual pinned image-message expansion, diagnostic redaction, and READY?exit 0 / ACCESS_BLOCKED?exit 2 preflight behavior using isolated pure test admission data. Full original 14-test CAD acceptance was reused; no old echo, old fixture or cube was regenerated. Generation and CAD-evaluation commands were **NOT RUN** because no model was admitted; their live behavior is not claimed as newly exercised in this batch.

### Three-model outcomes and stopping reason

| Slot | Admission | Robot generation | Generation queries | Generation OS exit | Robot files | File contract / rebuild / STEP / envelopes / XML |
|---|---|---|---:|---|---:|---|
| model_A | NOT_ADMITTED | NOT_STARTED | 0 | null (not launched) | 0 | NOT_RUN |
| model_B | NOT_ADMITTED | NOT_STARTED | 0 | null (not launched) | 0 | NOT_RUN |
| model_C | NOT_ADMITTED | NOT_STARTED | 0 | null (not launched) | 0 | NOT_RUN |

The new six requests provide an external account-group blocker. There is no remaining admitted model to run; no loop, extra diagnostic request or unauthorized route was attempted. All local wiring, shared condition freezing, targeted validation, safe diagnostics and result files that do not depend on account access are complete. The failure is not attributed to old quotas, old plans, expired baselines or the prior gpt timeout. No robot design is available for independent rebuild in this batch. Full topology/actuator, dynamics, motion and robustness remain NA; no subset score or model ranking is produced.

The complete new batch record contains `plan.json`, `plan_revision_2.json`, `PROMPT_ADDENDUM.md`, both admission records, normalized diagnostics, `results.csv`, `metrics.json`, `artifact_manifest.json`, and `NEXT_ACTION.md`. The latter includes a ready-to-forward, sanitized customer-support diagnostic. Runtime evidence and exact subprocess argv/OS exits remain under `results/pilot_20260923/restored_20260923_v1/`. The new artifact manifest binds these files by actual SHA-256; there are no new robot artifact links.
