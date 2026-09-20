#!/usr/bin/env python3
"""Compare compatible pilot scorecards; never invent missing model identities."""
import argparse
import csv
import json
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('scorecards', nargs='+', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    rows = [json.loads(f.read_text()) for f in args.scorecards]
    digital = 'score' in rows[0]
    if any(('score' in r) != digital for r in rows):
        sys.exit('拒绝比较：不能混合数字初评与旧工程验证量表。')
    keys = ('benchmark_version', 'profile_id', 'evaluator_sha256' if digital else 'evaluator_hashes')
    if any(any(r[k] != rows[0][k] for k in keys) for r in rows):
        sys.exit('拒绝比较：benchmark/profile/评测器哈希不同。用同一评测版本重新评分。')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if digital:
        fields = ['submission','core_score','metrics_with_test_evidence','full_virtual_assembly_approved'] + list(rows[0]['gates'])
    else:
        fields = ['submission', 'score_lower', 'score_upper', 'evidence_coverage_percent', 'official_ranking_eligible'] + list(rows[0]['gates'])
    with args.out.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fields); writer.writeheader()
        for path, r in zip(args.scorecards, rows):
            if digital:
                writer.writerow(dict(submission=str(path),core_score=r['score'],metrics_with_test_evidence=r['metrics_with_test_evidence'],
                                     full_virtual_assembly_approved=r['extended_checks']['full_virtual_assembly_approved'],**r['gates']))
            else:
                writer.writerow(dict(submission=str(path), **{k:r[k] for k in fields[1:5]}, **r['gates']))
    print('已输出同量表设计对照表；模型身份、任务、生成预算和人工干预须另核对，不能凭分数自动宣布AI排名。')


if __name__ == '__main__':
    main()
