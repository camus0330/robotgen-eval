# mini-swe-agent text parser smoke

**最终状态：ENVIRONMENT_BLOCKED。** 2026-09-21，复用上一轮临时 venv 执行 parser smoke，退出码 **2**。导入真实 `LitellmTextbasedModel` 时，LiteLLM/tiktoken 初始化尝试获取 tokenizer 资源，被离线访问限制拦截。**模型尚未实例化，Case A–F 均未执行；本轮不能报告 parser PASS。**

本轮没有调用真实 LLM API，没有读取或使用真实 API key。依赖确实调用了非 LLM 的 `requests.get` 下载路径，但在 `socket.getaddrinfo` 审计事件处被拒绝，未建立该下载连接；不能把这次运行描述为“依赖完全没有尝试联网”。

## 1. Baseline、固定来源与环境

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

## 2. 执行命令与阻断证据

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

## 3. 本地 fixture 与 Case A–F 状态

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

## 4. 离线边界与实际未执行内容

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

## 5. 结论、变更与回滚

本轮只确认固定 mini-swe 的安装 provenance 和顶层 import 版本仍正确，同时发现当前依赖/资源环境不能完成目标类的受限离线导入。**不能得出 parser 语义已实测稳定的结论。**

即使未来 Case A–F 全部 PASS，也只能证明固定 upstream 的 text-based parser 在这些输入下语义稳定且符合记录，不能证明 GPT/Claude/Gemini 都会稳定生成格式、smart-agi 支持这些模型、text-based 优于 native tools，或 RobotGen 已冻结正式 action protocol。

本轮不修复阻断；如果后续允许处理依赖离线资源，应单独明确验证范围，再在同一 upstream SHA 下复核。这里不自动进入该工作。

只新增本报告与 [mini_swe_text_parser_smoke.py](spikes/mini_swe_text_parser_smoke.py)。保留失败证据，以 `test: probe mini-swe text action parser` 提交并推送 `spike/mini-swe-text-parser`，不 merge。`git diff --check` 与相对 baseline 的文件范围检查应只覆盖这两个文件。审阅 REPAIR 仅修改这两者，不扩展到完整 Agent loop、Docker、真实 endpoint 或 RobotGen Harness。
