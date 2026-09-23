# Local runtime restoration after SDK smoke closure

Author-local result: **CAD/client/cache checks passed; generation remains closed.**
Execution code: `0e6037d297b352c6cba09c79cae2659dee6373a2`.
No model calls, Agent loop, robot generation, cube fixture or independent robot
evaluation occurred during restoration. The two SDK smoke request slots remain
consumed; see `../api_smoke_20260923_v1/closure.json`.

New dedicated local environments:

- `.tools/cad-runtime`: CadQuery 2.6.1, OCP 7.8.1.1.post1, NumPy 2.2.6.
- `.tools/pilot-client`: mini-swe-agent 2.4.6 from original Git commit
  `04d809ceab9df28f9adaed044884180159172930`, LiteLLM 1.102.0, tiktoken 0.14.0.
- `.tools/tiktoken-cache`: original required cache filename and SHA-256 verified.

The smoke SDK venv is separate and unchanged. No global packages, system proxy,
benchmark thresholds, Harness code or frozen inputs were modified. The CAD version
uses the explicitly recorded historical 2.6.1 override, not the input lock's 2.7.0.
Other CAD constraints were copied into a separate local file. Client transitive
dependencies were resolved and frozen here; they are not asserted identical to
the previous Windows environment. These packages are infrastructure preparation,
not a new experimental-condition freeze. MuJoCo/full dynamics remains unrestored.

Both dependency resolutions and installs exited 0. Installer logs reported an
ambient ROS PYTHONPATH dependency warning; subsequent isolated `python -I` checks
found no broken requirements in either venv. Isolated installed inventories match
the packages in pip's install reports. ROS packages were not modified. Use
isolated Python for further environment checks to avoid inherited Python paths.

Both environments were tested through the existing bubblewrap helper, read-only
at `/cad` with cleared environment, no host home, and no external network:

| Check | Exit | Evidence |
|---|---:|---|
| CAD import and original motor STEP readback | 0 | `cad_probe.json` |
| Client provenance, class imports, offline tokenizer | 0 | `client_probe.json` |
| CAD `pip check` using Python `-I` | 0 | `restoration.json` |
| Client `pip check` using Python `-I` | 0 | `restoration.json` |
| Separate restored-runtime preflight | 2 | `preflight.json`: ACCESS_BLOCKED |

The CAD probe observed 15 valid solids in the supplied original motor STEP and
verified a read-only CAD mount. It generated no geometry and cannot establish
robot design quality. Client provenance and cache pass, but no admitted image
channel is present; `generation_ready=false`. The prior text SDK success does
not open this gate. The client sandbox temporarily uses `/cad` as the existing
helper's generic venv mount; it is not a host interpreter path.

Reproduction commands (setup was actually executed after dry-run resolution;
do not overwrite existing venvs or evidence when reproducing):

```bash
python3 -m venv --without-pip .tools/cad-runtime
python3 -m venv --without-pip .tools/pilot-client
# constraints copied from this record to the corresponding venv directories
env -u ALL_PROXY -u all_proxy .tools/cad-runtime/bin/python .tools/api-smoke/pip.pyz --isolated install --report results/runtime_restore_20260923_v1/cad_install.json --index-url https://pypi.org/simple -c .tools/cad-runtime/constraints.txt 'cadquery==2.6.1' 'cadquery-ocp==7.8.1.1.post1'
env -u ALL_PROXY -u all_proxy .tools/pilot-client/bin/python .tools/api-smoke/pip.pyz --isolated install --report results/runtime_restore_20260923_v1/client_install.json --index-url https://pypi.org/simple -c .tools/pilot-client/constraints.txt 'mini-swe-agent @ git+https://github.com/SWE-agent/mini-swe-agent.git@04d809ceab9df28f9adaed044884180159172930' 'litellm==1.102.0' 'tiktoken==0.14.0'
.tools/cad-runtime/bin/python -I .tools/api-smoke/pip.pyz --isolated check
.tools/pilot-client/bin/python -I .tools/api-smoke/pip.pyz --isolated check
.tools/pilot-client/bin/python -I -B -c "import sys; sys.path.insert(0, 'model_comparison/tools'); import pilot_run; raise SystemExit(pilot_run.preflight('runtime_restore_20260923_v1'))"
```

Exact sandbox argv and operator-only probe source are recorded in the two probe
JSON files. Setup stdout/stderr and full pip reports remain locally under
`results/runtime_restore_20260923_v1/`; their hashes are committed in
`restoration.json`. Package lists and constraints are committed, not venvs,
wheels, binary artifacts or full setup logs. The cache URL and expected hash are
also in `restoration.json`; no cache data is committed. Original setup commands
used the provided PyPA pip zipapp because system ensurepip is absent.

To select the restored CAD venv for a later authorized existing Harness action,
set `ROBOTGEN_CAD_VENV=/home/camus/robotgen-eval-v2/.tools/cad-runtime` in that
process. This setting does not authorize any model request. Full generation still
requires separately reviewed channel admission and current budget/deadline.
