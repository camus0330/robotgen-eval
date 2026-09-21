# mini-swe-agent full text action path smoke

**最终状态：PASS。** 2026-09-21，在本轮新准备的 tokenizer cache 下，真实 `DefaultAgent + LitellmTextbasedModel + LocalEnvironment` 完成 query → parse → shell → observation → second query → submit。completion 调用 2 次，两次实际 kwargs 均无 `tools`；真实 observation 进入第二次 query；原生 trajectory 校验通过。smoke exit code 为 **0**，runtime forbidden network attempts 为 **0**。

`litellm.completion` 是本轮唯一被替换的 provider boundary；`litellm.cost_calculator.completion_cost` 仅作为确定性 cost fixture，固定返回 `0.001`。其余 Agent、Model query / `_query`、text parser、Environment、observation formatter、submit sentinel 与 trajectory serializer 均使用真实固定 upstream 实现。

## 1. Baseline 与环境 provenance

| 项目 | 实际记录 |
|---|---|
| Repository | https://github.com/camus0330/robotgen-eval |
| Baseline | `bca9d08321b738e997fc592238505911d8d515aa`；创建新分支前已核对 HEAD |
| Branch | `spike/mini-swe-text-e2e` |
| Commit message | `test: probe mini-swe full text action path` |
| mini-swe repository | https://github.com/SWE-agent/mini-swe-agent |
| mini-swe SHA | `04d809ceab9df28f9adaed044884180159172930` |
| distribution / import version | `2.4.6` / `2.4.6` |
| LiteLLM / tiktoken | `1.102.0` / `0.14.0` |
| Python | `3.13.13`，Anaconda，`MSC v.1942 64 bit (AMD64)` |
| Platform | `Windows-11-10.0.26100-SP0`；AMD64 |
| venv | `C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv` |
| smoke PID | `29180` |

重新读取的 distribution `direct_url.json` 确认 URL 为 `https://github.com/SWE-agent/mini-swe-agent.git`，`commit_id` 与 `requested_revision` 均为上述完整 SHA。实际 import 路径均检查位于 `<venv>\Lib\site-packages\minisweagent`：

- `DefaultAgent`：`agents\default.py`。
- `LitellmTextbasedModel`：`models\litellm_textbased_model.py`。
- `LocalEnvironment`：`environments\local.py`。

复用既有 venv，没有升级、降级或重装依赖。脚本对当前版本做环境校验，**不表示这些版本已正式 production pin**；没有修改任何 dependency manifest。

## 2. 本轮 prepared cache 与命令

首先运行已审阅且未修改的 preflight：

```powershell
& 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe' -B -u model_comparison/spikes/mini_swe_offline_import_preflight.py
```

实际结果：prepare PASS、fresh offline import / constructor PASS、`FINAL: PASS`，整体 exit code `0`。parent / prepare / offline PID 分别为 `24604` / `8196` / `24464`；offline network events 为 `[]`。

| Cache 项目 | 本次实际值 |
|---|---|
| prepared cache path | `C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-fdvf8lm8` |
| cache 文件 | `9b5ad71b2ce5302211f9c61530b329a4922fc6a4` |
| 大小 | `1,681,126` bytes |
| SHA-256 | `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7` |
| preparation resource | `https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken` |

只有 preflight preparation 使用 tiktoken 原生 loader 获取公开 tokenizer 资源。这属于环境资源准备，不是模型推理网络访问。缓存仍在工作树外，不进入 Git。

随后执行本轮 smoke：

```powershell
& 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe' -B -u model_comparison/spikes/mini_swe_text_e2e_smoke.py --cache 'C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-fdvf8lm8'
```

smoke 检查目录、cache 文件及 SHA-256，设置 `CUSTOM_TIKTOKEN_CACHE_DIR`；不手工设置 `TIKTOKEN_CACHE_DIR`，而是在 import 后检查 LiteLLM 原生选择结果。smoke 内没有 downloader，也没有联网 fallback。

## 3. Fixture 与真实执行路径

参照固定 upstream 的 `tests/models/test_litellm_textbased_model.py` 所采用的 completion patch 边界，fixture 仅用 `SimpleNamespace` 提供 message content、finish_reason=`stop` 和 `model_dump()` 所需结构。两条 response 的 content 分别为：

````text
First execute the marker.

```mswea_bash_command
echo robotgen_text_e2e
```
````

````text
Now submit.

```mswea_bash_command
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT&&echo robotgen_text_submission
```
````

fixture 不含 `extra.actions`，未预解析 action。`model_dump()` 返回独立的 payload 副本，避免 query 添加 extra 后污染输入 fixture；没有 parser、observation 或执行逻辑。completion fixture 在每次调用时深拷贝真实 kwargs，保留当时的 context，并与实际 mock call kwargs 对照。

真实模型使用 `model_name="robotgen/offline-text-e2e"`、默认 cost tracking，没有覆盖 regex 或错误模板。实际确认默认 regex 为：

```text
r"```mswea_bash_command\s*\n(.*?)\n```"
```

真实 `LocalEnvironment.cwd` 为新建的 `C:\Users\hp\AppData\Local\Temp\robotgen-text-e2e-envelkri`。真实 Agent 使用最小 system template `Offline RobotGen text-path integration smoke.`、instance template `{{task}}`，`step_limit=4`、`cost_limit=1.0`；这些仅配置成功路径上限，本轮不测试 limits。`output_path` 为该目录下 `native.traj.json`。没有使用默认 SWE prompt。

| 链路检查 | 本次实际结果 |
|---|---|
| completion call count | `2` |
| call 1 kwargs keys | `['messages', 'model']`；`tools` 不存在 |
| call 2 kwargs keys | `['messages', 'model']`；`tools` 不存在 |
| 第一条 assistant 的 parsed action | `[{"command": "echo robotgen_text_e2e"}]` |
| 第一条真实 observation role | `user` |
| observation returncode / exception_info | `0` / 空字符串 |
| observation raw_output | `robotgen_text_e2e\n`（实际末尾换行） |
| 第二次 completion context | 包含 user-role message，content 与真实第一次 observation 完全相等 |
| 第二条 assistant 的 parsed action | `[{"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT&&echo robotgen_text_submission"}]` |
| 最终 exit_status | `Submitted` |
| submission | `robotgen_text_submission\n`（实际末尾换行） |
| agent.n_calls | `2` |
| agent.cost | `0.002` |
| completion_cost fixture call count | `2`，分别收到对应真实 query response 和 model name |

第一次 observation 的实际 content 为：

```text
<returncode>0</returncode>
<output>
robotgen_text_e2e
</output>
```

两条命令确实由真实 `LocalEnvironment.execute()` 启动。当前 Windows 环境使用 `C:\WINDOWS\system32\cmd.exe /c`，并非 Linux bash；两个命令均使用 shell 内建 echo。审计观察到两次 Popen，cwd 均为上述临时目录，命令分别精确对应两个 fixture。没有手工构造 observation，也没有直接调用 `_check_finished`；第二个 shell 输出由 upstream sentinel 逻辑触发 `Submitted`。

## 4. 原生 trajectory 与网络证据

原生 trajectory 路径：`C:\Users\hp\AppData\Local\Temp\robotgen-text-e2e-envelkri\native.traj.json`。以下全部实际校验通过：

- `trajectory_format == "mini-swe-agent-1.1"`。
- `info.exit_status == "Submitted"`，`info.submission` 精确包含末尾换行。
- `info.model_stats.api_calls == 2`，`instance_cost == 0.002`。
- `info.config.agent_type == "minisweagent.agents.default.DefaultAgent"`。
- `info.config.model_type == "minisweagent.models.litellm_textbased_model.LitellmTextbasedModel"`。
- `info.config.environment_type == "minisweagent.environments.local.LocalEnvironment"`。
- 保存的 messages 与 agent.messages 完全一致，角色顺序为 `system, user, assistant, user, assistant, exit`，包含两条 parsed actions、真实 observation 和最终 exit。
- 两条 assistant 的 `extra.response` 与对应 fixture 的完整序列化 payload 相等，`extra.cost` 均为 `0.001`。

仅使用 upstream 的 trajectory 写入，没有 RobotGen 自有 transcript schema。这里验证真实 query 路径经过 cost accounting，不是 token/cost benchmark。

第三方模型 import 前安装 fail-closed Python audit hook，拒绝并记录 DNS、socket connect/send、HTTP connect/send 和敏感配置文件打开。Popen 仅允许这两条确定性命令按顺序在临时 cwd 运行；该检查是副作用边界，不替换 Environment 或调度 action。Python hook 不注入子 shell；本次允许的子 shell 仅执行上述内建 echo 命令，没有网络程序或子脚本。

导入前按环境变量名字删除非白名单项，不读取被删除的 credential 值。`MSWEA_GLOBAL_CONFIG_DIR` 指向新空目录，`PYTHON_DOTENV_DISABLED=1`、`MSWEA_SILENT_STARTUP=1`、`LITELLM_MODE=PRODUCTION`、`LITELLM_LOCAL_MODEL_COST_MAP=True` 防止个人配置和远程 cost map 加载。没有读取 `.env`、实际 api_config.json 或 API key，也没有输出完整环境变量。

实际 summary：

```text
completion calls=2; native tools passed to completion=False
first parsed action=PASS
real observation=PASS
second call contains observation=PASS
exit_status=Submitted; submission='robotgen_text_submission\n'
agent.n_calls=2; agent.cost=0.002; completion_cost calls=2
trajectory=PASS
forbidden accesses=[]
forbidden network attempt count=0
FINAL: PASS
```

smoke exit code 为 `0`。本次完整日志保存在 `<venv 的父目录>\text-e2e-preflight.log` 和 `text-e2e-smoke.log`，均在 Git 工作树外。

## 5. 结论、范围与回滚

**PASS 只能说明：固定 mini-swe upstream 的 text-based generation path，在确定性 LiteLLM response fixture 下，可以通过真实 Agent、Model query、text parser、LocalEnvironment、observation feedback 和 submission 完成完整离线闭环。**

| 审阅问题 | 答案 |
|---|---|
| 是否调用真实 LLM API | 否 |
| 是否读取 API key | 否；未读取 SMART_AGI_API_KEY、OPENAI_API_KEY、ANTHROPIC_API_KEY 或 GEMINI_API_KEY |
| 是否 patch completion | 是，唯一 provider boundary；另有 completion_cost 确定性 fixture |
| 是否 patch query / `_query` / parser | 否 |
| 是否 patch Agent / Environment / observation / serializer | 否 |
| 是否 runtime 联网 | 否，forbidden network attempts 为 0；仅 preflight preparation 获取 tokenizer |
| 是否执行 shell | 是，只执行本轮允许的两条固定 echo 命令 |
| 是否测试 native tools | 否；仅检查两次 text completion 实际 kwargs 无 tools |
| 是否冻结 text-based protocol | 否 |

不能据此说明 smart-agi endpoint 兼容、真实模型稳定输出该格式、text-based protocol 已正式冻结、native tools 已被淘汰、Docker sandbox 或 production Harness 已完成。

没有测试 FormatError recovery、malformed response、retry、API failure、limits、wall-time、hard deadline、Docker、真实模型、图像、CAD、submission adapter、benchmark 或 feedback rounds。没有创建 AgentLoop、ModelAdapter、parser、dispatcher、formatter 或 provider client。

本轮只新增本报告和 [mini_swe_text_e2e_smoke.py](spikes/mini_swe_text_e2e_smoke.py)，推送指定分支，不 merge。REPAIR 仅修改这两个文件；不修改既有 spike、Prompt、protocol、requirements 或 benchmark，也不扩展到下一阶段。
