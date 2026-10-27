# Comparison: Algo 1 (ours) vs Algo 2 (teammate)

Date: 2026-10-27. Final data: `results/compare_all.csv`.

## Setup

- Algo 1: `solver/solver.py`. Algo 2: `competitors/Algo_2/solver.py`.
- 12 instances: our 9 (`instances/small|medium|large`) and Algo 2's 3 (`instances/compare/algo2_*`,
  n = 100 / 500 / 1000, fleet 99.8% full).
- Real limits: 30 s small, 60 s medium, 180 s large. Seed 0 for both.
- One machine (Windows 11, Python 3.12.10, 16 cores). Both solvers ran side by side, one process each.
- Every answer was checked with `tools/validate.py`. All 24 runs were feasible.
- Runs hit by laptop sleep were rerun. The final `l_C_1500` row for Algo 2 is a solo rerun.

## Scores

Official formula, b = cheaper cost of the two, weighted 10% / 30% / 60%.

| Instance set | Algo 1 | Algo 2 |
|---|---|---|
| All 12 | **1.000** | 0.910 |
| Our 9 | **1.000** | 0.965 |
| Algo 2's 3 | **1.000** | 0.747 |

## Costs

| Instance | Algo 1 | Algo 2 | Algo 2 worse by |
|---|---|---|---|
| s_C_500 | 77755.5 | 78997.5 | 1.6% |
| s_T_500 | 55914.9 | 88451.8 | 58.2% |
| s_U_500 | 49266.7 | 50558.9 | 2.6% |
| m_C_800 | 134929.1 | 136147.4 | 0.9% |
| m_T_800 | 96799.4 | 153003.0 | 58.1% |
| m_U_800 | 74949.6 | 76399.2 | 1.9% |
| l_C_1500 | 246575.9 | 247569.7 | 0.4% |
| l_T_1500 | 160094.2 | 162240.1 | 1.3% |
| l_U_1500 | 133225.5 | 134882.3 | 1.2% |
| a2_small | 1666.83 | 1757.05 | 5.4% |
| a2_medium | 7394.29 | 9375.29 | 26.8% |
| a2_large | 13673.45 | 28950.74 | 111.7% |

Run time: Algo 1 stops at 25.5 / 51 / 153 s, Algo 2 at about 29 / 59 / 179 s. Both stay under L.

## Findings

1. Algo 1 is cheaper on all 12 instances.
2. Our tight fleet (T) instances work as intended. Algo 2 is 58% worse on s_T and m_T.
3. Algo 1 handles very full fleets well (a2_medium, a2_large). Algo 2 is 27% and 112% worse there.
4. On normal instances (U and C) the gap is small, 0.4% to 2.6%. A stronger team could beat us
   here, so speeding up the search for large n is still worth doing.
5. Algo 2 is slow on n = 1500: 33 s of start-up and only 150 search rounds in 180 s
   (`compare_raw/solo_algo2_lC.json`).

## Reproduce

```
sh results/run_compare.sh algo1 "python solver/solver.py"
sh results/run_compare.sh algo2 "python competitors/Algo_2/solver.py"
python -c "import csv;r=[x for f in ('results/compare_algo1.csv','results/compare_algo2.csv') for x in csv.DictReader(open(f))];w=csv.DictWriter(open('results/compare_all.csv','w',newline=''),r[0].keys());w.writeheader();w.writerows(r)"
python tools/score.py results/compare_all.csv
```

Keep the laptop awake during runs (Power > Sleep: Never). Sleep inflates wall time.
Intermediate files and logs are in `results/compare_raw/`.
