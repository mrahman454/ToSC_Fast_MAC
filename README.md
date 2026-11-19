# Artifact for the ToSC submission

Cipher descriptions, trails and the code to verify the security values of the designs in the paper.

| Folder | Contents |
|---|---|
| `metaheuristics/` | the 14 designs of the comparison table, with `run_milp.py` to run the MILP models on any of them (see its README) |
| `large_state/` | the large-state designs (LeMac shape) — to be added |
| `small_state/` | the small-state designs (PetitMac setting) — to be added |

Requirements: Python 3 with `numpy` and `gurobipy` (and a Gurobi licence); `pdflatex` or `lualatex` for the trail
PDFs.
