# RobotGen generation harness 技术路线决策

## 1. 研究目标与决策状态

RobotGen 主要比较不同 LLM 在 **same prompt、same frozen inputs、same agent scaffold、same tools/action protocol、same sandbox、same budget** 条件下生成机器人的能力。研究变量主要是 model；重点不是比较完整 Agent 产品，也不是判断哪个 framework 总体更强。

**决定：RobotGen v1 generation harness 选择 mini-swe-agent。** Inspect AI 保留为已调研、暂不采用的 alternative。选择依据是与 RobotGen 当前架构、模型公平性目标和维护边界的匹配程度。

记录日期：2026-09-21。本轮只记录技术路线，不实现 runtime。framework 选择已确定；最终 action protocol 尚未冻结，真实模型与运行环境的兼容性也未获实测放行。[protocol.json](protocol.json) 仍为 `PILOT_DRAFT`、`formal_scoring_ready=false`；本文不改变这些状态。

## 2. 已审阅候选与证据范围

两份 integration plan 均已通过架构审阅，分别从 RobotGen 基线 `f0a88217122b80b5d8fab32945d78df8645effc3` 独立研究；它们不互相作为实现依赖。本文读取固定 commit 的计划作为比较依据，不重新宣称已测试其中的运行能力。

| 候选 | 已审阅 RobotGen plan | 计划研究的上游版本 |
|---|---|---|
| Inspect AI | `design/inspect-harness`；commit `a13fcd32beb9297d69ceedc1dbb2699311146cf2`；[INSPECT_HARNESS_PLAN.md](https://github.com/camus0330/robotgen-eval/blob/a13fcd32beb9297d69ceedc1dbb2699311146cf2/model_comparison/INSPECT_HARNESS_PLAN.md) | `0.3.266` / `ec4dfc6953784dc45b79de3147530c89868c6e26` |
| mini-swe-agent | `design/mini-swe-harness`；commit `d41ec27cbfc1e39bf0306b7139dd62a74a77da90`；[MINI_SWE_HARNESS_PLAN.md](https://github.com/camus0330/robotgen-eval/blob/d41ec27cbfc1e39bf0306b7139dd62a74a77da90/model_comparison/MINI_SWE_HARNESS_PLAN.md) | `main@04d809ceab9df28f9adaed044884180159172930`；package version `2.4.6` |

mini-swe 的 package version 不能替代 commit pin：已审阅计划指出，远端 `v2.4.6` tag 与上述研究 commit 不同。下一阶段以指定 upstream SHA 为验证对象，记录实际依赖版本。

本决策分支 `design/harness-framework-decision` 同样从上述基线创建，创建前已确认 HEAD 等于该基线。两份候选 plan 仅通过固定 commit 链接引用，不 merge、不 cherry-pick、不复制进本分支。Inspect plan 中以采用 Inspect 为假设的路线以及 I1/I2 推进安排，作为候选研究保留；实际 v1 路线由本文决定，不并行执行两份计划。

## 3. 比较与取舍

下表是基于两份已审阅计划的架构判断，不是性能测评。Inspect 的 sandbox、limits、logs 和 batch evaluation 更成熟；mini-swe 的优势是更薄、Agent loop 更透明、bash-only 更适合当前生成工作，并有统一 text-based action 的可行路径。

| 维度 | Inspect AI | mini-swe-agent | 对 RobotGen v1 的影响 |
|---|---|---|---|
| 架构复杂度 | Task/Sample/react/provider/sandbox/eval 等完整评测抽象 | Agent/Model/Environment 可直接组合 | 现有评测层已在，优先较薄的 generation 接入 |
| Agent scaffold 透明度 | react 可配置并有源码可审计，但需跟踪续行、submit、工具映射等框架行为 | DefaultAgent 的 query/action/observation/exit 路径集中、易审计 | 更便于固定并解释模型实验所用循环 |
| tool/action protocol | 标准 bash/bash_session/text_editor 等；工具集与 provider 映射需共同冻结 | 以 bash action 为核心；相同 Environment 执行命令 | CAD、Python、仿真与文件操作可共用单一 bash interface |
| native tool calling | 原生 provider 支持；需约束 internal tools、emulation 与实际 schema | 默认 LitellmModel 使用 native bash tool calls | 两者都需验证被测模型与 relay，不能假定 native transport 无差异 |
| text-based action | 已审阅方案主要采用 native；有工具 emulation 能力，但不能直接视为相同 bash 文本协议 | `litellm_textbased` 与上游 regex parser 提供明确的一块 bash action 路径 | 可优先验证所有模型共用同一文本 action 格式；并非已证明兼容 |
| sandbox | 较成熟的 sample sandbox、Docker/Compose 与生命周期支持 | DockerEnvironment 提供启动/exec/基础清理；领域挂载与可靠封存需薄适配 | 接受较小基础层，前提是 cleanup 不演变成自研 sandbox manager |
| wall-time/limits | 较完整的 time/working/turn/message/token/cost limits 和请求限制 | step/cost、query 前 wall-time 软检查、command timeout；无一等总 token cap | mini-swe 的硬截止与后台进程清理是明确待验证缺口 |
| provider abstraction | get_model/Model 与内置 providers、OpenAI-compatible 接入 | 上游模型类与 LiteLLM transport | 均可避免自写 HTTP client；mini-swe 只需 RobotGen 配置映射 |
| trajectory/logging | 较成熟的 EvalLog/transcript、模型/工具事件、usage 与查看设施 | 原生 trajectory 保存消息/actions/outputs/config；完整时序、脱敏和异常落盘需核验 | 优先复用原生格式；不能用自建完整 event log 弥补所有缺口 |
| batch evaluation | epochs、多模型 eval/eval_set 等通用设施更完整 | 现有 batch runner 偏 SWE-bench dataset/patch 工作流 | RobotGen 沿用既有 attempts 计划，不引入 SWE evaluation 层 |
| RobotGen benchmark 边界 | 可用 scorer=None，独立交接现有 benchmark；不必复制评分 | primitives 只负责 generation，再交接 validate/benchmark | 两者都能分离 generation/scoring；mini-swe 更贴近当前所需范围 |
| RobotGen 新增代码量 | 薄 Task/Sample 工厂、环境声明与 submission bridge；计划未给定量行数 | 计划估计 runtime glue 约 360–600 行，另有配置/镜像定义与测试 | 不能据此断言 mini-swe 必然代码更少；实际维护面需 spike 后复核 |
| 长期维护成本 | 通用运行设施更多由上游承担，需要理解并锁定较多框架策略 | 核心组合小，但 limits/cleanup/logging 缺口可能扩大自有代码 | 以薄适配为约束，超出边界触发重新评估 |
| 论文解释性 | 可以描述统一 react，但需披露工具映射、续行、重试/重复等策略 | 容易解释为固定循环、bash 协议、环境与预算，只替换模型 | 符合当前论文归因目标；不免除 provider、上下文与延迟差异披露 |

依据定位：Inspect plan 第 2–7、9–10 节；mini-swe plan 第 2–10、12–13 节。两者的 sandbox/限额成熟度均不等于 RobotGen 已完成隔离、硬截止或工程环境验证。

## 4. 最终决定及主要原因

RobotGen v1 使用 mini-swe-agent 作为 generation harness，直接复用 Agent/Model/Environment primitives，保持 generation 与 scoring 分离。

1. RobotGen 已拥有 experiment protocol、submission contract、engineering benchmark 和 comparison layer，相关职责继续由本项目维护。
2. 当前不希望再引入一套完整 evaluation framework，与上述已有职责形成额外重叠和配置成本。Inspect 可以不使用 scorer；本次取舍不是认定其无法分离评分，而是优先匹配更小的接入范围。
3. 当前主要生成行为，包括读取文件、写 Python、CAD 构建/导出、MuJoCo 调试和检查产物，都可以通过统一 bash interface 承载。
4. mini-swe 可直接复用 DefaultAgent、上游模型类与 DockerEnvironment，无需 RobotGen 自研通用 AgentLoop、provider client 或 action parser。
5. 对本论文最重要的是固定 Agent scaffold 和 action protocol，只替换 model。较透明的 loop 和集中配置有利于审计、复现和解释。
6. `litellm_textbased` 提供统一 text-based bash action 的现实路径，可避免默认让不同模型依赖不同 provider-native tool-call transport。其公平性仍取决于共同 prompt、格式/错误处理、observation、图片输入与预算规则。

**text-based action 仍只是正式主轨候选，需要 compatibility pilot 后才能冻结。** 本文不提前选择最终 native/text 协议，不按 provider 给模型静默切换 action transport。离线 parser 测试通过也不等于所有真实模型/relay 已兼容；真实端点验证需在后续单独阶段审阅。

RobotGen 保留 task/prompt/config binding、冻结输入与 workspace、submission/validate/benchmark bridge 和必要 provenance。优先保留 mini-swe 原生 trajectory，不建立第二套 transcript。上游 step/cost 控制与 wall-time 软检查可以复用，但不能写成硬 deadline 已解决。

本决定不批准修改 Prompt、protocol、submission schema 或工程指标，也不批准直接启动完整 Harness 实现。`FILE_CONTRACT_ACCEPTED` 仍只代表文件契约通过；Harness 不计算 RobotGen engineering score，现有 benchmark 的通用工程适配与正式放行条件继续独立存在。

## 5. Inspect alternative 与 architecture escape hatch

`design/inspect-harness` 保留为 **alternative/reference branch**，不 merge 到正式 runtime，不继续 I1/I2 实现。已审阅计划中的 sandbox、limits、logs、batch evaluation 能力是未来重新评估的依据，不丢弃其研究结论。

以下任一情况出现，应暂停扩大 mini-swe 适配层，启动架构复核并重新评估 Inspect：

| 触发条件 | 重新评估的理由 |
|---|---|
| RobotGen 开始自行实现通用 sandbox manager | 已越出领域配置/挂载桥接，Inspect 的成熟 sandbox 生命周期可能更合适 |
| 开始自行实现完整 retry/cancellation engine | 通用失败控制不应成为 RobotGen 自有 framework |
| 开始自行实现完整 generic event log | 原生轨迹加少量 provenance 的维护边界已失效 |
| 开始自行实现通用 token/cost accounting | 需重新权衡 Inspect 已有 usage/limits/cost 设施 |
| hard deadline / process cleanup 无法通过薄 wrapper 或既有运行平台实现 | mini-swe 的简单性不再能覆盖实验的时间与封存要求 |
| mini-swe provider/action compatibility 无法覆盖被测模型 | 无法满足共同 scaffold/action 的模型比较目标，需重新检查替代框架的实际能力 |

这是 **architecture escape hatch**，不是同时维护两套 runtime，也不是触发后自动切换。复核应提交具体失败证据、已增加或拟增加的通用代码维护面，以及 Inspect 在固定版本下能否解决问题的验证计划，再更新路线决策。不能通过继续扩充自研基础设施来维持“薄适配”的名义。

## 6. 下一阶段：仅 offline compatibility spike

下一轮范围限定为 **offline compatibility spike**，验证固定上游 primitives 的实际行为；不能直接做完整 Harness。本轮只登记以下检查，不执行安装、导入、测试或 Docker 操作。

| 下一轮验证项 | 预期证据 |
|---|---|
| 固定 upstream 可安装/导入 | 指定 mini-swe SHA、实际 package/依赖版本与 import 结果；失败如实记录，不静默换成 latest |
| Deterministic/Test model 驱动真实 DefaultAgent | 使用上游真实 Agent 和确定性模型完成合成 action → observation → exit；不另写模拟 AgentLoop |
| text-based action parser | 用离线响应 fixture 检查合法 bash fence、缺块/多块/截断等错误；测试上游 parser，不实现替代 parser |
| 统一 bash execution | 在相同受控环境执行合成文件读写、stdout/stderr、非零退出码及结束标记 |
| trajectory 保存 | 检查真实 messages/actions/outputs/config/exit 及失败记录的可读性与实际缺失项 |
| step limit | 检查模型调用计数、格式错误占用与终止行为，不混同 shell 命令数 |
| wall-time 软限制 | 实测阻塞命令与下一轮检查的时序，明确超限窗口；不能据软限制测试声称已有硬截止 |
| DockerEnvironment 基本行为 | 启动、cwd、exec、command timeout、退出/清理与残留进程观察；记录平台要求和失败，不扩展成完整 RobotGen 镜像工程 |

下一轮不调用真实 LLM API、不使用真实模型凭据、不生成 RobotGen 机器人、不修改 benchmark。依赖取得/安装只是后续固定版本验证的准备事项，不表示本轮获准安装；“offline”要求测试执行使用确定性模型/响应，不能因缺 fixture 转向真实 API。

spike 产出应是小范围可复核的兼容性结果与差距清单，区分通过、失败、环境阻断及未测试。通过后再单独审阅最薄适配、环境与真实 endpoint pilot；不得把离线通过当成完整 Harness、action protocol 冻结或正式模型实验放行。

## 7. 本轮变更、验证与回滚

本轮唯一新增文件为 `model_comparison/HARNESS_FRAMEWORK_DECISION.md`。不新增 Python、YAML runtime config 或 Dockerfile，不安装 Inspect/mini-swe/pytest，不调用 API，不修改 protocol、Prompt、submission schema、experiment.py、benchmark、tests 或 HARNESS_DESIGN.md；不 merge 或 cherry-pick 任一候选 plan。

以单一文档 commit `docs: select mini-swe-agent generation harness` 推送 `design/harness-framework-decision`，不 merge，等待实际 commit/diff 审阅。检查 `git diff --check`，并核对 `git diff --name-only f0a88217122b80b5d8fab32945d78df8645effc3...HEAD` 仅包含本文；纯文档任务无需安装测试依赖。

如审阅失败，repair 只修改本文，不进入 runtime implementation。若撤销本轮，revert 该纯文档 commit；RobotGen runtime 与 benchmark 不受影响。
