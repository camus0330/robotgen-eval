# 自由基座动力学与动作验收

正式模型质量 **0.5605794217046942 kg**，来自当前CAD、真实电机质量以及明确的线束/紧固件/电子件余量。`export_simulation.py` 导出URDF和MuJoCo；`simulate.py` 只驱动8个pitch关节，root自由，没有固定基座、root位置伺服或悬吊力。参考root只用于初始放置和误差统计，没有逐帧回写。

## 正式结果

| 动作与目录 | 结果 |
|---|---|
| flat_palm_swing_release | 15.88s完成；双掌实际承重、双后足同时净空超过2mm持续6.96s；该区间身体前移20.990mm，整段净前移21.022mm；最后四点稳定2.36s |
| flat_palm_wave_release | 14.88s完成；左掌最高净空118.961mm，在矢状面挥动后恢复接触；最后四点稳定3.56s |

两项均没有跌倒，没有关节限位额外承载，执行器仍限幅±0.10N·m。前荡使用匹配最终质量/压力中心的准静态力矩前馈，未启用pitch反馈；挥手使用纯位置PD。root峰误差分别约0.879mm、2.406mm。动作1是一次前荡并落稳，未提供循环换掌行走控制器。

实际仿真姿态用完整CAD重新逐帧检查：前荡398帧、挥手373帧均无正体积自交；非TPU件最低离地分别1.887mm、1.814mm，TPU最大地面压入分别0.138mm、0.208mm（检查容差0.5mm）。参考两动作加中立姿态共772帧也通过。报告为 `flat_reference_collision.json`、`flat_swing_simulation_collision.json`、`flat_wave_simulation_collision.json`。

正式视频均为H.264、yuv420p、25fps、faststart，已完整解码并实际查看动作中段及结束帧；它们是模型仿真视频，不是真机视频。

## 契约与模型假设

世界X前、Y左、Z上。joint顺序：左肩、左肘、右肩、右肘、左髋、左膝、右髋、右膝；全部正轴+Y。参考NPZ为25Hz，时间秒、关节rad、root位置m、四元数wxyz。没有源视频/mocap、重定向或比例缩放；CAD网格仅按0.001从mm转m。

| 项目 | 设置 |
|---|---|
| timestep / decimation / control frequency | 0.002s / 20 / 25Hz，无RL策略 |
| 位置执行器 | kp=2.0，kv=0.055，未经XL330实测标定 |
| 执行器限幅 | ±0.10N·m，不能把0.52N·m堵转值当持续能力 |
| 被动项 | damping=0.015，frictionloss=0.002，armature=0.000015，均为仿真假设 |
| 地面摩擦 | 0.8，未实测TPU与实际地面 |
| 初始稳定 | 1s |
| 惯量 | 实际CAD网格按组件质量缩放，并加入明确的附件质量余量 |

前掌地面碰撞体是与TPU鞋底一致的65×34×2mm盒体，局部末端坐标X[-45,20]、Y±17、Z[-12,-10]mm。后足仍近似为横向R12圆柱，肢体为胶囊、躯干为盒体。视觉使用实际CAD。MuJoCo内部自碰撞关闭，另由实际qpos驱动完整CAD进行检查；近似地面碰撞不能代表所有壳体落地方式或新增线缆/紧固件。碰撞检查是25Hz采样，不含采样之间的连续扫掠。

## 复现

先按README重建CAD与正式参考，再执行：

```bash
.venv/bin/python examples/gorilla8/src/export_simulation.py
.venv/bin/python examples/gorilla8/src/simulate.py \
  --motion examples/gorilla8/output/motions/flat_palm_swing/motion.npz \
  --out examples/gorilla8/output/simulation_runs/flat_palm_swing_release \
  --gravity-feedforward --render
.venv/bin/python examples/gorilla8/src/simulate.py \
  --motion examples/gorilla8/output/motions/flat_palm_wave/motion.npz \
  --out examples/gorilla8/output/simulation_runs/flat_palm_wave_release --render
```

实际CAD检查要求trace绝对路径，例如从仓库根目录：

```bash
.venv/bin/python examples/gorilla8/src/verify_assembly.py --exhaustive-exact \
  --simulation-trace "$PWD/examples/gorilla8/output/simulation_runs/flat_palm_swing_release/trace.json" \
  --report examples/gorilla8/reports/flat_swing_simulation_collision.json
.venv/bin/python examples/gorilla8/src/verify_assembly.py --exhaustive-exact \
  --simulation-trace "$PWD/examples/gorilla8/output/simulation_runs/flat_palm_wave_release/trace.json" \
  --report examples/gorilla8/reports/flat_wave_simulation_collision.json
```

媒体检查和代表帧导出：

```bash
.venv/bin/python examples/gorilla8/src/verify_media.py \
  --run examples/gorilla8/output/simulation_runs/flat_palm_swing_release --frames 4.8 8 15
.venv/bin/python examples/gorilla8/src/verify_media.py \
  --run examples/gorilla8/output/simulation_runs/flat_palm_wave_release --frames 4.92 7.16 14
```

相同输出目录重跑会替换其派生输出，留存对照须另选目录。`--hold-seconds`仅用于单帧参考，必须显式给正时长，不能将零时长判成静态保持成功。

`--gravity-feedforward` 核对同目录poses.json与NPZ的时间、关节、root及模型总质量后，将准静态力矩作为位置偏置 `ctrl=q_ref+tau_ff/kp`；不提高力矩限幅。此计算适配所用仿真位置伺服，不能直接当成真实XL330电流/位置标定。

`--balance-pitch` 是保留的诊断选项：向两肩目标叠加有界pitch/角速度反馈，没有root外力。正式两项动作不使用它。

## 输出和判据

`result.json` 保存真实时长、跌倒、误差、2ms步长力矩饱和/限位力、双掌支撑区间、稳定落脚和掌接触载荷。`trace.json`以25Hz保存实际root/wxyz/q、目标、CoM、法向力、CoP、掌足最低点及速度；仿真视频与media_check.json为独立媒体证据。`inputs/`保存该次输入记录，但XML中的网格路径仍依赖同一制造包的几何文件。

`completed=true`只表示达到时长且未触发跌倒条件。双掌前荡还要求：实际双掌承载且各法向力>0.01N，双后足各净空>2mm，无其他部位触地；存在至少80ms且前移>1mm的连续区间；整段不跌倒；末尾四垫实际承载、up_z>0.95、线速<0.02m/s、角速<0.2rad/s持续至少1s；关节限位额外力不得超过0.001N·m。最终结果远超过最小前移阈值，且限位力为0。

跌倒判据为up_z<0.5、root高度<55mm或状态非有限。位置/速度、摩擦与力矩阈值是本模型的检验条件，不是硬件认证。0.10N·m仍是设计估算；真实温升、齿隙、伺服特性、打印层刚度、胶层和电缆拖力未标定。

## 保留的失败与诊断

旧圆掌前后接触跨度约0.177mm，双后足卸载后失稳，详见 `reports/palm_failure_diagnosis.md`。旧制造包与证据保存在本地 `output/archive/before_flat_palms.zip`。

平掌短行程候选先验证了有限接触面积能稳定支撑。随后局部载荷审计发现前掌前缘2mm薄板的组合弯扭筛查不足，因此前缘改为3mm；肩梁进一步改为13mm高实心矩形，并与电机安装杯全高连接。几何、质量、参考、仿真与碰撞已全部按最终版重做，原成功设计归档于本地output/archive/flat_before_strengthening.zip。正式大行程纯PD对照保存在 `flat_palm_swing_final`：虽然没有跌倒，却出现两肩0.002803/0.001870N·m限位力，严格动作判据为false，不能混入正式成功证据。加入匹配质量的准静态前馈后，成功run为 `flat_palm_swing_release`，没有借用限位承载。几何探针的前期交叠、导出错误及修复记录也保留在reports，最终状态只引用当前正式报告。
