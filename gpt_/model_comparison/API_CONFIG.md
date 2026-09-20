# 中转站 API 配置说明

已在3次预跑和15次正式尝试目录分别创建 `api_config.json`，共18份。它们使用本项目的JSON配置格式；当前文件验收工具 `experiment.py` 尚未读取这些配置，也没有实现模型调用器或工具执行循环。

## 填写方式

每个配置中的 `model` 填写中转站实际支持的精确模型ID，`api_key` 留空待本地填写。也可以在启动未来调用器的进程环境中设置 `SMART_AGI_API_KEY`，使所有配置使用同一个密钥；约定非空环境变量优先于配置内密钥。`.env.example` 仅为模板，当前没有自动加载 `.env` 的机制。

同一个槽位在pilot和formal的6份配置应使用相同的模型ID、参数与调用方式。不要把 `model_A`、`model_B`、`model_C` 当作服务端模型名称。模型ID和调用设置确认后，还需同步到 `protocol.json`，并按主README重新准备/冻结公开输入；不要把密钥复制进实验协议。

| 字段 | 当前值或用途 |
|---|---|
| `base_url` | `https://big-model.smart-agi.com`，原样保留用户提供的站点地址 |
| `api_path` | `/v1/chat/completions`，待核验的OpenAI兼容接口候选 |
| `api_format` | `openai_chat_completions`，待中转站说明确认 |
| `endpoint_verified` | `false`，未做带凭据的连通性或模型测试 |
| `api_key` | 空字符串，待填 |
| `api_key_env` | `SMART_AGI_API_KEY` |
| `model` | 空字符串，待填实际模型ID |
| `request.timeout_s` | 600秒，单次请求超时建议值 |
| `request.max_retries` | 0，默认不进行隐式重试，便于记录实际尝试 |
| `request.temperature/top_p/max_tokens/seed` | null表示暂未指定；未来调用器应省略这些参数，不能原样发送null |
| `experiment.wall_time_budget_s` | 3600秒，沿用现有预跑预算建议 |
| `experiment.max_feedback_rounds` | 2轮，沿用现有协议 |

## 路径与接口

所有 `paths` 字段相对 `api_config.json` 所在目录解析，移动整个项目不会失效。`prompt`与`input_dir`指向统一的输入包；日志与首次输出保存在各自尝试目录。

用普通HTTP客户端时，候选请求地址为 `base_url.rstrip('/') + api_path`。若后续使用会自行追加 `/chat/completions` 的兼容SDK，则SDK的base URL应含 `/v1`，不要再追加完整的 `api_path`。本次仅创建配置，没有接入SDK，也未验证服务支持的协议、模型、工具调用或图像输入。实际支持情况以中转站提供的接口说明为准；若采用Responses或其他原生协议，应同时调整格式和路径。

密钥和模型为空时，未来调用器应直接报缺配置，不能带空凭据重试。日志中应移除Authorization、API密钥及其他认证头。这里的协议配置不会自动赋予模型读取STEP、执行CAD或运行仿真的能力；这些由后续统一工具环境实现。

## 文件位置

- 预跑：`submissions/pilot/model_A/01/api_config.json`，B/C同理。
- 正式：`submissions/formal/model_A/01/api_config.json` 至 `05/api_config.json`，B/C同理。
- 无密钥模板：`templates/api_config.example.json`。

18份配置初始权限为仅当前用户可读写，`.gitignore`排除实际配置和.env文件；共享模板不含密钥。配置检查记录见 `records/api_config_check.json`。
