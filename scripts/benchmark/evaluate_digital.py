#!/usr/bin/env python3
"""Physical-prototype-free preliminary benchmark. Every item has an executable check.

FAIL with MISSING_EVIDENCE/ERROR means the digital submission was not accepted,
not that a physical robot was tested and failed. Thresholds remain versioned.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
try:
    from .evaluate import Audit, trace_stats
    from .check_extended import check_extended
except ImportError:  # Support direct execution: python scripts/benchmark/evaluate_digital.py
    from evaluate import Audit, trace_stats
    from check_extended import check_extended

HERE=Path(__file__).resolve().parent
REPO_ROOT=HERE.parents[1]
CONFIG_ROOT=REPO_ROOT/'configs/benchmark'
DEFAULT_ROBOT_ROOT=REPO_ROOT/'examples/gorilla8'


def read(path):
    def bad(v):raise ValueError('Non-finite JSON '+v)
    return json.loads(path.read_text(),parse_constant=bad)


def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def validate_manifest(root, rows):
    if not rows:
        return ['EMPTY_MANIFEST']
    failures=[]
    for item in rows:
        path=(root/item['path']).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or sha(path)!=item['sha256']:
            failures.append(item['path'])
    return failures


def paired_successes(rows, cases, motions):
    expected={(c['case_id'],m) for c in cases for m in motions}
    actual={(r['case_id'],r['motion']) for r in rows}
    complete=actual==expected and len(rows)==len(expected) and len({c['case_id'] for c in cases})==len(cases)
    if not complete:return False,0
    count=sum(all(r['task_pass'] is True and r['actuation_pass'] is True for r in rows if r['case_id']==c['case_id']) for c in cases)
    return True,count


class Digital:
    def __init__(self,root,run):
        self.root=root;self.run=run;self.workspace=run/'rebuild';self.rebuilt=self.workspace/'gorilla8'
        self.profile=read(CONFIG_ROOT/'digital_profile.json');self.motion_profile=read(CONFIG_ROOT/'profile.json')
        self.audit=Audit(self.rebuilt,self.motion_profile);self.rows={};self.raw={};self.used=set()

    def load(self,p):
        self.used.add(p.resolve());return read(p)

    def put(self,mid,passed,reason,evidence,raw=None):
        for p in evidence:self.used.add(Path(p).resolve())
        self.rows[mid]=dict(status='PASS' if passed else 'FAIL',failure_type=None if passed else 'THRESHOLD',
                           reason=reason,evidence=[str(p) for p in evidence],raw=raw)

    def check(self,ids,fn):
        try:fn()
        except (OSError,ValueError,KeyError,TypeError,IndexError,ZeroDivisionError,ET.ParseError) as e:
            for mid in ids:self.rows[mid]=dict(status='FAIL',failure_type='MISSING_EVIDENCE' if isinstance(e,FileNotFoundError) else 'ERROR',
                                             reason=f'{type(e).__name__}: {e}',evidence=[],raw=None)

    def existing(self,fn,mapping):
        fn()
        for old,new in mapping.items():
            r=self.audit.rows[old]
            self.put(new,r['status']=='PASS','独立重建后：'+r['reason'],[self.rebuilt/p for p in r['evidence']])
        self.used.update(self.audit.used)

    def exports(self):
        self.existing(self.audit.exports,{'A01':'DA01','A02':'DA02','A03':'DA03'})
        # Wording from legacy evidence adapter applies only to legacy E1 audit.
        self.rows['DA01']['reason']='已在新环境从冻结CAD源码重建并用CAD内核回读12种实体'
        self.rows['DA03']['reason']='已独立运行导出与回读，逐件重新计算体积相对误差'

    def bom(self):
        self.existing(self.audit.bom,{'A04':'DA04'})
        objects=self.load(self.rebuilt/'output/assembly/objects.json')
        with (self.rebuilt/'bom.csv').open() as f:rows=list(csv.DictReader(f))
        n=sum(int(r['quantity']) for r in rows if r['category']=='actuator')
        good=n==8 and sum(x['name'].endswith('_case') for x in objects)==8 and (self.workspace/'data/xl330_m288_t.step').is_file()
        if not good:self.rows['DA04'].update(status='FAIL',failure_type='THRESHOLD',reason='电机BOM/CAD数量不是8或缺原厂CAD')

    def geometry(self):
        path=self.run/'geometry_probes.json';r=self.load(path)
        bound=all(Path(p).is_file() and sha(Path(p))==v for p,v in r['input_sha256'].items())
        good=bound and len(r['checks'])==85 and len({x['id'] for x in r['checks']})==85 and all(
            x['intersection_mm3']<1e-5 if x['type']=='void' else abs(x['intersection_mm3']-x['probe_volume_mm3'])<1e-5 for x in r['checks'])
        self.put('DA05',good,'独立BREP共85个名义孔位/支承环/工具孔探针；不代表完整螺丝刀插入路径',[path],r['checks'])
        chains=r['length_chains']
        self.put('DC03',bound and len(chains)==3 and all(x['passed'] for x in chains),
                 '按CAD实测夹持厚度复算horn与机壳前后侧长度链；不评价拔出强度',[path],chains)

    def bed(self):
        path=self.rebuilt/'reports/print_parts.json';rows=self.load(path);limits=self.profile['print_bed_mm']
        measured=[dict(name=r['name'],bbox_mm=r['print_bbox_mm'],pass_bed=all(0<x<=lim for x,lim in zip(r['print_bbox_mm'],limits))) for r in rows]
        self.put('DA06',len(measured)==12 and all(r['pass_bed'] for r in measured),'逐件推荐朝向包络不超过220×220×250mm；不是切片完成证据',[path],measured)

    def kinematics(self):
        self.existing(self.audit.urdf,{'B01':'DB01'})
        path=self.rebuilt/'output/simulation/gorilla8.xml';model=ET.parse(path).getroot();self.used.add(path)
        good=len(model.findall('.//freejoint'))==1 and not model.findall('.//equality/*')
        good &= [a.get('joint') for a in model.find('actuator')]==self.motion_profile['joint_order']
        if not good:self.rows['DB01'].update(status='FAIL',failure_type='THRESHOLD',reason='自由基座或仅8轴驱动契约不符')

    def motions(self):
        reports=[];stats=[];evidence=[];margins=[]
        for index,name in enumerate(self.motion_profile['runs']):
            folder=self.rebuilt/'output/simulation_runs'/name
            r=self.load(folder/'result.json');tr=self.load(folder/'trace.json');s=trace_stats(tr,self.motion_profile)
            complete=r['completed'] is True and not r['fell'] and abs(tr[-1]['t']-r['requested_duration_s'])<1e-8 and tr[0]['t']==0
            complete &= tr[-1]['t']<=self.motion_profile['max_motion_duration_s'][index]
            s['complete']=complete;s['reported_peak_torque_nm']=r['peak_torque_nm'];s['reported_saturation_fraction']=r['torque_saturation_fraction']
            self.raw[name]=s;stats.append(s);reports.append(r)
            evidence += [folder/'result.json',folder/'trace.json']
            margins.append([min(min(math.degrees(row['q'][j])-lo,hi-math.degrees(row['q'][j])) for row in tr)
                            for j,(lo,hi) in enumerate(self.motion_profile['joint_limits_deg'])])
        self.put('DB02',stats[0]['complete'] and stats[0]['swing_pass'],'新环境重建模型的实际前荡轨迹通过原任务判据',evidence[:2],stats[0])
        self.put('DB03',stats[1]['complete'] and stats[1]['wave_pass'],'新环境重建模型的实际挥手轨迹通过原任务判据',evidence[2:],stats[1])
        good=all(s['complete'] and s['max_joint_error_deg']<=5 and s['max_root_error_mm']<=5 for s in stats)
        self.put('DB05',good,'两动作最大误差分别核对5deg及5mm；阈值未因样例而放宽',evidence,
                 [dict(joint_deg=s['max_joint_error_deg'],root_mm=s['max_root_error_mm']) for s in stats])
        good=all(s['complete'] and 0<=r['peak_torque_nm']<=.100001 and 0<=r['torque_saturation_fraction']<=.001
                 and max(r['peak_joint_limit_force_abs_Nm'])<=.001 and not r['joint_limit_support_observed'] for r,s in zip(reports,stats))
        self.put('DB06',good,'使用独立仿真的2ms全步力矩和限位力统计，非25Hz采样峰值',evidence)
        self.put('DC04',min(min(m) for m in margins)>=self.profile['minimum_limit_margin_deg'],
                 '实际记录帧距配置上下限至少1deg；全步限位力另由DB06检查',evidence,margins)

    def collision(self):
        self.existing(self.audit.collisions,{'B04':'DB04'})
        self.rows['DB04']['reason']='已独立重跑参考772帧及实际398/373帧的FCL筛选+BREP复核；不含帧间连续扫掠'

    def robustness(self):
        path=self.run/'robustness_original/summary.json';r=self.load(path)
        cases=[json.loads(s) for s in (CONFIG_ROOT/'robustness_cases_public.jsonl').read_text().splitlines()]
        bound=r['cases_sha256']==sha(CONFIG_ROOT/'robustness_cases_public.jsonl') and r['runner_sha256']==sha(HERE/'simulate_cases.py')
        # Check the actual per-run evidence, not just a claimed aggregate count.
        case_by_id={c['case_id']:c for c in cases}
        model_hash=sha(self.rebuilt/'output/simulation/gorilla8.xml')
        for row in r['rows']:
            folder=path.parent/row['case_id']/row['motion'];detail=self.load(folder/'result.json')
            bound &= detail['case']==case_by_id[row['case_id']] and detail['model_sha256']==model_hash
            bound &= detail['motion_sha256']==sha(self.rebuilt/'output/motions'/row['motion']/'motion.npz')
            bound &= detail['runner_sha256']==sha(HERE/'simulate_cases.py') and detail['trace_sha256']==sha(folder/'trace.json')
            tr=self.load(folder/'trace.json');measured=trace_stats(tr,self.motion_profile)
            task=measured['swing_pass' if row['motion'].endswith('swing') else 'wave_pass'] and detail['metrics']['completed']
            bound &= bool(task)==row['task_pass']
            actual=detail['metrics'];actuation=actual['peak_torque_nm']<=.100001 and actual['torque_saturation_fraction']<=.001 and actual['peak_limit_force_nm']<=.001
            bound &= bool(actuation)==row['actuation_pass']
        complete,successes=paired_successes(r['rows'],cases,self.motion_profile['motion_names'])
        self.put('DB07',bound and len(cases)==100 and complete and successes>=90,
                 '100组公开扰动、每组两动作均须完成且满足驱动限制；冻结原控制器',[path],
                 dict(successes=successes,total=100,wilson95=r['wilson95'],task_only_successes=sum(all(x['task_pass'] for x in r['rows'] if x['case_id']==c['case_id']) for c in cases)))

    def strength(self):self.existing(self.audit.strength,{'C03':'DC01'})

    def mass(self):
        path=self.rebuilt/'reports/masslinks.json';mass=self.load(path)
        residuals={name:abs(link['mass_kg']-sum(x['mass_kg'] for x in link['items'])) for name,link in mass.items()}
        total=sum(x['mass_kg'] for x in mass.values());cad=self.load(self.rebuilt/'reports/cad_checks.json')['total_mass_kg']
        tree=ET.parse(self.rebuilt/'output/simulation/gorilla8.urdf').getroot()
        urdf={x.get('name'):float(x.find('inertial/mass').get('value')) for x in tree.findall('link')}
        consistent=set(mass)==set(urdf) and all(abs(link['mass_kg']-urdf[name])<=1e-8 for name,link in mass.items())
        sim=[self.load(self.rebuilt/'output/simulation_runs'/name/'result.json')['total_mass_kg'] for name in self.motion_profile['runs']]
        good=consistent and max(residuals.values())<=1e-8 and all(abs(v-total)<=1e-8 for v in [cad]+sim)
        self.put('DC02',good,'逐物料→link→整机→URDF→两仿真估重闭环',[path],dict(total_mass_kg=total,link_residuals_kg=residuals))

    def reproducibility(self):
        path=self.workspace/'rebuild_report.json';r=self.load(path)
        expected={'build','plan','export','readback','simulate_swing','simulate_wave','reference_collision','collision_swing','collision_wave','strength'}
        good=r['complete'] is True and r['input_unchanged'] is True and {x['stage'] for x in r['stages']}==expected and all(x['returncode']==0 for x in r['stages'])
        tolerance=self.profile['reproduction_tolerances'];comparisons=[]
        before=self.load(self.root/'reports/print_parts.json');after=self.load(self.rebuilt/'reports/print_parts.json')
        b={x['name']:x['volume_mm3'] for x in before};a={x['name']:x['volume_mm3'] for x in after}
        good &= set(a)==set(b) and all(abs(a[k]/b[k]-1)<=tolerance['relative_part_volume'] for k in a)
        for name in self.motion_profile['runs']:
            old=self.load(self.root/'output/simulation_runs'/name/'result.json');new=self.load(self.rebuilt/'output/simulation_runs'/name/'result.json')
            diff=dict(mass_kg=abs(new['total_mass_kg']-old['total_mass_kg']),
                      root_peak_error_difference_mm=1000*abs(new['peak_root_error_m']-old['peak_root_error_m']),
                      joint_peak_error_difference_deg=math.degrees(abs(new['peak_joint_error_rad']-old['peak_joint_error_rad'])),
                      forward_difference_mm=1000*abs(new['actual_forward_displacement_m']-old['actual_forward_displacement_m']))
            good &= all(v<=tolerance[k] for k,v in diff.items());comparisons.append(diff)
        self.put('DD01',bool(good),'源码冻结后独立重建10阶段及与基线的预登记数值容差核对',[path],comparisons)

    def provenance(self):
        inp=self.workspace/'input_manifest.json';out=self.workspace/'output_manifest.json';r=self.load(self.workspace/'rebuild_report.json')
        failures=validate_manifest(self.workspace,self.load(inp)['files'])+validate_manifest(self.workspace,self.load(out))
        good=not failures and r['input_manifest_sha256']==sha(inp) and r['output_manifest_sha256']==sha(out)
        self.put('DD02',good,'逐文件复核本次冻结输入及生成输出哈希；不是历史AI生成过程证明',[inp,out],failures)

    def disclosure(self):
        p=self.root/'reports/manufacturing_validation_notes.md';text=p.read_text();self.used.add(p)
        contract=self.load(self.rebuilt/'output/simulation/contract.json')
        good='历史阶段记录' in text[:500] and contract['current_mapping_calibrated'] is False and contract['self_contact_in_mujoco'] is False
        self.put('DD03',good,'历史版本已标记；接触/伺服/自碰撞模型边界和所有指标失败类型均披露',[p,self.rebuilt/'output/simulation/contract.json'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=DEFAULT_ROBOT_ROOT)
    p.add_argument('--run',type=Path,default=REPO_ROOT/'results/runs/latest');p.add_argument('--out',type=Path,default=REPO_ROOT/'results/digital')
    args=p.parse_args();d=Digital(args.root.resolve(),args.run.resolve())
    for ids,fn in [(['DA01','DA02','DA03'],d.exports),(['DA04'],d.bom),(['DA05','DC03'],d.geometry),(['DA06'],d.bed),
                   (['DB01'],d.kinematics),(['DB02','DB03','DB05','DB06','DC04'],d.motions),(['DB04'],d.collision),
                   (['DB07'],d.robustness),(['DC01'],d.strength),(['DC02'],d.mass),(['DD01'],d.reproducibility),(['DD02'],d.provenance),(['DD03'],d.disclosure)]:
        d.check(ids,fn)
    with (CONFIG_ROOT/'digital_metrics.csv').open() as f:catalog=list(csv.DictReader(f))
    assert len(catalog)==20 and sum(int(m['weight']) for m in catalog)==100 and {m['id'] for m in catalog}==set(d.rows)
    rows=[dict(m,**d.rows[m['id']],earned=int(m['weight']) if d.rows[m['id']]['status']=='PASS' else 0) for m in catalog]
    score=sum(r['earned'] for r in rows);technical=sum(r['failure_type'] in ('MISSING_EVIDENCE','ERROR') for r in rows)
    gates={k:all(d.rows[mid]['status']=='PASS' for mid in ids) for k,ids in d.profile['gates'].items()}
    args.out.mkdir(parents=True,exist_ok=True)
    try:
        extended=check_extended(d.root,d.rebuilt,d.run,args.out)
    except (OSError,ValueError,KeyError) as e:
        extended=dict(full_virtual_assembly_approved=False,error=str(e))
    result=dict(benchmark_version=d.profile['benchmark_version'],profile_id=d.profile['profile_id'],created_utc=datetime.now(timezone.utc).isoformat(),
                submission_path=str(d.root),run_path=str(d.run),
                score=score,total_weight=100,metrics=rows,raw=d.raw,gates=gates,hardware_required=False,
                checks_executed=len(rows),metrics_with_test_evidence=len(rows)-technical,not_tested_due_to_missing_or_error=technical,
                extended_checks=extended,
                evaluator_sha256={p.name:sha(p) for p in [Path(__file__),HERE/'check_extended.py',CONFIG_ROOT/'digital_profile.json',CONFIG_ROOT/'digital_metrics.csv',HERE/'evaluate.py',CONFIG_ROOT/'profile.json']})
    (args.out/'scorecard.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    fields=['id','dimension','name','weight','status','earned','failure_type','reason','scope','evidence']
    with (args.out/'scorecard.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader()
        for r in rows:w.writerow(dict(r,evidence=';'.join(r['evidence'])))
    manifest=[dict(path=str(p),sha256=sha(p)) for p in sorted(d.used) if p.is_file()]
    (args.out/'evidence_manifest.json').write_text(json.dumps(manifest,indent=2))
    lines=['# 无实物数字初评结果','',f'**核心初评 {score}/100**；20项均运行判定；其中{len(rows)-technical}项有完整测试证据。',
           '扩展数字装配检查另见extended_checks.csv；核心高分不表示完整虚拟装配已通过。',
           'FAIL(MISSING_EVIDENCE/ERROR)表示数字验收未完成，不能描述成实机性能失败。','',
           '| 指标 | 权重 | 结果 | 失败类型 |','|---|---:|---|---|']
    lines += [f"| {r['id']} {r['name']} | {r['weight']} | {r['status']} | {r['failure_type'] or ''} |" for r in rows]
    (args.out/'scorecard.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(score=score,test_evidence=len(rows)-technical,failed=[dict(id=r['id'],type=r['failure_type'],reason=r['reason']) for r in rows if r['status']=='FAIL']),ensure_ascii=False,indent=2))
    return 2 if technical else 0


if __name__=='__main__':sys.exit(main())
