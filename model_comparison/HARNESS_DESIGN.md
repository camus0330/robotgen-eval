# RobotGen Harness 架构契约

本文基于 `b31c32dee70a4a2297a80f3823f028ef345c631f`，只冻结职责、数据边界和未来实现顺序，不表示 Harness 已实现。唯一新增文件为本文；不改变现有协议、Prompt、输入、提交契约或评分代码。

## 1. 定位与仓库事实

**Harness 是实验编排层，不是评分层。Harness ≠ benchmark。** 它不定义或修改 RobotGen benchmark 指标，不判断机器人设计质量，不包含模型质量评分逻辑。

职责依次为：加载一次实验的固定配置、统一 Prompt 和相同冻结输入；初始化统一 Agent 环境；通过 ModelAdapter 调用模型；运行 Shared Agent Loop 并提供相同工具；记录调用、耗时、token、错误和终态；收集机器人产物；整理为现有 submission contract；交给 `experiment.py validate` 验收，再由独立 benchmark 评分和报告层比较。

以下结论来自完整阅读根 README、本目录 README、EXPERIMENT_PROTOCOL、TASK_SPEC、PROMPT、SUBMISSION_SPEC、API_CONFIG、protocol.json、三个配置/提交模板、experiment.py、test_intake.py，以及 scripts/benchmark/、tests/benchmark/ 全部 Python 文件；另核对了 ADAPTER_AUDIT.md。路径均相对仓库，除非另有说明。

| 现有入口 | 已有能力与边界 |
|---|---|
| `model_comparison/protocol.json`、`EXPERIMENT_PROTOCOL.md` | 当前为 PILOT_DRAFT；模型身份与环境未填全，formal_scoring_ready=false。已有预算、重复次数、反馈与冻结规则，不能把草案当成正式放行。 |
| `model_comparison/templates/api_config.example.json`、`API_CONFIG.md` | 已有模型/API 配置格式；model 为空、endpoint_verified=false。配置不代表端点、工具调用或图像能力已经验证；experiment.py 不读取它。 |
| `model_comparison/tools/experiment.py` | prepare-inputs/verify-inputs 管理公开快照；freeze 绑定协议、模板和验收器；validate 只查文件、声明与哈希，不执行提交代码；inventory 不评分。freeze 仅产生 PROTOCOL_SNAPSHOT_ONLY。 |
| `model_comparison/tests/test_intake.py` | 用合成文本验证任意零件名、路径隔离、映射、失败记录、输入变更及冻结约束；通过不证明 CAD 或动力学正确。 |
| `scripts/benchmark/prepare_rebuild.py`、`run_rebuild.py`、`run_digital.py` | 现有独立重建/评测流水线依赖 Gorilla8 布局、固定脚本和阶段，不是通用 Agent runtime。 |
| `scripts/benchmark/digital_geometry.py`、`simulate_cases.py`、`make_public_cases.py` | 分别依赖固定零件/探针、模型路径/接触名/控制器及附件位置；用例生成器只生成公开扰动，不能视为隐藏评测已经实施。 |
| `scripts/benchmark/evaluate.py`、`evaluate_digital.py`、`check_extended.py` | 分别承担旧证据审计、数字初评、扩展覆盖检查。存在固定件数与结构案例等限制；保留各自缺证据、错误及评分语义，Harness 不重算或改写。 |
| `scripts/benchmark/compare.py`、`tests/benchmark/` | compare 检查量表、版本与评测器哈希兼容，不核实模型预算；回归测试检查评分假阳性、缺证据与哈希，不证明通用工程适配已完成。 |

**Future requirement：** 统一 Agent runtime、工具隔离和 provider 接入尚不存在。`ADAPTER_AUDIT.md` 中的通用工程适配仍是正式评分前置条件；它属于评测器的独立工作，不由 Harness 或 SubmissionAdapter 暗中修补，更不能靠重命名产物冒充适配完成。

## 2. 比较对象与统一数据流

比较对象是不同 LLM model，不是 Codex、Claude Code、Gemini CLI。所有模型共享 RobotGen 实现的 AgentLoop、ToolLayer、运行策略和版本；模型切换仅替换模型配置及 ModelAdapter，不使用 provider 各自的 agent runtime。API 格式转换不得带入专属规划器、工具或隐藏重试。若未来使用不同运行系统，必须另行标记为“模型+工具系统”实验。

```text
Frozen Inputs + PROMPT.md + Protocol + Model Config
                         |
                         v
                      RunSpec
                         |
                         v
                   Harness Runner
                         |
                         v
                  Shared Agent Loop
                         |
                         +---- ModelAdapter ---- LLM API
                         |
                         +---- ToolLayer ------- Robot/CAD/Simulation tools
                         |
                         v
                    Run Workspace
                         |
                         v
                  SubmissionAdapter
                         |
                         v
                experiment.py validate
                         |
                         v
                 existing benchmark
                         |
                         v
                  comparison/report
```

图示是目标数据流，不是当前已连通链路。Runner 负责准备、调度与收尾；EventLog/Provenance 覆盖全程。文件验收、工程评测和报告保留独立结果，不能把某一步退出码 0 当成机器人质量通过。

## 3. 核心对象与数据边界

### RunSpec：一次 attempt 的不可变配置视图

RunSpec 聚合现有文件的已核对值和来源引用，不新增配置文件或 JSON schema，也不复制一套 submission schema。冻结后不可由模型、adapter 或工具修改。下表中的 api_config.json 指遵循现有示例格式的本地配置；本轮不读取真实配置或凭据。

| 概念 | 来源与一致性规则 |
|---|---|
| run_id | 编排关联标识，绑定 protocol.experiment_id 与现有 submission_id；一个 attempt 对应一次独立运行。内部标识不新增 submission 字段，重试不能伪装成新 attempt。 |
| model_slot、phase、attempt | 来自 submission metadata 的既有身份；核对 API 配置同名字段及 protocol.models[].slot、replicates。目录名不证明模型身份。 |
| provider、model | API 配置的 provider/model 是调用目标；必须与同槽位 protocol.models[].provider/exact_version 一致，最终据调用记录写 model_provider/model_exact_version。不能以 model_A 等槽位代替精确模型版本。 |
| 调用参数 | base_url、api_path、api_format、endpoint_verified、request 来自 API 配置；调用方式和 settings 与 protocol 中的冻结记录核对。request 中可选参数的 null 按 API_CONFIG.md 表示省略，不猜测实际生效值。 |
| prompt | API 配置 paths.prompt 定位冻结输入的 PROMPT.md；哈希须等于 submission.prompt_sha256，并与已冻结来源一致。不是读取一份随时可改的工作副本。 |
| input snapshot/hash | paths.input_dir 定位公开快照；按 experiment.py verify_inputs 复核完整文件清单及逐文件哈希，再绑定 records/input_manifest.json 的文件哈希到 input_manifest_sha256。两种哈希含义不能混用。 |
| budget、feedback limit | protocol.budget 为实验约束来源；API 配置 experiment.wall_time_budget_s/max_feedback_rounds/allow_human_design_edits 必须与之相容，冲突拒绝启动，不静默覆盖。request.timeout_s/max_retries 是请求策略，不增加总预算。 |
| tool policy | 来源于 protocol.environment_description、budget.network 和冻结的共同工具环境。现有配置没有结构化工具策略及最大 Agent 轮数契约；这是 future requirement，本轮不添加字段或决定数值。 |

已有草案的 3600 秒、2 轮反馈只是现状，不在本文重新定值或批准用于正式实验。最大轮数、计时边界、重试与上下文管理策略需在实现阶段统一预登记；不能由 provider 私自选择。submission 的 actual_elapsed_s、usage_tokens、actual_cost 是运行后事实，不作为预算来源。API 配置的 paths 按其文件所在目录解析；现有路径约定不等于本轮决定最终 Harness 输出布局。

### ModelAdapter：协议转换边界

输入为统一消息历史、工具定义、冻结的模型参数和剩余预算；输出为统一的模型响应、工具调用意图、停止原因、usage 及错误，并保留 provider 原始含义的无密钥记录。未来可支持 OpenAI-compatible、Anthropic、Gemini，当前不选择 provider、不实现 adapter。

Adapter 只翻译 API 请求/响应，不改 Prompt、权限、预算、反馈或 benchmark，不执行工具、不自行规划或重试。不支持同等工具/输入能力时显式报告不兼容，不偷偷删工具或降级为另一种任务。上下文截断、压缩、工具并发及恢复规则归共享编排层统一冻结。

### AgentLoop：共享生命周期

```text
MODEL_REQUEST -> MODEL_RESPONSE -> optional TOOL_CALL -> TOOL_RESULT
      ^                                                    |
      +----------------------------------------------------+
MODEL_RESPONSE -> FINAL
```

FINAL 表示停止生成，不代表 intake 或工程通过。Runner 对每次调用、工具执行及反馈检查同一 wall-time 截止点与最大轮数；重试、等待、模型调试和反馈都消耗生成预算，独立最终评测不计入。反馈轮数与模型/工具轮数是不同计数；最大轮数的计数方式及具体上限留待后续统一冻结。

请求 timeout 受剩余 wall time 限制；可恢复 provider 错误只能按统一重试策略处理且逐次记账，不换模型、不刷新预算。工具失败作为明确 TOOL_RESULT 返回，是否继续由共享规则决定；权限违规、不可恢复 provider failure 或轮数耗尽终止为 GENERATION_FAILED。总时间耗尽为 TIMEOUT；单次请求超时尚未耗尽总时间时按冻结重试策略处理，耗尽重试则记录失败原因。达到终态后停止工具及子进程写入，保留已有产物和错误；恢复不得重置时间或隐藏失败。本轮不决定轮数、请求超时或重试的新数值。

### ToolLayer：等价工具 API 与权限

类别包括 filesystem（读写允许文件）、python（受限执行）、CAD/build（构建与导出）、simulation（公开调试）、inspection（产物查看）。所有模型必须获得等价 Tool API、参数语义、权限、依赖版本、资源上限和结果可见性；只允许 adapter 改变工具调用的传输编码。

工具执行边界由 Harness 控制，模型生成代码不能绕过文件/网络权限。默认网络遵循 protocol 的 disabled_except_model_service；模型服务连接由 adapter 处理，执行环境无凭据。公开检查仅返回预登记的诊断，不授予修改 benchmark 或访问隐藏用例的能力。统一工具不包含 Harness 自创的质量打分器。本轮不实现任何工具。

### RunWorkspace：隔离边界

每次 attempt 使用独立、可清理的运行空间和独立会话，模型只能写该 attempt 授权区域。冻结公开输入只读；benchmark、其他模型结果、历史答案及评测方隐藏资料不向模型开放写入或越权读取。不能把完整仓库当输入；统一复制/挂载的公开输入应与快照哈希一致。

模型写入区、编排器维护的元数据/日志及最终评测空间分别控制权限；日志不能由模型回写。保持协议要求的首次输出只读留存与最终产物可追溯；PROMPT 中已有 submission/ 和协议中的 first/ 是现有约定，本文不选择宿主根目录、最终输出目录树或隔离技术。输入准备失败不得调用模型。

### EventLog / Provenance：过程证据

至少记录 timestamp、run/attempt/session 关联、顺序与调用关联 ID、model request、model response、tool call、tool result、errors、token usage、可得 cost、elapsed time、状态迁移及 termination reason。记录模型精确版本、运行环境/编排版本、Prompt/输入哈希和产物引用；事件存储格式为 future requirement，不新增 schema。

记录实际发送的消息与工具参数、收到的可见响应及工具输出，不要求或虚构模型内部推理。失败、重试、超时、取消及未知 usage 都保留，未知成本/token/seed 按已有元数据以 null 和 unknown_fields_reason 解释，不能记成零。provider 原生计量口径与可用推理 token 单独注明，不声称跨 tokenizer 完全可比。

不得保存或输出 API key、Authorization header、token secret；不 dump 完整 API 配置。凭据只允许停留在未来 adapter 的认证边界，不能进入 Prompt、工具环境、日志或提交。请求/响应、异常和工具输出均在持久化前脱敏；“原始日志”指保留可审计内容，不包含认证秘密。认证秘密与统计用 token 数明确区分。

### SubmissionAdapter：只整理既有契约

输入是实际终态、过程记录和生成文件；输出沿用 submission.json、design_manifest.json 及机器人文件，不改变 schema，不补造设计、证据或工程 PASS。身份和实际耗时等由调用记录核实，设计映射由模型产物提供；元数据与设计声明保持分离。

COMPLETED 产物须按现有 SUBMISSION_SPEC 提供 CAD 源码、装配与打印件 STEP/STL、BOM、MJCF、URDF、控制/两动作参考、重建命令、依赖、说明和限制，保留八关节、四接触及电机接口映射。不强制改成 Gorilla8 名称。路径必须相对提交根且不越界、文件非空；打包只调整必要路径引用，不改工程内容。

验收继续调用 `python3 model_comparison/tools/experiment.py validate <submission-root>`。FILE_CONTRACT_ACCEPTED 仅表示文件契约通过；GENERATION_FAILED/TIMEOUT 在元数据和日志完整时可得 FAILED_ATTEMPT_RECORDED，且 CLI 同样可能返回 0；INVALID 表示验收未通过。必须读取 intake_status，不能仅看退出码。验收始终 engineering_evaluation=NOT_RUN、quality_score=null，不执行 rebuild_command；后续独立评测负责受限重建。

## 4. 运行状态机与现有状态映射

```text
PENDING -> PREPARING -> RUNNING -> COMPLETED
                          +----> GENERATION_FAILED
                          +----> TIMEOUT
PREPARING -> PENDING (preflight blocked; no model request)
```

| Harness 状态 | 含义 | 现有 submission.status |
|---|---|---|
| PENDING | 排队，尚未执行 | NOT_STARTED |
| PREPARING | 核对配置/哈希并准备环境 | 无直接中间态；仅记运行日志 |
| RUNNING | 模型与工具循环进行中 | 无直接中间态；仅记运行日志 |
| COMPLETED | 正常结束并交出待验收产物 | COMPLETED，直接映射；不代表质量合格 |
| GENERATION_FAILED | 已执行尝试不可恢复地失败 | GENERATION_FAILED，直接映射 |
| TIMEOUT | 已启动生成的总预算耗尽 | TIMEOUT，直接映射 |

不向 submission schema 加 PREPARING/RUNNING。启动前配置不合法、输入哈希不符属于准备阻断：记录内部失败，保留 NOT_STARTED，不伪装成已执行模型样本。进入 RUNNING 前应已有可核实的身份、session 和启动证据；开始后失败/超时必须保留日志并纳入已执行尝试，不能重置成 NOT_STARTED。中间态由 Runner 权威管理；未来运行时须防止 refresh-inputs 与活动运行并发，不能把现有 status 检查当成完整运行锁。

intake INVALID 与 evaluator error 单独记录，不覆盖生成终态。终态封存后不重入 AgentLoop；预算内的统一反馈属于同一次 RUNNING。不存在“高分终态”或由 Harness 赋分的状态。

## 5. 公平性与评分交接

不同模型至少固定：统一 Prompt（含共同系统指令）、frozen inputs、工具集合、工具权限、wall-time budget、feedback budget、文件访问范围、submission contract、benchmark version。还需固定编排版本、机器资源、依赖、网络、上下文策略及失败/重试规则；配置矛盾须在启动前暴露。

反馈只含相同公开检查的失败项、错误日志及剩余预算，不提供修复代码、其他模型方案或隐藏扰动结果。首次输出与每轮修复留存；操作者不代写设计，人工干预如实记录。各 attempt 独立、无跨模型记忆，沿用协议的运行计划与 pilot/formal 分离，不择优删除失败尝试。

tokenizer、上下文容量、内部推理实现、API-specific token accounting、服务延迟与参数支持不能完全统一，必须记录差异、未知项及实际 usage/cost。语义可比的设置事先冻结，不支持的设置明确披露；不把相同 token 数伪装成相同算力，也不因某 provider 慢而事后追加预算。

评分交接只传封存产物和 provenance。通用适配、评测环境与版本冻结等正式前置条件满足后，才交给现有 benchmark；Harness 不调用自创质量函数，也不把公开调试结果当独立最终评分。比较层沿用 compare.py 的版本/哈希兼容检查，并另核对身份、预算和全部重复尝试；现有 compare.py 不足以单独生成模型排名。

冻结协议不等于正式工程放行；formal_scoring_ready=false 与工程适配 OPEN 必须如实保留。评测器故障的处理和重测遵循 EXPERIMENT_PROTOCOL，不能由 Harness 改写为模型零分或成功。规则改变应建立新实验/评测版本并对受影响提交统一重测，本轮不执行这些变更。

## 6. 本轮明确不解决的问题

不调用真实 LLM API，不决定最终 API provider，不验证端点，不安装 SDK；不实现 ModelAdapter、AgentLoop、ToolLayer、workspace 或任何 Python Harness 代码；不决定最终输出目录、事件 schema 或预算新数值；不修改 benchmark、scoring、submission schema、Prompt 或 frozen input；不生成机器人、不运行重建/仿真、不产生模型排名。只新增本文，不改其他文件。

## 7. 建议实施阶段与独立验收

下列均为未来工作；各阶段独立提交、测试和回滚，不迁移或覆盖既有实验记录，不因下一阶段缺失而无法验证本阶段。回滚关闭新增入口并退回上一阶段版本，已经发生的调用与失败日志保留。

| Phase | 交付边界 | 独立测试与回滚 |
|---|---|---|
| 0：Architecture contract | 当前 HARNESS_DESIGN.md；冻结边界与未决事项 | 审阅来源、状态映射和单文件 diff；撤回文档即可，无运行影响。 |
| 1：Mock Harness | 不接 API；以 MockModel / deterministic fake model 验证 RunSpec、Agent lifecycle、tool-call/event lifecycle、隔离及 failure handling | 确定性重放正常结束、工具失败、provider 模拟失败、轮数耗尽、timeout、准备阻断和脱敏；撤回 mock 入口，不影响 intake/benchmark。 |
| 2：首个真实 provider | 只支持一个 provider，沿用 Phase 1 的共享循环/工具；不同时实现多个 provider | 协议转换 fixture、错误与 usage 映射、统一预算测试，再做受控连通验证；可退回 MockModel。 |
| 3：第二、第三个 ModelAdapter | 每次增加一个 adapter；AgentLoop 和 ToolLayer 保持不变 | 同一契约测试覆盖工具语义、权限与失败处理；能力不等价则阻断，单独撤回新增 adapter。 |
| 4：提交整理与 intake | 将运行产物映射到现有 submission contract，调用 experiment.py validate | 用合成文件验证完成、失败、超时、缺文件及越界；不声称工程通过。可撤回打包入口，原产物保留。 |
| 5：benchmark 与 comparison | 在独立工程适配和正式放行条件满足后连接 model → agent → robot generation → submission → benchmark → comparison | 检验同版本交接、评测故障保留、失败样本纳入及可追溯报告；撤回评分调度，生成与 intake 仍独立可用，不改变评分逻辑。 |
