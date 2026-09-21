# mini-swe-agent real gateway compatibility probe

**本轮结果：CONFIG_BLOCKED，exit code 2，logical query count 0。** 用户未指定实际本地 `api_config.json` 路径；当前工作树按文件名搜索未找到实际 `api_config.json`。已发出路径澄清请求，未自行选择 model slot 或猜测 model ID。

本轮实际执行的是仓库公开模板的配置拒绝检查：模板 `model` 为空，即使配置声明的环境变量可解析出密钥，也在模型 import / query / gateway DNS 前拒绝请求。**这不是实际本地配置的 gateway 测试，也不能声称 endpoint、authentication、模型或 parser 真实请求兼容性已验证。** 真实 query 分支尚未执行。

## 1. Baseline 与环境

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

## 2. 本轮 tokenizer preflight

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

## 3. 实际配置检查与结果

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

## 4. 已实现但尚未实际调用的 gateway 路径

脚本要求 `--config` 和 `--cache`。非空环境变量优先于非空 inline api_key；两者均空、model 为空或 slot 名、schema/provider/format 不匹配、stream 非 false、max_retries 非 0 或 endpoint 形状不支持，都拒绝请求。

对本轮 root base_url + `/v1/chat/completions` 配置，推导 SDK base 为 `<base_url>/v1`。实际模型名使用 `openai/<exact-config-model-id>`，不改写 model ID 本体。`temperature/top_p/max_tokens/seed` 为 null 时省略；非空 extra_body 按当前 LiteLLM 原生参数传递，但拒绝其覆盖本轮固定请求边界。

在 import 前设置 `MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT=1`、禁用 dotenv、使用随包 cost map 和 prepared tokenizer cache。读取指定 credential 后按变量名清理其他环境项与代理，设置 `NO_PROXY=*`。不放行配置代理，不加载用户 `.env`。

网络审计在第三方 import 前启用：import 阶段禁止外网，query 准备阶段只允许 config hostname 的 DNS、其解析地址的指定端口连接和对应 HTTP target；拒绝其他网络目标与进程执行。LiteLLM 原生设置关闭 telemetry，`drop_params=False`，全局及请求重试为 0。没有 provider/function patch，没有自写 HTTP provider client。

唯一主调用入口为真实 `LitellmTextbasedModel.query(MESSAGES)`，固定兼容性 prompt 要求 `echo robotgen_gateway_probe` 的单一 mswea block；不执行该命令。模型使用 `cost_tracking="ignore_errors"`，零成本标为 `cost unavailable / ignored`。只读 Python profile hook 观察真实 `_query` 返回对象的类型，不替换方法；其他 evidence 从真实 query 输出或 FormatError 的 persisted response 中提取。

真实结果分类支持 PASS、FORMAT_MISMATCH、CONFIG_BLOCKED、ENDPOINT_FAILED、ENVIRONMENT_BLOCKED 和本地 AssertionError 的 FAIL。合法 fence 但 command 非预期也归入 FORMAT_MISMATCH。FormatError 不执行恢复重试；不运行 Agent 或 Environment。

代码屏蔽原始第三方 stdout/stderr 和日志，丢弃捕获内容；仅输出经过已解析密钥值清洗的白名单证据及异常 class / sanitized message，不打印完整异常 traceback、header 或 config。真正的 query、错误分类、对象类型观察和网络访问路径仍需实际配置后验证，不能由本次配置拒绝检查推断成功。

## 5. 安全、边界与后续输入

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
