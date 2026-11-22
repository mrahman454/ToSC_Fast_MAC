"""
Verify a large-state design: run the MILP models on its cipher description and write the trails.

Usage (from any directory):
    python run_milp.py DESIGN [--measure all|collision|open] [--rounds N] [--lin]
                              [--threads T] [--outdir DIR] [--no-pdf]

Same program and model as ../metaheuristics/run_milp.py (see its docstring and README); this wrapper only looks up
DESIGN in this folder and the default N in this folder's designs.tsv.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "metaheuristics"))
import run_milp                                                 # noqa: E402

run_milp.HERE = HERE            # designs and designs.tsv are looked up here
if __name__ == "__main__":
    run_milp.main()
