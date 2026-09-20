# RobotGen Eval

RobotGen Eval 是面向 AI 生成机器人方案的可复现数字测评工程。仓库提供 Gorilla8 示例设计、无需实物的数字初评脚本、多模型实验协议，以及统一的输入和提交格式。

当前数字初评分为 20 项、100 分，覆盖 CAD 与数字装配、运动与任务、工程数字初筛、复现与审计。温升、疲劳、实装精度和通电安全等仍需要后续实物验证；数字高分不代表完整制造验收通过。

## 目录

```text
configs/benchmark/       指标、阈值、运动 profile、扰动样本和提交模板
data/                    参考图、XL330-M288-T STEP 及解析所需元数据
docs/                    评测说明、样例报告和研究资料
examples/gorilla8/       Gorilla8 参数化设计源码、BOM、文档和审计证据
model_comparison/        多模型实验协议、冻结输入、提交槽位和验收工具
scripts/benchmark/       评分、重建、仿真、几何检查和结果比较脚本
tests/benchmark/         数字评测回归测试
```

`outputs/`、`results/`、虚拟环境和运行缓存均为本地生成物，不进入 Git。历史完整输出可从整理前提交 `eee1f82` 恢复。

## 安装

推荐 Python 3.12。基础验收和单元测试只依赖标准库；完整 CAD 与 MuJoCo 重建需要安装全部依赖。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

完整锁定环境见 [`configs/benchmark/environment.lock.txt`](configs/benchmark/environment.lock.txt)。CAD/仿真还需要可用的 EGL/OpenGL、`ffmpeg` 和 `ffprobe`。

## 快速验证

从仓库根目录执行：

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s model_comparison/tests -v
python3 model_comparison/tools/experiment.py verify-inputs
```

这些命令验证评分逻辑、缺失证据处理、提交文件契约及冻结输入哈希，不执行耗时的 CAD 重建或仿真。

## 运行数字评测

使用已安装完整依赖的解释器运行一次隔离重建、两项动作仿真、扰动测试和评分：

```bash
python scripts/benchmark/run_digital.py \
  --root examples/gorilla8 \
  --run results/runs/demo \
  --out results/digital/demo \
  --workers 3
```

中断后可在同一命令末尾加 `--resume`。脚本把冻结输入、重建产物、日志和评分写入 `results/`，不会覆盖示例源码。

只审计已有提交证据时可运行旧量表适配器：

```bash
python scripts/benchmark/evaluate.py \
  --root /path/to/submission \
  --out results/submission_name
```

比较同一评测版本的多个评分卡：

```bash
python scripts/benchmark/compare.py \
  results/model_a/scorecard.json \
  results/model_b/scorecard.json \
  --out results/comparison.csv
```

## 指标说明

| 维度 | 权重 | 主要检查 |
|---|---:|---|
| CAD 与数字装配 | 30 | 实体健康、网格、导出一致性、BOM、接口几何、打印包络 |
| 运动与任务 | 35 | 模型契约、前荡、挥手、碰撞、跟踪误差、驱动约束、公开扰动 |
| 工程数字初筛 | 20 | 局部结构、质量预算、螺钉长度链、限位裕量 |
| 复现与审计 | 15 | 独立重建、输入/输出哈希、边界披露 |

指标、权重和阈值分别定义在 [`digital_metrics.csv`](configs/benchmark/digital_metrics.csv)、[`digital_profile.json`](configs/benchmark/digital_profile.json) 和 [`profile.json`](configs/benchmark/profile.json)。详细边界见 [数字评测说明](docs/benchmark/README.md)。

## 多模型评测流程

1. 阅读 [`TASK_SPEC.md`](model_comparison/TASK_SPEC.md)、[`PROMPT.md`](model_comparison/PROMPT.md) 和 [`EXPERIMENT_PROTOCOL.md`](model_comparison/EXPERIMENT_PROTOCOL.md)。
2. 为所有模型冻结相同的版本、预算、工具权限和输入快照。
3. 先各执行一次 pilot，协议稳定后再执行每个模型五次 formal。
4. 每次保留原始日志，填写 `submission.json` 与 `design_manifest.json`。
5. 使用 `experiment.py validate` 验收提交文件，再使用同一版本 benchmark 评分。
6. 同时报告失败尝试、成本、耗时、人工修改和模型精确版本；不能只挑选最佳结果。

详细命令见 [多模型工作包](model_comparison/README.md)。当前仓库只准备了 18 个尝试槽位，尚未生成跨模型质量排名。

## 凭据与安全

不要提交 `.env`、API key、token、私钥或带真实凭据的 `api_config.json`。使用 [`model_comparison/.env.example`](model_comparison/.env.example) 中的环境变量名，并从 [`api_config.example.json`](model_comparison/templates/api_config.example.json) 创建本地配置。仓库的 `.gitignore` 会排除常见凭据文件和本地生成物。

Gorilla8 的设计、制造和仿真说明见 [`examples/gorilla8/README.md`](examples/gorilla8/README.md)。
