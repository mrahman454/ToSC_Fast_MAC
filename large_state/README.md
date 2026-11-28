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
Without `--rounds`, N comes from `designs.tsv`: `N_open_equals_collision`, or `N_lin` with `--lin` (20 where the
entry is `-`).

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

### s8_m4_r5_w8_s101423 (s = 8, m = 4, r = 5, w = 8; one round repeated)

| Linear incompatibility | Open-end trail (lower bound) | Full collision (upper bound) | Exact | Shortest collision |
|---|---|---|---|---|
| off | 19 (11 rounds) | 19 (5 rounds; also over 6 and 11 rounds) | **19** | 5 rounds |
| on | 26 (20 rounds; 20 over 11 rounds) | 26 (6 rounds; 26 at every length from 6 to 9; 31 over 5, 33 over 4, 56 over 3, none over 2) | **26** | 6 rounds |

With linear incompatibility, the collision over 6 rounds followed by rounds without difference is a collision over
20 rounds, so the collision and the open-end trail over 20 rounds are both 26. The open-end trail over 11 rounds (20)
is too short to show it, so N = 20 here. That open-end solve took about 17 hours with 48 threads; the run without
linear incompatibility takes a few minutes.

Trails in `s8_m4_r5_w8_s101423/`:

- without linear incompatibility: collisions over 3 (48), 4 (22), 5 and 6 rounds (19 each); open-end trail over 11
  rounds (19);
- with linear incompatibility: collisions over 3 (56), 4 (33), 5 (31) and 6 to 9 rounds (26 each); open-end trails
  over 11 (20) and 20 rounds (26).

### s8_m4_r5_w8_n2559_n1744_n2501_n1630 (s = 8, m = 4, r = 5, w = 8; four rounds, period 4)

The rounds n2559, n1744, n2501, n1630, repeated in this order; the first message difference may be in any of rounds
1 to 4.

| Linear incompatibility | Open-end trail (lower bound) | Full collision (upper bound) | Exact | Shortest collision |
|---|---|---|---|---|
| off | 21 (11 rounds after each start: 22, 21, 21, 21) | 21 | **21** | |
| on | >= 23 (15 rounds after each of the 4 starts) | 23 (8 rounds; 24 over 5, 28 over 4, 45 over 3, none over 2) | **23** | 8 rounds or fewer |

With linear incompatibility, the open-end trails were solved per start (first message difference in round j, 15
rounds after it, for j = 1..4), each with a Gurobi cutoff at 22.5: no start has a trail of 22 or fewer active S-boxes,
so there is no open-end trail file. A trail of the one-solve model over N = 18 rounds whose first difference is in
round j <= 4 has at least 15 rounds from round j on, so the open-end trail over 18 rounds is >= 23. The collision of 23
(first difference in round 4, state and accumulator zero after round 8) followed by rounds without difference is a
collision over 18 rounds, so both are 23 over N = 18. The value over 18 rounds follows from these solves; `run_milp.py`
has not been run over 18 rounds for this design (the per-start solves took 19 to 39 hours with 20 threads each). The
collision over 10 rounds took 19 hours with 40 threads; over 6 and 7 rounds it was not solved, so the shortest
collision of 23 has 8 rounds or fewer.

Without linear incompatibility, the values are those of the genetic algorithm's run (open-end trails over 11 rounds
after each start, collision 21); its trails are not included here, and N is not set (`-`, so `run_milp.py` uses 20).

Trails in `s8_m4_r5_w8_n2559_n1744_n2501_n1630/` (all with linear incompatibility): collisions over 3 (45), 4 (28),
5 (24) and 10 rounds (23; the collision ends after round 8).
