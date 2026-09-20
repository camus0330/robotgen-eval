# Gorilla Digital Bench v0.2：无需实物的机器人初步评测

**本版只用设计文件和计算，评测 AI 生成的机器人是否具备合理几何、名义装配接口、可执行动作、仿真驱动裕量及可复现证据。无需打印、接电机或提供实测数据。**

依据用户的 [装配验证研究报告](../../deep-research-report.md)，将上一版混合数字/实物验证的框架分为两个层次：**20项可执行的核心初评**，以及**8项扩展数字装配覆盖检查**。温升、真实疲劳、实装精度、电气安全等另列后续阶段，不因没有实物数据扣核心分。扩展检查中的缺口不会被计为通过。

本次已实际执行核心20项：**18项通过、2项失败，核心初评分91/100**。8项扩展数字装配检查仍未闭环，因此**不能称为“完整虚拟装配验证通过”**。91分与v0.1的39分不是同一量表，不能解读为机器人能力提高52分。

## 先看这些文件

| 文件 | 内容 |
|---|---|
| [SAMPLE_REPORT.md](SAMPLE_REPORT.md) | 当前样例的具体结果与失败原因 |
| [results/digital/scorecard.csv](results/digital/scorecard.csv) | 核心20项逐项得分、判据、证据和范围，可用Excel打开 |
| [results/digital/scorecard.json](results/digital/scorecard.json) | 原始数值、Gate、代码哈希与结果 |
| [results/digital/extended_checks.csv](results/digital/extended_checks.csv) | 8项扩展检查的覆盖缺口，避免核心高分掩盖未完成项 |
| [digital_metrics.csv](digital_metrics.csv) / [digital_profile.json](digital_profile.json) | 新版核心指标、权重、门槛和范围 |
| [scope_mapping.csv](scope_mapping.csv) | 上一版30项逐项去向；未静默删除困难项目 |
| [runs/20260920/rebuild/rebuild_report.json](runs/20260920/rebuild/rebuild_report.json) | 从冻结源码开始的10阶段独立重建日志 |
| [runs/20260920/geometry_probes.json](runs/20260920/geometry_probes.json) | 85个接口BREP探针与螺钉长度链 |
| [runs/20260920/robustness_original/summary.json](runs/20260920/robustness_original/summary.json) | 实际完成的100组、200次扰动仿真 |
| [archive/v0.1/](archive/v0.1/) | 上一版文档、评分和历史证据快照 |

`results/gorilla8/` 保留旧量表的结果；当前应查看 `results/digital/`。旧文件仍在，不把历史39分覆盖成新版91分。

## 核心指标：20项，100分

| 维度 | 权重 | 可执行检查 |
|---|---:|---|
| CAD与数字装配 | 30 | DA01实体健康6；DA02制造网格4；DA03导出一致性5；DA04物料闭环5；DA05接口几何与工具孔5；DA06打印包络5 |
| 运动与任务 | 35 | DB01模型契约5；DB02腾足前荡6；DB03抬手挥动6；DB04采样CAD碰撞5；DB05跟踪误差5；DB06驱动约束4；DB07公开扰动4 |
| 工程数字初筛 | 20 | DC01局部结构6；DC02质量预算5；DC03关键螺钉长度链5；DC04实际限位裕量4 |
| 复现与审计 | 15 | DD01独立完整重建6；DD02本次版本绑定5；DD03结果和边界披露4 |

所有主指标都由脚本读数据判定。PASS获得该项权重，FAIL得0。完整数值门槛在 `digital_metrics.csv`、`digital_profile.json` 及继承的动作 `profile.json` 中固定；没有为了让样例通过而放宽5°跟踪误差或0.1%扭矩饱和门槛。

FAIL必须带类型：

- `THRESHOLD`：已执行计算，实际结果未达到门槛。
- `MISSING_EVIDENCE`：要求的数字文件不存在，提交验收失败，不等于实物机械失败。
- `ERROR`：输入格式或计算出错，未产生可靠工程结论。
- 扩展表的 `COVERAGE_GAP`：现有报告明确只覆盖部分对象或工况。

本样例20个核心项都有测试证据，2个失败均为 `THRESHOLD`，没有靠将缺文件当作性能失败来凑齐结果。文件验证的退出码0仅表示评测过程正常完成；是否通过看评分卡。缺证据或程序错误返回2。

## 本次实际运行了什么

1. 在 `.tools/benchmark-venv` 建立可用的Python3.12环境，安装锁定的CAD、MuJoCo、FCL等依赖；原先复制的Python3.10虚拟环境保留。
2. 在独立目录冻结71个输入文件及其SHA-256，从源码重新生成CAD、正式前荡/挥手参考、URDF和MuJoCo模型。
3. 重跑12种零件的实体/网格回读检查、两项自由基座动力学、三份逐记录帧的完整现有CAD碰撞报告、20例局部结构计算。
4. 独立执行85个BREP孔位、支承环、工具孔探针；用CAD实体交集体积量取夹持厚度并复算horn/机壳螺钉进入与咬合长度。
5. 运行100组公开扰动，每组两项动作，共200次仿真；复核每次配置、模型/轨迹哈希及原始trace，不只读取一个总成功率。
6. 生成当前评分卡、扩展覆盖表和证据manifest；原始交付CAD和正式运动参数未改动。

完整重建不是“读取旧报告再显示PASS”。新产物位于 `runs/20260920/rebuild/gorilla8/`；输入、输出manifest均逐文件校验。原版与重建版动作误差及位移差异在约1e-13量级，远小于预登记0.1mm/0.1°复现容差。

## 固定任务与公平性

本profile限定8台XL330-M288-T、肩/肘/髋/膝全部pitch、无主动腕踝、外部5V供电。世界坐标+X前、+Y左、+Z上；CAD用mm，仿真用m/kg/s/rad。自由基座不得用root位置伺服、悬吊或回写root轨迹。材料及附件质量假设必须一致并披露。

- **前荡**：双掌真实模型接触力均>0.01N、双后足不接触且离地>2mm，连续≥0.5s；同一窗口内前移≥10mm；最后稳定落地。脚留地推进不算通过。
- **挥手**：左掌离地>50mm，另三垫有效接触，连续≥1s；肩、肘各跨度≥0.1rad，最后稳定落地。允许全pitch的矢状面挥动。
- **落稳**：尾段四垫接触、各力>0.01N、up_z>0.95、线速<0.02m/s、角速<0.2rad/s连续≥1s，无其他部位撑地。
- **控制**：2ms仿真步长、25Hz控制；峰值力矩≤0.100001N·m，饱和比例≤0.1%，限位支撑力矩≤0.001N·m；跟踪误差≤5°及root≤5mm。

门槛为本项目先导设计，不是行业标准，也尚未经过多机器人样本统计标定。当前形态、轴数、任务相同的其他AI输出可以比较；其他拓扑须另建profile，不能混排。

不同AI必须使用同一原始参考图、电机CAD、任务、材料/预算/工具权限、生成次数和评测版本。至少保留5次独立生成及所有失败尝试；同时报告模型精确版本、时间费用与人工修改。目录名不能证明模型身份，现有交付副本不能算第二个AI样本。单一样例91分不说明某个AI比另一个更强。

## 扰动评测及其解释

测试输入由 `make_public_cases.py`、种子20260918生成，保存在 `robustness_cases_public.jsonl`。各模型用完全相同case_id：

| 扰动 | 分布及实现 |
|---|---|
| 接触摩擦 | U[0.4,1.0]；同时改地面与机器人geom，避免max组合使修改失效 |
| 质量与惯量 | 同比例U[0.9,1.1] |
| 附件CoM | 35g机身附件位置三轴各U[-5,5]mm；通过平行轴定理重算机身CoM和惯量 |
| 伺服增益 | U[0.8,1.2] |
| 编码器零偏 | 8轴独立U[-1,1]°；作用于控制命令，不直接修改真实状态 |
| 额外指令延迟 | 0/20/40ms等概率，采用命令保持与延迟调度 |

这些是初筛压力测试假设，不是制造误差实测分布。参考动作和控制器冻结；前荡的原始准静态前馈不根据真实扰动重新求解，避免控制器获得不现实的参数真值。改变附件位置只改变动力学假设，不声称该位置的线束或安装结构已验证。

每组要求两动作都完成任务且满足驱动限制，至少90/100组通过才获得DB07分。当前19/100组通过，Wilson95%区间约12.5%–27.8%；仅看动作完成是75/100组。这个区间描述该设计在指定抽样分布下的仿真结果，不是实机成功概率，也不是AI模型之间的置信结论。

公开集可以用于开发；正式泛化比较须另由评测方保管同分布的隐藏集。调参必须冻结后重新跑全套并登记人工干预，不能挑选每项指标最好的不同版本拼成一个提交。

## 不被核心分数覆盖的数字装配项目

[extended_checks.csv](results/digital/extended_checks.csv) 对下列8项逐项执行了**证据覆盖检查**，当前均未闭环：完整公差链、完整装配/工具路径、全部新增紧固件实体、切片/支撑去除、包含完整BOM的静态干涉、连续扫掠与误差预算、全机完整载荷路径、线缆数字包络。

这些项目本身也可以不依赖实物开展；它们不因“没有实物”失败，而是当前设计包缺少相应数字模型或计算结果。`check_extended.py` 是覆盖审计器，不是假装已经实现了八种完整CAD/FEA求解器；即使放入同名文件，也不会自动给PASS。**核心91分与扩展验收未通过必须一起展示。**

这也是本版“初步评测”的边界。局部孔位可达不代表螺丝刀能完成整段插入，STL闭合/尺寸合适不代表支撑能拆，局部梁截面通过不代表整机刚强度通过，离散碰撞通过不代表帧间无碰撞。

实际温升、材料疲劳、真实标定、通电安全与实装质量则属于后续实机阶段；在本数字profile里不加分、不扣分、不宣称通过。

## 运行与复现

从工作区 `gpt_` 执行。重新评分已有数字结果只需要Python3.12标准库：

```bash
python3 gorilla8/benchmark/evaluate_digital.py
python3 -m unittest discover -s gorilla8/benchmark -p 'test_*.py' -v
```

用已恢复的环境，从当前设计建立**另一个新运行目录**并重跑全套：

```bash
PYTHONPATH='' .tools/benchmark-venv/bin/python gorilla8/benchmark/run_digital.py \
  --root gorilla8 \
  --run gorilla8/benchmark/runs/new_run \
  --out gorilla8/benchmark/results/new_run \
  --workers 3
```

中断后使用同一命令加 `--resume`；重建仅跳过该冻结输入已成功的阶段，接口/扰动/评分重新运行。选择新运行目录不会覆盖正式CAD或旧证据。`run_digital.py` 在数字检查本身失败但计算正常时仍保留结果；重建工具错误会中止并保留日志。

在另一台机器新建环境，可用Python3.12的venv并安装 [完整依赖锁](runs/20260920/environment.lock.txt)。本机系统缺ensurepip，因此恢复时先用 `python3 -m venv --without-pip`，下载PyPA官方 `get-pip.py` 到 `.tools/tmp/` 后仅在新虚拟环境内执行。不要直接复用旧 `.tools/venv` 的跨Python版本二进制包。核心脚本不需要连接电机，也不执行实物动作。

## 参考依据

风险分类依据用户原报告。接触参数与仿真接口实现核对了 [MuJoCo建模文档](https://mujoco.readthedocs.io/en/stable/modeling.html#contact-parameters) 和 [MuJoCo API](https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mj-setconst)。厂商接口尺寸由本地原厂STEP、[actuator_geometry.md](../docs/actuator_geometry.md) 与 [ROBOTIS手册](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/) 提供依据。官方资料不为本benchmark的权重或试行门槛背书。

同一版本不同提交的对照：

```bash
python3 gorilla8/benchmark/compare.py \
  /path/to/model_A/scorecard.json /path/to/model_B/scorecard.json \
  --out /path/to/comparison.csv
```

比较器拒绝混合量表、profile或评测器哈希不同的结果。各提交填写 [digital_submission.json](templates/digital_submission.json) 并保留原始生成日志；没有模型身份与相同预算的数据，只能比较两个设计文件包，不能据此排AI模型名次。
