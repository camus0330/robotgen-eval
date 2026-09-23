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


## Alternate access pilot ? 2026-09-23: image access confirmed, generation safety blocked

**Status: PARTIAL_ACCESS_CONFIRMED_SAFETY_BLOCKED.** Three independent native Codex image checks succeeded. Robot generation was not started because scoped native host-file isolation could not be established. This is an access result, not three robot results or measured robot CAD evidence.

Execution baseline: `8c474b968e91a99a10c32f8ec0a72e9e3d2e6a80`; source local/remote `deadline/three-model-pilot-20260923` matched and the working tree was clean after `git fetch origin` (exit 0). New branch: `deadline/alternate-access-20260923`. Frozen input baseline remains `f1d77516e35d7191a942d842b83f7ae23bb0710b`. Original inputs, formal configuration, old six Smart AGI 404 cases, CAD acceptance and frozen artifacts were preserved.

### Actual channel and access evidence

Discovery started 2026-09-23 **02:56:47 +08:00**. All three responses were obtained by **03:05:21 +08:00**, within the 20-minute limit. `Get-Command codex`, `codex --version`, `codex login status`, `codex exec --help`, and `codex debug models --bundled` succeeded (exit 0). Installed client: **codex-cli 0.154.0-alpha.6.1**; authentication: **existing ChatGPT login**, managed by the official CLI. `auth.json`, browser stores and token values were not read or exported. Each invocation explicitly selected provider `openai`, ignored user configuration, and received no API-key environment variable. The unused Smart AGI custom provider was not selected. Actual network hostname and independently returned backend model were not captured: **not_observed**, not an asserted backend attestation.

The first three visible bundled-catalog IDs were fixed before design quality was observable. Each advertised text/image input and was then tested once with the actual canonical reference image (SHA-256 `518def2bf44234a9476f505319ae167a3d831d1178a2f4c70b1c3c23f3f1761b`). All gave an image-specific short description and `ACCESS_IMAGE_OK` in a fresh independent `codex exec` session, with no resume/fork of engineering history.

| Requested client model | Image response | OS exit | Elapsed seconds | Native usage input/output tokens | Robot attempt |
|---|---|---:|---:|---:|---|
| gpt-6-astra | PASS | 0 | 7.570447 | 9939 / 30 | NOT_STARTED |
| gpt-5.6-sol | PASS | 0 | 7.728377 | 8723 / 35 | NOT_STARTED |
| gpt-5.6-terra | PASS | 0 | 6.088138 | 8726 / 31 | NOT_STARTED |

These are client-requested identities supported by native catalog/configuration and visible responses. Server-returned model, fallback/override observation and backend identity remain not_observed. API query/retry counts are **null / not_observed**; a session is not counted as one underlying API request. No new Smart AGI request, differential request, alias sweep, or old fixture/cube rerun occurred. The candidate list is not DeepSeek/Kimi/GLM and is not merged into that comparison.

An initial local launch exited 1 in 0.114 seconds before creating a session: the CLI rejected nested overrides of the reserved built-in `openai` provider. Its safe startup diagnostic is retained in `gpt-6-astra_config_rejected.json` (zero model requests). Removing those unsupported retry overrides allowed the one image admission above; native retry counts remain unknown. No network retry is inferred from this local correction.

Exact native argv, timestamps, independent session IDs, whitelisted visible final messages and native usage are in each `*_admission.json`. No hidden reasoning text, raw SDK dump or token was retained. Admission used the model's native tool protocol and a deny-all tool hook; no robot design/code was requested. It does not constitute a same-task robot experiment.

### Minimal wiring and actual isolation checks

`pilot_alt_mcp.py` exposes only `execute` and `submit`, with execute delegated to the unchanged `pilot_sandbox.execute_command(..., cad=True)`. The actual tool uses `/cad/bin/python` in Ubuntu-24.04 bubblewrap, read-only `/kit` and `/cad`, writable `/work`, no external network or inherited credentials. Existing accepted versions remain Python 3.12.3, CadQuery 2.6.1 and cadquery-ocp 7.8.1.1.post1. The existing `safe_snapshot`, `source_rebuild` and `step_readback` code and prior acceptance hashes were reused, not retested as new CAD results.

| Directed check | Actual result |
|---|---|
| PreToolUse policy: native shell/patch/read/other MCP denied; only fixed CAD endpoints allowed in generation mode | PASS, local policy test |
| Actual MCP initialize/list/execute into existing CAD namespace | PASS; action OS exit 0; public task readable, `/mnt` and host home absent, synthetic credential absent |
| Native scoped filesystem sandbox: allowed local file readable, external synthetic marker denied | **FAIL before executing the check**, sandbox OS exit 1, `CreateProcessWithLogonW failed: 267` |
| Native ordinary `:read-only` sandbox control, `exit 0` only | OS exit 0; does **not** prove restricted host-file reads |

Owner-only Windows `mkdtemp` ACLs were observed and investigated, but changing only the new test directory creation to inherited ACLs did not fix the failure. Nested/flat directories, explicit/implicit workspace roots and documented minimal-read profiles still failed. No ACL on existing user data, global Codex config, login, system proxy or installed environment was changed. Only synthetic markers were used, never real sensitive files.

The native guard is additional protection, not a substitute for a working file boundary. Official [hooks documentation](https://learn.chatgpt.com/docs/hooks) describes paths outside hook coverage; the installed `debug prompt-input` does not expose the authoritative complete registered tool list. Thus disabling documented shell/browser/apps features and passing the guard unit check cannot alone certify absence of every host file-read path. The [permissions documentation](https://learn.chatgpt.com/docs/permissions) supplied the scoped profile used in the failing check. No broad-read fallback, `--yolo`, global sandbox disable or credential-bearing host execution was used for design.

### Commands, results and remaining work

Interpreter for the batch tools/tests:
`C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe`

```powershell
& $py -B -u model_comparison/tools/pilot_alt_access.py --admit gpt-6-astra
# local unsupported-config launch: 1; corrected pre-request config: one image session, 0
& $py -B -u model_comparison/tools/pilot_alt_access.py --admit gpt-5.6-sol  # 0
& $py -B -u model_comparison/tools/pilot_alt_access.py --admit gpt-5.6-terra # 0
& $py -B -m unittest discover -s model_comparison/tests -p 'test_pilot_alt_*.py' -v
# 1: two checks passed, scoped native sandbox failed
& $py -B -m unittest discover -s model_comparison/tests -p 'test_pilot_alt_*.py' -k native_external -v
# 1: focused startup variants still fail; exact argv and diagnostics retained
codex sandbox -P :read-only -C <fresh synthetic test root> <PowerShell> -NoProfile -NonInteractive -Command 'exit 0'
# 0: control only
```

The initial two-check test runs exited 1 (guard pass, native boundary fail). The later three-check run exited 1 (guard and MCP pass, native boundary fail). Focused native checks also exited 1. The final test-only change gives future evidence unique filenames so reruns cannot replace this batch's records; it does not change the failing assertion. One documentation-inspection command mistakenly treated `windows` as a sandbox subcommand; the installed Windows CLI interpreted it as an executable and exited 1 / Windows error 2. The top-level `codex sandbox --help` was then followed. This invoked no model or design code.

Two authorized read-only engineering subagents were used: one for client/provider/model capabilities, one for existing input/CAD/evaluator contracts. They made no design calls, source changes or descendant agents. Contestant design sessions: **0**. Three admission sessions were independent.

`access_inventory.json`, `plan.json`, `validation.json`, the individual native records, `metrics.json`, `results.csv`, `NEXT_ACTION.md` and `artifact_manifest.json` are under `model_comparison/records/pilot_20260923/alternate_access_20260923/`. Runtime copies of the summary and safe checks are under `results/pilot_20260923/alternate_access_20260923/`. There is no first/final robot snapshot; its path/hash is null. File acceptance, independent robot rebuild, STEP solids/volume/bounds and XML were **NOT_RUN**. Dynamics, motion, robustness and total score remain NA; no subset score is invented.

The remaining blocker is specific: this installed native client's scoped filesystem sandbox fails before executing the synthetic read-boundary test, and there is no independently verified complete native tool exclusion to replace that boundary. The existing CAD namespace itself works. Generation has not been enabled or claimed implemented end-to-end. The full task/Codex public addendum and generation configuration remain to be frozen after the safety gate is resolved; canonical input hashes were rechecked unchanged. The three models retain unused single-attempt 1800-second design budgets, subject to the unchanged 2026-09-23 12:00 +08:00 closure deadline. This run stops at the user's explicit unsafe-wiring condition, not because model access is absent.

Pre-commit checks: actual authorized environment-key scan plus token-pattern scan of new evidence, source and report found no credential match. New Python source parsed successfully. `git diff --check` exited 0; only allowed paths changed. No generated model, CAD build or MCP worker remains running. Final Git push/remote SHA and clean-tree checks are reported in the review pack.


## Continuation 2026-09-23 03:31 +08 ? WSL boundary PASS; waiting for official login

**STATUS: WAITING_OFFICIAL_LINUX_LOGIN.** The native Linux scoped filesystem boundary and actual CAD MCP checks passed. Real robot generation is not started: the new official Linux client's `login status` returns **Not logged in / exit 1**. This is the explicit human-login stopping condition, not a new model-access failure. Existing three image admissions remain valid evidence and were not repeated; new model requests and Smart AGI requests are **0**.

Execution baseline/local/remote at startup: `60d8a88a5726144f60900bfe410815e036ab4fe1`, branch `deadline/alternate-access-20260923`, clean worktree after `git fetch origin`. Original frozen input SHA and old results are unchanged. New evidence uses `continuation_20260923_0332` beneath the alternate-access records/results directories. No engineering subagents were used in this continuation.

### One bounded Windows launch difference, then WSL2

The one new no-model Windows check used an ordinary non-reparse D-drive directory, explicit Python `subprocess.run(cwd=work)`, matching Codex `-C work`, absolute Codex and PowerShell executables, a named `robotgen-alt` permissions profile, and no legacy `--sandbox`/`sandbox_mode`. Parent cwd, child cwd, executables and exact argv are recorded in `windows_startup_1.json`. External synthetic markers were in a dedicated D-drive sibling data directory, outside workspace and platform minimal runtime paths.

The installed `sandbox --help` has no `--ignore-user-config`, so this no-auth check used an empty dedicated `CODEX_HOME` plus explicit profile parameters. Planned authenticated `exec` uses its supported `--ignore-user-config` and the same scoped profile policy; no global config was edited.

Result: native OS exit **1**, wrapper exit **2**, with `Restricted read-only access requires the elevated Windows sandbox backend`. The read/write assertions did not run. This is neither an ACL finding nor a model-permission denial. It was no longer 267, so the conditional second Windows launch experiment was not used. Windows debugging stopped after this one check, within the ten-minute bound. Historical 267 evidence was retained unchanged.

Ubuntu-24.04 was confirmed as **WSL version 2**, WSL runtime 2.6.3.0, x86_64. No native Linux Codex was found; the Linux PATH's npm was a Windows installation and was not used. An official same-version release was available, so a single dedicated install was made without modifying Windows Codex, global toolchains or the CAD venv:

- Official asset: `https://github.com/openai/codex/releases/download/rust-v0.154.0-alpha.6.1/codex-x86_64-unknown-linux-musl.tar.gz`
- Archive size: 98,984,633 bytes.
- Actual SHA-256 matched release metadata: `d7d23bf50decb639cee9eded7a66174e86c349efb5f3f4fbbc7db6cd8dd16d00`.
- Binary: `/home/camus/robotgen-alt-client-20260923/codex-x86_64-unknown-linux-musl`.
- `file`: **ELF 64-bit x86-64 static PIE**, not Windows EXE.
- `--version`: **codex-cli 0.154.0-alpha.6.1**, same as all previous image admissions.
- Installation and version checks: OS exit 0; `login status`: OS exit 1, `Not logged in`.

Native bundled metadata still lists gpt-6-astra, gpt-5.6-sol and gpt-5.6-terra with text/image input. Defaults are low, low and medium reasoning respectively; no override is requested, and this difference is disclosed in the continuation plan. No model call was used to recheck the catalog.

### Linux acceptance and minimal cross-platform adaptation

Linux workspace/public-kit/operator directories are dedicated under `/home/camus/robotgen-alt-runtime/continuation_20260923_0332`. Public input copies match all frozen hashes. The permission profile grants only minimal runtime files, the exact installed Codex binary, and the current isolated session root. It does not grant entire `/mnt/c`, `/mnt/d`, home, repository, authentication directory or other designs.

The first Linux sandbox launch showed that re-executing its dedicated Codex binary required an explicit runtime-file read grant. That failure and a rejected quoted dotted-key config form were preserved. Supplying the exact binary path as an inline filesystem-table entry succeeded. These were no-model configuration checks, not model retries.

| Actual check | OS exit / result |
|---|---|
| Scoped Linux inside synthetic-file read | 0 / PASS |
| Outside synthetic-file read denied | 0 / PASS |
| Outside unauthorized write denied | 0 / PASS |
| Native CAD MCP initialize / tools list / execute | 0 / PASS |
| `/kit` and `/cad` mount readonly; HOME=/tmp; host mounts/home absent; synthetic credential absent | PASS |
| Actual `/cad/bin/python` runtime | Python 3.12.3, CadQuery 2.6.1, cadquery-ocp 7.8.1.1.post1 |
| MCP submit then execute rejection | PASS; tool calls stay 1, submitted=true, tool_stopped=true |
| Native `mcp get cad --json` with prepared per-run configuration | 0; stdio command/args/server/env match the intended CAD bridge |
| Prepared Linux worker `--help` import check | 0; no model call, not live validation |

Only the allowed cross-platform changes were made to `pilot_sandbox.py`: accept native Linux absolute paths and invoke the existing identical timeout/bubblewrap argv directly on Linux. Windows invocation remains unchanged. The CAD environment was not rebuilt. Snapshot, CAD and evaluator implementation files were not edited. No old cube, four-triangle fixture, or historical smoke suite was run; the new synthetic file is boundary-test data, not a robot result.

The shared configuration builder now has an explicit CAD mode with Linux-safe command quoting. Generation argv calls `pilot_alt_guard.py --cad`, allows the fixed `mcp__cad__execute` / `mcp__cad__submit` endpoints, and disables native shell, browser/apps, extra skills/memory and contestant subagents. The OS permissions profile supplies the file boundary; the hook is additional tool restriction. Direct MCP checks and native config inspection passed; authenticated model-mediated tool calls have not yet occurred.

### Frozen continuation and actual commands

`plan.json` preserves the three-model order, client_requested identity, backend_identity=not_independently_verified, one independent 1800-second attempt per model, serial execution, zero operator design edits, unchanged evaluator `pilot-cad-20260923.2`, and the 2026-09-23 12:00 +08 closure deadline. Public `PROMPT_ADDENDUM.md` explicitly replaces mini-swe fences/submit markers with native CAD execute/submit, preserves original task/rebuild contracts, and identifies `/kit/inputs`, `/cad/bin/python` and `/work`. Actual model-specific argv and per-model Linux cwd are frozen in the plan; prepared commands are clearly marked unexecuted.

Windows tools interpreter:
`C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe`

```powershell
& $py -B -u model_comparison/tools/pilot_alt_continue.py --windows-check
# wrapper 2; native sandbox 1; no model
& $py -B -m unittest discover -s model_comparison/tests -p 'test_pilot_alt_*.py' -v
# 0, four tests pass; native Linux boundary/MCP actually executed
```

The four tests cover generation hook configuration, guard allowlist, actual Linux boundary/CAD MCP, and preservation of failed Windows evidence. The last is an integrity check, **not** Windows isolation PASS; no skip was used. Linux checks ran through actual WSL `/usr/bin/python3`, and exact nested commands/cwd/OS exits are retained in the unique `linux_test_*.json` records.

Prepared actual generation entrypoint (not executed for any slot):

```powershell
wsl -d Ubuntu-24.04 -- /usr/bin/python3 -B /home/camus/robotgen-alt-runtime/continuation_20260923_0332/operator/pilot_alt_worker.py --plan /home/camus/robotgen-alt-runtime/continuation_20260923_0332/operator/plan.json --slot model_A
# Repeat serially with model_B and model_C only after each attempt is frozen/evaluated.
```

The worker checks official login and input hashes before creating its one-attempt journal, uses the frozen native exec argv, filters reasoning text from persisted CLI events, records visible messages/MCP/usage/OS exit, applies the 1800-second bound, terminates its process group and refuses complete snapshots when tool stop is unconfirmed. Explicit fallback errors stop the process and invalidate its model classification. Process metadata is overlaid separately from the raw model snapshot; CAD source/manifest design fields are not repaired. This worker has only passed import/syntax checks at this point; live lifecycle behavior is not claimed validated. Independent artifact transfer/evaluation remains to be performed after each real attempt, using the existing safe-snapshot and evaluate_integration path.

| Requested model / run_id suffix | Actual started | Attempt used | OS exit | Robot / rebuild / STEP / STL / XML |
|---|---|---|---|---|
| gpt-6-astra / model_A | no | no | null | NOT_RUN |
| gpt-5.6-sol / model_B | no | no | null | NOT_RUN |
| gpt-5.6-terra / model_C | no | no | null | NOT_RUN |

No first/final robot hash exists. Physics, full topology/drive contracts, motion, robustness and total score remain NA. Underlying API query/retry values stay null/not_observed; no session-to-query conversion is made.

### Required human step

The official Linux client has no existing login. Run this one command in local PowerShell and finish its official browser/device flow:

```powershell
wsl -d Ubuntu-24.04 -- /home/camus/robotgen-alt-client-20260923/codex-x86_64-unknown-linux-musl login --device-auth
```

Do not send a device code, token or key to chat. No Windows auth.json/token, browser credential database or `.sandbox-secrets` was read, copied or exported; no subscription token was repurposed as an API key. No model/CAD generation worker or background login process was left running by this task. The remaining external blocker is **official Linux login**. After it is completed, continue the frozen three real attempts and independent measurement without repeating image admission or old gateway requests. This pauses under the user's explicit authentication exception, not at a claimed completed pilot.


## 2026-09-23: verified host proxy for the native Linux client

Execution baseline: `8880a50c13c9d7af192c69b7a2cb2d91eac88d4b`; branch `deadline/alternate-access-20260923`. Local and remote matched. The only pre-existing worktree addition was our `execution_20260923_0403` evidence from the resumed attempts. Original frozen inputs and `continuation_20260923_0332/plan.json` are unchanged.

Diagnosis began at **04:29:15 +08:00**. Windows 11 build 26100.6584 / WSL 2.6.3.0 / Ubuntu-24.04, user `camus`, HOME `/home/camus`. `.wslconfig` reports mirrored networking, autoProxy=true and dnsTunneling=true; actual `wslinfo --networking-mode` is mirrored. The default route is via 192.168.1.1 on eth5; neither this nor a DNS address was used as the proxy host.

| Check | Actual result |
|---|---|
| WINDOWS_PROXY_DISCOVERED | PASS: enabled Windows system proxy 127.0.0.1:7897; TCP listener owned by verge-mihomo.exe PID 15776; Clash Verge and service running |
| WSL_PROXY_REACHABLE | PASS: mirrored-loopback TCP connection to the observed listener |
| OFFICIAL_HTTPS_TRANSPORT | PASS in WSL: auth.openai.com and chatgpt.com CONNECT 200, verified TLS, HTTP 403, curl exit 0 |
| CODEX_CLIENT_ENV_CONFIGURED | PASS: one allowlisted environment builder used by check/login/status and worker; actual child inheritance test passes |
| CAD_NETWORK_STILL_BLOCKED | PASS: actual bubblewrap CAD child has no proxy/synthetic-secret variables; TEST-NET external and host-proxy connections fail |
| OFFICIAL_LOGIN_STATUS | authenticated=true, official login status exit 0 through the same wrapper; no new device login needed |

The active Clash configuration reports mixed-port=7897, allow-lan=false and TUN enabled (gvisor). The observed listener is loopback despite the configuration's bind-address field. PAC is not configured. TUN's actual routing effectiveness is NOT_VERIFIED. Only these selected non-sensitive fields were retained; no full YAML, subscriptions, nodes, controller secrets or authentication files were exported.

Windows comparison: auth.openai.com CONNECT 200 followed by TLS handshake failure (curl 35, no HTTP response); chatgpt.com CONNECT 200, TLS verified, HTTP 403, exit 0. WSL reached both HTTPS targets with HTTP 403 in approximately 0.36 seconds each. HTTP policy rejection is separate from successful transport and does not prove model generation availability. No repeated failed configuration, TLS bypass, body, cookie or full-header capture was used.

### Minimal process-only change and validation

`pilot_alt_network.py` reads the private Linux operator `client_network.json`, containing the verified credential-free HTTP proxy origin. `HTTP_PROXY`, `HTTPS_PROXY`, `http_proxy`, `https_proxy` all use `http://127.0.0.1:7897`; both NO_PROXY forms contain only `localhost,127.0.0.1,::1`. ALL_PROXY forms and all unrelated inherited variables are absent. The fixed PATH/HOME/LANG remain unchanged. Worker changes are limited to importing and using this environment builder for its existing authentication check and Codex subprocess. No process lifecycle, prompt, tool permissions or CAD code changed.

The new helper and worker were copied into the existing Linux operator directory and both hashes verified against repository files (`operator_sync.json`). The private config is mode 0600, outside model sessions and CAD mounts. No `.bashrc`, global Codex config, Windows proxy, firewall, WSL setting or service was changed/restarted. The CAD namespace remains network-disabled with its original read-only kit/CAD mounts and clear environment.

Actual commands (all user-specific paths filled):

```powershell
$py = 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe'
& $py -B -m unittest discover -s model_comparison/tests -p 'test_pilot_alt_network.py' -v
# exit 0; 3 targeted tests, including actual Linux child and CAD namespace
wsl -d Ubuntu-24.04 -u camus -- /usr/bin/python3 -B /home/camus/robotgen-alt-runtime/continuation_20260923_0332/operator/pilot_alt_network.py check
# exit 0; two public HTTPS requests, no model request
wsl -d Ubuntu-24.04 -u camus -- /usr/bin/python3 -B /home/camus/robotgen-alt-runtime/continuation_20260923_0332/operator/pilot_alt_network.py login-status
# exit 0; authenticated
```

The same helper provides interactive `login` if later needed, but no device-auth flow was started here. Detailed safe argv, individual curl exits/timing/CONNECT/HTTP fields and isolation evidence are in `network_fix_20260923/{discovery,windows_transport,check,login-status,isolation_test,validation,operator_sync}.json`. No image admission, old fixture, cube, Smart AGI or model request was made by network diagnostics. Existing unaffected tests are reused.

### Interrupted attempts and explicit continuation authorization

Astra was cancelled by the user and excluded. Its prior client was stopped with SIGTERM after 866.95 seconds, client exit -15, outer observed exit 1, tool calls 0, no design. Sol's old environment also produced only connection timeout events; it was stopped for this network repair after 735.15 seconds, client exit -15, outer observed exit 1, tool calls 0. Both workers completed safe final snapshots containing operator metadata, not robot designs. Raw worker GENERATION_FAILED classifications are preserved; neither is interpreted as a robot design quality failure. Astra's evidence is under `execution_20260923_0403/model_A`; sol's is under `network_fix_20260923/model_B_interrupted`. Original API request/retry counts remain null/not_observed; CLI reconnect events are not server request counts.

The user then explicitly authorized **one new complete 1800-second sol attempt**. `network_execution_plan.json` records that authorization, the new independent `model_B_network1` paths, the network code hashes and the original plan hash; terra retains its unused original attempt. Astra stays excluded. The public task, image, CAD environment, tools, reasoning defaults and evaluator remain unchanged. Continue serially sol then terra, with immediate independent intake/rebuild/measurement after each; generation outcomes will be appended below. The 12:00 +08:00 closure deadline remains in force.


### Actual proxy-routed attempts and independent evaluation ? closed 04:43 +08:00

Network repair commit: `a5ef54fd862e69300956742061fb4171377213e3`. Network preparation completed in about eight minutes; it made **0 model requests**. The subsequent two explicitly authorized design sessions did contact the official client service and returned visible model messages and CLI usage. Those generation sessions are not part of the zero-call network diagnostic count.

| Requested model (client_requested) | Run suffix | Elapsed s | Codex OS exit / outer PowerShell exit | CAD calls / native submit | Design files | Independent intake / evaluator exit |
|---|---|---:|---|---|---:|---|
| gpt-5.6-sol | model_B_network1 | 23.819 | 0 / 1 | 0 / no | 0 | FAILED_ATTEMPT_RECORDED / 2 |
| gpt-5.6-terra | model_C | 26.371 | 0 / 1 | 0 / no | 0 | FAILED_ATTEMPT_RECORDED / 2 |

Both raw workers report `GENERATION_FAILED`, while the directly observed client failure layer is **CLIENT_TOOL_EXPOSURE**: `code-mode host is disabled`. Both models report that native CAD execute/submit were unavailable, and actual CAD MCP state confirms zero calls. Therefore this is not scored as robot design quality failure. Direct MCP tests from the earlier environment work remain historical evidence; they did not prove model-facing tool exposure. No public tool configuration was changed to work around this error, and neither model was retried after this result.

The independent existing evaluator was invoked immediately after each session, with mode `CODEX_HARNESS_PILOT`, rule `pilot-cad-20260923.2`, and the corresponding safe final snapshot. Its isolated intake child exited 0 and recorded the failed attempt; the evaluator exited 2. Rebuild was not attempted because no model source/manifest/CAD existed. STEP solid counts/validity/volume/bounds, STL envelopes, XML, full topology/drives, dynamics, motion, robustness and scores are **NA / NOT_RUN**. No fixture or operator-written robot substituted for either design.

All four stopped-session snapshots (cancelled astra, old sol, newly authorized sol, terra) preserve their original journals. There is no first-design snapshot because no model wrote a design file. Each post-fix final directory contains three operator metadata/log files, not three design artifacts. Safe Linux-to-Windows transfer digests were independently rechecked.

| Run suffix | Final metadata snapshot SHA-256 | Independent evaluation SHA-256 |
|---|---|---|
| model_B_network1 | `b3a095c52a5876b492e9016daf3266622528b1f73d072c562f24ddce3e8c2bbb` | `4131ab17f9e2cd8c1de895fb0234df4b7eb0d2498179e7e694920cc206be93b0` |
| model_C | `02d358f678102c293e6bec40336825e4420cf7bb55c73297353d87cf8e2e15fb` | `b7a72391615ba05bafefcf391543f71c68ecc67b9d22eb0d52b10e7917370b90` |

CLI usage (not independently metered API billing): sol input=22105, cached input=10880, output=507, reasoning output=294; terra input=56173, cached input=43264, output=580, reasoning output=317. API queries, provider retries, returned backend identity and billing cost remain null/not_observed. The requested identities are not independently confirmed backend identities. Default reasoning remained low for sol and medium for terra, as disclosed in the frozen plan. Human design edits=0.

Exact generation and evaluation argv, start/end times with timezone, raw safe CLI events, usage, snapshot inventories and individual evaluation/metric JSON are under `network_fix_20260923/{model_B_network1,model_C,final_results.json}`. Runtime snapshots remain under `outputs/pilot_20260923/alternate_access_20260923/continuation_20260923_0332/`; original independent evaluator files remain under the matching `results/pilot_20260923/alternate_access_20260923/continuation_20260923_0332/` directories.

Exit-code clarification: the launch tool observed **PowerShell outer exit 1** on each failed worker command; the separate WSL/Python worker native exit was not captured and is not inferred. The Codex child exit is directly captured (0 for these two completed sessions, -15 for interrupted ones). Evaluator LASTEXITCODE=2 was captured immediately. `exit_code_clarification.json` clarifies earlier transfer field naming without rewriting historical records.

At 04:40:53 +08:00, process inspection found no matching Codex client, worker or MCP process. All authorized post-fix attempts are now consumed. Astra remains user-cancelled/excluded. The only remaining generation blocker is model-facing CAD tool exposure in the unchanged official CLI configuration; addressing it would require a separate public-tool configuration revision and any further generation budget. This network-only repair does not expand that scope. Host/system proxy settings, CAD network permissions, official model_A config and frozen inputs were untouched.


## 2026-09-23: Code-mode runtime repair and single real CAD-tool gate

Execution baseline: `e1277cb789e7d1b508fc7cf3251c238d2f2c7760`; branch `deadline/alternate-access-20260923`. Initial fetch/local/remote checks matched and the worktree was clean. Started at **04:51:52 +08:00**; runtime verification and closure reached **05:04:22 +08:00**, before the unchanged 12:00 deadline. This is a **two-model pilot** scope; astra remains cancelled/excluded.

| Delivery status | Actual result |
|---|---|
| CODE_MODE_RUNTIME | PASS: verified same-release helper installed; real model session spawned it (PID 695); disabled-host error absent |
| MODEL_MEDIATED_CAD_TOOL_CHECK | FAIL: CAD execute and submit each attempted once by the client, both rejected by MCP approval policy before server execution |
| SOL_REPLACEMENT_PILOT | NOT_STARTED_TOOL_CHECK_FAILED; replacement allowance unused |
| TERRA_REPLACEMENT_PILOT | NOT_STARTED_TOOL_CHECK_FAILED; replacement allowance unused |
| ASTRA | CANCELLED_EXCLUDED |

### Fixed-version component and scoped configuration

The exact official release `rust-v0.154.0-alpha.6.1` supplied asset `codex-code-mode-host-x86_64-unknown-linux-musl.tar.gz` (25,720,846 bytes). Its actual SHA-256 matched the digest returned by the [official release metadata](https://api.github.com/repos/openai/codex/releases/tags/rust-v0.154.0-alpha.6.1):
`43a7f7697fc6b8733ad294a03b918df6c94e02c8d1ff240e22b87308199b7ed5`.

Installed only at `/home/camus/robotgen-alt-client-20260923/codex-code-mode-host`, mode 0755; actual binary SHA-256 `d8a92060f125f1c6117be823e34bb33585aa5cea6bf82f61266bfd3ed5801580`. `file` reported x86-64 static-PIE ELF; `--help` exited 0. This helper has no reported independent version string: release identity is established by the verified official asset, not fabricated `--version` output. Main CLI stayed 0.154.0-alpha.6.1 and was not replaced. No binary is committed.

[Fixed-version install-context source](https://github.com/openai/codex/blob/rust-v0.154.0-alpha.6.1/codex-rs/install-context/src/lib.rs) resolves this custom installation's sibling `codex-code-mode-host`. Only that exact runtime file was added to the existing read permission grants. No home, repository, authentication directory or broad filesystem grant was added.

`config_args(cad=True)` now explicitly emits **code_mode=true** and **code_mode_host=true**, once each, after removing both from unconditional disabling. Non-CAD admission remains disabled. These are distinct exposure/runtime features; model metadata may also select tool mode. New actual argv are rebuilt in `pilot_alt_runtime.generation_argv`, not copied from old frozen argv. `code_mode_fix_20260923/plan.json` and its Linux `operator/code_mode_plan.json` copy have matching hash `c0cfce1114126818f302e40bb1841e98f573559a116bc7bb24af6dcb4394fced`. Script, plan and per-model argv hashes are in `sync.json`. Original plans and public prompt/addendum/input hashes are unchanged.

The official feature query reports code_mode=true, code_mode_host=true, shell_tool=false, multi_agent=false. It reports unified_exec=true despite the preserved legacy false argument: [managed_features.rs](https://github.com/openai/codex/blob/rust-v0.154.0-alpha.6.1/codex-rs/core/src/config/managed_features.rs) deliberately enables that backend absent a managed pin, while [spec_plan.rs](https://github.com/openai/codex/blob/rust-v0.154.0-alpha.6.1/codex-rs/core/src/tools/spec_plan.rs) returns before registering shell tools when shell_tool is false. This is disclosed rather than falsely claiming every supplied false flag is effective.

The first no-model features command incorrectly used exec-only ignore flags and exited 2. The corrected supported features query exited 0; its initial verifier assertion exited 1 because it expected unified_exec=false. The source-backed explanation above resolves that assertion expectation; both records are preserved. Actual generation/short-session exec retains `--ignore-user-config --ignore-rules --strict-config` with no later code_mode_host=false override.

The [Code-mode nested dispatcher](https://github.com/openai/codex/blob/rust-v0.154.0-alpha.6.1/codex-rs/core/src/tools/code_mode/mod.rs) routes inner calls through normal tool handling. Outer exec is a custom payload, whereas inner CAD MCP function calls receive existing hooks. Guard code was **not changed**; native exec/shell/patch/read_file/subagent/other-MCP requests remain denied. No blanket exec exemption, sandbox bypass, CAD network change or authentication mount was introduced. Working proxy/login/CAD isolation results were reused without network probes, cube/fixture reruns or image admission.

### Actual validation and one model-mediated check

Pinned Windows test interpreter:
`C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe`.

```powershell
& $py -B -m unittest discover -s model_comparison/tests -p 'test_pilot_alt_runtime.py' -v
# exit 0, three tests: distinct effective argv flags/exact runtime grant,
# unchanged admission disabling, original inner-tool deny rules
wsl -d Ubuntu-24.04 -u camus -- /home/camus/robotgen-alt-client-20260923/codex-code-mode-host --help
# exit 0; component startup only, not the model-mediated acceptance
wsl -d Ubuntu-24.04 -u camus -- /usr/bin/python3 -B /home/camus/robotgen-alt-runtime/continuation_20260923_0332/operator/pilot_alt_runtime.py --short-check /home/camus/robotgen-alt-runtime/continuation_20260923_0332/operator/code_mode_plan.json
# official client exit 0; short-check runner and immediately captured LASTEXITCODE 2
```

The one fresh gpt-5.6-sol connectivity session used a new empty directory, no image and no robot prompt, and ran **30.809 seconds** within its 120-second bound. Its exact task was one `echo ROBOTGEN_CODE_MODE_CAD_OK` through CAD execute, inspect output, then CAD submit. The actual standalone host process was observed. CLI events contain one execute attempt with that exact command and one submit attempt. Both failed with:
`MCP tool call requires approval, but approval policy is never`.

The server-side state is authoritative: **tool_calls=0, records=[], submitted=false, tool_stopped=true**. No CAD action exit code or marker exists; neither a visible model assertion nor client exit 0 is counted as acceptance. No native host command execution event occurred. This proves the disabled-host failure was resolved and identifies a subsequent MCP approval gate; it does **not** prove end-to-end CAD execution. The separate approval path is evidenced in fixed-version `mcp_tool_call.rs`; no approval setting was relaxed after the failure.

CLI usage: input 24799, cached input 22528, output 708, reasoning-output count 309. Hidden reasoning text was not retained. Underlying API query/retry counts remain null/not_observed. **One short model session was used; zero replacement robot sessions were started.** The short check is infrastructure evidence, never a robot result. There was no second short check, no model fallback and no Smart AGI request.

### Replacement scope, failure references and stop condition

| Requested model / identity | New run_id suffix | Replaces prior run | Result |
|---|---|---|---|
| gpt-5.6-sol / client_requested | code_mode_fix_20260923/model_B | continuation_20260923_0332/model_B_network1 | Not started; failed required tool gate |
| gpt-5.6-terra / client_requested | code_mode_fix_20260923/model_C | continuation_20260923_0332/model_C | Not started; failed required tool gate |

Backend identities remain unverified. `prior_failure_annotation.json` adds failure_domain=INFRASTRUCTURE_TOOL_CONFIGURATION and reason=code-mode host disabled before CAD execution to references to the old failures; original GENERATION_FAILED journals, requests, replies and exits are not rewritten or dismissed as zero requests.

No replacement source, CAD artifact or first/final robot snapshot exists. File-contract assessment, source rebuild, STEP/STL/XML measurements and all other engineering metrics are NOT_RUN/NA; no total score is reported. Replacement worker commands were prepared in the new plan but **not executed**. This follows the explicit instruction to stop real design startup if the single short model tool check fails; sufficient time remains, but elapsed time cannot override that gate.

Safe short-check records are retained in `results/pilot_20260923/alternate_access_20260923/continuation_20260923_0332/code_mode_fix_20260923/tool_check`, with committed copies `short_check.json`, `short_tool_state.json`, and snapshot/path/hash bindings in `closure.json`. Runtime process inspection at 05:04:22 +08:00 found no remaining client, host, worker or MCP process. The remaining blocker is the CAD MCP approval configuration conflicting with approval_policy=never. No user credentials, global settings, old CAD environment, evaluator or formal configuration were changed.

## Ubuntu migration — independent batch `ubuntu_migration_20260923_v1`

The active checkout is now `/home/camus/robotgen-eval-v2` on Ubuntu/Bash.
The target was empty including hidden files before a full, non-shallow clone.
Branch `deadline/alternate-access-20260923`, local HEAD and origin initially all
matched review baseline `8ab4b57d262b0a66eb4fbdebef750fffd5166418`.
No applicable ancestor or repository `AGENTS.md` was found. Historical Windows
paths and session budgets above describe prior runs only.

Host `/usr/bin/python3` is 3.12.3; `/usr/bin/bwrap` is 0.9.0. Native namespace
checks passed: no inherited synthetic credential/proxy, no host home or other
participant directory, read-only public inputs, writable own output, no external
network, timeout exit 124 and safe stopped-output snapshots. No cube or echo
model session was run. These checks do not establish CAD package availability.

The old `/home/camus/robotgen-pilot-runtime-20260922` does not exist here. No
usable CAD or pinned model-client environment was found in the inspected local
locations. Host Python lacks CadQuery/OCP, MuJoCo, mini-swe, LiteLLM and tiktoken.
Deleted environment entries found in Trash were not executed or restored.
No dependencies were installed. Historical ignored outputs/results and tokenizer
cache were absent; no historical attempt was reconstructed as a new result.

Minimal portability changes retain the existing Harness and evaluator:

- `pilot_sandbox.py` uses the native Linux argv without constructing a Windows
  launcher on Linux. `ROBOTGEN_CAD_VENV` selects an existing dedicated host venv,
  mounted read-only at `/cad`; `/cad` itself is rejected as a host setting.
  Missing environments fail before launching CAD. Namespace and mount policy
  are retained; no credential mount or network relaxation was added.
- `pilot_run.py` uses `TIKTOKEN_CACHE_DIR`, defaulting to the checkout's
  `.tools/tiktoken-cache`. No cache download is implicit. Its preflight records
  absent packages/provenance/cache/admission as blocked instead of crashing.
  `preflight --batch NAME` writes a separate input kit and report, and refuses
  to overwrite an existing preflight report. An admission record from an older
  batch cannot open this batch's gate.
- The historical restored worker launcher uses `sys.executable` instead of a
  deleted Windows interpreter. Its old candidate list and budgets remain
  historical and were not executed or reused for the new three-provider scope.

The frozen input commit remains `f1d77516e35d7191a942d842b83f7ae23bb0710b`.
`experiment.py verify-inputs` exited 0 with manifest hash
`31c147981b08a2a6c335e1b270de86520042ca9006c0c028929c705893588e9d`.
The reference and motor remain `assets/reference.png` and
`assets/xl330_m288_t.step` relative to `model_comparison/inputs`.
No benchmark thresholds, public inputs, snapshot code or evaluator definitions
were changed. The legacy benchmark entrypoints already use `sys.executable`
and repo-relative paths, but assume the existing gorilla8 layout; they were not
run against a nonexistent new design. The pilot evaluator still cannot claim
full dynamics/motion/robustness scores.

```bash
python3 -B model_comparison/tools/experiment.py verify-inputs
# exit 0
python3 -B -m unittest discover -s model_comparison/tests -p test_pilot_ubuntu.py -v
# exit 0; 4 tests, actual Linux isolation included
python3 -B model_comparison/tools/pilot_run.py preflight --batch ubuntu_migration_20260923_v1
# exit 2; ENVIRONMENT_BLOCKED, generation_ready=false
```

The first test development run had one test-only Git cwd error; it was corrected
and the four tests passed. The full historical suite was not run because parts
require absent runtimes and recreate CAD fixtures excluded from this task.
Safe evidence and the preflight copy are in
`records/pilot_20260923/ubuntu_migration_20260923_v1/`.

Continuation scope is DeepSeek/Gemini/Claude, with no GPT expansion.
[Google's official image-input documentation](https://ai.google.dev/gemini-api/docs/image-understanding)
establishes a source-backed Gemini channel candidate;
[Anthropic's vision documentation](https://platform.claude.com/docs/en/build-with-claude/vision)
establishes a Claude candidate. This is documentation evidence, not successful
account admission or confirmed backend identity. No model route was selected
or queried. The current process has no standard API-key variable for these
providers or the old Smart AGI gateway; only presence booleans were checked.

Real API work is blocked pending current deadline/timezone/shared-budget
confirmation and a usable, securely configured channel. CAD and the pinned
client/cache also need an existing verified runtime or a scoped restoration.
The old deadline and budget are not authorization for new requests.
Actual model calls = 0; real generation = NOT_STARTED; independent robot
evaluation = NOT_RUN. No design or score is claimed by this migration batch.
