# 多模型机器人设计测评工作包

本目录将现有 Gorilla8 数字初评整理成可执行的多模型实验准备流程。研究对象是 **相同任务与预算下，模型生成机器人结构及控制方案的能力**。材料来源为本地会议纪要与现有 benchmark；会议中的模型优胜预期不是实验结论。

**当前状态：任务书、提示词、提交协议、18次尝试计划、输入资料包和验收工具已建立；未调用模型，未生成跨模型工程分数。现有工程评测器仍需适配。**

## 从这里开始

1. 阅读 [统一任务书](TASK_SPEC.md) 和 [实验协议](EXPERIMENT_PROTOCOL.md)。本轮默认8台 XL330-M288-T、结构与控制联合生成。
2. 在 [protocol.json](protocol.json) 填入三个模型的精确版本、调用方式和相同工具环境。默认预算是试运行建议，正式实验前锁定。
3. 查看 [评测器适配审计](ADAPTER_AUDIT.md)。新模型的合理设计不能直接套旧版固定坐标探针评分。
4. 把 `inputs/` **单独复制到干净工作区**，为每次尝试运行同一份 `inputs/PROMPT.md`。不要把本项目完整目录交给参评模型，否则它能看到现有答案与后续评测资料。
5. 每个模型先做1次 pilot；修改协议或评测器后重新冻结，再做每个模型5次 formal。目录已按此建立；空模板均为 `NOT_STARTED`。
6. 保存模型输出及原始日志，填写 `submission.json` 与 `design_manifest.json`，运行下列验收。验收只核对文件和声明，不等于工程通过。

从仓库根目录执行（Python 3.12 标准库即可）：

```bash
# 检查所有公开输入是否与本次快照一致；含文件清单增删检查
python3 model_comparison/tools/experiment.py verify-inputs

# 空模板会返回退出码2，这是正常的未完成状态
python3 model_comparison/tools/experiment.py validate model_comparison/submissions/pilot/model_A/01

# 只检查路径与命名映射，不执行模型生成的代码
python3 model_comparison/tools/experiment.py validate model_comparison/submissions/pilot/model_A/01 --out /tmp/model_A_intake.json

# 查看全部18次尝试的文件验收状态；不会生成虚假的质量排名
python3 model_comparison/tools/experiment.py inventory --out /tmp/model_comparison_inventory.csv

# 首次实验开始前，填全配置后归档旧输入并更新输入包和18份空元数据
python3 model_comparison/tools/experiment.py refresh-inputs --archive-label initial_draft

# 输入包复核后，写出新的协议冻结快照（拒绝覆盖）
python3 model_comparison/tools/experiment.py freeze --out model_comparison/records/protocol_freeze_v1.json

# 验收工具回归测试
python3 -m unittest discover -s model_comparison/tests -v
```

`tools/experiment.py prepare-inputs` 可在全新位置建立输入包，但拒绝覆盖现有 `inputs/`。首次尝试开始前可用 `refresh-inputs` 归档草稿；任何尝试开始后均拒绝此操作。如要改规则，应建立新版本目录，保留旧输入和对应尝试记录。

## 文件导航

| 文件/目录 | 用途 |
|---|---|
| `TASK_SPEC.md` / `PROMPT.md` | 统一任务与可直接交给模型的提示词 |
| `SUBMISSION_SPEC.md` / `templates/` | 提交协议、设计映射与元数据模板 |
| `EXPERIMENT_PROTOCOL.md` / `protocol.json` | 预算、重复次数、反馈、失败处理与冻结规则 |
| `ADAPTER_AUDIT.md` / `records/adapter_audit.csv` | 现有代码依赖的逐项审计与验收条件 |
| `inputs/` | 原图、电机STEP、阈值、协议和模板的独立公开输入包 |
| `records/input_manifest.json` | 公开输入逐文件SHA-256 |
| `records/source_snapshot.json` | 被审计源文件哈希，只供评测方使用 |
| `records/attempts.csv` | 3个模型各1次预跑和5次正式生成的计划 |
| `submissions/` | 18个独立尝试目录，内含空模板 |
| `records/results_template.csv` | 每次生成一行，质量结果留空 |
| `REPORT_TEMPLATE.md` | 主表、失败分析及论文文字模板 |
| `tools/experiment.py` | 准备输入、验收、冻结、状态汇总 |

现有91分和19%扰动成功率仅作为旧样例背景，不进入这里的正式结果。原目录的脚本、结果、CAD均未修改。

## 中转站配置

已为18个尝试目录添加 `api_config.json`，使用 `https://big-model.smart-agi.com`，API密钥及精确模型ID待填。参见 [配置说明](API_CONFIG.md)。当前只完成配置文件；尚未连接中转站或接入自动调用器。
