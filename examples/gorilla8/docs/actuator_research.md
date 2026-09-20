# XL330-M288-T 机械和电气接口核对

核对日期：2026-09-16。仅使用 ROBOTIS、JST 官方资料。本文件记录资料证据，不表示实物负载、温升或装配已经测试。

## 机械接口

实际查看了 [ROBOTIS X330 尺寸图](https://www.robotis.com/service/download.php?no=1986)（图签 28-May-20，单位 mm）。原件已保存为 [XL_XC_330_official.pdf](sources/XL_XC_330_official.pdf)，完整截图为 [XL_XC_330_drawing-1.png](sources/XL_XC_330_drawing-1.png)。

| 项目 | 官方图尺寸/规定 |
|---|---|
| 机身宽、高、前后壳面距离 | 20 × 34 × 23 mm |
| 输出轴中心 | 宽度中心；距顶部 9.5 mm |
| 原厂塑料输出 horn | 外径 16 mm，突出前壳面 3 mm |
| 输出 horn 安装孔 | 4 × Ø1.6 自攻底孔，PCD Ø12 mm，最大深度 3.0 mm |
| 机身框架孔 | 前后面均为 16 × 30 mm 矩形四孔布局；M2 tapping screw |
| 前面框架孔 Detail A | 入口 Ø2，入口段长度 3.5 mm，后接 Ø1.6 |
| 后面框架孔 Detail B | 入口 Ø2，入口段长度 4.5 mm，后接 Ø1.6 |
| 安装反侧 idler 后 | 前后 horn 外表面总距离 29 mm，即 3 + 23 + 3 mm |
| 反侧 idler 的框架接口 | Ø16，4 × Ø1.6 自攻底孔，PCD Ø12 mm，最大深度 3.0 mm |

由图纸对称布局推导：以正视图左上机身角为原点、右/下为正，轴心为 (10, 9.5)，框架孔为 (2, 2)、(18, 2)、(2, 32)、(18, 32)。这是图纸尺寸推导，CAD 中应再与实际 STEP 圆柱面位置核对。

官方 [horn 螺钉安装图](https://emanual.robotis.com/assets/images/dxl/x/x330/x330_horn_screw.png)明确：**3 mm 厚连接板配 PHS M2×6 TAP；禁止把 M2×8 TAP 用在同样的 horn 接口**。进入塑料 horn 的长度不得超过 3 mm；不可把“自攻底孔 Ø1.6”理解为已攻 M2 机牙孔。库存金属 M2 螺钉不能无条件替代这些 TAP 螺钉。

[官方总装图](https://emanual.robotis.com/assets/images/dxl/x/x330/xl330_assembly_integrated.png)显示，机身前后框架孔与内部壳体螺钉为不同孔；idler 通过独立 cap 和 M2.6×6 tapping screw 装在反侧。图纸没有给出 idler 轴向配合公差、允许预紧力、机身孔总可用深度或这些塑料螺孔的拧紧力矩，不能编造数值。3 mm 的 horn 连接板示例不能自动推广为所有机身框架板的规定厚度。

## 采购边界

[XL330 官方商品页](https://www.robotis.com/shop/item_export_only.php?it_id=902-0163-000)列出每台随附：1 根 180 mm X3P 线、6 颗 PHS M2×6 TAP、10 颗 PHS M2×8 TAP。**电机本体不附反侧 idler/cap**。

[FPX330-H101 4PCS SET](https://en.robotis.com/shop_en/item.php?it_id=903-0302-000)，SKU 903-0302-000，每包包含 4 个 idler、4 个 cap、8 颗 BHS M2.6×6 TAP 及框架/其他紧固件。官方指出 idler/cap 不单卖。8 个关节全部采用反侧支承时，需 2 包。STEP 中出现 idler 不代表电机包装中已经包含它。

[HNX330-N101](https://en.robotis.com/shop_en/item.php?it_id=903-0314-000)是可选**金属输出 horn**，配 M2×4 机牙螺钉，不是 idler。当前原厂塑料 horn 的孔深、螺钉契约不能未经重新核对直接用于金属 horn。HN11-I101 属于 X430 尺寸系列，也不能代用。

## 电机、电源和通信

[XL330-M288-T e-Manual](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/)给出的主要数值：

| 项目 | 数值 |
|---|---|
| 质量 | 18 g/台，8 台为 144 g，不含支架/线缆 |
| 电压 | 3.7–6.0 V，推荐 5.0 V |
| 5 V 堵转 | 0.52 N·m、1.47 A |
| 5 V 空载速度 | 103 rpm |
| 输出位置分辨率 | 4096 count/rev |
| 通信 | 半双工 TTL；3.3 V 逻辑、兼容 5 V |
| 插针 | 1 GND，2 VDD，3 DATA |
| 接插件 | JST EHR-03、B3B-EH-A、SEH-001T-P0.6 |

[ROBOTIS US 的持续力矩条目](https://robotis.us/dynamixel-xl330-m288-t/)列为 **0.10 N·m estimated**，说明它是堵转力矩的 20% 估算值。它适合作为保守设计目标，不能视为带温升/占空比保证的实测热额定力矩。公开资料未给出可用于地面冲击验收的径向/轴向负载限值。

[JST EH 数据表](https://www.jst-mfg.com/product/pdf/eng/eEH.pdf)规定 3 A（AWG22 条件）、2.5 mm 间距；SEH-001T-P0.6 线规范围 AWG30–22。ROBOTIS e-Manual 列成品线 21 AWG，两者存在规格表述差异，应采购原厂成品线；自行压接时按 JST 端子/工具规格核对，不能把 AWG21 当作该端子的已验证压接规格。

[OpenRB-150 官方规格](https://docs.robotis.com/docs/parts/controller/openrb-150/)给 DYNAMIXEL 供电通路额定 3 A，USB 不能承担动态电机负载。推导：8 台在 5 V 的堵转电流和为 11.76 A，不能经过单根 EH 首段线或全部通过 OpenRB 电源通路。设计时采用独立电源分配，按四肢划分 4 条供电支路，每条最多 2 台；2 台堵转为 2.94 A，已接近 3 A，实际动作需限制电流并验证线缆温升。数据线共用 TTL 总线，信号地与电源地相连。电源分配的连接器、开关、保险和主线必须按总电流另外选型。

接插件、电机线不能带电插拔；普通 2S 锂电池不能直接接 XL330。低压大电流电源和任何电池应留在最终质量、重心和压降核算中。

## 保留的不确定项

- 图纸标注为 reference only，未包含制造公差；打印孔径与壳体配合需用独立小试片核对。
- 未给出塑料孔拧紧力矩、机身孔底深度、idler 轴向预紧公差；装配不能强压、过拧或依赖未核对的螺钉突出长度。
- 0.10 N·m 仅为商家估算；瞬态摆动、反复撑地和温升必须在真机上分阶段验证。
- 数据手册支持电流反馈，但 XL330 测量的是输入电源电流；不能用堵转 Nm/A 系数把动态电流直接当作已校准关节力矩。
