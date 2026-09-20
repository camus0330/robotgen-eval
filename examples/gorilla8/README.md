# Gorilla8：8 轴 pitch 猩猩机器人制造包

依据仓库 [`data/reference.png`](../../data/reference.png) 设计，使用 **8 台 XL330-M288-T**：左右肩、肘、髋、膝各一台，全部为 pitch。手腕、脚踝、头和躯干没有额外电机。原图的长臂外形与猩猩面部保留为设计参考，关节配置按本次要求重新设计。

交付内容是可编辑 STEP、逐件 STL、实际装配、BOM、图纸和两项动作的模型验证。**动作 1 要求双后足同时离地、双掌承重向前转移并稳定落脚；保足推进不算通过。** 当前验收结论以 [release_status.json](reports/release_status.json) 为准。尚未进行实物打印、装配或通电试验。

当前模型估计装配质量 **560.58 g**。自由基座仿真中，前荡双脚同时悬空 **6.96 s**，期间前移 **20.99 mm** 后稳定落脚；挥手最高掌面离地 **118.96 mm**。两项动作均通过记录帧的完整 CAD 碰撞检查，实际接触载荷的局部承力截面筛查也通过。该结果对应一次前荡，并不证明连续循环行走或实物性能。

## 查看与制造

下列文件由源码生成，默认位于本目录的 `output/`，不会提交到 Git：

- [装配图](output/renders/neutral_three_quarter.png)、[前荡](output/renders/palm_swing_three_quarter.png)、[挥手](output/renders/wave_three_quarter.png)
- [爆炸图](output/renders/exploded.png)、[打印件平铺图](output/renders/print_parts_layout.png)
- [整机 STEP](output/assembly/gorilla8_neutral.step)、[整机 GLB](output/assembly/gorilla8_neutral.glb)
- [逐件 STL](output/parts/stl/)、[逐件 STEP](output/parts/step/)、[数量与尺寸](output/parts/parts.csv)
- [采购 BOM](bom.csv)、[制造装配说明](docs/manufacturing.md)、[供电布线](docs/wiring.md)、[接口图纸](output/drawings/interfaces.pdf)
- [前荡仿真视频](output/simulation_runs/flat_palm_swing_release/simulation.mp4)、[挥手仿真视频](output/simulation_runs/flat_palm_wave_release/simulation.mp4)
- [URDF](output/simulation/gorilla8.urdf)、[MuJoCo](output/simulation/gorilla8.xml)、[控制契约](output/simulation/contract.json)

10 种正式打印件共 **17 件**，另有 2 种原厂电机接口试片。STEP、STL 的单位为 mm；GLB、URDF、MuJoCo 为 m。打印 STL 已转到推荐朝向并落台，保持 100% 比例；它们不是装配原位坐标，装配使用 STEP 或 `output/meshes/`。

PETG 承力件，TPU 95A 掌/足垫。前掌为固定的 65 × 34 mm 平底、4 mm 宽加强筋及 2 mm TPU 胶接鞋底；后足保留 R12 滚动接触面。没有新增腕关节。电机使用原厂 horn/idler 双侧支承，需另外采购 FPX330-H101 idler 两包。整机外部 5 V 供电、PC/U2D2 控制；本版不含机载电池。预计装配质量和明确附件余量见交付状态及质量表。

## 机械与数据契约

`src/design.py` 定义尺寸、命名、轴向和顺序。世界系 X 向前、Y 向左、Z 向上，全部关节正轴为 +Y。前链 60 + 76 mm，后链 55 + 52 mm。中立 root=(0,0,147.08846518) mm，左右肩/肘=-10°/+10°，左右髋/膝约21.49544°/-33.22632°。

| ID | 关节 | 名义限位（度） |
|---:|---|---|
| 1 | left_shoulder_pitch | -135 … +12 |
| 2 | left_elbow_pitch | -12 … +125 |
| 3 | right_shoulder_pitch | -135 … +12 |
| 4 | right_elbow_pitch | -12 … +125 |
| 5 | left_hip_pitch | +5 … +85 |
| 6 | left_knee_pitch | -125 … -5 |
| 7 | right_hip_pitch | +5 … +85 |
| 8 | right_knee_pitch | -125 … -5 |

肘关节在前荡中允许少量反向过伸，髋连接桥与肩内叉避让已相应修改。限位不是实体挡块，不代表任意关节组合均无碰撞。正式动作留出限位余量，仿真还检查是否借助限位约束承载。电机编码器的零位、左右符号必须按装配说明标定，不能把表中相对角直接发给电机。

正式解析参考为 `flat_palm_swing` 和 `flat_palm_wave`。前者是一次双掌支撑的腾足前荡并落稳，尚未提供重复循环换掌步态；后者是在矢状面抬手并前后挥动，全部 pitch 的结构没有侧向肩外展。参考 25 Hz；MuJoCo timestep=0.002 s、decimation=20、控制25 Hz，无 RL policy。joint为rad，root为m，四元数wxyz，没有来源视频/mocap FPS、隐式缩放或 root 重对齐。

## 复现

以下命令从仓库根目录执行，脚本按自身位置解析路径。输入资产位于 `data/`，派生产物写入本示例的 `output/` 和 `reports/`。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

.venv/bin/python examples/gorilla8/src/build_robot.py
.venv/bin/python examples/gorilla8/src/plan_flat_palm_motion.py
.venv/bin/python examples/gorilla8/src/export_simulation.py
.venv/bin/python examples/gorilla8/src/verify_exports.py
.venv/bin/python examples/gorilla8/src/verify_assembly.py \
  --motion flat_palm_swing --motion flat_palm_wave --exhaustive-exact \
  --report examples/gorilla8/reports/flat_reference_collision.json
.venv/bin/python examples/gorilla8/src/make_drawings.py
```

需要可用的 EGL/OpenGL、`ffmpeg` 和 `ffprobe`。动力学、实际轨迹碰撞和媒体检查步骤见 [simulation.md](docs/simulation.md)，参考文件格式见 [motion_pipeline.md](docs/motion_pipeline.md)。动作和媒体检查完成后，复算实际局部载荷，再汇总与打包：

```bash
.venv/bin/python examples/gorilla8/src/audit_strength.py \
  --simulation-result examples/gorilla8/output/simulation_runs/flat_palm_swing_release/result.json \
  --simulation-result examples/gorilla8/output/simulation_runs/flat_palm_wave_release/result.json
.venv/bin/python examples/gorilla8/src/finalize_release.py
.venv/bin/python examples/gorilla8/src/package_release.py
```

汇总入口读取实际报告；打包要求制造导出、局部载荷筛查与两项动作均通过。

## 目录与证据边界

`src/` 为参数 CAD、动作与验证入口；`docs/` 为制造及数据说明；生成后的 `output/parts/`、`assembly/`、`meshes/` 为制造几何，`output/motions/` 是参考，`simulation_runs/` 是实际仿真，`renders/`、`drawings/` 为实际几何图；`reports/` 保存已筛选的审计证据及新生成的诊断。

`plan_motion.py` 和 `plan_palm_swing.py` 是旧圆弧前掌方案的规划入口，不能用于当前平掌。前期圆掌失败、短行程候选和过零避让探针均是历史诊断，不能与正式交付状态混用。最终压缩包只选取正式两项动作与正式仿真目录。

正式件要求单一连续有效 STEP 实体、闭合 STL，回读体积与源 CAD 一致。碰撞检查覆盖记录的参考/实际帧，采用网格筛查及 BREP 交叠复核；不含帧间连续扫掠、新增螺钉和柔性线束实体。MuJoCo 采用近似接触及未标定的位置伺服，不能取代实物制造和热验证。0.10 N·m 是设计估算目标，非实测热额定；试片、胶接、塑料螺纹、打印方向、线束及温升检查见制造说明。
