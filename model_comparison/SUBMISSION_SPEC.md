# 提交接口 v0.1

每次尝试单独目录。`submission.json` 由操作者核实身份和过程；`design_manifest.json` 描述设计。所有路径相对该目录，禁止绝对路径、`..`或符号链接越出提交目录。文件不得为空。验收器不相信自报的工程PASS，不执行重建命令。

## submission.json

- `submission_id`、`model_slot`、`phase`、`attempt`：目录对应的唯一身份。
- `status`：NOT_STARTED、COMPLETED、GENERATION_FAILED、TIMEOUT之一。
- `model_provider`、`model_exact_version`、`invocation_mode`、`session_id`：从调用系统记录，不由模型猜测。
- `input_manifest_sha256`：评测方 `records/input_manifest.json` 的SHA-256。
- `prompt_sha256`：输入包PROMPT的SHA-256。
- `actual_elapsed_s`、`feedback_rounds`、`human_edit_minutes`：实际记录，不因0值而当缺失。
- `actual_cost`、`usage_tokens`、`generation_seed`：未知可null，`unknown_fields_reason`解释。
- `logs`：全部原始会话/工具日志文件路径；`human_edits`：如有人工修改，提供diff及理由。正式主轨默认不允许人工设计修改。

失败或超时提交允许缺少设计文件，但仍须保存元数据和日志；文件验收输出 `FAILED_ATTEMPT_RECORDED`，不能误称交付成功。

## design_manifest.json

| 字段 | 内容 |
|---|---|
| `units` | 固定cad=mm、simulation=m/kg/s/rad |
| `files` | cad_source、assembly_step、bom、mjcf、urdf、controller、readme、limitations、dependencies，值均为文件路径 |
| `rebuild_command` | 非空字符串数组，如 `["python3", "src/build.py"]`；只记录不执行 |
| `parts` | 全部打印件，每项唯一id、正整数quantity、step与stl路径 |
| `joints` | 恰好8个语义角色，与motion_profile关节顺序对应；每项role及实际模型joint name |
| `contacts` | left_hand、right_hand、left_foot、right_foot到模型geom名称的完整映射 |
| `motions` | swing与wave，各有reference和config文件路径 |
| `interfaces` | 每个关节至少case_mount和horn_mount两类接口，各有id、joint_role、part_id、kind及frame_in_part_mm |

`frame_in_part_mm` 为4×4齐次变换：最后一列是mm平移，旋转正交且行列式+1，最后一行[0,0,0,1]。接口frame的+Z沿原厂电机STEP原始轴方向，XY方向同原厂参考；评测方据此定位探针，随后仍必须独立确认真实CAD几何及装配变换。对idler支承、螺钉长度、工具通道、结构截面另补工程适配字段；当前最低协议不能证明这些约束已通过。

不要强行改名为P02等旧版零件名。零件数可变；BOM数量与CAD的真实闭环由后续工程评测完成。验收器目前仅检验映射完整性、路径、基础类型、坐标变换与输入版本绑定，不能确认CAD内容、MJCF动力学或日志真实性。
