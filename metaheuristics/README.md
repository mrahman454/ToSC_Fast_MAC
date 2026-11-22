# Metaheuristic designs (comparison table)

The 14 designs of the comparison table, found by the genetic algorithm with its local-search step. Each design has
its own folder, holding its cipher description and the trails behind its value. `run_milp.py` runs the MILP models
on any of them.

## Layout

```
metaheuristics/
  run_milp.py              run the MILP models on one design (see Usage)
  designs.tsv              per design: exact value, rounds N at which open-end trail = collision
  code/                    the model: cipher description reader, cipher builder, Gurobi MILP, LaTeX trail drawing
  <design>/
    <design>_cipher.txt            cipher description
    <design>_W20_trail.pdf         full collision over 20 rounds (the minimum)
    <design>_W20_open_trail.pdf    open-end trail over 20 rounds (the lower bound)
    <design>_W<k>_trail.pdf        the shortest collision found (k rounds)
    rerun/                         created by run_milp.py
```

## Requirements

- Python 3 with `numpy` and `gurobipy`, and a Gurobi licence.
- For the PDFs: `pdflatex` or `lualatex` with TikZ on the `PATH`. Without one, the trails are written as `.txt` and
  `.tex` only.

## Usage

```
python run_milp.py <design> [--measure all|collision|open] [--rounds N] [--lin]
                            [--threads T] [--outdir DIR] [--no-pdf]
```

For example, `python run_milp.py s8_m2_r3_w5` reads `s8_m2_r3_w5/s8_m2_r3_w5_cipher.txt` and solves:

- the full collision over N rounds, with N taken from `designs.tsv` (the rounds at which the open-end trail reaches
  the collision value; 11 for this design);
- the open-end trail over the same N rounds.

It prints the values and writes each trail (`.txt`, `.tex`, `.pdf`) to `s8_m2_r3_w5/rerun/`, so the shipped trails are
kept. Options:

| Option | Effect |
|---|---|
| `--measure` | solve the collision or the open-end trail only |
| `--rounds N` | change N for the collision and the open-end trail (default: `designs.tsv`, else 20) |
| `--lin` | add the linear-incompatibility constraints; the table values are without them |
| `--threads T` | Gurobi threads (default 4) |
| `--outdir DIR` | write the trails to `DIR` instead of `rerun/` |
| `--no-pdf` | write `.txt` and `.tex` only |

There is no time limit on any solve. Timed with `--threads 20` over the default N: under 30 minutes per solve for
s5_m1_r3_w3 to s8_m2_r3_w4, s9_m3_r4_w7 and s12_m3_r6_w6, except the collision of s6_m2_r3_w5 (about 2 hours).

## Cipher description

A file holds one base period of the design (P = 4 rounds here). Each round is written as two layers:

- `LAYER k: LINEAR`: an s × s binary matrix.
- `LAYER k+1: NONLINEAR`, with two parts:
  - `Pattern:` says which of the s state words get a keyless AES round.
  - `Transition matrix:` is an (s+r) × (m+r) binary matrix. Its rows are the words added to the state, V_0..V_{s-1},
    then the new accumulator words. Its columns are the message words M_0..M_{m-1}, then the old accumulator words.

A cipher of N rounds applies the base rounds cyclically. s, m and r are read from the matrix sizes; the
`Parameters:` line is checked against them. `Rounds:` gives k, the length of the shortest collision found. Lines starting with `#` are
comments: they record how the design was found and refer to the development repository.

## Model

The MILP model:

- **Differences:** byte-level truncated differences (each byte active or not). MixColumns is modelled by its branch
  number, 5. No linear-incompatibility constraints (unless `--lin`).
- **Start:** the state and accumulator differences are zero before the first round. The first message difference
  enters in some round of the first period (rounds 1..p, where p is the design's period: 4 for a design with four
  different rounds, 1 for one round repeated). One solve gives the minimum over all starting rounds, and it loses
  nothing: the design is periodic, so a collision that starts later can be shifted back by a multiple of p.
- **Collision over N rounds:** the state and accumulator differences are both zero after round N (a full internal
  collision). A shorter collision followed by rounds without difference is one too, so the value can only decrease
  as N grows.
- **Open-end trail over N rounds:** the same model without the end condition. Its value is a lower bound on every
  collision of the design, of any length. The first N rounds of a longer collision are such a trail, and so is a
  shorter collision padded with rounds without difference.
- **Exact value:** when the collision and the open-end trail over the same N rounds have the same value, that value
  is the minimum number of active S-boxes over all collisions of the design, of any length. N is counted from
  round 1 of the cipher.
- **Objective:** the number of active S-boxes, i.e. active bytes entering AES rounds.

## Values

Rate = w/m. All values are without linear incompatibility. N is the number of rounds over which the collision and the
open-end trail are both equal to the exact value (`designs.tsv`).

| Design | s | m | r | w | Rate | Rounds per period | Exact value | N |
|---|---|---|---|---|---|---|---|---|
| s5_m1_r3_w3 | 5 | 1 | 3 | 3 | 3 | 1 round repeated | 31 | 11 |
| s5_m1_r3_w3_mix | 5 | 1 | 3 | 3 | 3 | 4 different | 32 | 18 |
| s6_m2_r3_w5 | 6 | 2 | 3 | 5 | 2.5 | 4 different | 23 | 10 |
| s6_m2_r3_w6 | 6 | 2 | 3 | 6 | 3 | 4 different | 29 | 11 |
| s7_m2_r3_w5 | 7 | 2 | 3 | 5 | 2.5 | 1 round repeated | 29 | 9 |
| s7_m2_r3_w6 | 7 | 2 | 3 | 6 | 3 | 1 round repeated | 43 | 12 |
| s8_m2_r3_w4 | 8 | 2 | 3 | 4 | 2 | 1 round repeated | 27 | 14 |
| s8_m2_r3_w5 | 8 | 2 | 3 | 5 | 2.5 | 1 round repeated | 39 | 11 |
| s8_m2_r4_w6 | 8 | 2 | 4 | 6 | 3 | 1 round repeated | 51 | 11 |
| s8_m3_r3_w8 | 8 | 3 | 3 | 8 | 2.67 | 1 round repeated | 29 | 11 |
| s9_m3_r4_w7 | 9 | 3 | 4 | 7 | 2.33 | 1 round repeated | 29 | 11 |
| s9_m3_r4_w9 | 9 | 3 | 4 | 9 | 3 | 1 round repeated | 45 | 11 |
| s10_m3_r3_w6 | 10 | 3 | 3 | 6 | 2 | 1 round repeated | 25 | 11 |
| s12_m3_r6_w6 | 12 | 3 | 6 | 6 | 2 | 1 round repeated | 30 | 12 |
