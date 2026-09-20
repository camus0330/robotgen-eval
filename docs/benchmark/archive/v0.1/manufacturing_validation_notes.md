# 制造导出验证记录

本文件是整理前历史记录；当时全部项目读写位于 `gpt_/`。用户参考 PNG 与电机原始 STEP 未改写。以下失败均发生于生成/校核过程，不将中间失败文件作为最终打印件。

## CAD / 实体装配

- 初次 `build_robot.py` 返回 `RuntimeError: Invalid or disconnected print parts`，涉及胸壳连接耳、悬空托盘及曲面退化三角形。已连接承力体、清除零面积三角形。
- 42 mm 初选大腿导致叉架横桥穿入膝电机，BREP 共体积约 1295.94 mm³；最终大腿为 55 mm、髋位为 `(-20,±52,-33)`，再修肩横梁局部干涉。原始诊断见 `pre_fix_collision.json`。
- 最终参考路径有 568 帧 baseline 和独立 451 帧 palm_swing（两者都含中立帧）；最终精确结果读取各自 JSON，不使用旧质量或旧腿长的报告。

## 交付文件回读发现并修复的问题

1. Trimesh 默认的多壳法线修复把空心掌体内部三个 cavity shell 翻为正体积。例如 P03 的旧 STL 体积 25542.02 mm³，而 CAD 约 16999.15 mm³。已改为 `fix_normals(multibody=False)`，保留内部空腔的负向闭合壳。**一个正向外壳与若干负向空腔不等于多个脱离零件**；BREP 仍须单 solid。
2. 头壳内椭球与 z=8 颈口点相切，源体积 17694.20 mm³，旧 STEP 再导入错误变为 58227.28 mm³。最终颈口切至 z=10，形成有面积的开口；法兰仍保持原配合。修复后源体积 17461.66 mm³、STEP 回读 17461.71 mm³，拓扑与体积一致。
3. NURBS 的保守包围盒使旧头壳和胸壳 STL 离平台约 0.53 / 0.72 mm。现在按实际导出网格的最低点移到 z=0，所有打印 STL 已落床。
4. 胸壳是薄曲面，早期网格体积误差 2.20%；细化最终离散公差后再回读，达到脚本规定的 1.5% 网格体积误差上限。没有降低阈值绕过失败。

最后执行 `verify_exports.py` 返回 0，`export_readback.json` 中 `all_exported_parts_pass=true`、`failures=[]`。12 个 STEP 均 valid/单 solid，12 个 STL 均闭合、正体积、一个正向外壳；STEP 体积相对误差要求 <0.1%，STL 要求 <1.5%。URDF 恰有 8 个 revolute joint，轴均为 `0 1 0`。

验证脚本初次写 JSON 还曾报 `TypeError: Object of type int64 is not JSON serializable`；显式转换计数为 Python int 后重跑。写报告失败没有被当作几何通过。

最终质量 0.5220157988653644 kg；较前一轮减少约 0.295 g，来自头壳颈口拓扑修复。动作计划与最终动力学模型均已按新质量重算，空腔法线修复后的惯量也重新导出。

曾有一条 MuJoCo 加载发生在网格导出过程中，真实报错 `left_leg_motor_0_case.stl is empty`；停止并发读取，待全部 CAD 写完后重导出/加载成功。未将该工程错误记作动作失败。

动力学成功和失败分别见 `output/simulation_runs/final_simulation_summary.json` 与 `docs/simulation.md`。CAD 和打印文件通过不代表双掌腾空前荡或硬件验证已经通过。
