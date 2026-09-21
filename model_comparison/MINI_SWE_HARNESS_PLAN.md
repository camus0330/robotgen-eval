# RobotGen × mini-swe-agent 最小集成计划

调研日期：2026-09-21。本文仅为 integration plan，不实现、不安装、不调用模型、不生成机器人，也不改变现有协议或评分。

| 研究对象 | 本次实际读取的版本 |
|---|---|
| RobotGen repository | https://github.com/camus0330/robotgen-eval |
| RobotGen baseline | `f0a88217122b80b5d8fab32945d78df8645effc3`；在此 HEAD 创建 `design/mini-swe-harness` |
| mini-swe-agent repository | https://github.com/SWE-agent/mini-swe-agent |
| upstream branch / commit | 调研时远端 `main`：`04d809ceab9df28f9adaed044884180159172930` |
| package / version | `pyproject.toml` 的包名为 `mini-swe-agent`，动态版本取自 `src/minisweagent/__init__.py`，值为 `2.4.6` |
| tag 核查 | HEAD 无本地所指 tag；远端 `v2.4.6` 指向 `a83fcae82d2a08f0ee0c688f9d137b3566c097f8`，**不是本次研究的 HEAD**。不能以版本字符串替代 commit pin |
| 依赖证据边界 | 上游声明 Python ≥3.10、`litellm >=1.75.5, !=1.82.7, !=1.82.8`，并依赖 OpenAI SDK 等；本轮没有安装或解析依赖，因此没有声称验证过某个实际 LiteLLM/SDK 组合 |

上游在 RobotGen 工作树外临时克隆并逐文件读取；没有复制源码入库。本文不依赖历史 `feat/harness-agent-loop` / `2d1bfc3fd86b819cbe28d0060740d2b4a7f80e94`，也未读取或修改 Inspect 路线文件。

证据标记约定：**confirmed capability** 表示从本次固定源码或官方资料确认的行为，不表示已完成 RobotGen 集成实测；**provisional recommendation** 是待审阅的方案；**future validation required** 是仍需测试或预登记的条件。后文所有拟议路径、参数选择和代码预算都属于后两者，不是新增协议字段。

## 1. 结论与职责边界

**provisional recommendation：复用 mini-swe-agent 的 Agent/Model/Environment primitives，RobotGen 维护一个配置和两个薄模块；不复用 SWE-bench 的任务/patch/evaluation 层，不另建通用 Harness framework。**

```text
RobotGen 冻结协议、公开输入、PROMPT、模型配置
       │  RobotGen：核对身份/哈希/预算，建立本 attempt 工作区
       ▼
host: mini-swe DefaultAgent ── LiteLLM Model ── 指定模型 endpoint
       │                          API 凭据仅留 host
       └── DockerEnvironment ── 无外网 generation container
                                  bash → CAD/Python/MuJoCo → submission/
       │ 原生 trajectory + RobotGen 少量 provenance
       ▼
RobotGen：封存 first/ 与最终文件，填写既有 submission.json
       ▼
experiment.py validate → 独立工程 benchmark → comparison/report
```

| 能力 | 维护方与最小边界 |
|---|---|
| 模型/工具迭代、格式错误恢复、标准退出异常 | mini-swe `DefaultAgent.run/step/query/execute_actions`；RobotGen 不重写循环 |
| provider transport、消息转换、bash action parsing | 上游 `LitellmModel` 或 `LitellmTextbasedModel` 与 LiteLLM；RobotGen 仅翻译现有配置，不写 HTTP client / parser |
| bash 执行、Docker 启动与基础清理 | 上游 `DockerEnvironment`；RobotGen 冻结 image、挂载与资源参数，不开发通用 sandbox manager |
| 原生 trajectory、step/cost 与轮间 wall-time 检查 | 上游直接提供；严格截止、脱敏及 RobotGen 反馈生命周期的缺口见第 6–8 节 |
| task adapter / prompt binding | RobotGen：读取冻结输入、绑定相同 system scaffold/action 指令、处理参考图片 |
| workspace / submission / provenance | RobotGen：每 attempt 隔离、只读输入、first/ 留存、元数据、哈希与既有 intake 桥接 |
| 工程评分与比较 | 现有 RobotGen benchmark 独立负责；Harness 只交接封存文件与证据，不生成工程分数 |

### RobotGen 当前实际边界

**confirmed capability：** `protocol.json` 为 `PILOT_DRAFT`，三个槽位身份/settings 和 `environment_description` 尚空；预算草案为 3600 秒、最多 2 轮标准反馈、0 分钟人工设计修改、`token_limit=null`、`network=disabled_except_model_service`。每模型 pilot 1 次、formal 5 次；`formal_scoring_ready=false`。这些值是现状，不是本文批准的正式配置。

`tools/experiment.py` 已有 `prepare-inputs` / `verify-inputs` / `refresh-inputs` / `freeze` / `validate` / `inventory`，没有模型调用或 generation loop。`verify_inputs` 比较完整文件清单及逐文件 SHA-256，返回 **records/input_manifest.json 文件自身**的哈希；submission 的 `prompt_sha256` 则绑定 `inputs/PROMPT.md`。`freeze` 核对身份、环境及根配置与 inputs 的一致性，只输出 `PROTOCOL_SNAPSHOT_ONLY`、`formal_engineering_ready=false`。

`PROMPT.md` / `TASK_SPEC.md` 要求从公开参考图和 XL330 STEP 从零设计 8 自由度机器人，交付 CAD、STEP/STL、BOM、MJCF、URDF、控制与两动作参考；不能把已有 Gorilla8 答案作为模型输入。`SUBMISSION_SPEC.md` 与三个 `templates/` 将操作者填写的运行事实和模型设计声明分开。`API_CONFIG.md` 的配置机制尚未被 `experiment.py` 实现；本文只读无密钥 example，不读取本地实际凭据。

现有 benchmark 入口及限制已核对实际代码：

| 路径 | 当前职责 / 集成限制 |
|---|---|
| `scripts/benchmark/run_digital.py` | `--root --run --out` 编排重建、几何探针、扰动仿真、数字评分；不是 Agent runtime |
| `prepare_rebuild.py:prepare`、`run_rebuild.py:main` | 固定复制 src/docs/BOM/README，并按 Gorilla8 固定阶段执行；不直接消费任意新 design_manifest 的重建契约 |
| `digital_geometry.py`、`simulate_cases.py` | 前者依赖 P02 等固定件名/探针；后者依赖 gorilla8.xml、固定接触/控制器等，不能默认适配新结构 |
| `evaluate_digital.py` | 包含 `len(measured)==12`、固定模型路径等；独立产生 scorecard，不由 generation 重算 |
| `evaluate.py`、`check_extended.py` | 旧证据审计与扩展覆盖；保留缺证据、错误和各自评分语义 |
| `compare.py` | 检查量表、benchmark/profile/评测器哈希一致性；不验证模型预算，也不自动证明模型排名 |

`ADAPTER_AUDIT.md` 的独立重建、通用 BREP 探针、控制器重放、结构覆盖和隐藏集适配仍 OPEN。它们阻塞正式通用工程评分，**不要求先解决才能做 endpoint 连通性 pilot**；Harness 不通过改名或包装伪造适配完成。`model_comparison/tests/test_intake.py` 用合成文本验证契约，`tests/benchmark/test_digital.py` / `test_evaluate.py` 验证缺证据、哈希与评分假阳性，均不是 CAD/动力学集成证明。

## 2. 对 HARNESS_DESIGN.md 的映射

原 `HARNESS_DESIGN.md` 基于“自研 Harness”假设写成。本文把名称解释为**职责边界**，不是要求 RobotGen 重新实现同名通用组件；本轮不修改原文，也不沿用其逐 provider 自建 ModelAdapter 的实施路径。

| 原概念 | mini-swe 对应实现 | RobotGen 剩余责任 |
|---|---|---|
| ModelAdapter | `models/__init__.py:get_model`、LiteLLM model 类、上游 action/observation utilities | existing api_config → 上游 config；精确身份核对、参数省略、凭据注入与脱敏 |
| AgentLoop | `agents/default.py:DefaultAgent` | 使用同一类/版本；仅在扩展点处理标准反馈、截止和存档，不写另一个决策循环 |
| ToolLayer | 模型层 bash parser + `DockerEnvironment.execute` | 镜像中相同 CLI/依赖、权限、输出展示策略；一般无需 run_cad/run_python 工具 |
| RunWorkspace | Docker 提供执行载体 | 输入/挂载/attempt 布局/first/封存全部由 RobotGen 定义，上游不懂这些协议 |
| EventLog | `DefaultAgent.serialize/save` + Model/Environment serialization | 保留原生 trajectory，补极少 metadata 和失败/截止记录；不新建 transcript schema |
| SubmissionAdapter | 无 RobotGen-specific 对应物 | 整理已有文件、权威填写 submission.json、调用既有 validate、交接独立评分 |

通用部分直接复用不意味着满足原设计的全部强约束：硬 wall-time、每次实际 API 尝试证据、强制停止容器写入以及反馈快照需要小型集成钩子或运行平台能力，必须按源码缺口验收。

## 3. native tool calling 与 text-based action

### 已确认的数据流

**confirmed capability：** `models/__init__.py:get_model_class` 在未指定类时返回 `LitellmModel`；必须显式冻结 `model_class`，不能依赖模型名称或 CLI 默认值决定实验分组。

| 项目 | A：`litellm` / `LitellmModel` | B：`litellm_textbased` / `LitellmTextbasedModel` |
|---|---|---|
| 请求 | `litellm.completion(..., tools=[BASH_TOOL])` | `litellm.completion(...)`，该类不自动传 tools |
| action | `actions_toolcall.py` 解析 native function `bash` 的 JSON arguments 中的 command | `actions_text.py` 对 message.content 用 DOTALL regex 提取，strip 后构成 command |
| 默认文本 regex | 不适用 | `` ```mswea_bash_command\s*\n(.*?)\n``` `` |
| action 数量 | 至少一个；允许多个 tool calls | 必须且只能匹配一个代码块，否则 FormatError |
| observation | role=tool，带 tool_call_id | role=user，无 native tool_call_id |
| 执行 | 两者均返回 `extra.actions`，进入同一 `DefaultAgent.execute_actions`，逐项调用同一 Environment | 同左 |

两种模式可以使用相同的 Agent 与 Docker bash 语义，但 **messages/格式约束不是完全相同的 scaffold**。A 的多个 actions 在默认 Agent 中顺序执行，并非并行；一次模型调用可以包含多个命令，故 step 不是 shell 命令数。B 一个代码块内也可包含多个 shell 命令。native parser 检查 JSON、工具名和 command 键，但不是完整的 schema/type/权限校验器，不能把它当安全边界。

`DefaultAgent` 对 FormatError 累计连续次数，默认 3 次终止为 `RepeatedFormatError`；错误调用仍计入 n_calls，已知 cost 也计入。普通无 action 的“最终文字”并不结束；两模式都依赖 Docker 的提交 sentinel（第 4 节）。

### 公平性与兼容性

| 维度 | 方案 A：所有模型 native bash | 方案 B：所有模型 text-based bash |
|---|---|---|
| 可比较内容 | 固定同一 bash schema、tool selection / 多 action 策略与 tool observations；仍有 provider 编码和模型工具训练差异 | 固定同一 action regex、示例、错误模板和 user observations；额外测量文本格式遵循能力 |
| 主要风险 | relay 可能不支持 tools、丢失 tool_call_id、返回错误 arguments，或不支持控制多 tool calls 的参数 | 代码中的嵌套 fence、无闭合 fence、截断、多块、只有 reasoning 无 content 都会导致格式失败 |
| endpoint 要求 | Chat Completions 多轮 native tool-call/tool-result round trip | 基础 chat 文本多轮即可承载 action；图片仍另外需要多模态支持 |
| step 公平性 | 多 action / 每响应必须预登记，不能假称与 B 的一块一轮等价 | 一次响应一块，明确且上游直接强制 |
| 与上游建议关系 | 上游 `actions_text.py` 明确推荐 v2 用 tool calls | 可作为本项目 relay 兼容性优先的实验选择，不声称普遍优于 native |

**provisional recommendation：第一轮兼容性 pilot 优先 B。** 当前 RobotGen 只有未核验的 OpenAI-compatible Chat Completions 候选接口，B 能先检查所有槽位在共同文本 action 协议下是否完成同一最小闭环，少一个 relay native tools 的不确定性。随后以相同模型/任务/预算独立测试 A，比较格式失败、可见 usage、延迟及工具往返可靠性，再决定正式 action protocol。

不得给 GPT 用 native、Claude/Gemini 用 text 后声称仅替换模型；某槽位失败不自动切类、换 provider 或重置预算。若保留 A/B 两组，作为明确不同 scaffold 的实验分组报告。不同 provider 经 LiteLLM 可走同一类/action 协议是代码架构支持，**每个精确 endpoint/model 的实际支持仍 future validation required**。

pilot 前需确认：所有模型接受相同 system/user 信息；A 的参数/schema/回传 ID 与 action 数约束，或 B 的精确 fence 与 format-error 恢复；相同 observation 裁剪；结束标记；不支持参数显式报错；同一图片可见；相同预算/重试；不要求输出隐藏 reasoning。不能因 relay 简单文本响应成功就批准 RobotGen generation。

## 4. Prompt/config 绑定与反馈

**confirmed capability：** `AgentConfig.system_template` 和 `instance_template` 必填，`run(task=...)` 用 Jinja StrictUndefined 渲染 system/user 两条初始消息。`mini.yaml`/`mini_textbased.yaml`/`default.yaml` 带 SWE issue 修复工作流；text 配置要求 THOUGHT，native mini 配置也建议 reasoning text；`benchmarks/swebench.yaml` 要求 `/testbed`、修改非测试源码、提交 git patch，并允许安装工具。它们都不能直接作为 RobotGen scaffold。

`run/mini.py` 默认使用 interactive Agent 和 local environment；`mini.yaml` 还有 `mode=confirm`、cost_limit=3 与 `drop_params=true`。RobotGen launcher 应显式选 DefaultAgent/Docker/model_class，提供完整独立配置，**不递归叠加这些 SWE 默认 prompt**。`get_model` 对 Anthropic 名称自动设 cache_control；需要显式配置并记录该策略，不能让名称偷偷改变传输设置。包导入会加载全局 `.env`，故未来 worker 还应固定隔离的全局配置位置和允许的环境变量，排除个人设置干扰。

**provisional recommendation：**

1. `task` 绑定经 `verify_inputs` 核验的 `inputs/PROMPT.md` 原文；instance template 用 `{{task}}` 插入，不重写任务、单位、交付与反馈规则。输入原文中即使有 Jinja 字符也不得二次求值。
2. 共同 system scaffold 只解释容器路径、唯一 bash interface、预算/反馈边界、文件交付与结束语义。冻结渲染后文本及配置哈希；不包含每机器变化的 `platform.uname()` 模板，也不强制 THOUGHT 或内部推理。
3. 在同一实验组内固定 action-format instructions、regex/schema、格式错误模板、max_consecutive_format_errors、observation 展示长度/截断规则、context 策略、command timeout 和 step/cost 设置。A/B 只在明确分组时换格式指令。
4. `DockerEnvironment._check_finished` 硬编码检查：stdout 去前导空白后的首行等于 `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` 且 returncode=0，才抛出 `Submitted`；后续输出是 submission 文本。配置没有改 sentinel 的字段。保留该通用完成信号，要求单独执行 `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`；目录、重建命令和限制先写文件。不要求 patch.txt，不把 stdout 当机器人文件。
5. 冻结 image/cwd、input/protocol/prompt/config hash、模型参数与 API 模式、重试/缓存/多模态策略。`PROMPT.md` 本轮保持原样。

### 图片是输入契约的一部分

`assets/reference.png` 的文件存在不等于模型看到了图。上游 `multimodal_regex` 默认空；`models/utils/openai_multimodal.py` 可以将匹配的 `image_url` 标记转为结构化图像消息，但不替 RobotGen 自动读取 PNG，也不渲染 CAD。

**provisional recommendation：** task adapter 从同一冻结 PNG 生成同一 data URL，并经上游多模态消息扩展附于共同初始输入；保存原图哈希及实际发送结构，不增加 agent tool。API 仍需对所有槽位实测图片解码/可见性；B 表示 action 为文本，不表示任务可以删掉参考图。若模型/relay 不接受图片，本轮不能默默改成只有文字的 RobotGen 正式任务。生成后的 CAD 渲染、屏幕回看属于另一个待预登记的 observation 能力；bash-only 默认不会把本地图片自动回传给模型。

### 首次提交与标准反馈

`DefaultAgent.run` 遇到 exit 消息即返回；它没有 RobotGen `first/`、最多两轮反馈或“提交候选后等待评测方”的语义。重复调用 run 会清空 messages，却不重置所有计数/起始时间，不能拿它当反馈续跑机制。`InteractiveAgent._check_for_new_task_or_submit` 说明上游已有提交拦截/用户反馈扩展点，但交互 CLI 还允许人工命令与上调限额，不宜直接作为实验入口。

**provisional recommendation：** 在 DefaultAgent/Environment 已有扩展点加一个 RobotGen 提交候选钩子，仍由原 run 循环推进。首次 sentinel 触发写入暂停/一致性快照，host 将完整首次设计存到模型不可写的 `first/`；仅把预登记公开检查的失败项、错误日志、剩余时间作为反馈。需要修复且未耗尽反馈/总预算时，将候选提交作为普通 observation 并追加反馈后继续；不生成最终 exit，不重建 Agent，不恢复预算。最终候选或反馈结束时才透传 Submitted。

native 路径必须闭合正在等待的 tool_call_id；不能在悬空工具调用后直接插入 user 反馈。钩子需要保留真实执行输出，不能捏造工具成功记录。`first/` 不能简单放入可写 bind mount 后 chmod 来冒充不可变；有后台写进程时应通过执行平台暂停并验证快照一致性。这些细节及反馈钩子规模均 **future validation required**；若尚未实现，只能运行明确标注无反馈的兼容性 smoke，不能宣称已实现完整 RobotGen pilot。

## 5. bash-only Tool Model

| RobotGen 操作 | 同一 bash + 镜像内 CLI 能否覆盖 |
|---|---|
| 读取输入、列目录、检查文件/哈希 | 可以；常规 shell/Python，无需 filesystem agent tool |
| 写 Python、修改 CAD/控制源码 | 可以；heredoc/编辑命令等，无需 run_python tool |
| CADQuery/其他 CAD CLI、STEP/STL 导出 | 可以承载；依赖镜像中真实可用的库/二进制，不由 parser 保证导出正确 |
| Python、MJCF/URDF 构建、MuJoCo/debug | 可以承载；headless 依赖、CPU/GPU、GL 后端须实测 |
| 已有生成代码 | 可以执行本 attempt 模型刚生成的代码；现有 Gorilla8 解答源码不在公开输入内，不能因“可复用”而泄露给模型 |
| 文件统计、渲染文件生成 | 可以；生成 PNG 并不自动赋予视觉观察能力 |

`requirements.txt` 与 `inputs/environment.lock.txt` 给出了 CADQuery 2.7.0、MuJoCo 3.13.0 等环境来源，根 README 还列 EGL/OpenGL、ffmpeg/ffprobe。它们是镜像设计依据，不是现成 Docker image 或跨平台可运行证明。模型可以编写所需脚本，但禁止生成时联网补依赖，环境预装应在实验开始前完成。

没有源码证据要求新增 `run_cad`、`run_python`、`filesystem` 专用 agent API。确需 RobotGen adapter 的是**公开图像绑定、标准反馈与提交文件/元数据交接**，不是再造工具协议。如果将来要回传渲染图，先验证上游 multimodal observation 是否足够，再决定最小文件到消息桥接；不在本轮实现。

## 6. 最小 Sandbox 方案

**confirmed capability：** `DockerEnvironmentConfig` 支持 image、cwd、env、forward_env、run_args、interpreter、timeout、container_timeout、pull_timeout、executable。它拼接 `docker run -d -w ... <run_args> <image> sleep ...`；action 用 `docker exec -w ... bash -lc <command>`，每次独立 subshell。没有内建 RobotGen 挂载清单、GPU 公平性、网络 allowlist、文件配额或只读策略；通过 run_args 和运行平台配置实现。

**provisional recommendation：** 所有 attempt 使用同一 Linux image digest、固定 cwd `/work`，仅布局实例路径不同：

| 区域 | 可见性 / 权限 |
|---|---|
| `/inputs` | 只读挂载同一 verified inputs 快照 |
| `/work` | 本 attempt 私有可写工作区；建立稳定只读引用以便 cwd 下访问 TASK_SPEC.md、assets/ 等 PROMPT 相对路径 |
| `/work/submission` | 本 attempt 唯一交付目录，模型可写设计文件 |
| host attempt root 的 logs、first、权威 submission.json | 不挂载给模型写；由 host 封存/维护，最终交付与 existing attempts 布局对应 |
| benchmark、隐藏资料、仓库 .git、其他模型/历史设计 | 不挂载；镜像构建上下文也不得夹带原答案 |

CPU cores/cpuset、memory、pids、线程变量、磁盘配额、UID/GID、临时目录大小必须共同冻结。建议非 root、只读 rootfs、明确 tmpfs/可写区、丢弃不需要的 capabilities；不得挂 host Docker socket、host home 或广泛共享目录。`run_args` 可以表达 Docker 的网络/资源/挂载参数，但其生效与 Docker/host 平台支持必须另测。本轮不选择未讨论过的具体 CPU/内存/step 数字。

GPU 不能由各模型自行开关。先验证 CPU/headless 是否满足共同任务；确需 GPU 时对所有模型分配相同设备/显存与并发条件，记录驱动和 GL backend。共享一张繁忙 GPU 会影响 3600 秒预算，不能仅靠 image 一样就称资源等价。

### `disabled_except_model_service` 的具体解释

模型调用在 host 的 LiteLLM 层，bash 在 container。因此可将 **container 设为 `--network=none`**，全部生成依赖与公开输入预先就绪；host 仅允许访问已指定模型服务（及该访问所必需的网络基础设施）。这是对现有预算策略的部署解释，不更改 protocol 字符串。container 不需要模型 API 例外，也不需要凭据。

`forward_env=[]`，env 仅含明确非秘密运行参数；不能把 SMART_AGI_API_KEY/OPENAI_API_KEY 注入容器。host 需限制模型服务之外的出网、禁止 fallback endpoint，并核验 LiteLLM 动态下载/遥测/价格表等行为不会造成未登记的外联。`--network=none` 单独不能管住 host worker；本机 Windows Docker/未来 Linux runner 的实际隔离都属 **future validation required**。

### 截止与清理缺口

上游 command timeout 仅包住 host `subprocess.run(docker exec ...)`；不能据此保证容器内子进程/后台任务全部被杀。`cleanup()` 用带 `timeout` 的 POSIX shell 后台命令 stop/rm，依赖平台且不等待清理完成；`__del__` 不是可靠封存屏障。`container_timeout` 默认 2h 只是 `sleep` 生命周期，也不是 RobotGen 3600 秒生成 deadline。

未来 launcher 应利用执行平台的单 attempt deadline supervision：到截止同步停止/确认容器不再写，停止 host generation worker，再封存并记录实际停止时间。只操作自己创建的容器，不扩展为通用 sandbox 服务。优先复用已有作业监管能力；若目标平台没有，launcher 内补少量 standard subprocess/Docker lifecycle glue。容器退出、超时和 snapshot 的一致性验证是真实 generation pilot 的前置条件。

## 7. Limits：可直接映射与缺口

| RobotGen 约束 | confirmed capability | 集成判断 |
|---|---|---|
| step limit（现协议未定） | Agent `step_limit`，0 不限；query 前比较 n_calls，每次调用先加 1，格式失败也占一次 | 支持；未来统一预登记数值/计数含义。不是 max_feedback_rounds，也不是 HTTP 请求数或 bash 命令数 |
| wall_time_s=3600 草案 | `wall_time_limit_seconds`，0 不限；从 Agent 构造时的 `_start_time` 计时，query 前用整数 elapsed 检查 | 名称可映射，但只是轮间软检查。API 等待、重试、一批 actions 期间不检查，超时后仍可能收到 Submitted；需 host 权威 deadline，超时优先于迟到成功 |
| cost（当前无预算字段） | cost_limit 默认 3.0；query 前检查累计 cost，0 关闭；单次响应可超过限额后才在下一轮被发现 | 不得把上游默认 $3 偷偷带入实验。建议显式 0，或另行预登记共同 cap；不是精确预付费硬上限 |
| command timeout（待定） | Docker timeout 默认 30s，execute 接受 timeout override；异常返回 returncode=-1 和 exception_info | 需按 CAD/仿真负载统一冻结，并约束剩余总时间；不是 generation TIMEOUT 的充分条件 |
| API timeout=600s 候选 | `model_kwargs` 可传 timeout，LiteLLM 承担 transport | 由现有 timeout_s 翻译；实际请求应受剩余 deadline 约束，不能调用末尾再增加 600s |
| max_retries=0 | 上游 `utils/retry.py` 默认 stop_after_attempt=10，指数等待 4–60 秒；部分异常不重试 | 将 `MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT=1`，并显式关闭 LiteLLM/SDK 内层 retries；验证实际网络尝试数，不能只改一层 |
| token usage | 原生 response.model_dump 保存 provider usage（若有），没有统一 Agent token 累加器 | 薄映射 input/output/reasoning/cache usage，保留原始口径；失败/中断可能未知，不能补零 |
| total token limit=null | 未在上述 Agent/Model 中找到一等 total-token budget；max_tokens 是单响应参数 | 当前不阻塞 pilot。若未来要求硬 total cap，重新审议上游扩展/协议，不现在建通用 token framework |
| feedback≤2、human edits=0 | DefaultAgent 没有对应计数/快照 | RobotGen 提交候选钩子维护，不用 step_limit 替代 |

`TimeExceeded` 继承 `LimitsExceeded`；映射时先识别 TimeExceeded。上游先检查 step/cost 再检查 time，若同时耗尽可能报 LimitsExceeded，因此 RobotGen 还须以 host deadline 记录裁定 TIMEOUT。构造 Agent 到首次 query 之间的时间也在上游计时内；未来明确 generation 开始点，先完成镜像准备，再开始包含模型、工具、标准反馈等待的同一计时。排队/拉镜像与独立最终评分单独记录，不偷偷改变各槽位可用生成时间。

LiteLLM 官方资料支持 `num_retries` 等请求可靠性参数；使用哪一参数实际关闭内层 SDK 重试，需对未来锁定依赖用失败注入证明，不能从上游 tenacity 的 n_calls 推导网络次数。[LiteLLM retries](https://docs.litellm.ai/docs/completion/reliable_completions)

全局 `GLOBAL_MODEL_STATS` 还读取 `MSWEA_GLOBAL_COST_LIMIT` / `MSWEA_GLOBAL_CALL_LIMIT`，是进程级状态。建议一 attempt 一 worker、显式排除未登记全局上限；否则之前的模型调用可能改变后续样本的预算。无隐藏 retry/fallback；若之后预登记重试，等待、费用和失败仍属于本 attempt。

## 8. 原生 trajectory、日志与 provenance

**confirmed capability：** `DefaultAgent.serialize/save` 递归合并 agent/model/environment 数据，格式为 `trajectory_format=mini-swe-agent-1.1`；每个 step 的 finally 会 save（须设置 output_path），未捕获 Exception 会记录退出异常后再次抛出。文件用 `Path.write_text` 整体写入，不是 append-only/原子事务日志。

| 所需证据 | 原生来源与可靠边界 |
|---|---|
| model identity | `info.config.model.model_name` / model_type；chat response 的 model/id（provider 返回时）。配置名称不证明 relay 后端实际精确版本 |
| messages | `messages` 包含初始模板、assistant、observations、错误与 exit；不是每个 HTTP wire request 的完全副本 |
| actions | assistant `extra.actions`；native 含 tool_call_id，text 为 command |
| bash outputs | observation `extra.raw_output/returncode/exception_info`；展示 content 可被模板裁剪，raw_output 通常仍完整 |
| timestamps | 成功模型响应和普通 observation 的 `extra.timestamp`；不是每个 request start、system、exit 都有时间戳 |
| API calls | `info.model_stats.api_calls` 是 Agent query 次数，包括进入 model.query 后失败的调用；不枚举 tenacity/SDK 的内部 HTTP attempts |
| cost | 每响应 extra.cost、instance_cost，来自 LiteLLM 价格计算；不是 relay 账单保证 |
| usage/tokens | chat `extra.response.usage`（成功及 FormatError 响应），Responses 路线保存 response 本体；字段依赖 provider，不保证所有失败都有 usage |
| exit status | `info.exit_status/submission`、exit message；hard kill 可没有最终 exit |
| environment | info.config.environment 与 environment_type；记录请求配置，不自动记录 image resolved digest、真实硬件、内核/驱动或容器 ID |
| version | info.mini_version=2.4.6；没有上游 commit、完整依赖 lock |

重要缺口不能省略：

- `_prepare_messages_for_api` 移除 extra，并可能重排 Anthropic thinking blocks/加 cache markers，因此轨迹中的消息不总是逐字等于实际发送 payload。只有返回或错误落盘的可见 reasoning 才有证据，不要求隐藏思维链。
- FormatError 保存响应和已算 cost，但某些早于该分支的失败（cost calculation / global stats 异常）仍可能使已返回 response 未进入 trajectory；不能保证“每笔账单都有对应响应”。
- `DefaultAgent.execute_actions` 用列表推导收集 outputs；若多 actions 中某个抛 Submitted，先前已执行 actions 的 observations 可能未加入 messages，提交 sentinel 自身也由 exit 替代普通 observation。B 的单 action 降低部分输出丢失面；A 的多 action 完整存档必须额外验收，必要时通过小 hook 保留而非重写 parser/循环。
- cost_tracking=default 遇到未知价格或非正 cost 会抛错；`ignore_errors` 则回填 0。未知/缺失 cost 时 RobotGen `actual_cost` 必须 null 并解释，不能把内部 0 当免费。经已审定 registry 得到的估算也应标明估算来源。

**provisional recommendation：** 以原生 `.traj.json` 为唯一完整会话格式；host logs 留在模型不可写路径，最终按现有 submission.logs 引用。薄 provenance/manifest 只补：experiment_id、slot/phase/attempt/session、requested/resolved identity 与可信来源、RobotGen commit、mini commit、依赖锁摘要、prompt/input-manifest/scaffold/config hash、image digest、资源/网络策略、开始/截止/实际停止时间、termination reason、反馈计数、first/final 文件哈希和 trajectory 引用/哈希。不要在其中重复整套 messages/actions。

为满足请求开始/失败审计，可在上游 query/save 扩展点及可用的 LiteLLM callbacks 增加少量计时/调用关联元数据；先保持 retries=0，使关系可审计。不能声称原生轨迹已有每次 HTTP retry。若硬停止造成未完成响应，保留原生最后完整检查点和 supervisor 终态记录，注明缺失区间/未知费用；不得补造终态模型响应。save 钩子只做脱敏和原生结构原子落盘，避免强杀时截断唯一轨迹，不引入第二种 transcript。

### 密钥边界

`LitellmModel.serialize` 会保存完整 model config，`get_template_vars` 也暴露 config；Docker serialization 会保存 env/forward_env 参数。因此把 api_key 放进 model_kwargs 后只在“最终导出”脱敏太迟：中途 save 已泄露。未来 launcher 应按 API_CONFIG 的优先级取得秘密，只放 host worker 内所需 provider 环境/运行时认证边界，非秘密 config 不含 key、认证头或 secret URL。若调用必须显式传 key，应经运行时 query 参数传入并在每次持久化前脱敏。异常、SDK 日志与 response 也要用合成 secret fixture 验证；不 dump 实际 api_config，也不允许容器继承 host credentials。

## 9. OpenAI-compatible relay 配置与 smoke test

当前 RobotGen example 指定 provider=`smart_agi_gateway`、base_url=`https://big-model.smart-agi.com`、api_path=`/v1/chat/completions`、api_format=`openai_chat_completions`、endpoint_verified=false，model/key 空。这里的 provider 是实验来源标签，**不能未经翻译当作 LiteLLM provider 名**。

| 现有 RobotGen 字段 | 最小绑定方式 / 边界 |
|---|---|
| model | 对已核验 OpenAI-compatible chat endpoint 用 `model_name=openai/<精确服务端ID>`，或经验证的 custom_llm_provider 配置；保留服务端 ID 与路由前缀的区别 |
| provider | 保留为 submission.model_provider / provenance，核对 protocol 同槽位身份，不猜测真实后端 |
| base_url + api_path | 校验 API 模式；本候选的 `model_kwargs.api_base` 应为 `https://big-model.smart-agi.com/v1`，由 SDK 追加 `/chat/completions`，只出现一个 `/v1`；不是填完整 endpoint |
| api_key_env / api_key | 非空指定环境变量优先、否则配置值；两者都空拒绝启动。转换到 LiteLLM 所需认证边界，秘密不进入序列化 config |
| request.* | stream=false；timeout_s 翻译 timeout；temperature/top_p/max_tokens/seed 的 null 省略；非空 extra_body 明确校验和记录 |
| request.max_retries | 同时控制外层 mini 与内层 transport，见第 7 节；不接受隐式多次尝试 |
| paths.* | 相对 api_config 所在目录解析，再核验允许路径、输入快照与 attempt 身份；不把实际 api_config 挂进容器 |

上游 `model_kwargs` 透传能力及 `docs/models/local_models.md` 支持 api_base/custom_llm_provider；LiteLLM 官方也描述 openai/ 前缀、api_base 和认证。**直接可配置不等于当前中转站已兼容。** 不把 SDK 的 base_url 名称与 mini 顶层字段混用，不假定任意自定义 api_path 都能由修改 api_base 自动实现。[LiteLLM OpenAI-compatible endpoints](https://docs.litellm.ai/docs/providers/openai_compatible)

### Chat Completions 与 Responses 必须显式区分

`LitellmModel` / `LitellmTextbasedModel` 调用 `litellm.completion`。另有 `LitellmResponseModel`，其 `_query` 调用 `litellm.responses(input=..., tools=[BASH_TOOL_RESPONSE_API])`，使用不同工具事件格式和历史展开规则。实际 class alias 是 `litellm_response`；本次上游 `docs/models/quickstart.md` 出现的 `litellm_response_toolcall` 不在当前 mapping 中，不能照抄该示例。

OpenAI 官方也区分 `/v1/chat/completions` 的 messages 与 `/v1/responses` 的 typed output/items/function 格式；不能仅改 URL 就认为协议转换完成。本轮不因官方推荐 Responses 而替 RobotGen 当前候选 endpoint 做迁移决议。[OpenAI API migration](https://developers.openai.com/api/docs/guides/migrate-to-responses)

**future validation required：第一轮 endpoint smoke 清单（本轮不执行）**

1. 每个精确 ID 的认证、URL 拼接、provider 路由、返回 identity；不接受槽位名、静默 fallback 或未披露模型别名漂移。
2. 同一 system/user scaffold 的多轮 text completion；非 ASCII、长脚本、B fence 提取，空 content、截断及多个 action 的错误行为。
3. 独立 A 组测试 bash schema、tool_call_id/arguments、tool-result 往返、无工具/未知工具、多 action 和结束标记；不能只测一次 tools 请求成功。
4. 同一参考图 data URL 的实际解码/可见性；确认 relay 不丢图片，记录消息证据和图片哈希。
5. 请求参数支持与实际生效：temperature/top_p/max_tokens/seed/reasoning 设置/extra_body/stream；显式 `drop_params=false`，不支持则报告。不能通过 silently drop 伪装设置一致。
6. timeout、429/5xx/认证/上下文超限的失败路径；用 fixture/本地故障服务验证 retries=0 与无 fallback，真实 endpoint 验证必要路径。确认不同层重试不会叠加。
7. response usage 的 input/output/cache/reasoning、cost registry 或计费来源、失败缺失值及响应时间。缺价格不能阻断整个兼容性研究，但必须预先决定允许 null 的记录方式。
8. 如另测 Responses，核验其独立路径、工具事件和历史；不得将其结果混入 Chat Completions 同 scaffold 组。
9. 同一 Docker bash 闭环：写/读一个合成文件、返回非零退出码、超时、最终 sentinel、保存 trajectory；检查无秘密外泄与容器无网。此处无需生成机器人。

第一轮 smoke 成功后，才做 CAD/MuJoCo 环境验证及 RobotGen generation pilot。此清单不是已通过的测试报告。

## 10. Batch experiments

**confirmed capability：** 上游 `run/benchmarks/swebench.py` 使用 datasets.load_dataset、problem_statement/instance_id、SWE-bench image naming、ThreadPoolExecutor、ProgressTrackingAgent 和 preds.json 的 model_patch；支持 filter/slice/shuffle、跳过已有结果与 redo。它是 SWE-bench 批量 generation runner，不是 RobotGen attempt 调度器，也不应把它误称为已经集成 RobotGen scoring。

其 shuffle 使用自己的 seed，redo 会移除已有 prediction/trajectory；这些语义不符合 RobotGen 的 `records/attempts.csv`、schedule_seed、失败样本保留和不可覆盖证据约束。不要把 RobotGen submission 假装成 patch 或引入 SWE dataset/evaluation pipeline。上游包元数据本身仍列 datasets 为依赖；“不使用 SWE runner”不等于宣称安装该包没有这一依赖。

**provisional recommendation：** RobotGen launcher 按既有 attempts 表调度、每 attempt 一个独立 worker/model/env/session，先顺序执行，以免资源竞争污染 wall-time。只调用上游 primitives；不写通用任务队列、不复制上游 batch 实现。未来并发必须预登记相同资源份额与 endpoint 限流策略，保留全部尝试，绝不将自动重试当成新 replicate。

## 11. SubmissionAdapter 与 scoring 交接

最薄桥接顺序：核对配置/哈希并启动 → 保存首次与反馈过程 → 判定权威 generation 终态 → 停止写入并封存 → 由 host 写既有 metadata → 调用 validate → 保留 intake 独立结果 → 满足评测前置条件后交接现有 benchmark。

| 上游/运行事件 | 既有 submission.status | 处理 |
|---|---|---|
| 最终 Submitted，在 deadline 内收到且产物可收集 | COMPLETED | 仅代表正常交付到验收；设计缺项让 intake 判 INVALID，不人工补设计，也不虚构工程成功 |
| step/cost LimitsExceeded、RepeatedFormatError | GENERATION_FAILED | 记录具体原因/计数、保留部分文件和日志；若 host deadline 已耗尽则 TIMEOUT 优先 |
| TimeExceeded / host 硬 deadline | TIMEOUT | 即使迟到响应或有部分产物也不能改成成功；记录实际停止与超限区间 |
| provider/认证/参数/上下文错误在已开始的调用中不可恢复 | GENERATION_FAILED | 保存异常类型及可得证据，费用未知就 null；无免费换模型 |
| 单条命令 timeout / nonzero | 不立即固定最终 status | 普通 observation，预算允许时让同一 Agent 决定修复；总 deadline 耗尽才 TIMEOUT |
| 容器或 host worker 意外崩溃、非预算取消 | GENERATION_FAILED（已启动） | supervisor 补事实终态，原生轨迹可能不完整；不假造正常 exit |
| 启动前缺 key/model、hash mismatch、环境未就绪 | NOT_STARTED | 拒绝请求并留 preflight 记录；不是已执行模型失败样本 |

不要直接用进程 exit code 或上游 submission 字符串作为 RobotGen status。正常停止后没有完整设计，也应保留生成与 intake 两个事实；能记录的失败仍计入已执行尝试，不回滚成 NOT_STARTED。

最终设计文件从私有 `/work/submission` 保持相对路径复制到对应既有 attempt root，模型提交的 design_manifest 保持原意。必要路径调整必须记录，不能代写缺失 CAD、控制器、rebuild_command 或验证证据。host 权威填写 model_provider/model_exact_version/invocation_mode/session_id、elapsed、feedback、human_edit_minutes、usage/cost/seed 及 unknown_fields_reason；不能相信模型自报身份。模型生成的 submission.json 如存在只作为非权威产物，不能覆盖 host 事实或原生日志。

沿用已有八关节/四接触/机壳与 horn 接口映射、units、打印件及文件契约；不强制 Gorilla8 名称。所有入包路径须相对 root、不越界、不跟随外部符号链接；复制前也检查，不能先读到 host 任意文件后才指望 validate 拒绝。first/、logs、provenance 由 host 添加后通过现有 logs 引用，不增加 submission schema。

交接命令保持：

```bash
python3 model_comparison/tools/experiment.py validate <submission-root>
```

读取输出的 `intake_status`：COMPLETED 合约完整时为 `FILE_CONTRACT_ACCEPTED`；GENERATION_FAILED/TIMEOUT 元数据日志完整时为 `FAILED_ATTEMPT_RECORDED`；错误为 INVALID。前两者 CLI 都可能返回 0。始终 `engineering_evaluation=NOT_RUN`、`quality_score=null`，验收不运行 rebuild_command，也不核实日志真实性。

**FILE_CONTRACT_ACCEPTED 不代表工程质量通过。Harness 不计算 RobotGen engineering score。** 评分桥只把封存 root、manifest/hash、版本引用交给独立评测流程；鉴于第 1 节固定布局限制，不自动对任意新设计运行旧 run_digital 并发布排名。正式比较还需审查身份、预算、全部重复及 evaluator errors，不能只依赖 compare.py。

## 12. 最小新增代码预算（未来，不在本轮实现）

下表是便于审阅维护面的估计，不是承诺精确行数，也不是生成新框架的许可。

| 未来组件 | 估算规模 | 内容与避免的重复 |
|---|---:|---|
| 一个 RobotGen mini-swe YAML config | 约 80–140 行 | 完整共同 prompt/action/observation、显式类、策略；不复制 SWE prompt |
| 一个 run adapter / launcher | 约 160–260 行 Python | 现有 api_config/protocol 绑定、preflight、worker 启动、primitives 组合、退出映射；不写 transport/AgentLoop |
| 一个 workspace/submission bridge | 约 140–220 行 Python | 挂载清单、输入/产物/first 哈希与封存、既有 metadata/intake/评分交接 |
| 必要集成钩子，放在上述两个模块内 | 另约 60–120 行 Python | 标准反馈、deadline/停止确认、原生 save 脱敏/原子存储和少量时序证据；不单独建通用库 |
| RobotGen generation image 定义 | 约 30–80 行配置 | 预装 CAD/仿真及 headless 系统依赖；引用锁定来源，镜像无既有答案 |
| 必要测试 | 约 200–350 行 | 配置、失败/预算、隔离/封存、脱敏/trajectory、submission 状态的确定性 fixture 与少量容器集成测试 |

目标约 **360–600 行 RobotGen runtime glue**，外加一个配置、镜像定义和必要测试；不是“只有几十行”就能满足全部实验约束。若运行平台已有 hard deadline / 同步清理，可接近下界。之所以仍要小 hook：上游不认识 RobotGen 反馈/first/契约，且源码明确缺少硬截止、原子脱敏保存和完整请求时序。若实作超出范围，先检查是否在重复上游能力；确实需要通用改进时优先向上游提出独立变更，不复制/维护 fork loop。

未来测试重点：同一模型类/scaffold/图像绑定；null 参数省略与 key 优先级；不支持参数拒绝；零重试；正常/格式失败/provider failure/soft 与 hard timeout；迟到 Submitted；总预算跨反馈不重置；后台写进程停止；input/benchmark/其他 attempt/credentials 隔离；native tool history 闭合与部分输出；secret 脱敏；原生 trajectory 完整检查点；既有 intake 三种结果。合成文件不冒称 robot 验证。真实 endpoint 与 CAD/MuJoCo 环境检查独立进行。

## 13. 风险、未决问题与放行门槛

| 风险 / 未决问题 | 当前状态 | 下一阶段需取得的证据 |
|---|---|---|
| upstream version pinning | 版本字符串与 tag/HEAD 不同 | pin 上述 SHA 并锁 LiteLLM/SDK/镜像依赖；升级必须重验 action/trajectory/limits |
| native vs text | B 仅 provisional recommendation | 三槽位同协议 smoke；A 独立组验证；正式方案另行决议 |
| relay compatibility / 精确模型身份 | endpoint_verified=false、model 空 | 认证/路由/身份、文本/工具/图片多轮证据，无隐藏 fallback |
| CAD/MuJoCo Docker 环境 | 尚无已验证 image | 锁定 image digest，离线 CAD 导出、MuJoCo/headless/资源测试；不安装到 generation session 补救 |
| GPU access | 未决定需求与分配 | CPU 可行性或相同 GPU/driver/资源与并发策略 |
| network isolation | 设计可 container 无网、host 调模型 | container/host 双边实际出网测试，image 无 secret/历史答案 |
| hard wall-time / API latency | 上游只有 query 前软检查 | 故障注入证明 API 等待和容器后台进程可截止；慢 provider 不补时，记录实际 latency |
| retry / unsupported params | 上游 10 attempts 和示例 drop_params=true 与项目要求冲突 | 锁定依赖下显式零重试、禁 silent dropping；记录能力不等价 |
| total token accounting | 无一等总 token cap，协议为 null | 不阻塞 pilot；记录 provider usage 与未知项，不推导等算力 |
| usage/cost 可靠性 | relay 价格/失败 usage/已返回响应丢失风险 | 区分估算与账单、未知写 null、失败日志保留；未验证不能当成本准确对照 |
| context window 差异 | DefaultAgent 不提供统一自动压缩策略 | 冻结共同历史/输出裁剪规则，记录各模型容量；超窗明确失败，不偷偷给某模型摘要/换窗口 |
| 图片可见性 | 默认 regex 禁用，文件挂载不够 | 同一图片真实送达全部模型，必要多模态能力 smoke |
| 反馈 / first / native partial output | 上游无 RobotGen 原生契约 | 小 hook fixture + snapshot/闭合 tool-call/预算不刷新验证 |
| 日志秘密与 crash 一致性 | 原生 config 全量序列化、write_text 非原子 | 合成 secret、失败/强杀 fixture；持久化前脱敏、完整检查点与停止确认 |
| 平台与输入 hash | 本机 Windows，预期执行环境 Linux | 固定 checkout/字节/路径规则；`manifest()` 使用 str(relative_path)，需验证路径分隔符与换行对现有冻结清单的影响，失败即 preflight 阻断 |
| 独立工程适配与 formal 放行 | ADAPTER_AUDIT OPEN、formal_scoring_ready=false | 由 benchmark 独立工作完成，不能由本路线宣布解决 |

当前仍阻塞**真实 RobotGen generation pilot**的是：精确模型与端点配置/共同 action 和图像可见性未核验、可用 CAD/MuJoCo image 与资源/隔离未验证、硬截止及反馈/封存/证据桥尚未实现。token_limit=null 本身不阻塞；通用工程评分适配阻塞正式评分，不应混作简单 endpoint smoke 的前置条件。

## 14. 实施顺序、路线独立与回滚

本计划不决定 mini-swe-agent 与 Inspect 的最终胜负；两份 integration plan 完成后再独立比较。历史 AgentLoop spike 不作为运行依赖，不迁移其 loop/provider/parser。后续建议按以下小阶段独立审阅：

1. 固定 upstream/依赖与候选 action/scaffold，补无 API 的配置和状态 fixture；完成两个薄模块所需 hook 设计。
2. 用确定性上游 test model/fixture 验证工作区、失败、反馈、硬截止和原生证据，不先生成机器人。
3. 在独立验证环境完成 endpoint smoke 与 CAD/MuJoCo 镜像/网络/资源检查；正式 pilot 前共同冻结设置和新输入版本。
4. 按既有 pilot attempts 生成、封存、validate；不输出未经适配的工程排名。
5. 独立 benchmark 适配/冻结达到条件后，才连接评分与 comparison。

本轮只新增本文。校验为 `git diff --check`、两组既有 pytest，以及 baseline...HEAD 仅本文件；不为本机缺依赖/权限改代码或装依赖。以一个 `docs: plan mini-swe-agent harness integration` commit 推送 `design/mini-swe-harness`，不 merge。审阅 repair 仅改本文；整轮废弃可 revert 该单文档 commit，runtime 与 benchmark 不受影响。

## 源码证据索引

RobotGen 引用均相对本目录及指定 baseline：已读取 [HARNESS_DESIGN.md](HARNESS_DESIGN.md)、[PROMPT.md](PROMPT.md)、[TASK_SPEC.md](TASK_SPEC.md)、[SUBMISSION_SPEC.md](SUBMISSION_SPEC.md)、[EXPERIMENT_PROTOCOL.md](EXPERIMENT_PROTOCOL.md)、[API_CONFIG.md](API_CONFIG.md)、[protocol.json](protocol.json)、[experiment.py](tools/experiment.py)、[templates](templates)、[test_intake.py](tests/test_intake.py)、[ADAPTER_AUDIT.md](ADAPTER_AUDIT.md)、本目录/根 README、requirements/环境锁以及上文列出的 benchmark 入口、评分函数与两组现有测试源码。没有以旧 spike 或 Inspect 文件补充事实。

下列上游链接全部固定到本次读取的 SHA，正文函数/配置名对应这些文件：

- [Agent loop / limits / serialize](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/agents/default.py)、[exceptions](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/exceptions.py)、[interactive 扩展点](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/agents/interactive.py)。
- [Model selection / global stats](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/models/__init__.py)、[LitellmModel](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/models/litellm_model.py)、[LitellmTextbasedModel](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/models/litellm_textbased_model.py)、[LitellmResponseModel](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/models/litellm_response_model.py)。
- [native actions](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/models/utils/actions_toolcall.py)、[text actions](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/models/utils/actions_text.py)、[retry](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/models/utils/retry.py)、[multimodal](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/models/utils/openai_multimodal.py)。
- [DockerEnvironment](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/environments/docker.py)、[mini CLI](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/run/mini.py)、[config loader](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/config/__init__.py)。
- [mini.yaml](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/config/mini.yaml)、[mini_textbased.yaml](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/config/mini_textbased.yaml)、[default.yaml](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/config/default.yaml)、[swebench.yaml](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/config/benchmarks/swebench.yaml)。
- [SWE-bench batch runner](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/run/benchmarks/swebench.py)、[ProgressTrackingAgent](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/run/benchmarks/utils/common.py)。
- [package/version/global config](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/__init__.py)、[pyproject.toml](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/pyproject.toml)、[local model 配置](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/docs/models/local_models.md)、[quickstart 配置示例](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/docs/models/quickstart.md)。
- 辅助核对：[wall-time 测试](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/tests/agents/test_default.py) 在 1s 限额下执行 sleep 2 后才退出，支持“轮间软检查”的判断；[FormatError 响应留存测试](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/tests/models/test_format_error_response_persistence.py)。本轮只读取这些上游测试，未安装依赖或运行它们。
