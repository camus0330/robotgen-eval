# Common native Ubuntu CAD process addendum

The original robot task, reference image, motor, motion constraints, materials,
units and scoring thresholds remain unchanged. This addendum supplies only the
execution environment and submission/rebuild process. It provides no design.

Use the restored native Ubuntu runtime: Python 3.12.3, CadQuery 2.6.1 and
cadquery-ocp 7.8.1.1.post1. This retains the recorded runtime override of the
original input lock. The same selected environment applies to every configured
slot. Packages are already installed; do not install or access the network.

Public inputs are read-only at `/kit/inputs`. The original assets are
`/kit/inputs/assets/reference.png` and `/kit/inputs/assets/xl330_m288_t.step`.
Use `/cad/bin/python`; `/cad` is a read-only sandbox mount, not a host path.
Your only persistent writable design directory is `/work`. Each action gets a
fresh namespace with no credentials, external network or other participant's
files. Scratch HOME is `/tmp`. Tool actions are bounded to at most 60 seconds wall
and 30 seconds CPU. Snapshot quotas are 2048 files / 256 MiB. Links are rejected.

The operator appends this batch's explicit deadline and execution budget to the
task. Those fields, not a historical deadline or draft budget in the input kit,
govern this run. There are no provider retries or human design edits. No real
generation starts while deadline, budget, authorization or admission is missing.

Read the original task and submission specifications. Copy process metadata from
`/work/operator_metadata.json` into `submission.json`; the runner fills observed
status, elapsed time and logs after the tools stop. Do not invent identity,
usage, billing or validation results. `runner_log.json` is runner-managed.

Declare the following additional manifest fields explicitly:

- `rebuild_inputs`: source and local data needed by the build.
- `rebuild_outputs`: every newly generated assessed STEP/STL and other output.
- `rebuild_excluded`: logs and other non-build files, including
  `operator_metadata.json` and `runner_log.json`.
- `rebuild_command`: an explicit Python source entrypoint, for example the array
  `["python3", "build.py"]`, where the entrypoint is a declared rebuild input.

All files must be classified except `design_manifest.json` and `submission.json`,
which are recognized metadata. Paths must be relative, distinct and free of
traversal or links. Inputs and outputs must not overlap. Prebuilt STEP/STL cannot
be source inputs; read the supplied motor directly from `/kit/inputs`.
The independent evaluator rebuilds from declared source/data in a fresh workspace
and measures newly generated files. A zero exit without expected readable outputs
does not pass. Do not change source files during rebuilding.

Use one literal `mswea_bash_command` action per response and wait for its actual
observation. Submit with a successful command whose first stdout line is
`COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`. Submission alone is not an engineering
pass; measurements may fail or remain unavailable.
