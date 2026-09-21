# mini-swe-agent text parser smoke

**当前最终状态：PASS。** 在本轮重新执行并通过 resource preflight 后，真实 `LitellmTextbasedModel._parse_actions()` 的 Case A–F 均已通过；parser runtime 网络尝试为 0，smoke exit code 为 0。固定 upstream 的 text parser contract 已在当前 dependency/resource environment 中实际验证。以下按初次阻断、资源解决、本次重跑三个阶段记录。

## 1. Initial blocked run

本节保留初次运行的历史记录，原文中的“本轮/本次”均指 `spike/mini-swe-text-parser`、commit `f6c3086a35c2fc574f85256a08ec4ff965add937` 的运行，不代表当前状态。该次没有运行 A–F，不能追溯改写为 PASS。

**最终状态：ENVIRONMENT_BLOCKED。** 2026-09-21，复用上一轮临时 venv 执行 parser smoke，退出码 **2**。导入真实 `LitellmTextbasedModel` 时，LiteLLM/tiktoken 初始化尝试获取 tokenizer 资源，被离线访问限制拦截。**模型尚未实例化，Case A–F 均未执行；本轮不能报告 parser PASS。**

本轮没有调用真实 LLM API，没有读取或使用真实 API key。依赖确实调用了非 LLM 的 `requests.get` 下载路径，但在 `socket.getaddrinfo` 审计事件处被拒绝，未建立该下载连接；不能把这次运行描述为“依赖完全没有尝试联网”。

### 1.1 Baseline、固定来源与环境

| 项目 | 实际记录 |
|---|---|
| Repository | https://github.com/camus0330/robotgen-eval |
| RobotGen baseline | `157a17bbac0c2327ed87fc48e7af5ee4c7778f36`；创建新分支前已核对 HEAD |
| Branch | `spike/mini-swe-text-parser` |
| Upstream repository | https://github.com/SWE-agent/mini-swe-agent |
| Fixed upstream SHA | `04d809ceab9df28f9adaed044884180159172930` |
| 实际 mini-swe distribution / import version | `2.4.6` / `minisweagent.__version__ == "2.4.6"` |
| Python | `3.13.13`，Anaconda，`[MSC v.1942 64 bit (AMD64)]` |
| Platform | `Windows-11-10.0.26100-SP0`；`AMD64` |
| venv | `C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv` |
| 安装方式 | 复用上一轮通过 pip VCS 完整 SHA 安装的非 editable distribution；本轮没有安装、升级或更换依赖 |

重新读取 distribution 的 `direct_url.json`，确认：

```json
{"url": "https://github.com/SWE-agent/mini-swe-agent.git", "vcs_info": {"commit_id": "04d809ceab9df28f9adaed044884180159172930", "requested_revision": "04d809ceab9df28f9adaed044884180159172930", "vcs": "git"}}
```

实际 import 路径：

- 顶层 `minisweagent` 已成功导入：`<venv>\Lib\site-packages\minisweagent\__init__.py`。阻断后另做只读 provenance 检查，在禁止 dotenv 加载的进程中重新确认该路径和 `__version__=2.4.6`；没有重试导入 LiteLLM/parser。
- traceback 显示本次目标模块从 `<venv>\Lib\site-packages\minisweagent\models\litellm_textbased_model.py:1` 开始导入，随后在 `import litellm` 内失败。**这不是模型类成功导入或实例创建的证据。**
- 脚本保留了成功导入后检查类/helper 的真实源码路径、helper 绑定及默认 config 的断言，但本次未到达这些检查。

本次实际依赖版本：

| 依赖 | 版本 |
|---|---|
| litellm | 1.102.0 |
| tiktoken | 0.14.0 |
| openai | 2.54.0 |
| pydantic | 2.13.5 |
| jinja2 | 3.1.6 |
| python-dotenv | 1.2.3 |

没有改 RobotGen requirements、environment lock 或其他 dependency manifest；没有改 upstream SHA 或使用 `v2.4.6` tag 替代。

### 1.2 执行命令与阻断证据

从仓库根执行：

```powershell
& 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe' model_comparison/spikes/mini_swe_text_parser_smoke.py
```

即使用该 venv 的 `python model_comparison/spikes/mini_swe_text_parser_smoke.py`。完整 stdout/stderr 保存在工作树外的 `C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\text-parser-smoke.log`，没有提交日志文件或缓存。

实际关键输出：

```text
PermissionError: Offline parser boundary rejected socket.getaddrinfo
requests.exceptions.ProxyError: HTTPSConnectionPool(host='openaipublic.blob.core.windows.net', port=443): Max retries exceeded with url: /encodings/cl100k_base.tiktoken ...
Cases A-F not run: ENVIRONMENT_BLOCKED; precondition failed
FINAL: ENVIRONMENT_BLOCKED
```

上段第二行是长异常的节录；完整异常链包含本机代理 `127.0.0.1:7897`、`NewConnectionError` 和 `Offline parser boundary rejected socket.getaddrinfo`。没有拿 `Max retries exceeded` 字面值当成已执行的 LLM API retry 测试。

traceback 的主要路径为：

```text
minisweagent/models/litellm_textbased_model.py:1 -> import litellm
litellm/__init__.py -> provider/integration imports
litellm/litellm_core_utils/token_counter.py:32
litellm/litellm_core_utils/default_encoding.py:59
  -> tiktoken.get_encoding("cl100k_base")
tiktoken_ext/openai_public.py:76 -> load_tiktoken_bpe(...)
tiktoken/load.py:66 -> read_file(blobpath)
tiktoken/load.py:17 -> requests.get(blobpath)
socket.getaddrinfo -> PermissionError (offline audit hook)
```

实际尝试的资源是 `https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken`，属于 tokenizer 文件，不是 Chat Completions、Responses 或 smart-agi endpoint。

阻断后仅静态核对依赖源码：`default_encoding.py` 将缓存位置设为 bundled tokenizers 目录，导入时调用 `tiktoken.get_encoding`；`tiktoken/load.py` 在缓存不存在或哈希不符时进入下载路径。事后检查预期文件 `<venv>\Lib\site-packages\litellm\litellm_core_utils\tokenizers\9b5ad71b2ce5302211f9c61530b329a4922fc6a4` 不存在。现有证据不能单独区分运行前就缺文件与缓存校验失败后被依赖移除，故不进一步断言打包根因。没有下载、替换文件或重配缓存来绕过错误。

### 1.3 本地 fixture 与 Case A–F 状态

脚本的 synthetic response 只用 `SimpleNamespace` 提供 `choices[0].message.content` 和 `choices[0].finish_reason`，没有 parser 或 action extraction 逻辑。测试入口全部预定为真实 `LitellmTextbasedModel._parse_actions()`，没有调用 helper 绕过模型类导入，也没有调用 `query()`。

实例化参数在脚本中为 `model_name="robotgen/offline-parser-test"`、`cost_tracking="ignore_errors"`，没有传入 `action_regex` 或错误模板覆盖值。**该实例化语句本次尚未执行。**

| Case | 准备的 fixture / 断言 | 本次实际结果 |
|---|---|---|
| A | 普通说明加一个 mswea block；期望一个 `echo robotgen_parser_ok` action | ENVIRONMENT_BLOCKED：未执行 |
| B | 一个 block 包含 `printf first\nprintf second`；期望仍为一个 action 且保留内部换行 | ENVIRONMENT_BLOCKED：未执行 |
| C | 纯文本；期望真实 FormatError、n_actions=0、原始 content 保留 | ENVIRONMENT_BLOCKED：未执行 |
| D | 两个完整 mswea blocks；期望 FormatError、n_actions=2，不选择第一个执行 | ENVIRONMENT_BLOCKED：未执行 |
| E | 未闭合 mswea block，finish_reason=length；期望 n_actions=0，并与同内容/stop 的默认错误文本对照 | ENVIRONMENT_BLOCKED：未执行；无实际错误 message 或 finish_reason 对照结果 |
| F | 普通 bash fence；期望不识别、FormatError、n_actions=0 | ENVIRONMENT_BLOCKED：未执行 |

默认 action_regex 的**静态源码值**为：

```text
r"```mswea_bash_command\s*\n(.*?)\n```"
```

该值来自本次读取的固定 upstream `models/litellm_textbased_model.py`；没有复制 parser 实现。由于类导入阻断，**没有通过 `model.config.action_regex` 得到运行时确认**。

FormatError 的运行结果同样不能伪造：本次没有捕获到真实 parser FormatError，因而 `e.messages`、role=user、`extra.interrupt_type`、`extra.n_actions`、`extra.model_response` 和错误措辞都尚未运行验证。脚本准备检查这些字段，错误文字只检查 exactly-one / found-count 含义，不锁死完整英文。

静态阅读可见：`_parse_actions` 把 finish_reason 传给真实 `parse_regex_actions`；helper 的错误消息包含上述 extra 字段；模型类的默认错误模板只引用 actions 数量，不引用 finish_reason。**这些是源码观察，不是 Case E 已通过**，也不代表 query 层完整 response/cost 持久化契约已验证。

### 1.4 离线边界与实际未执行内容

脚本在第三方导入前删除非白名单环境变量，只枚举名字，不读取被删变量的值。没有读取/使用 SMART_AGI_API_KEY、OPENAI_API_KEY、实际 api_config.json 或个人 `.env`，没有打印完整环境变量。

针对已读依赖源码，预先使用其现有设置：

- `MSWEA_GLOBAL_CONFIG_DIR` 指向全新临时目录，`MSWEA_SILENT_STARTUP=1`。
- `PYTHON_DOTENV_DISABLED=1`，禁用 dotenv 文件加载；`LITELLM_MODE=PRODUCTION` 跳过默认 DEV dotenv 加载入口。
- `LITELLM_LOCAL_MODEL_COST_MAP=True`，只用 LiteLLM 随包价格表，避免其导入时远程价格表获取；这不执行 cost calculation，也不保证 tokenizer 资源离线齐全。

此外使用 Python 标准 audit hook 拒绝连接、DNS、网络发送、子进程/shell 及敏感配置文件打开。它仅拒绝副作用，不替换 parser/model/provider，不返回假响应，也不做 provider monkeypatch。遇到这次依赖联网尝试后，保留真实 traceback 并以非零状态退出；没有通过修改断言、安装其他版本、手工加载 helper 或补 tokenizer 让错误消失。

明确回答：

| 问题 | 答案 |
|---|---|
| 是否调用真实 API | 没有调用真实 LLM/provider API；发生非 LLM tokenizer HTTP 下载尝试，在连接前被拦截 |
| 是否读取/使用真实 API key | 否 |
| 是否运行 DefaultAgent | 否，未调用或导入它作为测试入口 |
| 是否执行 shell | parser smoke 内没有执行任何 shell/action 命令或子进程；echo/printf 仅为未执行的 fixture 文本 |
| 是否测试 native tool calling | 否 |
| 是否使用 Docker/LocalEnvironment | 否 |
| 是否调用 query/completion、测试 cost/retry/observation formatting | 否；依赖导入内部报错不算这些契约的测试 |
| 是否冻结 RobotGen 正式 text-based protocol | 否 |

同样没有测试 step/wall-time、hard deadline、submit sentinel、多模态、RobotGen Prompt、CAD/MuJoCo、submission adapter、benchmark 或 full Harness；没有运行上一轮 Agent smoke 或整个 pytest suite。

### 1.5 历史结论、变更与回滚

本轮只确认固定 mini-swe 的安装 provenance 和顶层 import 版本仍正确，同时发现当前依赖/资源环境不能完成目标类的受限离线导入。**不能得出 parser 语义已实测稳定的结论。**

即使未来 Case A–F 全部 PASS，也只能证明固定 upstream 的 text-based parser 在这些输入下语义稳定且符合记录，不能证明 GPT/Claude/Gemini 都会稳定生成格式、smart-agi 支持这些模型、text-based 优于 native tools，或 RobotGen 已冻结正式 action protocol。

本轮不修复阻断；如果后续允许处理依赖离线资源，应单独明确验证范围，再在同一 upstream SHA 下复核。这里不自动进入该工作。

只新增本报告与 [mini_swe_text_parser_smoke.py](spikes/mini_swe_text_parser_smoke.py)。保留失败证据，以 `test: probe mini-swe text action parser` 提交并推送 `spike/mini-swe-text-parser`，不 merge。`git diff --check` 与相对 baseline 的文件范围检查应只覆盖这两个文件。审阅 REPAIR 仅修改这两者，不扩展到完整 Agent loop、Docker、真实 endpoint 或 RobotGen Harness。

## 2. Resource preflight resolution

`spike/mini-swe-offline-import` / `be90a7d434fd1034c6e5e87bf5b565384d947900` 已通过环境资源预检，详见 [MINI_SWE_OFFLINE_IMPORT_PREFLIGHT.md](MINI_SWE_OFFLINE_IMPORT_PREFLIGHT.md)。本轮没有修改该报告或 preflight 脚本，而是先重新运行已审阅脚本，再使用它本次新生成的缓存。

实际命令，仓库根目录：

```powershell
& 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe' -B -u model_comparison/spikes/mini_swe_offline_import_preflight.py
```

| 本轮 preflight 实际记录 | 结果 |
|---|---|
| parent / prepare / offline PID | `5876` / `10164` / `26408` |
| prepared cache path | `C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-vllnieo2` |
| Cache 文件 | `9b5ad71b2ce5302211f9c61530b329a4922fc6a4` |
| 文件大小 | `1,681,126` bytes |
| SHA-256 | `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7` |
| prepare 网络资源 | `https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken` |
| prepare 结果 / exit code | PASS / `0` |
| fresh offline import / constructor | PASS / PASS |
| fresh offline network events | `[]`，forbidden network attempt count=`0` |
| preflight 结尾 / exit code | `FINAL: PASS (resource preparation + fresh offline import/constructor only)` / `0` |

准备阶段由 tiktoken 原生 loader 获取公开资源，仅发生 tokenizer 资源网络访问；这是环境构建/资源准备，不是模型推理网络访问。LiteLLM 使用其原生 `CUSTOM_TIKTOKEN_CACHE_DIR` 机制选取目录。没有修改第三方源码，没有升级或降级依赖。完整本次 preflight 日志保存为 `<venv 的父目录>\parser-runtime-preflight.log`，位于 Git 工作树外。

## 3. Current offline parser rerun

### 3.1 本轮 provenance 与命令

| 项目 | 本次实际记录 |
|---|---|
| Repository | https://github.com/camus0330/robotgen-eval |
| Baseline | `be90a7d434fd1034c6e5e87bf5b565384d947900`，建分支前已核对 |
| Branch | `spike/mini-swe-text-parser-runtime` |
| HEAD（运行时、提交前） | `be90a7d434fd1034c6e5e87bf5b565384d947900`；最终提交 HEAD 见交付审阅包及该分支提交记录 |
| Commit message | `test: validate mini-swe text parser offline` |
| mini-swe SHA | `04d809ceab9df28f9adaed044884180159172930` |
| mini-swe distribution / import version | `2.4.6` / `2.4.6` |
| LiteLLM / tiktoken | `1.102.0` / `0.14.0` |
| Python / platform | `3.13.13`，Anaconda / `Windows-11-10.0.26100-SP0` / AMD64 |
| parser PID | `32424`，不同于 preflight 各进程 |
| parser smoke exit code | `0` |

本次重新验证 `direct_url.json` 的 repository 与完整 commit，内容与 1.1 节所列一致。成功导入并检查了 `minisweagent`、`LitellmTextbasedModel`、`parse_regex_actions` 和 `FormatError` 的实际源码路径，均位于上述 venv 的 `Lib\site-packages\minisweagent` 内；模型类路径为 `models\litellm_textbased_model.py`，helper 路径为 `models\utils\actions_text.py`，异常路径为 `exceptions.py`。

脚本还检查 `_parse_actions.__globals__["parse_regex_actions"]` 确为导入的上游真实 helper；所有测试入口仍是 `model._parse_actions(response)`，未直接调用 helper 代替模型入口，未复制 parser。模型参数仍为 `model_name="robotgen/offline-parser-test"`、`cost_tracking="ignore_errors"`。

实际 parser smoke 命令：

```powershell
& 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe' -B -u model_comparison/spikes/mini_swe_text_parser_smoke.py --cache 'C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-vllnieo2'
```

`--cache` 是必需参数。脚本先检查目录、cl100k 文件与 SHA-256，再设置 `CUSTOM_TIKTOKEN_CACHE_DIR`；没有手工设置 `TIKTOKEN_CACHE_DIR`，也没有 downloader 或联网 fallback。模型构造后实际确认 LiteLLM 设置的 `TIKTOKEN_CACHE_DIR` 与 prepared path 一致。

本次读取并验证的 **runtime 默认 action_regex** 为：

```text
r"```mswea_bash_command\s*\n(.*?)\n```"
```

未向模型传入自定义 action_regex 或错误模板。LiteLLM/tiktoken 版本检查只是本 spike 对已审阅环境的校验，不是正式 dependency pin；未修改任何 dependency manifest。

### 3.2 Case A–F 实测结果

| Case | 真实结果 |
|---|---|
| A | PASS；普通说明加单 block 返回恰好一个 action，command=`echo robotgen_parser_ok` |
| B | PASS；返回恰好一个 action，command 精确等于 `printf first\nprintf second`，内部换行保留 |
| C | PASS；真实 FormatError，role=`user`，n_actions=`0`，原始 content 保留，错误含 exactly-one / found-0 语义 |
| D | PASS；真实 FormatError，n_actions=`2`，两个 block 的原始 content 完整保留；没有返回任一 action |
| E | PASS；未闭合 block、finish_reason=`length` 得到 FormatError / n_actions=`0`；原始 content 保留。同内容、finish_reason=`stop` 也得到 FormatError / n_actions=`0`，默认错误文本完全相同 |
| F | PASS；普通 `bash` fence 不被接受，真实 FormatError / n_actions=`0`，原始 content 保留 |

C、D、E、F 均验证异常的真实类型为 `minisweagent.exceptions.FormatError`，`e.messages[0]` 中实际确认：

- `role == "user"`。
- `extra.interrupt_type == "FormatError"`。
- `extra.n_actions` 分别为 `0 / 2 / 0 / 0`。
- `extra.model_response` 与该 case 输入 content 逐字符一致，包括 fence 与换行。
- `content` 具有 exactly-one / found-count 错误语义；断言未锁死整段英文。

Case E 的实际 message（JSON 中的 `\n` 表示原始换行）：

```json
{"role": "user", "content": "Please always provide EXACTLY ONE action in triple backticks, found 0 actions.", "extra": {"interrupt_type": "FormatError", "n_actions": 0, "model_response": "```mswea_bash_command\necho truncated\n"}}
```

同内容的 `stop` 对照通过同样字段检查，并与 `length` 的 `content` 做相等断言。D 的实际错误文本将 `found 0 actions` 改为 `found 2 actions`。这些是本次 runtime 观测，不再只是 1.3 节的静态推断；仍未验证 query 层的完整 response/cost 持久化。

### 3.3 网络审计、输出与结论边界

在第三方模型 import 前安装 fail-closed audit hook，记录并禁止 DNS、socket connect/send、HTTP connect/send，以及子进程/shell 和 `.env` / `api_config.json` 打开。审计事件一旦发生即抛出 PermissionError；即使依赖吞掉异常，保存的记录仍会阻止 PASS，并返回 ENVIRONMENT_BLOCKED。成功计数由实际记录计算，而非因为请求未成功就宣称离线。

parser runtime 实际记录为 `forbidden accesses=[]`、`forbidden network attempt count=0`。runtime 中没有下载 tokenizer，也没有网络尝试。环境变量只按名字清理，不读取被删的 API key 值；dotenv 禁用，mini-swe global config 指向新的空临时目录。

实际 summary（A/B 行省略已在表中记录的 command 值）：

```text
Case A: PASS
Case B: PASS
Case C: PASS n_actions=0
Case D: PASS n_actions=2
Case E finish_reason length vs stop: default error text identical
Case E: PASS n_actions=0
Case F: PASS n_actions=0
forbidden accesses=[]
forbidden network attempt count=0
FINAL: PASS
```

完整 parser stdout/stderr 保存在 `<venv 的父目录>\text-parser-runtime-smoke.log`。没有覆盖历史 `text-parser-smoke.log`。

| 审阅问题 | 本轮答案 |
|---|---|
| 是否调用真实 API | 未调用真实 LLM/provider API；只有 preflight preparation 获取公开 tokenizer 资源 |
| 是否读取/使用 API key | 否 |
| 是否 parser runtime 联网 | 否，网络尝试计数为 0 |
| 是否调用 query/completion | 否 |
| 是否运行 DefaultAgent / LocalEnvironment | 否 |
| 是否执行 shell actions | 否；echo/printf 仅作为 parser 输入字符串，parser smoke 没有启动子进程 |
| 是否测试 native tools / retry / cost / Docker / wall time | 否 |
| 是否冻结正式 text-based protocol | 否 |

**本轮 PASS 只代表固定 upstream 的 text parser contract 已在当前 dependency/resource environment 中实际验证。** 不能证明 GPT / Claude / Gemini 会稳定生成该格式、smart-agi endpoint 兼容、text-based 比 native 更公平或更好，也不代表 RobotGen 已冻结最终 action protocol。

只修改现有两个 parser spike 文件；没有修改 preflight 文件、Prompt、protocol、benchmark 或任何其他项目文件。提交并推送本节所列 branch，不 merge；REPAIR 仅修改这两个文件，不进入 Agent loop、Docker、真实 endpoint 或 Harness implementation。
