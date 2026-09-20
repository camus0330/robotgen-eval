#!/usr/bin/env python3
"""Explicitly audit digital checks beyond the 20-item preliminary core.

These coverage failures are not physical failures and earn no hidden PASS.
Full virtual assembly approval requires resolving these separately.
"""
import csv
import json
from pathlib import Path


def check_extended(root, rebuilt, run, out):
    collision=json.loads((rebuilt/'reports/flat_reference_collision.json').read_text())
    strength=json.loads((rebuilt/'reports/strength_actual_loads.json').read_text())
    definitions=[
        ('X01','A05','关键接口公差链','tolerance_chains.json','没有覆盖所有关键接口的尺寸公差/基准/最坏情况公差链；名义探针不代替公差链'),
        ('X02','A06','完整装配与工具路径','assembly_paths.json','85个探针仅检查接口局部；没有全部插入步骤和工具扫掠证据'),
        ('X03','A07','全部紧固件数字装配','fastener_assembly.json','当前只验证horn与机壳的长度链，掌足/头胸壳/附加件未做完整实体紧固链检查'),
        ('X04','A08','切片和支撑可去除性','slicing_validation.json','平台包络检查不能代替实际切片及支撑去除路径'),
        ('X05','A09','完整BOM静态干涉',None,'正式CAD碰撞报告明确cad_contains_added_fasteners=false'),
        ('X06','B05','连续扫掠与误差预算',None,'碰撞报告明确不含记录帧之间连续检测，未提供完整最小距离误差预算'),
        ('X07','C02','全机载荷路径结构',None,'强度报告仅含局部理想截面及接触载荷贡献，缺完整重力/惯性内力和所有连接件'),
        ('X08','C05','线缆数字包络', 'cable_envelopes.json','线束仅为质量余量及布线说明，缺全行程几何包络与弯曲半径数据')]
    rows=[]
    for mid,legacy,name,file,reason in definitions:
        if file:
            path=run/'extended_evidence'/file
            # The artifact alone must never be promoted to geometric proof.
            failure='REVIEW_REQUIRED' if path.exists() else 'MISSING_EVIDENCE'
            evidence=str(path)
        elif mid=='X05':
            failure='COVERAGE_GAP' if collision['cad_contains_added_fasteners'] is False else 'REVIEW_REQUIRED'
            evidence=str(rebuilt/'reports/flat_reference_collision.json')
        elif mid=='X06':
            failure='COVERAGE_GAP' if any('continuous' in s.lower() for s in collision['limitations']) else 'REVIEW_REQUIRED'
            evidence=str(rebuilt/'reports/flat_reference_collision.json')
        else:
            failure='COVERAGE_GAP' if strength['method']['assumed_isotropic_PETG'] else 'REVIEW_REQUIRED'
            evidence=str(rebuilt/'reports/strength_actual_loads.json')
        rows.append(dict(id=mid,legacy_metric=legacy,name=name,status='FAIL',failure_type=failure,reason=reason,evidence=evidence))
    result=dict(scope='extended_digital_coverage_audit_not_physical_tests',full_virtual_assembly_approved=False,
                core_score_not_adjusted=True,checks=rows,
                note='These are executable evidence-coverage checks, not implemented full CAD solvers. Additional evidence requires a numerical validator before PASS.')
    out.mkdir(parents=True,exist_ok=True)
    (out/'extended_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    with (out/'extended_checks.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
    return result
