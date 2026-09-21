# mini-swe-agent single FormatError recovery smoke

**最终状态：PASS。** 2026-09-21，真实固定 upstream `DefaultAgent + LitellmTextbasedModel + LocalEnvironment` 在一条 malformed response 后生成真实 FormatError feedback，将其送入下一次 completion context，再经合法 action、真实 observation 和第三次 query 完成 submit。smoke exit code 为 **0**，runtime forbidden network attempts 为 **0**。

**第一次 malformed response 消耗 model call 和 cost，但不执行 shell。** 最终 completion calls / `agent.n_calls` 为 `3`，shell executions 为 `2`，`agent.cost=0.003`，`agent.n_consecutive_format_errors=0`。本轮只有一次格式错误，不测试 repeated-error threshold。

## 1. Baseline 与 provenance

| 项目 | 实际记录 |
|---|---|
| Repository | https://github.com/camus0330/robotgen-eval |
| Baseline | `94459f9e888ce2b7650a744670ac94198e6a0a31`；建分支前已核对 HEAD |
| Branch | `spike/mini-swe-text-format-recovery` |
| Commit message | `test: probe mini-swe text format recovery` |
| mini-swe repository | https://github.com/SWE-agent/mini-swe-agent |
| mini-swe SHA | `04d809ceab9df28f9adaed044884180159172930` |
| distribution / import version | `2.4.6` / `2.4.6` |
| LiteLLM / tiktoken | `1.102.0` / `0.14.0` |
| Python | `3.13.13`，Anaconda，`MSC v.1942 64 bit (AMD64)` |
| Platform | `Windows-11-10.0.26100-SP0`；AMD64 |
| venv | `C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv` |
| smoke PID | `35536` |

本次重新读取 `direct_url.json`，确认 URL 为 `https://github.com/SWE-agent/mini-swe-agent.git`，commit_id 与 requested_revision 均为上述完整 SHA。实际类源码路径检查均通过，位于 `<venv>\Lib\site-packages\minisweagent` 下的 `agents\default.py`、`models\litellm_textbased_model.py` 和 `environments\local.py`。

没有升级、降级或重新安装依赖。版本断言只约束本次已审阅的实验环境，不是 production dependency pin；未修改 requirements 或其他 dependency manifest。

## 2. 本次 preflight 与执行命令

先运行已审阅且未修改的 preflight：

```powershell
& 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe' -B -u model_comparison/spikes/mini_swe_offline_import_preflight.py
```

实际 preflight `FINAL: PASS`，exit code `0`；prepare、fresh offline import / constructor 均通过。parent / prepare / offline PID 为 `30060` / `32452` / `18352`；offline network events 为 `[]`。

| Resource 项目 | 实际值 |
|---|---|
| prepared cache path | `C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-xy3pke7y` |
| cache 文件 | `9b5ad71b2ce5302211f9c61530b329a4922fc6a4` |
| 文件大小 | `1,681,126` bytes |
| SHA-256 | `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7` |
| preparation resource | `https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken` |

仅 preparation 使用 tiktoken 原生 loader 获取公开 tokenizer 资源，属于环境构建/资源准备，不是模型推理网络访问。cache 保存在 Git 工作树外。

实际 recovery smoke 命令：

```powershell
& 'C:\Users\hp\AppData\Local\Temp\robotgen-offline-agent-de53eee2e2ea4f1a88d777a566a5cb05\venv\Scripts\python.exe' -B -u model_comparison/spikes/mini_swe_text_format_recovery_smoke.py --cache 'C:\Users\hp\AppData\Local\Temp\robotgen-tokenizer-cache-xy3pke7y'
```

runtime 检查 cache 文件和 SHA-256，设置 `CUSTOM_TIKTOKEN_CACHE_DIR`，确认 LiteLLM 原生逻辑选用了相同目录；不手工设置 `TIKTOKEN_CACHE_DIR`，不下载 tokenizer，不 fallback 到联网。

## 3. 实验边界与输入

唯一 provider boundary patch 为 `litellm.completion`；另以 `litellm.cost_calculator.completion_cost -> 0.001` 作为确定性成本 fixture。未 patch Agent、Model query / `_query` / parser、FormatError handler、Environment、observation formatter 或 trajectory serializer。未人工调整 Agent cost、calls、messages 或 counter。

fixture 仅提供 `choices[0].message.content`、finish_reason=`stop`、message / response 的 `model_dump()` 结构，不含 `extra.actions`，不做解析。三个 response 顺序为：

1. Malformed content：`I will execute the command now, but this response intentionally contains no mini-swe action block.`，没有合法 fence。
2. `Recovery action.` 加一个 `mswea_bash_command` block，内容为 `echo robotgen_format_recovery`。
3. `Submit recovered result.` 加一个 `mswea_bash_command` block，内容为 `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT&&echo robotgen_recovery_submission`。

真实模型名为 `robotgen/offline-format-recovery`，默认 cost tracking；未覆盖默认 regex，实际断言为 `r"```mswea_bash_command\s*\n(.*?)\n```"`。

真实 Agent 使用 system template `Offline RobotGen FormatError recovery smoke.`、instance template `{{task}}`，`step_limit=5`、`cost_limit=1.0`、`max_consecutive_format_errors=3`。这些是单次恢复场景的配置，不测试 limits 或 threshold。环境 cwd / 原生 trajectory 目录为 `C:\Users\hp\AppData\Local\Temp\robotgen-text-format-recovery-7gyvp5g2`，输出文件为 `native.traj.json`。

## 4. FormatError、计费与恢复的真实证据

completion fixture 在每次调用入口只读保存实际 kwargs、Agent 状态和上一步原生 checkpoint；没有替代 handler、构造 observation 或提前解析 action。

| Completion 入口 | 已发生 shell launches | agent.n_calls | agent.cost | consecutive errors |
|---|---:|---:|---:|---:|
| 第一次，malformed response 返回前 | 0 | 1 | 0.000 | 0 |
| 第二次，FormatError 已由 Agent 处理 | 0 | 2 | 0.001 | 1 |
| 第三次，合法 recovery step 已完成 | 1 | 3 | 0.002 | 0 |
| 最终 Submitted 后 | 2 | 3 | 0.003 | 0 |

completion 入口的 n_calls 已包含当前即将返回的调用。为单独证明第一次错误也被计数，第二次 completion 入口读取的**上一步原生 checkpoint**实际为 `api_calls=1`、`instance_cost=0.001`，最后一条 message 正是 FormatError feedback。这也证明成本由真实 handler 累加，没有因 query 抛异常而丢失。

本次仅出现一个 `interrupt_type=FormatError` message。实际字段全部检查通过：

| 字段 | 实际值 |
|---|---|
| role | `user` |
| content | `Please always provide EXACTLY ONE action in triple backticks, found 0 actions.` |
| extra.interrupt_type | `FormatError` |
| extra.n_actions | `0` |
| extra.model_response | 与上面 malformed content 逐字符相同 |
| extra.cost | `0.001` |
| extra.response | 与第一个 synthetic response 的完整序列化 payload 相等 |

其中 persisted response 实际为：

```json
{"choices": [{"message": {"role": "assistant", "content": "I will execute the command now, but this response intentionally contains no mini-swe action block."}, "finish_reason": "stop"}]}
```

第二次 completion 的实际 `messages` 包含 role=`user` 且 content 与上述 feedback 完全相等的 message。Agent 内该 feedback 的完整 extra 和第一步 checkpoint 也一致。错误 assistant 文本并未作为独立 assistant message 加入序列，而是由真实 query 保存于错误 feedback 的 model_response / response。

| 恢复链路检查 | 实际结果 |
|---|---|
| completion calls / completion_cost calls | `3` / `3`；cost fixture 分别收到三个对应 response 与真实 model name |
| 三次实际 completion kwargs | 每次均为 `['messages', 'model']`，均不存在 `tools` |
| recovery parsed action | `[{"command": "echo robotgen_format_recovery"}]` |
| recovery observation | user role；returncode=`0`，exception_info 为空，raw_output=`robotgen_format_recovery\n` |
| 第三次 completion context | 包含与真实 recovery observation content 完全相等的 user message |
| submit parsed action | `[{"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT&&echo robotgen_recovery_submission"}]` |
| exit_status / submission | `Submitted` / `robotgen_recovery_submission\n` |
| agent.n_calls / cost / final consecutive errors | `3` / `0.003` / `0` |

实际 observation content：

```text
<returncode>0</returncode>
<output>
robotgen_format_recovery
</output>
```

最终 roles 与预期一致：`["system", "user", "user", "assistant", "user", "assistant", "exit"]`。没有修改框架以迎合角色顺序。真实 `LocalEnvironment` 在当前 Windows 上使用 `C:\WINDOWS\system32\cmd.exe /c` 执行两条固定 echo 命令，不是 Linux bash；没有手工填入 shell observation 或 submission。

## 5. Trajectory 与 runtime 网络边界

原生 trajectory 位于 `C:\Users\hp\AppData\Local\Temp\robotgen-text-format-recovery-7gyvp5g2\native.traj.json`，实际校验通过：

- `trajectory_format == "mini-swe-agent-1.1"`。
- `info.exit_status == "Submitted"`，submission 保留末尾换行。
- `info.model_stats.api_calls == 3`，`instance_cost == 0.003`。
- messages 与 agent.messages 完全一致，包含初始 system/task、FormatError、recovery assistant、真实 observation、submit assistant 和 exit。
- FormatError 的 `model_response`、完整 `response`、`cost=0.001` 未丢失；两条合法 assistant response payload 与每次 `0.001` cost 也保留。
- 配置类型仍为真实 `DefaultAgent`、`LitellmTextbasedModel`、`LocalEnvironment`，未引入其他 wrapper 类型。

第三方 import 前安装 fail-closed Python audit hook，禁止并记录 DNS、socket connect/send、HTTP connect/send，以及 `.env` / `api_config.json` 打开。仅允许两个 fixture command 按顺序在专用临时 cwd 启动，而且第一次 completion 后不允许 shell；实际 Popen 记录和 completion 入口快照分别证明 malformed 后 0 次、recovery 后 1 次、最终 2 次执行。此审计仅限制副作用，不替代 dispatcher 或 Environment。

Python audit hook 不注入子 shell；本次允许的子 shell 只执行明确列出的内建 echo 命令，没有网络程序或子脚本。runtime 的 `forbidden accesses=[]`，`forbidden network attempt count=0`。

仅按环境变量名字移除非白名单项，不读取被移除的 credentials；使用全新空 global config、禁用 dotenv、使用随包 cost map。未读取 SMART_AGI_API_KEY、OPENAI_API_KEY、ANTHROPIC_API_KEY、GEMINI_API_KEY、个人 `.env` 或实际 api_config.json；未输出完整环境变量。

本轮实际 summary：

```text
completion calls=3
malformed response -> FormatError=PASS
shell launches after malformed=0
second call contains FormatError feedback=PASS
recovery parsed action=PASS
real recovery observation=PASS
third call contains observation=PASS
exit_status=Submitted
agent.n_calls=3
agent.cost=0.003
final consecutive format errors=0
shell launches total=2
trajectory=PASS
forbidden network attempt count=0
FINAL: PASS
```

exit code 为 `0`。完整日志保存在 `<venv 的父目录>\text-format-recovery-preflight.log` 与 `text-format-recovery-smoke.log`；cache、日志、trajectory 均在工作树外。

## 6. PASS 含义与范围

**本次 PASS 只能证明：固定 mini-swe text-based path 在一次 malformed text response 后，会按固定 upstream 语义把 FormatError 反馈给下一次 model context，并能在后续合法 response 下恢复、执行 action、收到 observation 并完成 submit。**

未调用真实 LLM API，未读取 API key；只 patch completion 和确定性 completion_cost，未 patch `_query`、parser、Agent、FormatError handler 或 Environment。malformed response 没有执行 shell；runtime 没有联网；未冻结 text-based protocol。

本结果不能证明真实模型会自我纠错、gateway 兼容、所有格式错误均可恢复、repeated-error threshold 已验证或 production Harness 已完成。没有测试多个错误、threshold、retry、transport/API failure、AuthenticationError、rate limit、limits、wall-time、hard deadline、Docker、真实模型、CAD、benchmark 或 feedback rounds。

本轮只新增本报告与 [mini_swe_text_format_recovery_smoke.py](spikes/mini_swe_text_format_recovery_smoke.py)，提交指定 commit message 并推送指定分支，不 merge。REPAIR 只修改这两个文件；不修改既有 spike、Prompt、protocol、requirements 或 benchmark，不进入下一阶段。
