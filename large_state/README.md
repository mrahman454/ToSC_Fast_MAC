# Large-state designs

Large-state designs found by the genetic algorithm. Each design has its own folder, holding its cipher description and
the trails behind its values. `run_milp.py` runs the MILP models on any of them; it is the program of
`../metaheuristics/` (same model and options, see `../metaheuristics/README.md`), looking up the designs and their
default N in this folder.

## Layout

```
large_state/
  run_milp.py              run the MILP models on one design (see Usage)
  designs.tsv              per design: exact values without / with linear incompatibility, and the N for each
  <design>/
    <design>_cipher.txt                cipher description (format: ../metaheuristics/README.md)
    <design>_W<k>_trail.*              full collision over k rounds, without linear incompatibility
    <design>_W<k>_open_trail.*         open-end trail over k rounds, without linear incompatibility
    <design>_W<k>_lin_trail.*          full collision over k rounds, with linear incompatibility
    <design>_W<k>_lin_open_trail.*     open-end trail over k rounds, with linear incompatibility
    rerun/                             created by run_milp.py
```

`.txt` is the trail byte by byte, `.tex` the TikZ figure, `.pdf` the compiled figure.

## Usage

```
python run_milp.py <design> [--measure all|collision|open] [--rounds N] [--lin]
                            [--threads T] [--outdir DIR] [--no-pdf]
```

For example, `python run_milp.py s8_m4_r5_w8_s105168` solves the full collision and the open-end trail over N = 11
rounds without linear incompatibility (a minute); `--lin` adds the linear-incompatibility constraints (the open-end
trail then takes about an hour with `--threads 32`). The value is exact when the two agree over the same N.

## Values

The model: byte-level truncated differences, zero initial state and accumulator, first message difference anywhere
in the first period, full collision = state and accumulator differences zero after the last round (details:
`../metaheuristics/README.md`, section Model).

### s8_m4_r5_w8_s105168 (s = 8, m = 4, r = 5, w = 8; one round repeated)

| Linear incompatibility | Open-end trail (lower bound) | Full collision (upper bound) | Exact | Shortest collision |
|---|---|---|---|---|
| off | 21 (11 rounds) | 21 (6 rounds; also over 11 and 20 rounds) | **21** | 6 rounds |
| on | 22 (11 rounds) | 22 (4 rounds; 22 at every length from 4 to 13, none over 2 or 3) | **22** | 4 rounds |

Trails in `s8_m4_r5_w8_s105168/`:

- without linear incompatibility: collisions over 4, 5 (22 each), 6 and 20 rounds (21 each); open-end trail over
  11 rounds (21);
- with linear incompatibility: collisions over 4 to 13 rounds (22 each); open-end trail over 11 rounds (22).
