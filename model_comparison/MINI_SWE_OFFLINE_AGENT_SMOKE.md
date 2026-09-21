# mini-swe-agent offline agent smoke

**最终状态：PASS。** 2026-09-21，在 Windows 的独立临时 virtualenv 中，固定 upstream 的真实 `DefaultAgent + DeterministicModel + LocalEnvironment` 完成离线闭环和 step limit 检查。smoke exit code 为 **0**。

这个 PASS 只覆盖本轮两个场景及原生 trajectory。`DeterministicModel` 直接提供 parsed actions；本轮没有证明任何真实模型或 action transport 的兼容性。

## 1. 基线、安装与来源

| 项目 | 实际记录 |
|---|---|
| Repository | https://github.com/camus0330/robotgen-eval |
| RobotGen baseline | `706fcdaee572f18574c916a75799aafaffdaa20c`；创建分支前 `git rev-parse HEAD` 已确认 |
| Branch | `spike/mini-swe-offline-agent` |
| Upstream repository | https://github.com/SWE-agent/mini-swe-agent |
| 固定 upstream SHA | `04d809ceab9df28f9adaed044884180159172930` |
| 实际 distribution / import version | `mini-swe-agent==2.4.6`；`minisweagent.__version__ == "2.4.6"` |
| Python | `3.13.13`，Anaconda，`[MSC v.1942 64 bit (AMD64)]` |
| OS/platform | `Windows-11-10.0.26100-SP0`；machine=`AMD64` |
| 安装方式 | 标准库 venv；pip VCS 安装指定完整 SHA，构建非 editable wheel；未用 latest、tag 或其他 commit |
| 安装 exit code | `0` |

本次临时安装根目录为 `C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05`，下文简称 `<temp-root>`。virtualenv 位于其 `venv/`，pip cache 位于 `pip-cache/`，完整安装输出位于 `pip-install.log`，smoke 控制台证据位于 `smoke.log`；均不进入 Git。

安装使用以下方式，其中 `<venv-python>` 为 `<temp-root>\venv\Scripts\python.exe`：

```text
python -m venv <temp-root>\venv
<venv-python> -m pip --isolated --cache-dir <temp-root>\pip-cache install git+https://github.com/SWE-agent/mini-swe-agent.git@04d809ceab9df28f9adaed044884180159172930
```

安装进程的 `MSWEA_GLOBAL_CONFIG_DIR` 指向新建临时根下的 `install-config`，不使用个人全局配置。安装只是兼容性验证，不代表正式依赖已冻结进 RobotGen；没有改 requirements、environment lock、pyproject 或 Dockerfile。

pip 记录 `Resolved ... to commit 04d809ceab9df28f9adaed044884180159172930`。安装后的 `direct_url.json` 为：

```json
{"url": "https://github.com/SWE-agent/mini-swe-agent.git", "vcs_info": {"commit_id": "04d809ceab9df28f9adaed044884180159172930", "requested_revision": "04d809ceab9df28f9adaed044884180159172930", "vcs": "git"}}
```

脚本核对该 VCS URL/SHA、distribution version、import version，并确认 package 位于当前 venv，四个指定入口的实际源码路径都位于该 distribution 的 `Lib/site-packages/minisweagent/`。另外只读比较了安装文件与工作树干净、HEAD 为固定 SHA 的临时上游 checkout，以下文件逐字节 SHA-256 一致：

| 上游 package 内文件 | 本次安装文件 SHA-256 |
|---|---|
| `__init__.py` | `345e98017170baeea72f527b0cda7c0204f22e286b05c06d97e011ad4eda585d` |
| `agents/default.py` | `b921f0223dc191de398a518df6279bc54ff792582c150476abc2d19c5715be89` |
| `models/test_models.py` | `9daa113e015b3d6781e84a50b5859bee6030d8a7fff09079477fdf8dd0b9be3b` |
| `environments/local.py` | `c44d21c4c461b0d9f5b2bd2bb180a65537d33808ae6a388341b51d8ddf84e926` |

实际关键依赖：

| 依赖 | 安装版本 |
|---|---|
| pip | 26.0.1 |
| pydantic | 2.13.5 |
| jinja2 | 3.1.6 |
| python-dotenv | 1.2.3 |
| platformdirs | 4.11.11 |
| rich | 15.0.0 |
| litellm | 1.102.0 |
| openai | 2.54.0 |
| tenacity | 9.1.4 |

LiteLLM/OpenAI 等由上游依赖声明安装；列出版本不代表调用或测试其 transport、parser、retry 或 endpoint。没有安装无关的 RobotGen 测试/CAD 依赖。

## 2. 实际执行与 Scenario A

从 RobotGen 仓库根运行的实际命令：

```powershell
& 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe' model_comparison/spikes/mini_swe_offline_agent_smoke.py
```

即在上述 venv 中执行 `python model_comparison/spikes/mini_swe_offline_agent_smoke.py`。实际退出码 **0**，脚本输出 `FINAL: PASS`。

脚本仅通过上游 `make_output` 构造两个确定性 assistant 输出，并直接传给真实 `DeterministicModel`；由真实 DefaultAgent 负责执行循环。两个 parsed actions 为：

```text
echo robotgen_offline_smoke
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT&&echo robotgen_offline_submission
```

没有手工构造 observation，没有重写、继承或 patch 上游 Agent/Model/Environment。第一条命令由 `LocalEnvironment.execute()` 实际执行，第二条触发上游原有 submit sentinel。

| Scenario A 检查 | 实际值 / 结果 |
|---|---|
| 场景状态 | PASS |
| exit_status | `Submitted` |
| submission | `robotgen_offline_submission\n` |
| agent.n_calls | `2` |
| model.current_index | `1`，两个输出均已消费 |
| message roles，按顺序 | `system, user, assistant, user, assistant, exit` |
| 初始 user | `Run offline scenario A.` |
| 第一步 observation role | `user`，这是 DeterministicModel 原有 observation 格式 |
| 第一步 raw_output | `robotgen_offline_smoke\n` |
| 第一步 returncode / exception_info | `0` / 空字符串 |
| observation content | 真实包含 `robotgen_offline_smoke` |

此处 `\n` 是展示字符串中的换行转义。第一步 observation 由上游环境结果与原有 observation formatter 生成，不是 fixture 填写的响应。

## 3. Scenario B：step_limit=1

使用独立 DefaultAgent、DeterministicModel 与 LocalEnvironment，准备两个普通 command responses：`echo robotgen_step_one` 和 `echo robotgen_step_two`。配置 `step_limit=1`。

| Scenario B 检查 | 实际值 / 结果 |
|---|---|
| 场景状态 | PASS |
| exit_status | `LimitsExceeded` |
| agent.n_calls | `1` |
| model.current_index | `0` |
| 第一步 raw_output / returncode | `robotgen_step_one\n` / `0` |
| message roles，按顺序 | `system, user, assistant, user, exit` |
| 第二个输出未被消费 | 已确认：outputs 仍有两项，第二项未改变，current_index=0，第二条 assistant 未进入 messages |

证明的是 step limit 在下一次 model query 前阻止继续消费响应，不是 shell 命令数量限制。两个场景的 synthetic cost 都设为 0、cost_limit=0，未验证 cost limit；未设置或测试 wall-time/retry。

## 4. 原生 trajectory 检查

DefaultAgent 的 `output_path` 指向临时目录，由上游 `save` 写出原生 JSON；脚本在 run 返回后读取文件核对，没有定义 RobotGen trajectory schema。

本次原生文件根为 `C:\Users\hp\AppData\Local\Temp\robotgen-mini-swe-smoke-04zylzrf`，下含 `A/native.traj.json` 与 `B/native.traj.json`。临时文件保留在工作树外供本地复核，不提交 Git。

| 原生字段 / 检查 | Scenario A | Scenario B |
|---|---|---|
| trajectory_format | `mini-swe-agent-1.1` | `mini-swe-agent-1.1` |
| info.mini_version | `2.4.6` | `2.4.6` |
| info.model_stats.api_calls | `2` | `1` |
| info.exit_status | `Submitted` | `LimitsExceeded` |
| messages | 与 agent.messages 完整相等，6 条 | 与 agent.messages 完整相等，5 条 |
| info.config.model | model_name=`deterministic`，完整确定性 outputs 已保存 | 同左 |
| info.config.environment | 对应场景临时 cwd 已保存 | 同左 |
| info.config.agent_type/model_type/environment_type | 均为指定上游真实类路径 | 同左 |
| messages[2].extra.actions | 与第一步预定 command 相等 | 同左 |
| messages[3].extra.raw_output | 与真实 shell observation 相等 | 同左 |

`api_calls` 是上游字段名，在这两个场景中表示确定性 model query 次数，**不是外部 API 请求数**。

本次文件 SHA-256：

- A：`e971e33d9076dd9796a9b4bf5b3762ff7393c784f6e095b9459a2aa43581a72b`
- B：`83606e1b7cf94558c1be3e9eae40ffd06e41e644376ce0f3251a925054b70071`

原生轨迹包含时间戳和临时路径，上述哈希仅绑定本次运行，不是要求复跑字节一致的 golden fixture。

## 5. 安全、warning 与兼容性边界

- **本轮没有调用真实 LLM API。** 安装期间仅进行了获取上游源码和依赖所需的网络访问；smoke 使用确定性输出，不创建 provider client。
- **本轮没有使用或读取真实 API key。** 未读取 SMART_AGI_API_KEY、OPENAI_API_KEY 的值、个人 `.env` 或实际 api_config.json，未打印完整环境变量。
- 上游 LocalEnvironment 会把进程环境用于模板和 shell。脚本在导入上游前仅枚举变量名，删除非系统路径/临时目录白名单变量，不读取被删变量值；随后把全局配置目录固定到全新临时目录，其下没有 `.env`。这是 smoke 进程的输入隔离，不是新增 sandbox manager 或修改上游环境执行实现。
- Windows 实测使用上游 `shell=True` 的系统默认 shell，未指定 `/bin/bash`，未添加 shell 兼容层；本轮简单 echo/sentinel 命令未发现平台阻断。没有测试 POSIX 平台，也不据此声称所有 bash 脚本均能在 Windows 运行。
- pip 仅提示可从 26.0.1 更新到 26.2.1；未升级。安装日志未出现 WARNING/ERROR，smoke 未报告 warning 或异常。
- LocalEnvironment 不是隔离 sandbox；这里只执行脚本内固定的无害命令。没有测试超时、进程清理或安全隔离。

## 6. 未验证内容与结论

**本轮没有验证 `LitellmTextbasedModel` parser。** DeterministicModel 已直接提供 parsed actions；上游 observation formatter 的使用不能被称为 text-based action parsing 验证，也没有验证 native tool calling。

**本轮没有验证 DockerEnvironment。** 没有使用 Docker。

**本轮不是 RobotGen Harness implementation。** 没有创建 RobotGen AgentLoop、ModelAdapter、tool dispatcher、HTTP client、action parser、sandbox manager、event schema 或 retry wrapper；脚本的两个场景调度不承担 Agent 迭代。

此外均未验证：LiteLLM/真实 endpoint/smart-agi、HTTP retry、任何真实模型、cost/wall-time/hard deadline/process cleanup、多模态图片、RobotGen Prompt/frozen inputs、CADQuery/MuJoCo/机器人生成、submission adapter、experiment.py、benchmark 或 feedback rounds。没有运行整个 RobotGen pytest suite。

本轮只能得出：固定 upstream 在上述实际环境中可安装/导入；真实 `DefaultAgent + DeterministicModel + LocalEnvironment` 的 action → shell → observation → submit → 原生 trajectory 闭环与 step limit 基础语义可离线运行。下一阶段不因这个 PASS 自动获得扩大范围的许可。

## 7. 变更与回滚

只新增本报告和 [mini_swe_offline_agent_smoke.py](spikes/mini_swe_offline_agent_smoke.py)。上游源码、virtualenv、cache、安装日志与轨迹均在临时目录，不提交；没有改项目其他文件或正式 dependency manifest。

提交信息：`test: probe mini-swe offline agent loop`；推送 `spike/mini-swe-offline-agent`，不 merge。核对 `git diff --check` 及相对 baseline 的 diff 仅包含这两个文件。若审阅 REPAIR，只修这两个 spike 文件；不得扩展到 text parser、Docker、真实 endpoint 或正式 Harness。
