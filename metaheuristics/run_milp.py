"""
Verify a metaheuristic design: run the MILP models on its cipher description and write the trails.

Usage (from any directory):
    python run_milp.py VARIANT [--measure all|collision|open] [--rounds N] [--lin]
                               [--threads T] [--outdir DIR] [--no-pdf]

VARIANT is a folder next to this script (e.g. s8_m2_r3_w5) or a path to one; the cipher description is read from
VARIANT/VARIANT_cipher.txt (format: see README.md). Results are printed and the trails (.txt, .tex and, with a LaTeX
engine on the PATH, .pdf) are written to VARIANT/rerun/ (or --outdir), so the trails shipped in VARIANT/ are kept.

Model: byte-level truncated differences (each byte active or inactive), MixColumns by its branch number 5, no
difference in the initial state and accumulator (memory), the design's base rounds applied cyclically. The first
message difference may enter in any round of the first period (rounds 1..p, p = the design's period: the smallest
p such that the file's base rounds repeat with period p; a design with one round repeated has p = 1). This gives
the minimum over all starting rounds in one solve: the design is periodic, so a collision that starts later can be
shifted back by a multiple of p. N rounds are counted from round 1; the default N is the design's entry in
designs.tsv (the number of rounds at which the open-end trail reaches the collision value), else 20. Measures:
  collision  full internal collision over N rounds: state AND accumulator differences zero after round N.
  open       open-end trail over N rounds: no condition at the end. A lower bound on every collision of the design,
             of any length (the first N rounds of a longer collision are such a trail; a shorter one, padded with
             rounds without difference, is one too).
  all        collision and open (default).
The collision value is exact when collision(N) = open(N) over the same N. --lin adds the linear-incompatibility
constraints (the paper's table values are without them). No time limit on any solve.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "code"))
import config                                                   # noqa: E402
config.GurobiTrailOutputLogPrinting = False                     # trail files are written below, by name
import gurobipy as gp                                           # noqa: E402
from gurobipy import GRB                                        # noqa: E402
from SecurityMod.gurobiModelBuilder import GurobiModelBuilder   # noqa: E402
from cipher_io import read_cipher_file, build_cipher            # noqa: E402


class Builder(GurobiModelBuilder):
    """The base model: zero initial state and accumulator, at least one active message byte in round 1, state zero after
    the last round if zero_output. first_period = p: the active message byte may be in any of rounds 1..p instead.
    full_collision: also the accumulator difference zero after the last round."""
    first_period = None
    full_collision = False

    def _add_active_input_constraints(self):
        if not self.first_period:
            return super()._add_active_input_constraints()
        for block in range(self.cipher.s):
            self._set_block_to_zero(self.x[0][block])
        first = min(self.first_period, self.num_transitions)
        self.model.addConstr(gp.quicksum(self.m[t][b][k] for t in range(first)
                                         for b in range(self.cipher.m) for k in range(16)) >= 1,
                             name='active_message_first_period')

    def _add_zero_output_constraint(self):
        super()._add_zero_output_constraint()                   # state zero after the last round (if zero_output)
        if self.full_collision and self.zero_output:
            for j in range(self.cipher.r):
                self._set_block_to_zero(self.r[self.num_transitions][j], constraint_name=f"_final_mem{j}")


def solve(desc, rounds, start, end, lin, threads, tmpdir, first_period=None):
    """end: 'collision' (state and accumulator zero) or 'open' (no end condition)."""
    b = Builder(build_cipher(desc, rounds, start), active_input='messages', zero_output=(end == 'collision'),
                linear_incompatibility=lin)
    b.first_period = first_period
    b.full_collision = (end == 'collision')
    t0 = time.time()
    res = b.build_and_solve(output_dir=tmpdir, num_threads=threads)
    value = int(round(res['objective'])) if res['status'] == GRB.OPTIMAL else None
    return b, value, time.time() - t0


def true_period(desc):
    """Smallest p dividing the number of base rounds such that base round i equals base round i mod p."""
    base, P = desc['base'], len(desc['base'])
    def same(a, b):
        return all(np.array_equal(np.asarray(a[k]), np.asarray(b[k])) for k in ('linear', 'pattern', 'transition'))
    for p in range(1, P + 1):
        if P % p == 0 and all(same(base[i], base[i % p]) for i in range(P)):
            return p
    return P


def default_rounds(name, lin=False):
    """N from designs.tsv: column 3, or column 5 (N with linear incompatibility) for --lin when the file has it."""
    f = os.path.join(HERE, "designs.tsv")
    if os.path.exists(f):
        for line in open(f):
            t = line.rstrip("\n").split("\t")
            if lin and t and t[0] == name and len(t) > 4 and t[4].isdigit():
                return int(t[4])
            if t and t[0] == name and len(t) > 2 and t[2].isdigit():
                return int(t[2])
    return 20


def compile_pdf(tex):
    eng = shutil.which("pdflatex") or shutil.which("lualatex")
    if not eng:
        return None
    d, f = os.path.split(tex)
    subprocess.run([eng, "-interaction=nonstopmode", f], cwd=d or ".", stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=900)
    stem = os.path.splitext(tex)[0]
    for ext in (".aux", ".log"):
        if os.path.exists(stem + ext):
            os.remove(stem + ext)
    return stem + ".pdf" if os.path.exists(stem + ".pdf") else None


def save(b, base, pdf):
    b._print_trail_to_file(base + ".txt")
    b._generate_latex(base + ".tex", auto_compile=False)
    p = compile_pdf(base + ".tex") if pdf else None
    return base + ".txt, .tex" + (", .pdf" if p else "")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("variant")
    ap.add_argument("--measure", choices=["all", "collision", "open"], default="all")
    ap.add_argument("--rounds", type=int, help="N for collision and open (default: designs.tsv, else 20)")
    ap.add_argument("--lin", action="store_true", help="add linear-incompatibility constraints")
    ap.add_argument("--threads", type=int, default=4, help="Gurobi threads (default 4)")
    ap.add_argument("--outdir", help="output folder (default: VARIANT/rerun)")
    ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args()

    vdir = a.variant if os.path.isdir(a.variant) else os.path.join(HERE, a.variant)
    vdir = os.path.abspath(vdir)
    name = os.path.basename(vdir.rstrip("/"))
    cfile = os.path.join(vdir, f"{name}_cipher.txt")
    if not os.path.isfile(cfile):
        sys.exit(f"cipher description not found: {cfile}")
    desc = read_cipher_file(cfile)
    P = true_period(desc)
    outdir = os.path.abspath(a.outdir or os.path.join(vdir, "rerun"))
    tmpdir = os.path.join(outdir, "gurobi")
    os.makedirs(tmpdir, exist_ok=True)
    tag = "_lin" if a.lin else ""
    N, pdf = a.rounds or default_rounds(name, a.lin), not a.no_pdf
    print(f"{name}: s={desc['s']} m={desc['m']} r={desc['r']}, period {P}, "
          f"N = {N}; linear incompatibility {'on' if a.lin else 'off'}; trails to {outdir}", flush=True)

    res = {}
    for end in ("collision", "open"):
        if a.measure not in ("all", end):
            continue
        b, v, dt = solve(desc, N, 0, end, a.lin, a.threads, tmpdir, first_period=P)
        res[end] = v
        what = "full collision" if end == "collision" else "open-end trail (lower bound on every collision)"
        print(f"  {what} over {N} rounds, first difference in rounds 1..{P}: {v} ({dt:.0f} s)", flush=True)
        if v is not None:
            suffix = "trail" if end == "collision" else "open_trail"
            print("    trail:", save(b, os.path.join(outdir, f"{name}_W{N}{tag}_{suffix}"), pdf), flush=True)
    if res.get("collision") is not None and "open" in res:
        exact = res["collision"] == res["open"]
        print(f"  => {'EXACT' if exact else 'not exact'} over {N} rounds: collision {res['collision']}, "
              f"open-end trail {res['open']}", flush=True)
    shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
