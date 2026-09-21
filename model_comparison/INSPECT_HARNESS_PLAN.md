# RobotGen Inspect Harness integration plan

## 1. Why Inspect：决定与依据

采用 Inspect AI 承担生成阶段的通用运行设施；RobotGen 只定义任务、环境及现有提交/评分的适配边界。第一版使用同一个 `inspect_ai.agent.react()`，不选 deepagent，不实现另一套 agent loop。研究变量是 model，不是 agent scaffold。

本文是 compatibility / integration design，不是可运行实现，也不表示 smart-agi 或 RobotGen 工程链路已验证。本轮仅新增本文；不安装依赖、不调用模型、不读取或使用 API key，不修改代码、requirements、benchmark、tests、protocol、Prompt、submission schema 或 HARNESS_DESIGN。

核对日期：2026-09-21。RobotGen 基线为 `f0a88217122b80b5d8fab32945d78df8645effc3`。Inspect 官方仓库当日检出的正式标签为 `0.3.266`，对应 `ec4dfc6953784dc45b79de3147530c89868c6e26`；以下源码链接固定到该提交。官网会滚动更新，未来 I1 必须锁定实际安装版本、依赖和工具支持产物，升级后重新验收，不能只记录 latest。

已核对根 README；model_comparison 下 HARNESS_DESIGN、PROMPT、TASK_SPEC、SUBMISSION_SPEC、EXPERIMENT_PROTOCOL、API_CONFIG、protocol.json、tools/experiment.py、三个 api_config/submission/design_manifest 模板；scripts/benchmark 和 tests/benchmark 的入口、依赖与回归检查。另读 ADAPTER_AUDIT、环境锁文件，并只读检查 `2d1bfc3` 原型，未以它为开发基线。

现状必须保留：protocol 为 `PILOT_DRAFT`、`formal_scoring_ready=false`，模型身份与环境尚未填全；模板 `endpoint_verified=false`。`experiment.py` 不调用 API，不执行重建，不评分。现有独立重建、几何探针、仿真及部分评分仍依赖 Gorilla8 布局/结构；接入 Inspect 不会自动完成工程泛化。

官方依据：[Task/API](https://inspect.aisi.org.uk/reference/inspect_ai.html)、[ReAct](https://inspect.aisi.org.uk/react-agent.html)、[标准工具](https://inspect.aisi.org.uk/tools-standard.html)、[limits](https://inspect.aisi.org.uk/setting-limits.html)、[sandbox](https://inspect.aisi.org.uk/sandboxing.html)、[providers](https://inspect.aisi.org.uk/providers.html)、[eval log](https://inspect.aisi.org.uk/eval-logs.html)、[eval sets](https://inspect.aisi.org.uk/eval-sets.html)。只使用 Inspect 官方文档和官方源码判断其 API；未用第三方教程推断。

## 2. 一一映射与目标架构

| 旧 Harness 概念 | Inspect 承担 | RobotGen 保留的边界 |
|---|---|---|
| RunSpec / Runner | Task、Sample、eval；需要时 eval_set | 读取已有协议、核对哈希/身份、按既有 attempts 计划传参；不建通用调度引擎 |
| AgentLoop | react；内部生成、续行、tool dispatch、submit | 冻结共同配置与系统指令 |
| ModelAdapter | get_model / Model / 内置 providers | 配置映射与能力准入；不写 HTTP client |
| ToolLayer | bash_session、text_editor，必要时 python | 预装领域软件；确有缺口才另提领域工具 |
| RunWorkspace | Inspect Docker sandbox，每 sample 独立实例 | 镜像、Compose 声明、公开输入和单 attempt 输出挂载 |
| EventLog | Inspect EvalLog / transcript / ModelEvent / ToolEvent 等 | 使用 metadata 绑定实验身份和哈希；不定义事件 schema |
| limits / timeout | Task/sample limits、GenerateConfig、标准工具 timeout | 选择预算值、解释终止状态；不实现计时/取消引擎 |
| usage accounting | ModelUsage、eval/sample 时间、Inspect model cost | 将已记录事实投影到 submission；未知仍为 null |
| repeated evaluation | datasets / samples、epochs、多模型 eval / eval_set | 保持 pilot/formal、尝试编号、既有随机顺序及统计单位 |
| SubmissionAdapter | 无 RobotGen 原生契约映射 | 收集产物、填写操作者元数据、调用 experiment.py validate |
| benchmark / comparison | 不由 Inspect 重新定义 | 现有 scripts/benchmark 评分；报告关联 Inspect 日志 |

```text
RobotGen frozen inputs + PROMPT.md + experiment protocol
                         |
                 RobotGen Inspect Task
                         |
                 Inspect shared react()
                 same prompt / tools / limits / sandbox
                         |
                 Inspect Model Provider
                    /    |    \
                model A  B    C
                    \    |    /
              isolated writable workspace per attempt
                         |
              generated STEP/STL/URDF/MJCF + source
                         |
              RobotGen submission adapter
                         |
               experiment.py validate
                         |
              existing benchmark -> comparison/report
```

## 3. 当前 API 与 agent/tool 决策

`inspect_ai.Task` 接受 dataset、solver（可直接传 Agent）、sandbox、config、cleanup、epochs 及六类 limits；scorer 可为 None。`inspect_ai.dataset.Sample` 接受 input（文本或 ChatMessage 列表）、id、metadata、files、setup、sandbox；target 默认空，不放参考答案或隐藏数据。`Sample.files` 只是复制文件，不保证只读。详见固定源码 [Task](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/_eval/task/task.py)、[Sample](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/dataset/_dataset.py)。

首版配置意图：Task.solver=react，Task.scorer=None；react 使用 `attempts=1`、`submit=True`、`compaction=None`、`truncation="disabled"`，不启用 refusal 重试、fallback、子 agent 或自动恢复。参数最终在 I1/I3 核验后共同冻结，不在本轮写 task。

react 默认加入 submit 工具；普通文字“完成”不等于终止，无工具调用时会追加续行消息。`prompt` 传字符串会与默认 agent 指令组合，不能把 PROMPT.md 哈希当作完整 system prompt 哈希。通过 `AgentPrompt` 明确共同 instructions、assistant_prompt、handoff_prompt、submit_prompt；保留必要的 submit 指引，记录实际展开后的 system/user prompt、续行文本、submit 名称/描述及哈希。PROMPT.md 原文作为统一用户任务，公开图片若以 ContentImage 注入则所有模型使用同一字节与 detail 策略；仅挂载 PNG 不代表模型实际看到了图像。图像能力不足不能静默变成纯文本任务。

`react(attempts=N)` 会依据 task 主 scorer 判断是否再提交，不等于 N 个独立设计，也不等于 protocol 的操作者反馈轮数。首版不让工程分驱动生成，不接 benchmark scorer。`inspect_ai.solver.generate(tool_calls="loop")` 也已实现工具循环，默认在无工具调用时结束；single/none 有不同 dispatch 行为。因此不能把 generate 当作只有一次 HTTP 调用而再包一个自写 while。首选 react 的显式 submit 和共同续行规则。详见 [react 源码](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/agent/_react.py)、[generate 源码](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/solver/_solver.py)。

| 标准工具 | 已核对行为 | 首版决定 |
|---|---|---|
| bash_session(*, timeout, wait_for_output, user, instance) | 持久 shell，支持 type/type_submit/read/interrupt/restart；可分次收取输出 | 主要 shell；统一用户、等待/输出策略，允许通过相同入口运行 CAD 与公开 debug |
| text_editor(timeout, user) | sandbox 内查看、创建、替换、插入、撤销文件；不是路径安全边界 | 直接复用，文件权限由容器落实 |
| python(timeout, user, sandbox) | sandbox 内单次 python3 脚本；不保留解释器状态 | 只有 pilot 证明需要才统一加入；shell 已能运行 Python |
| bash(timeout, user, sandbox, background) | 每次新 shell；支持并行，background 只改变工具说明 | 作为已核对的备选；不得按模型分别选择 bash 与 bash_session |

源码：[bash/python](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/tool/_tools/_execute.py)、[bash_session](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/tool/_tools/_bash_session.py)、[text_editor](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/tool/_tools/_text_editor.py)。当前 bash_session 的实际最小 timeout 是 wait_for_output + 180 秒；源码旁的“+5”注释已不符实现，不能抄注释设值。等待输出返回不表示后台构建已经结束；最终收尾必须验证写入已经停止。

第一版不需要 CAD-specific tool：预装 CadQuery/OCP、NumPy/SciPy、trimesh、python-fcl、MuJoCo、Pillow、绘图及 EGL/OpenGL/ffmpeg 等实际依赖，模型通过 shell/editor 生成脚本和产物。版本以已核对环境及构建验证冻结，不照抄未经验证的镜像。若后续确需图像查看，先评估 Inspect 标准 image 工具；仅在标准工具无法表达必要的 RobotGen 公共操作时另行说明、审阅最小领域工具，本轮不实现。

## 4. execution limits：直接配置，区分口径

| API | 当前含义 | RobotGen 选择/约束 |
|---|---|---|
| time_limit | 每 sample 墙钟限制 | 承接 protocol.budget.wall_time_s（草案 3600）；等待、模型调用和工具工作均计入生成阶段 |
| working_limit | 工作时间，扣除失败请求/重试及共享资源等待等时间 | 首版不启用为额外公平预算，不能替代墙钟限制；记录 working_time |
| turn_limit | 顶层 generate 产生 assistant message 的次数；重试/fallback 解决后记一次，cache hit 也算，compaction 不算 | I1/I3 统一确定上限；不同于旧原型“每次 respond 调用” |
| message_limit | 会话内所有消息，包括 system/user/assistant/tool；生成前和消息修改时检查 | 与 turn_limit 分别冻结；并行多工具会增加消息数 |
| token_limit | sample 累计 token；也支持 output 或公式口径 | 当前协议为 null；不强求不同 tokenizer 的 token 等额；不要与单次 max_tokens 混淆 |
| cost_limit | 用配置价格和 usage 计算的美元成本限制 | 需要所有涉及模型的成本数据；缺失会报错。首版无可信 gateway 定价则不用，不能填零价伪装受限 |

六类限制均为 Task / eval 正式参数，react 自身不接 `time_limit=`。limits 正常触发可以是 sample 提前结束而非 error，之后 Inspect 仍可能评分；必须查看 sample.limit / transcript，不能用 eval success 判定交付。token/cost 是生成边界上的检查，单次调用可能超出阈值，不宣称是服务端硬截断。依据 [limits 文档](https://inspect.aisi.org.uk/setting-limits.html)及固定 [limits 文档源码](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/docs/setting-limits.qmd)。

计时边界：当前 Inspect 在 sandbox 初始化之后启动 sample 的执行时钟；solver 结束后评分有独立计时，cleanup 也不是给模型追加预算。RobotGen 将输入核验、镜像准备视为 preflight；模型可开始工作到生成停止为生成窗口，最终 benchmark 在窗口外。EvalSample.total_time 还可能包含评分/收尾，不能未经核对直接写成 actual_elapsed_s；adapter 从 Inspect 原有时间/事件跨度提取生成窗口，同时保留 total_time/working_time 与准备、收尾口径。I1 要验证边界，不自写 stopwatch/timeout engine。依据 [sample runner](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/_eval/task/run.py)。

请求策略用 GenerateConfig.timeout / attempt_timeout / max_retries；前者涵盖整个逻辑请求，attempt_timeout 限一次尝试。现有 timeout_s=600、max_retries=0 是候选配置，不能假设 Inspect 默认也是零重试。OpenAI-compatible 还把额外 model args 传给 SDK：必须分别冻结 Inspect 重试和 SDK `max_retries`，验证都为预定值（初版均零），不增加自写重试器。client_timeout 是 transport 参数，也不替代 time_limit。工具 timeout 和后台进程退出行为在 I2 验收。源码 [GenerateConfig](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/model/_generate_config.py)。

## 5. Docker sandbox 方案

使用 `sandbox=("docker", <explicit compose path>)`，或正式 `SandboxEnvironmentSpec("docker", ComposeConfig(...))`。Inspect 管理启动、每 sample 实例、exec 和 teardown；RobotGen 只声明镜像/挂载/资源。自定义 Compose 会替换默认配置，必须显式 `network_mode: none`，不能继承默认断网的假设。模型 provider 在宿主 Inspect 进程访问服务，不从 agent 容器访问。依据 [Docker 官方配置说明](https://inspect.aisi.org.uk/sandboxing.html#sec-docker-configuration)及 [Docker 实现](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/util/_sandbox/docker/docker.py)。

| 区域 | 设计 |
|---|---|
| /inputs | 仅核验通过的公开 inputs 快照，host bind read-only；哈希与 records/input_manifest.json 一致 |
| /workspace | 仅当前 attempt 的独立空 host 目录 bind writable；working_dir 指向此处，产物在 submission/ |
| runtime | 非 root agent 用户，无 sudo；固定 CPU/RAM/PID/磁盘额度、线程数；固定镜像 digest 和工具支持版本 |
| evaluator | benchmark、tests、隐藏数据/种子、其他 attempts、Gorilla8 答案、.git、API 配置及日志都不挂载 |
| host provider | API key 仅进程环境；Compose 不引用 key、不 env_file、不继承宿主完整 environment |

禁止 privileged、host PID/network、Docker socket 和宿主父目录挂载；使用最小能力与 no-new-privileges，避免容器路径穿越映射到其他 attempt。可写临时目录与 Inspect 标准工具支持目录按官方需求配置；不要盲目把整个 root filesystem 改只读而破坏工具注入。Inspect bash_session/text_editor 需要工具支持程序，须在预备阶段取得并固定其版本/哈希，离线工具测试确认无运行时下载依赖。资源参数与宿主 OS/架构/渲染能力需实测一致；Docker 隔离能力不能仅凭配置文本宣布通过。

镜像只包含软件，不 COPY 整个仓库；公开仿真仅使用允许的库/模型自己的代码和公开用例，不把评分脚本包装成“debug”暴露。公共阈值和公开用例本来在 frozen inputs 中，不声称它们是秘密；真正隐藏集由 evaluator 另行托管。

优先采用单 attempt bind 输出以保留大体积 CAD 文件及异常退出时的部分产物。每次由 Inspect 完成容器收尾、确认没有 agent 进程继续写入后，evaluator 才读 workspace、安全复制并封存/哈希；日志保存在不可见宿主目录。后台构建、超时、取消、容器故障和磁盘耗尽均须验证；清理失败则隔离该 attempt，不能边写边验收或交给 benchmark。只使用 Inspect 的生命周期/cleanup 命令处理容器，不写 sandbox manager。

不依赖“eval 返回后从已删除容器读文件”。如以后改用容器内部存储，可通过 Task.cleanup(state) 在 sandbox context 退出前用官方 sandbox 文件 API 导出；cleanup 可能遇到容器故障，不能保证产物完整。read_file 默认大小限制也不适合无限大 STEP 文件。该替代方案必须另测，首版选择 bind 输出。

## 6. model provider 与 smart-agi 接入

优先 Inspect 原生 `openai-api/<gateway>/<model>`，不使用各厂商独立 agent runtime。当前源码按 service 名转大写并把连字符替换为下划线寻找环境变量；发往服务的 model 去掉 service 前缀。设计配置如下，均非本轮执行命令：

| 项目 | 候选值/映射 |
|---|---|
| Inspect model | `openai-api/smart-agi/<精确服务端 model ID>` |
| credential | Inspect/provider 进程环境 `SMART_AGI_API_KEY`；只记录变量名 |
| base URL | `SMART_AGI_BASE_URL=https://big-model.smart-agi.com/v1` |
| 协议 | model args `responses_api=False`、`emulate_tools=False`、`stream=False` |
| schema | `strict_tools=True` 是原生默认；以 I3 契约测试决定共同冻结值 |
| 采样参数 | 从已有配置白名单映射；null 表示不显式传值，同时记录 Inspect/provider 最终解析默认值 |
| 请求限制 | GenerateConfig 的 timeout/attempt_timeout/max_retries，另核对 SDK max_retries/client_timeout |

SDK 会追加 `/chat/completions`，base URL 只能含一个 `/v1`，不能把完整 api_path 再拼进去。RobotGen `provider=smart_agi_gateway` 是既有配置标签，不是 Inspect 注册 provider 名；最小配置适配只做此类映射与前置一致性校验。Inspect 的 `openai/` 与 `openai-api/` 有不同默认行为，不能互换推断。依据 [OpenAI-compatible 文档](https://inspect.aisi.org.uk/providers.html#openai-api)及 [OpenAICompatibleAPI](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/model/_providers/openai_compatible.py)。

新路线只接受环境变量认证；API_CONFIG 和示例曾允许 JSON api_key fallback，此路径不再采用。后续入口应拒绝非空 inline key，禁止把真实 api_config 复制到 inputs/workspace；本轮保留旧文件不修改。key 不得进入 Git、prompt、metadata、submission、transcript、工具环境、异常输出或日志；不传含密钥的 URL/extra_body/extra_headers，不 dump 环境变量或认证请求头。

不能宣称“用 env 就绝不会泄漏”：Inspect 可记录原始请求/响应和错误，provider 若在错误 body 回显认证信息仍有风险。I1 用合成哨兵测试所有持久化/错误路径，I3 前确认 provider 错误行为；使用原生日志配置和已验证的过滤能力，不能靠结束后删日志补救。`log_model_api=False` 仍保留错误 API 调用，不是保密开关。未满足凭据不落盘条件则阻断 pilot，先解决上游/配置问题，不发明第二套日志系统。

smart-agi 兼容性仍为 UNVERIFIED。I3 才使用 Inspect 原生 provider 做最小请求：精确 model 返回、同一 system/user/图片输入、工具 schema、tool_call ID/参数/结果回传、连续多轮、submit、usage、拒绝、429/错误/超时与重试；确认不会忽略 tools、strict、采样参数或改用其他模型。记录非敏感证据和实际可见限制，不依赖 model ID 字面推测。若不支持某选项，优先共同配置调整并重跑全部 pilot；原生 provider 确实无法使用的证据成立后，才另行决策最薄 provider 扩展，不能先写 HTTP client。

## 7. 日志、usage 与 repeated evaluation

Inspect `.eval` 为生成证据权威来源；用 `read_eval_log` / sample 读取 API 和 Inspect View 检查 messages、events、model/tool 关联、错误、limit、model_usage、started_at/completed_at、total_time/working_time。采用原有 metadata 记录 protocol/input/prompt 哈希、model slot、submission_id、phase、attempt、镜像和 Inspect 版本；不复制成自定义 MODEL_REQUEST 等事件体系。正式运行保留完整 sample/transcript；全量 API payload logging 需先通过上一节保密验收。源码 [EvalLog](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/log/_log.py)。

ModelUsage 包括 input/output/total、缓存读写、可得 reasoning_tokens 和 total_cost。当前 input_tokens 不含缓存 token，不能把它直接当全部 prompt token；也不能把 reasoning 再加到已包含它的 output。成本使用 Inspect `set_model_cost(model_id, ModelCost(...))` 或 `--model-cost-config` 的冻结价格，不自己写计费器。gateway 折扣、账单费用、失败请求未知用量和估算口径要与 Inspect token 推算费用区分；不可得则 submission 对应值 null 并写 unknown_fields_reason，不把默认零值当已知零消耗。源码 [ModelUsage](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/model/_model_output.py)。

Inspect 支持 Task/ eval `epochs` 重复 sample、多个 Sample、`eval(model=[...])` 和 eval_set 多模型/任务；sample ID、epoch 与日志标识能区分重复。没有评分器时也能保留逐次生成记录，不需要造一个工程 metric 才能运行。epoch reducer 不是 RobotGen 的最终统计器。

RobotGen 首版按 `records/attempts.csv` 既有顺序逐行调用 Inspect eval：每行一个 sample、epochs=1、独立 sandbox/output/log，绑定原有 submission_id。这只是领域计划适配，不实现执行调度器；避免模型列表/epochs 的默认调度改变原先随机化的交错顺序。pilot 为每模型 1 次，formal 为每模型 5 次；未来若改成 epochs=5，必须先验证独立 workspace、编号和预登记顺序等价，不能再叠加 5 个 attempt sample 变成 25 次。

禁用生成结果 cache、额外 sample retry（eval.retry_on_error=0）和未登记恢复；显式冻结并发与连接数，初版逐次运行以避免机器争用。eval_set 默认会重试失败任务，首版不直接采用其默认值；以后使用必须明确 retry 策略并保留所有失败日志。HTTP retry、sample retry、react attempts、epoch 是四个不同层次。独立设计是统计单位，100 组扰动不是 100 次模型生成；报告全部五次及失败，不能仅取最佳结果。依据 [eval 源码](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/_eval/eval.py)及 [eval sets](https://inspect.aisi.org.uk/eval-sets.html)。

## 8. submission / benchmark handoff

1. preflight 用现有 verify-inputs 及配置一致性检查，失败不启动模型。生成停止并完成 Inspect sandbox 收尾后，封存 workspace；拒绝绝对路径、越界链接及危险文件类型，不执行打包目录中的代码。
2. adapter 保留模型原始工程内容和 design_manifest：CAD 源码、装配及每打印件 STEP/STL、BOM、MJCF、URDF、controller、swing/wave reference/config、重建命令、依赖与说明，核对八关节、四接触及 case/horn 接口声明。不得用重命名冒充通用适配，也不补写缺失设计或 PASS。
3. 操作者字段从 Inspect 证据填入既有 submission.json：身份/session、phase/attempt、实际生成时间、反馈和人工编辑量、可得 usage/cost/seed。在 sandbox 关闭后把日志复制到提交下的相对 logs/ 路径并列入 logs；agent 从未拥有这份权威日志的写权限。input_manifest_sha256 是 records/input_manifest.json 文件哈希，prompt_sha256 是输入包 PROMPT.md 哈希；额外的完整 system prompt/tool 哈希保留在 Inspect metadata。
4. 调用现有 `python model_comparison/tools/experiment.py validate <submission-root>`，读取 intake_status，不能只看退出码。FILE_CONTRACT_ACCEPTED 只代表文件契约；失败提交可得 FAILED_ATTEMPT_RECORDED 且同样退出 0；INVALID 是验收失败。保持 engineering_evaluation=NOT_RUN、quality_score=null。
5. evaluator 在独立、无凭据且 agent 不可访问的执行环境接手封存设计，按现有 benchmark 入口重建/评分。run_digital、prepare_rebuild、run_rebuild、digital_geometry、simulate_cases 的 Gorilla8 假设及 ADAPTER_AUDIT 的 OPEN 项须另行适配验收，不能把任意提交直接喂给旧 runner 后声称通用评分已完成。compare.py 检查版本/profile/evaluator hashes；报告层另关联模型身份、预算和全部尝试。

状态映射：有证据的正常 submit -> COMPLETED（仍待 intake）；sample time limit -> TIMEOUT；turn/message/token/cost 耗尽、拒绝、上下文溢出或不可恢复生成错误 -> GENERATION_FAILED，保留原始 reason。仅启动前准备阻断保留 NOT_STARTED；启动后失败不能回填 NOT_STARTED。Inspect 正常退出可能只是 limit/refusal，不足以标记 COMPLETED。intake INVALID、导出失败和 EVALUATOR_ERROR 分别保留，不能变成模型工程零分。外部取消需记录事实及已发生用量，按预登记失败政策处理。

反馈：协议是最多 2 轮，并非必须 2 轮。最小 pilot 建议共同预登记 0 轮操作者反馈，react.attempts=1；模型内部公开 debug 仍允许并计时。首次交付由 evaluator 只读保存 first/，最终版另封存。若未来启用反馈，用 Inspect 原生 continuation/提交定制接口加薄 RobotGen 公共反馈适配，在同一次受限 sample 内保存首版和反馈；不能每轮重启 eval 刷新预算，不能把隐藏 benchmark scorer 接到 react.attempts。该反馈路径须单独验收，未实现时不能声称支持两轮。

未来 Inspect scorer 只允许薄调用现有 benchmark、保留原 scorecard/版本/错误；不复制几何、仿真、权重或评分逻辑。首版 scorer=None，最终 benchmark 完全在生成结束之后运行。

## 9. 实验公平性风险与冻结条件

固定变量：PROMPT、完整 system instruction/续行/submit 文本、input snapshot、react 实现及参数、工具集合/名称/描述/schema/输出截断、sandbox image digest、依赖及工具支持版本、机器资源、墙钟与 turn/message limit、反馈政策、网络政策、benchmark 版本；同时固定 cache、重试、并发、采样参数的共同政策。主要变化变量只有 model ID；必要 provider 配置差异单列证据，不能偷偷换 prompt 或工具。

无法伪造等价的变量：tokenizer、上下文容量/实现、内部 reasoning、provider latency、native tool-call encoding 和参数支持。记录可观测值和未知项；不要求披露内部思维链，不因某模型慢而临时加时，不把相同 token 数描述为同等算力。

尤其不能假定“同名工具 = 相同模型可见工具”：官网称 text_editor 可自动绑定 Claude 原生工具，实际 Anthropic 源码受模型家族及参数集合匹配约束，版本变动会影响是否触发；`GenerateConfig(internal_tools=False)` 可关闭该 provider 的自动映射。OpenAI-compatible `emulate_tools=True` 会把 schema/调用转换成 XML 提示；AzureAI 对部分 Llama 模型可默认启用 emulation。这会改变模型可见任务，不只是无影响的编码。源码 [Anthropic](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/model/_providers/anthropic.py)、[AzureAI](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/model/_providers/azureai.py)。

正式主轨候选策略：所有模型走同一 gateway 的原生 function calling（emulate_tools=False），共同 internal_tools=False，不启用 provider 内建执行工具。冻结 strict_tools、stream、parallel_tool_calls 的实际生效政策；“原生 function calling”与“provider 专用内建工具”不是同一概念。I3/I4 检查真实请求中工具名称、描述、参数、system/user 内容与返回行为；不能只比 Python Tool 对象。若某模型只能 emulation，主轨判为不兼容，或另开统一 emulation 的新实验，不能混入原生工具组。gateway 内部是否重写协议仍是不可见风险，需要记录其版本/路由保证，无法确认时收窄归因。

正式放行还须满足：全部模型独立 pilot 可执行；工具/图片能力和密钥不落盘验收；只读输入、跨 attempt 隔离、断网、超时后台进程收尾测试；首次输出与完整日志留存；Inspect 配置、镜像、预算和隐藏集托管冻结；ADAPTER_AUDIT 全部必要项通过并冻结独立工程评测器。当前不能将上述任何条件写成已通过。

## 10. 最小自有代码、替代范围与分支处置

RobotGen 后续只需：薄 Task/Sample 工厂与既有配置/计划校验；Dockerfile/Compose 环境定义；必要的公开领域反馈/工具适配；输出封存与 submission 元数据投影；调用现有 validate 和 benchmark 的 handoff。实际 model/tool 循环、日志生成、重试、计时、usage、容器生命周期全部委托 Inspect；配置适配不能演变成另一套 ModelAdapter 或通用 RunSpec 框架。

停止实现：自写 AgentLoop、Model/ModelReply 协议、ToolCall/ToolResult dispatch、HTTP client/retry、timeout/cancellation engine、RunEvent schema、usage accounting、sandbox manager、独立通用 mock runtime。离线测试直接使用 Inspect 已有 `mockllm/model` 与 custom_outputs，fixture 只表达 RobotGen 边界；依据 [官方 mock provider](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec4dfc6953784dc45b79de3147530c89868c6e26/src/inspect_ai/model/_providers/mockllm.py)。

`design/harness-architecture` 保留：模型比较目标、冻结输入、统一环境/预算、provenance、提交契约、生成/验收/评分边界、失败样本统计和正式放行门槛。其“由 RobotGen 自行实现通用运行组件”及旧 Phase 1–3 路线由本文取代；HARNESS_DESIGN 本轮不改。

`feat/harness-agent-loop` / `2d1bfc3` 停止作为正式路线推进，只保留历史 spike，不 merge、不 cherry-pick。harness_core.py 的循环、mock model、dispatch、边界计时和事件对象均已在职责上被 Inspect react/providers/tools/limits/logs 替代，不迁移代码。不是逐字节行为等价：旧同步循环不能中断阻塞调用，turn 计数和终止语义也不同；只保留其正常结束、工具失败、预算耗尽等测试场景作为 I1 用例。RobotGen submission 状态投影仍需薄适配，不借此保留旧 runtime。

## 11. 最小实施阶段（本轮止于 I0）

| 阶段 | 小 diff 交付 | 验收与退出条件 |
|---|---|---|
| I0 Inspect integration decision | 仅本文 | 官方 API/源码证据、职责和未验证项明确；单文件 diff |
| I1 offline Inspect smoke test | 后续单独锁定 Inspect；最小合成 task/fixture，复用 mockllm | 无真实 API/key；真实 react 的 tool->result->submit、续行、拒绝/错误、各 limit、日志/usage 缺失、计时和合成凭据泄漏测试；不复制 loop |
| I2 RobotGen Docker sandbox | 独立环境定义与离线文件探针 | 同版本 bash_session/editor 可用；只读 inputs、单 attempt 写入、不可读 benchmark/隐藏集/其他输出；断网、无凭据、资源限制；后台任务与失败收尾、产物存活验收；不生成真实机器人 |
| I3 single-model real API pilot | 一个模型的原生 provider 配置及最薄 Task 接线 | 后续授权范围内才用 env key；先协议/工具/图片/usage/日志契约，再受限单模型 pilot；不兼容留证据，不先写 client，不得据此排名 |
| I4 multi-model same-agent comparison | 新增模型配置及既有计划映射 | 同 react/tools/system/user/limits/image；先完成全部 pilot 并冻结，再按 formal 准入运行；全部重复/失败保留，生成比较不冒充工程排名 |
| I5 submission + benchmark handoff | 最薄输出/metadata/validate/benchmark adapter | 先合成提交验证状态/路径/日志，再真实封存产物；独立工程适配通过后运行同版本 benchmark；可选 scorer 只做 adapter |

阶段可各自细分提交；不在单个 diff 同时引入 provider、环境、scorer 和协议变更。I4 formal 工程排名须等待 I5 和原有正式门槛，不能按编号越过准备条件。每阶段可撤回新增入口，已经产生的失败/调用记录不得删除或重算成未执行。I0 不开始 I1。

## 12. 本轮交付检查

工作分支 `design/inspect-harness` 从指定 f0a8821 创建，不基于 2d1bfc3。提交信息 `docs: adopt Inspect AI for model harness`；推送同名分支，不合并 main。

执行 `git diff --check`、`git status --short`，并核对 `git diff --name-status f0a88217122b80b5d8fab32945d78df8645effc3 HEAD` 只新增本文；提交前另检查 staged diff。审阅包包含 branch、commit SHA、相对基线 diff --stat、本文全文、完整 diff 和检查结果。本轮没有安装 Inspect、运行 task、调用模型或运行 RobotGen benchmark。
