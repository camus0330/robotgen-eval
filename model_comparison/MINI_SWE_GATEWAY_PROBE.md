# mini-swe-agent real gateway compatibility probe

**当前结果：ENVIRONMENT_BLOCKED，exit code 5，恰好一次 logical query。** 2026-09-22 使用实际 model_A 配置对 `glm-5.3` 发出真实请求。gateway 返回 `NotFoundError`，指出当前账号组没有支持该模型的配置账号；同时 runtime 审计记录一次被拒绝的 loopback 连接。既有脚本以审计阻断优先，最终分类为 ENVIRONMENT_BLOCKED。没有模型 completion、parser action 或成功兼容性结论；没有重试或修改 probe。

## Initial config-blocked run

以下保留 commit `fb1f8e82fc9b464892552772b5fd5b84b0686e10` 的原始历史；本节“本轮/本次”均指当时的模板检查。实际本地配置和真实 query 结果见后面的 **Real glm-5.3 gateway run**，不能把两次结果混在一起。

**本轮结果：CONFIG_BLOCKED，exit code 2，logical query count 0。** 用户未指定实际本地 `api_config.json` 路径；当前工作树按文件名搜索未找到实际 `api_config.json`。已发出路径澄清请求，未自行选择 model slot 或猜测 model ID。

本轮实际执行的是仓库公开模板的配置拒绝检查：模板 `model` 为空，即使配置声明的环境变量可解析出密钥，也在模型 import / query / gateway DNS 前拒绝请求。**这不是实际本地配置的 gateway 测试，也不能声称 endpoint、authentication、模型或 parser 真实请求兼容性已验证。** 真实 query 分支尚未执行。

### 1. Baseline 与环境

| 项目 | 实际记录 |
|---|---|
| Repository | https://github.com/camus0330/robotgen-eval |
| Baseline | `8c20e6768b021ce2bcef5150b4243382dfd2c2f0`；创建分支前已核对 |
| Branch | `spike/mini-swe-real-gateway` |
| Commit message | `test: probe mini-swe real gateway compatibility` |
| mini-swe SHA | `04d809ceab9df28f9adaed044884180159172930` |
| mini-swe version | `2.4.6` |
| LiteLLM / tiktoken | `1.102.0` / `0.14.0` |
| Python / platform | `3.13.13`，Anaconda / `Windows-11-10.0.26100-SP0` / AMD64 |
| venv | `C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv` |

以上环境由本轮先行运行的既有 offline import preflight 重新核对：direct_url 的 commit_id / requested_revision 均为固定 SHA，实际模型类从该 venv 的 `Lib\site-packages\minisweagent\models\litellm_textbased_model.py` 导入。没有更换依赖；这些版本仍不是 production lock。

### 2. 本轮 tokenizer preflight

实际先执行未修改的已审阅脚本：

```powershell
& 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe' -B -u model_comparison/spikes/mini_swe_offline_import_preflight.py
```

结果为 `FINAL: PASS`、exit code `0`。parent / prepare / fresh offline PID 为 `17600` / `23604` / `33772`。准备阶段使用 tiktoken 原生资源机制；fresh offline import / constructor 成功且 network events 为 `[]`。

| Cache 项目 | 实际值 |
|---|---|
| prepared cache path | `C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-13k3kqb1` |
| cache 文件 | `9b5ad71b2ce5302211f9c61530b329a4922fc6a4` |
| 文件大小 | `1,681,126` bytes |
| SHA-256 | `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7` |

tokenizer preparation 只访问公开 `openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken` 资源，属于环境准备，不是 gateway model request。缓存和日志均在 Git 工作树外。

### 3. 实际配置检查与结果

复用现有 [API_CONFIG.md](API_CONFIG.md) 和 [api_config.example.json](templates/api_config.example.json)，没有增加 provider schema 或修改实际配置。实际检查命令：

```powershell
& 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe' -B -u model_comparison/spikes/mini_swe_gateway_probe.py --config model_comparison/templates/api_config.example.json --cache 'C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-13k3kqb1'
```

| 字段 | 实际结果 |
|---|---|
| config path | `model_comparison/templates/api_config.example.json`；仅模板拒绝检查，非用户指定实际配置 |
| provider | `smart_agi_gateway` |
| configured model ID | 空字符串 |
| LiteLLM routed model name | 未构造；必须由非空实际 model ID 加 `openai/` 前缀得到 |
| config base_url | `https://big-model.smart-agi.com` |
| config api_path | `/v1/chat/completions` |
| derived api_base | `https://big-model.smart-agi.com/v1` |
| api_format | `openai_chat_completions` |
| key source | `env`，值未输出；本次按模板声明解析了对应环境变量 |
| timeout_s | `600` |
| mini-swe retry attempts | 配置为 `1`；未执行 query |
| LiteLLM/provider retries | 代码设为 `0`；未执行请求 |
| non-null generation parameters actually sent | 无；没有请求 |
| logical query count | `0` |
| classification / reason | `CONFIG_BLOCKED` / `model is empty` |
| response type / returned model / finish_reason | 未取得 |
| assistant content / parsed actions / FormatError | 未取得 |
| usage / cost availability | 未取得；不能记为免费或 $0 |
| gateway network targets | `[]` |
| unrelated runtime network attempts | `[]` |
| exit code | `2` |

原始 SDK traceback 没有生成或输出。该次在配置检查返回，未到达 gateway runtime 的 import / audit / query 分支；空网络记录来自未发起请求，不能据此断言真实请求的 allowlist 已实测通过。

### 4. 已实现但尚未实际调用的 gateway 路径

脚本要求 `--config` 和 `--cache`。非空环境变量优先于非空 inline api_key；两者均空、model 为空或 slot 名、schema/provider/format 不匹配、stream 非 false、max_retries 非 0 或 endpoint 形状不支持，都拒绝请求。

对本轮 root base_url + `/v1/chat/completions` 配置，推导 SDK base 为 `<base_url>/v1`。实际模型名使用 `openai/<exact-config-model-id>`，不改写 model ID 本体。`temperature/top_p/max_tokens/seed` 为 null 时省略；非空 extra_body 按当前 LiteLLM 原生参数传递，但拒绝其覆盖本轮固定请求边界。

在 import 前设置 `MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT=1`、禁用 dotenv、使用随包 cost map 和 prepared tokenizer cache。读取指定 credential 后按变量名清理其他环境项与代理，设置 `NO_PROXY=*`。不放行配置代理，不加载用户 `.env`。

网络审计在第三方 import 前启用：import 阶段禁止外网，query 准备阶段只允许 config hostname 的 DNS、其解析地址的指定端口连接和对应 HTTP target；拒绝其他网络目标与进程执行。LiteLLM 原生设置关闭 telemetry，`drop_params=False`，全局及请求重试为 0。没有 provider/function patch，没有自写 HTTP provider client。

唯一主调用入口为真实 `LitellmTextbasedModel.query(MESSAGES)`，固定兼容性 prompt 要求 `echo robotgen_gateway_probe` 的单一 mswea block；不执行该命令。模型使用 `cost_tracking="ignore_errors"`，零成本标为 `cost unavailable / ignored`。只读 Python profile hook 观察真实 `_query` 返回对象的类型，不替换方法；其他 evidence 从真实 query 输出或 FormatError 的 persisted response 中提取。

真实结果分类支持 PASS、FORMAT_MISMATCH、CONFIG_BLOCKED、ENDPOINT_FAILED、ENVIRONMENT_BLOCKED 和本地 AssertionError 的 FAIL。合法 fence 但 command 非预期也归入 FORMAT_MISMATCH。FormatError 不执行恢复重试；不运行 Agent 或 Environment。

代码屏蔽原始第三方 stdout/stderr 和日志，丢弃捕获内容；仅输出经过已解析密钥值清洗的白名单证据及异常 class / sanitized message，不打印完整异常 traceback、header 或 config。真正的 query、错误分类、对象类型观察和网络访问路径仍需实际配置后验证，不能由本次配置拒绝检查推断成功。

### 5. 安全、边界与后续输入

提交前检查范围包括两个新增文件、暂存 Git diff 及本轮配置检查日志：按本次配置声明在进程内取密钥做匹配检查，只输出检查结果，不输出密钥。报告不复制 config secret，不写 trajectory，也不保存原始 SDK dump。

| 审阅问题 | 本轮实际答案 |
|---|---|
| 是否调用真实 LLM API / exactly one logical query | 否 / 否，query count 为 0 |
| 是否有自动 retry | 没有发生；真实调用路径配置为 1 次 mini-swe attempt、0 次 provider retry |
| 是否读取 API key / 泄露 API key | 是，按模板声明读取环境变量 / 未输出或写入报告、Git |
| 是否 patch completion / parser / cost | 否 |
| 是否运行 DefaultAgent / Environment | 否 |
| 是否执行 shell action / RobotGen generation / benchmark | 否 |
| 是否修改实际 api_config / endpoint_verified | 否 |
| 是否冻结 text protocol | 否 |

仍需用户提供本轮实际 `api_config.json` 路径，且文件中含精确非空 model ID；不要在对话中提供 API key。拿到配置后才能执行本轮允许的一次真实 query。当前不能得出 gateway transport 或候选 text protocol 的真实兼容性结论。

本轮只新增本报告与 [mini_swe_gateway_probe.py](spikes/mini_swe_gateway_probe.py)，推送指定分支，不 merge。若 REPAIR，仅修改这两个文件；不进入 DefaultAgent + real gateway、RobotGen generation、Docker、benchmark 或正式 Harness。

## Real glm-5.3 gateway run

### 1. 本轮基线、目录与配置核对

| 项目 | 实际记录 |
|---|---|
| Repository / branch | `camus0330/robotgen-eval` / `spike/mini-swe-real-gateway` |
| 上一轮 probe HEAD | `fb1f8e82fc9b464892552772b5fd5b84b0686e10` |
| 本轮开始的本地及远端 HEAD | `b26f5f0c832f971e3567f91beaa6e5e8d411c915` |
| 已有目录修正 commit | `fix: restore pilot model_A slot path` |
| 本轮 commit message | `test: record glm real gateway probe` |
| 实际 config path | `model_comparison/submissions/pilot/model_A/01/api_config.json` |
| configured / routed model | `glm-5.3` / `openai/glm-5.3` |
| provider / api_format | `smart_agi_gateway` / `openai_chat_completions` |
| base_url / api_path | `https://big-model.smart-agi.com` / `/v1/chat/completions` |
| derived api_base | `https://big-model.smart-agi.com/v1` |
| key source | `env` |
| timeout / stream / request.max_retries | `600` / `false` / `0` |

开始时工作树干净，分支正确。`b26f5f0` 已将 pilot `Gemini/01` 下 README.md、design_manifest.json、submission.json 三个 tracked 文件以 100% 相同内容改名到 `model_A/01`；submission.json 仍声明 `model_slot=model_A`。本轮没有重复 rename 或调整 slot。

实际配置经只读检查确认 schema_version=`robot-model-api-config/0.1`、model_slot=`model_A`、phase=`pilot`、attempt=`1`，其余字段如表所列。首次检查发现 inline api_key 非空，因用户要求为空而暂缓请求；用户在本地清空并回复确认后，再次检查所有前置条件均通过，且 `SMART_AGI_API_KEY present=True`。没有输出该环境变量值，没有由助手改写配置。

`git check-ignore -v` 命中 `model_comparison/.gitignore:2:submissions/**/api_config.json`，`git ls-files` 确认配置未 tracked。本次真实 query 前保存配置内容摘要用于运行后比对；配置及 endpoint_verified 保持不变，不进入 Git。

### 2. 本轮资源与固定环境

使用上述既有 venv 重新运行未修改的 `mini_swe_offline_import_preflight.py`，结果 `FINAL: PASS`，exit code `0`。parent / prepare / offline PID 为 `26376` / `4948` / `30672`；fresh offline import / constructor 成功，network events=`[]`。在用户清空配置后又检查缓存文件仍存在且内容 hash 正确，没有再次下载。

| 项目 | 实际值 |
|---|---|
| prepared cache path | `C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-lbsr6h93` |
| cache 文件 | `9b5ad71b2ce5302211f9c61530b329a4922fc6a4` |
| SHA-256 | `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7` |
| mini-swe SHA / version | `04d809ceab9df28f9adaed044884180159172930` / `2.4.6` |
| LiteLLM / tiktoken | `1.102.0` / `0.14.0` |
| Python / platform | `3.13.13`，Anaconda / `Windows-11-10.0.26100-SP0` / AMD64 |

preflight preparation 获取公开 tokenizer 资源；gateway runtime 没有访问该资源。没有修改 preflight、现有 probe 或依赖版本；未建立 production dependency lock。

### 3. 唯一一次真实 query 与原样结果

实际执行命令：

```powershell
& 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe' -B -u model_comparison/spikes/mini_swe_gateway_probe.py --config model_comparison/submissions/pilot/model_A/01/api_config.json --cache 'C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-lbsr6h93'
```

| 结果项 | 本次实际输出 |
|---|---|
| logical query count | `1` |
| mini-swe retry attempts / LiteLLM-provider retries | `1` / `0` |
| non-null generation parameters | `{}`；temperature/top_p/max_tokens/seed 为 null，已省略；未增加 extra_body 私有参数 |
| exception class | `NotFoundError` |
| 最终 classification | `ENVIRONMENT_BLOCKED`，保留现有 probe 的分类结果 |
| exit code | `5` |
| response type / returned model / finish_reason | 未取得 model completion，均为 null |
| assistant_content / parsed actions | 未取得，均为 null |
| FormatError fields | 无；未进入成功 response 的 text parser 验证 |
| usage | 未取得 |
| cost | `not observed`，不可用；不是免费或 $0 |

实际 sanitized exception message：

```text
litellm.NotFoundError: NotFoundError: OpenAIException - Model "glm-5.3" is not supported by any configured account in this group
```

这条真实 gateway/model error 属于 model availability 的 endpoint 失败证据，不能解释为 FORMAT_MISMATCH。没有返回可供 parser 验证的 assistant completion。由于同次运行另有下述审计拒绝，脚本最终 ENVIRONMENT_BLOCKED 优先覆盖 endpoint 分类；报告同时保留二者，不将返回码改写为 PASS 或单独的 ENDPOINT_FAILED。

### 4. 网络与本地清理异常证据

| 审计类别 | 实际记录 |
|---|---|
| gateway DNS | `socket.getaddrinfo(big-model.smart-agi.com, 443)` 两次 |
| gateway socket connect | `198.18.0.68:443` 一次，由当前 DNS 解析结果进入 allowlist |
| 被拒绝的非 gateway target | `socket.connect(127.0.0.1, 14091)` 一次 |
| unrelated_network_attempts 数量 | `1`；目标为本机 loopback，不是证实的其他公网访问 |

两次 DNS 分别符合脚本预解析与 SDK 连接解析，不是两次逻辑 query。代码关闭了 mini-swe 自动重复 attempt、LiteLLM/provider retry；没有第二次手动 query，没有恢复重试。没有放行额外目标或改变代理策略。

在 `FINAL: ENVIRONMENT_BLOCKED` 后，进程清理阶段还输出了无凭据的异常：`BaseEventLoop.__del__` → `ProactorEventLoop.close()` → `_close_self_pipe()`，最终 `AttributeError: 'ProactorEventLoop' object has no attribute '_ssock'`。这个清理 traceback 没有被 query 期间的输出捕获覆盖，必须保留为本轮观察，不能声称整个过程没有 traceback。

事后仅只读检查本机 Python 源码：`asyncio/proactor_events.py` 的 `_make_self_pipe` 调用 `socket.socketpair()`，`socket.py` 的 fallback 实现使用本机 loopback TCP。这与此次 loopback 拒绝和缺失 `_ssock` 的清理异常相符，**但本次 audit 未保存拒绝点调用栈，不能据此确认唯一调用来源或进一步推断代理/telemetry 原因**。没有修补 event loop 或脚本以重发请求。

完整本次 preflight 和脱敏 probe 输出分别保存在 `<venv 的父目录>\glm-real-preflight.log`、`glm-real-gateway-probe.log`，均位于 Git 工作树外。没有保存原始凭据或请求 header。

### 5. 安全检查、范围与结论

commit 前对报告、probe 文件、工作树 diff、暂存 diff 与本次 probe 输出进行密钥匹配检查，仅打印检查结果，不打印密钥。配置运行前后的内容摘要一致，endpoint_verified 未被改写，配置继续被 Git 忽略。

| 审阅问题 | 本轮答案 |
|---|---|
| 是否调用真实 LLM API | 是，向真实模型 endpoint 发起请求，收到 NotFoundError；未取得成功 completion |
| 是否 exactly one logical query / retry | 是 / 没有重试 |
| 是否读取 / 泄露 API key | 按现有规则读取 env / 未输出或提交其值 |
| 是否 patch completion / parser / cost / provider | 否，probe 脚本未修改 |
| 是否运行 DefaultAgent / Environment | 否 |
| 是否执行 shell action / RobotGen generation / benchmark | 否 |
| 是否由助手修改或提交 api_config | 否；用户自行清空 inline 字段后，运行前后文件保持一致 |
| 是否修改 endpoint_verified | 否 |
| 是否冻结 text protocol | 否 |

本轮仅更新现有报告，使用 `test: record glm real gateway probe` 提交并推送原分支，不 merge。现有 model_A 目录修正 commit 保持不变，没有新增 spike 或 Harness 功能。

**本轮只验证真实 glm-5.3 gateway + mini-swe text parser compatibility；本次没有验证通过。** 不代表 production Harness 已完成、text protocol 已冻结、RobotGen generation 已完成或 formal benchmark 已开始。
