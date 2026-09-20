#!/usr/bin/env python3
"""Generate reproducible public perturbations, not simulation results or holdouts."""
import json
import random
from pathlib import Path

SEED = 20260918
rng = random.Random(SEED)
rows = []
for i in range(100):
    rows.append(dict(case_id=f'public-{i:03d}', generator_seed=SEED, split='public_development',
                     friction=round(rng.uniform(.4, 1.0), 6),
                     mass_and_inertia_scale=round(rng.uniform(.9, 1.1), 6),
                     equivalent_accessory_com_offset_mm=[round(rng.uniform(-5, 5), 6) for _ in range(3)],
                     servo_gain_scale=round(rng.uniform(.8, 1.2), 6),
                     encoder_zero_error_deg=[round(rng.uniform(-1, 1), 6) for _ in range(8)],
                     added_command_delay_ms=rng.choice([0, 20, 40])))
path = Path(__file__).resolve().parents[2] / 'configs/benchmark/robustness_cases_public.jsonl'
path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
print(f'Wrote {len(rows)} public cases; no simulations executed.')
