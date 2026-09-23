# Explicit Ubuntu batch entry: author-local review pack

Objective: add one isolated SDK image-request mode and complete the existing
`pilot_restored` CAD execution entry. B implementation and offline verification
are complete; A is **not started because SMART_AGI_API_KEY is absent**. Actual
live model requests in this round: **0**. No robot design, frozen robot output,
real CAD rebuild, or independent robot evaluation was produced this round.

Starting branch: `deadline/alternate-access-20260923`.
Starting/reviewed SHA: `94d25ec9459ccff9d64d786d920552b1af99f445`.
The commit containing this pack is the delivery revision; its pushed SHA is
reported separately after push (avoids a self-referential commit hash).
Unknown untracked `paper/` was left untouched and excluded.

## What changed

- `pilot_batch.py` validates explicit batch/run paths, model configs, runtime,
  public addendum, deadline, authorization and uniform per-run budget. It binds
  original Git input bytes to the existing frozen BASELINE, plus current runner
  code hashes; no input or score change. New directories are exclusive.
- `pilot_restored.py` requires an explicit v2 plan at CLI entry. It propagates
  the selected kit/config/run/addendum/output/evidence/deadline/budget through
  preflight, the existing pinned Agent, CAD actions (`cad=True`), safe freezing
  and evaluation. Both parent and direct worker check gates before client setup.
  The dedicated CAD environment is passed as ROBOTGEN_CAD_VENV; the existing
  bubblewrap credential/network/file isolation remains in place.
- `pilot_evaluate.py` accepts explicit batch paths and verifies execution-plan
  context. Its original experiment intake, source_rebuild, step_readback and
  scoring logic are reused. Frozen plan/config/input/addendum, budget and
  deadline are recorded in run/evaluation evidence. Independent evaluation of
  already frozen output does not authorize another model request.
- `pilot_run.py` supports a supplied kit destination. Legacy runtime-only
  preflight can no longer report generation_ready from an old successful call.
- SDK `smoke.py --image-only` calls only run_image_only, never run_checks. It
  has one new journal directory, exact original PNG binding, one HTTP-send guard,
  zero retries, visible refusal capture and durable user-cancellation evidence.
  See [image-request instructions](../deepseek_image_20260923_v1/README.md).

The historical helper functions remain available for reading old records, but
the executable restored CLI no longer exposes old admission/implicit-run modes.
No new Harness or automatic paid admission workflow was added.

## Current prepared plan and commands

The checked-in spec is an intentionally unauthorized template: deadline and
budget values are null, robot_generation is false, and no admission exists.
Only DeepSeek is configured; no Gemini/Claude alias is inferred. The runner
supports the three existing slots when their explicit reviewed configs exist.
This is not an approved robot experiment configuration.

Preparation already ran once successfully:

```bash
cd /home/camus/robotgen-eval-v2
.tools/pilot-client/bin/python -B model_comparison/tools/pilot_restored.py prepare \
  --spec model_comparison/batches/ubuntu_execution_20260923_v2.spec.json \
  --plan model_comparison/records/ubuntu_execution_20260923_v2/plan.json
```

Do not repeat prepare against existing directories. These commands use the
prepared plan; preflight writes a new uniquely named report by default:

```bash
.tools/pilot-client/bin/python -B model_comparison/tools/pilot_restored.py preflight \
  --plan model_comparison/records/ubuntu_execution_20260923_v2/plan.json
.tools/pilot-client/bin/python -B model_comparison/tools/pilot_restored.py run-batch \
  --plan model_comparison/records/ubuntu_execution_20260923_v2/plan.json
```

Both currently exit 2. `run-batch` is the existing serial generation → freeze →
independent evaluation path; it makes no automatic admission request. Individual
`run --slot model_A` and `evaluate --slot model_A` accept the same mandatory plan.
Evaluation requires this plan's complete, unchanged final snapshot.

For an authorized experiment, create a new spec with a new batch ID and unique
paths, exact slot configs, reviewed public addendum, timezone-aware future
deadline, robot_generation/source authorization, and explicit positive wall
time/query/cost/format-error limits. Prepare it once. Do not edit this frozen
plan or set null values from historical defaults. The budget scope is explicitly
per_run, uniform for configured slots. Library estimated USD cost is **not a
gateway billing cap**; no claim of a hard monetary ceiling is made.

Admission must be a separately reviewed artifact from authorized Harness/image
evidence, at the plan's record_root/admission.json (or explicit --admission).
It binds batch_id and plan_sha256. Each selected slot requires exactly one case
with scope HARNESS_PROTOCOL_IMAGE_ADMISSION, exact canonical config hash,
requested model, original image hash, finish_reason=stop, parser_pass,
nonempty_completion, image_url_in_completion_messages and image_content_review_pass.
The last four must be true and supported by actual evidence, not manually
asserted to open the gate. An SDK result alone lacks Harness admission.
Runtime, channel, authorization and credential gates are reported separately;
generation_ready=true/exit 0 requires all of them.

## Author-local verification and evidence

See `verification.json`, `preflight_01.json`, `test_pilot_batch.txt` and the
image directory's `preparation.json` / `test_smoke.txt` for commands and results.

- Batch suite: 9 tests, exit 0. It covers explicit paths and switching batches,
  all positive/negative gates, plan/config/image binding, no overwrite, direct
  worker bypass prevention, pinned model message preparation with original PNG,
  existing worker CAD=True, snapshot/evaluator dispatch and rebuild plumbing.
  Runtime gate and action/Agent boundaries are mocked; no real CAD/API call.
- SDK suite: 10 tests, exit 0, synthetic MockTransport only. It covers exact
  request policy/PNG, image-only CLI routing, retry/replay bounds, refusal,
  timeout, interruption and preservation of journals.
- Actual v2 CLI: prepare exit 0; preflight exit 2; run exit 2 before client setup.
  runtime_available=true (prior evidence + passive file/version validation),
  channel_admitted=false, experiment_authorized=false, credential_available=false,
  generation_ready=false. No environment/CAD acceptance probes were repeated.
- During development a fake-worker test initially failed because its client
  scrubbed the parent test environment in the same process. The fixture now
  restores that environment to simulate the actual child process; final tests
  passed. This was not a live gateway failure.
- `git diff --check`: exit 0. Frozen inputs, sandbox/snapshot/CAD helpers,
  experiment.py and benchmark thresholds were not edited.

`ubuntu_execution_20260923_v1` preserves an earlier development plan/preflight.
Later evaluator-context changes made its code hashes stale. It is superseded,
not runnable with this source, and was neither overwritten nor refreshed.
Use v2. Canonical kits, empty output directories and local result roots stay
under ignored outputs/results; they are not restored by Git clone. A future
checkout must prepare a new batch to materialize its kit.

Evidence categories: runtime restoration is historical author-local evidence;
this round has source changes and author-local offline tests only. User-pasted
older API results are not new requests. GPT web review, assistant independent
re-execution, new real model generation and vision-content comparison have not
occurred. No completion exists to compare with the PNG in this round.

Next step: run the one authorized image-only terminal command, retain the single
outcome (including unknown/refusal), and review its content against the PNG.
Before robot generation, obtain reviewed Harness admission plus explicit formal
budget/deadline/authorization for a new batch; do not launch another paid batch
based on this pack.
