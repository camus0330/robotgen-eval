# mini-swe-agent offline import resource preflight

**最终状态：PASS。** 2026-09-21，使用依赖原生缓存机制准备 `cl100k_base` 后，在全新 Python 进程中成功导入并实例化真实 `LitellmTextbasedModel`，读取默认 `action_regex`。offline 进程网络审计事件为 **0**，forbidden network attempts 为 **0**；prepare、offline 和整体 preflight 的退出码均为 **0**。

本结论只覆盖固定 mini-swe SHA 与本次实际解析到的 dependency 组合的资源准备、离线 import 和 constructor。没有运行上一轮 parser Case A–F，也没有修改上一轮脚本或失败报告。

## 1. Baseline 与 Phase 0 provenance

| 项目 | 实际值 |
|---|---|
| Repository | https://github.com/camus0330/robotgen-eval |
| Baseline | `f6c3086a35c2fc574f85256a08ec4ff965add937`；创建分支前已核对 HEAD |
| Branch | `spike/mini-swe-offline-import` |
| mini-swe upstream | https://github.com/SWE-agent/mini-swe-agent |
| mini-swe SHA | `04d809ceab9df28f9adaed044884180159172930` |
| mini-swe distribution / import version | `2.4.6` / `2.4.6` |
| LiteLLM | `1.102.0` |
| tiktoken | `0.14.0` |
| Python | `3.13.13`，Anaconda，`MSC v.1942 64 bit (AMD64)` |
| Platform | `Windows-11-10.0.26100-SP0`；AMD64 |
| venv | `<temp>\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv` |
| site-packages | `<venv>\Lib\site-packages` |
| 成功导入的 minisweagent | `<venv>\Lib\site-packages\minisweagent\__init__.py` |
| 成功导入的模型类 | `<venv>\Lib\site-packages\minisweagent\models\litellm_textbased_model.py` |

这里 `<temp>` 实际为 `C:\Users\hp\AppData\Local\Temp`。复用上一轮 venv，没有重装、升级或降级任何依赖。重新读取的 `direct_url.json` 为：

```json
{"url": "https://github.com/SWE-agent/mini-swe-agent.git", "vcs_info": {"commit_id": "04d809ceab9df28f9adaed044884180159172930", "requested_revision": "04d809ceab9df28f9adaed044884180159172930", "vcs": "git"}}
```

只读核对固定 SHA 的 [pyproject.toml](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/pyproject.toml)：LiteLLM constraint 为 `litellm >= 1.75.5, != 1.82.7, != 1.82.8`。实际 distribution metadata 同样记录 `litellm!=1.82.7,!=1.82.8,>=1.75.5`。这是 lower bound 加两个排除版本，**不是 exact pin**。`1.102.0` / `0.14.0` 只是本次 resolver 结果，不是 RobotGen 正式冻结依赖；没有修改 requirements、lock、pyproject 或其他 manifest。

## 2. Phase 1：实际安装源码行为

只读检查并在 preflight 输出当前 `<site-packages>\litellm\litellm_core_utils\default_encoding.py`，确认：

- 默认 resource directory 是 LiteLLM 包内 `litellm_core_utils/tokenizers`，通过 `importlib.resources.files(litellm)` 定位；源码保留 `pkg_resources` fallback。
- 当前安装版本支持 `CUSTOM_TIKTOKEN_CACHE_DIR`。设置非空目录时调用 `os.makedirs(..., exist_ok=True)` 并选用该目录，否则选用 bundled directory；随后把选定路径写入 `TIKTOKEN_CACHE_DIR`。
- import 阶段调用 `tiktoken.get_encoding("cl100k_base")`。源码包含针对 `FileExistsError` / `OSError` 的重试逻辑，本轮没有测试 retry 契约。
- 预期 cl100k cache basename 为 `9b5ad71b2ce5302211f9c61530b329a4922fc6a4`。**本轮准备前，bundled directory 内该文件不存在。**

另读当前 tiktoken 的 `load.py` 与 `tiktoken_ext/openai_public.py`：原生 cache key 是 resource URL 的 SHA-1；内容按 SHA-256 校验。缓存有效则直接读取，否则由依赖自身 `requests.get` 路径获取资源，再原子写入 cache。本轮没有复制、修改或替换这些 loader。

## 3. Phase 2：tokenizer 资源准备

在 Git 工作树外创建全新专用目录：

```text
C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-1r0q7ion
```

prepare worker 设置 `CUSTOM_TIKTOKEN_CACHE_DIR` 和 tiktoken 原生的 `TIKTOKEN_CACHE_DIR`，随后只调用 `tiktoken.get_encoding("cl100k_base")`。没有在准备进程 import LiteLLM 或模型类；没有自写 downloader 或构造 tokenizer 文件。

| 准备记录 | 实际结果 |
|---|---|
| prepare PID | `24248`；parent PID `28960` |
| Resource host | `openaipublic.blob.core.windows.net` |
| Resource path | `/encodings/cl100k_base.tiktoken` |
| 请求 | `GET /encodings/cl100k_base.tiktoken HTTP/1.1`，HTTPS / 443 |
| 准备状态 / exit code | PASS / `0` |
| 新增 cache 文件 | `9b5ad71b2ce5302211f9c61530b329a4922fc6a4`，仅此一个 |
| 文件大小 | `1,681,126` bytes |
| 文件 SHA-256 | `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7` |

SHA-256 与当前 tiktoken 源码中的预期值一致。prepare 审计记录包括该 host 的两次 `socket.getaddrinfo`、连接 `198.18.0.141:443`、对应 host 的 `http.client.connect`，以及上述 GET。地址是本次系统 DNS 的实际返回，不把它硬编码为资源服务器地址。

准备边界仅允许指定 resource host 的 DNS、其解析地址的 443 连接，以及该 host/path 的 HTTPS GET；设置 `NO_PROXY=*` 避免读取代理环境或采用系统代理配置。没有访问 LLM inference endpoint，forbidden attempts 为 0。缓存和日志均留在临时目录，没有提交到 Git。

**tokenizer preparation 属于环境构建/资源准备，不属于模型推理网络访问。正式 RobotGen runtime 尚未决定如何封装/锁定该资源。**

## 4. Phase 3：fresh offline process

实际整体执行命令（仓库根目录）：

```powershell
& 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe' -B -u model_comparison/spikes/mini_swe_offline_import_preflight.py
```

脚本以 `subprocess.run([...], shell=False)` 顺序启动 prepare 与 offline 两个独立进程，不复用 Python import 状态。实际 fresh offline command 为：

```powershell
& 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe' -B -u 'D:\Robotics Engineer\SEALab\robotgen-eval-swe\model_comparison\spikes\mini_swe_offline_import_preflight.py' --phase offline --cache 'C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-1r0q7ion'
```

父进程先按环境变量名字删除非白名单项，不检查被删值；子进程再次清理。worker 使用独立空的 `MSWEA_GLOBAL_CONFIG_DIR`、`MSWEA_SILENT_STARTUP=1`、`PYTHON_DOTENV_DISABLED=1`、`LITELLM_MODE=PRODUCTION`、`LITELLM_LOCAL_MODEL_COST_MAP=True`。offline worker 只设置 `CUSTOM_TIKTOKEN_CACHE_DIR`，让 LiteLLM 自己设置 `TIKTOKEN_CACHE_DIR`，并确认最终路径确为准备好的目录。

第三方 import 前安装 Python fail-closed audit hook，拒绝 socket DNS、connect、network send、HTTP connect/send，并记录任何此类尝试；同时拒绝 `.env` / `api_config.json` 打开和 worker 内子进程/shell。没有 monkeypatch provider、requests、tokenizer 或模型。父进程允许的 subprocess 仅用于上述两阶段分离，不构成 supervisor 或 Harness。

| fresh offline 记录 | 实际结果 |
|---|---|
| PID | `32116`，与 prepare / parent 不同 |
| import minisweagent | PASS，版本 `2.4.6` |
| import LitellmTextbasedModel | PASS，实际路径见 provenance |
| constructor | PASS；`model_name="robotgen/offline-import-test"`, `cost_tracking="ignore_errors"` |
| runtime cache | `C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-1r0q7ion` |
| network events | `[]` |
| forbidden accesses | `[]` |
| forbidden network attempt count | `0` |
| offline exit code | `0` |
| 整体 preflight exit code | `0` |

实际读取的 `model.config.action_regex`，以 raw-string 表示：

```text
r"```mswea_bash_command\s*\n(.*?)\n```"
```

没有覆盖 regex，也没有调用 `_parse_actions()`。实际结尾输出：

```text
constructor=PASS
network events=[]
forbidden accesses=[]
forbidden network attempt count=0
offline result=PASS
offline process exit code=0
FINAL: PASS (resource preparation + fresh offline import/constructor only)
```

完整 stdout/stderr 保存在 `<temp>\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\offline-import-preflight.log`。本轮没有异常 traceback。

## 5. 结论与边界

本次证明：**当前固定 mini-swe SHA + 当前解析到的 dependency 组合，可以在预先准备 tokenizer resource 后，在 fresh process 中离线导入并实例化 LitellmTextbasedModel。** 上一轮阻断可以通过环境资源准备解决，无需修改第三方源码。

| 审阅问题 | 答案 |
|---|---|
| 是否修改第三方源码 | 否；未修改 mini-swe、LiteLLM、tiktoken，也未 monkeypatch |
| 是否调用任何 LLM API | 否；prepare 仅取得公开 tokenizer 资源 |
| 是否读取/使用 API key | 否；未读取 SMART_AGI_API_KEY、OPENAI_API_KEY、ANTHROPIC_API_KEY、GEMINI_API_KEY、个人 `.env` 或实际 api_config.json |
| 是否 runtime 联网 | 否；offline 网络审计事件和 forbidden network attempts 均为 0 |
| 是否运行 parser / query / completion | 否 |
| 是否运行 DefaultAgent | 否 |
| 是否执行 shell actions | 否；只用 `shell=False` 启动验证所需的 Python worker |
| 是否正式 pin LiteLLM / tiktoken | 否；没有完成 dependency lock |
| 是否冻结 text-based protocol | 否 |

不能由本次 PASS 推断 parser 已验证、text-based 优于 native tools、真实模型兼容、Docker 已验证或 production Harness 已完成。没有运行 parser smoke、全量 pytest、Agent loop、Docker 或 benchmark。

本轮只新增本报告和 [mini_swe_offline_import_preflight.py](spikes/mini_swe_offline_import_preflight.py)。提交信息为 `test: probe mini-swe offline model import`，推送 `spike/mini-swe-offline-import`，不 merge。若审阅要求 REPAIR，仅修改这两个文件；不修改上一轮 parser 文件、dependency manifests，不接入真实 endpoint 或实现 Harness。
