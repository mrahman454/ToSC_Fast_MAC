"""
Read a cipher description file and build the cipher for a given number of rounds.

File format (plain text; '#' starts a comment line):

    Design: <name>                      optional, free text
    Parameters: s=<s> m=<m> r=<r> w=<w> optional; checked against the matrices if present
    Rounds: <N>                         optional; the default number of rounds to analyse

    LAYER 1: LINEAR                     one LINEAR + one NONLINEAR block per round of the base period
    ----------------------------------------
    <s x s binary matrix, one row per line>

    LAYER 2: NONLINEAR
    ----------------------------------------
    Pattern: <s bits: 1 = AES round on that state word, 0 = identity>

    Transition matrix:
    <(s+r) x (m+r) binary matrix: rows = injected values V_0..V_{s-1}, then the new memory
     R'_0..R'_{r-1}; columns = message words M_0..M_{m-1}, then the old memory R_0..R_{r-1}>

    LAYER 3: LINEAR
    ...

The blocks describe one base period (e.g. 4 rounds for a base-4 design). A cipher of N rounds
applies them cyclically: round i (1-indexed) uses base round ((i - 1 + start) mod period).
s, m and r are read from the matrix sizes; w = number of AES words per round.
"""
import re
import numpy as np

from Cipher import Cipher

_LAYER = re.compile(r'^LAYER\s+(\d+):\s+(LINEAR|NONLINEAR)\s*$')
_ROW = re.compile(r'^-?\d+(\s+-?\d+)*$')


def _matrix(lines, i):
    rows = []
    while i < len(lines):
        t = lines[i].strip()
        if not t or not _ROW.match(t):
            break
        rows.append([int(x) for x in t.split()])
        i += 1
    return rows, i


def read_cipher_file(path):
    """Return {'name', 'rounds' (int or None), 's', 'm', 'r', 'w' (list per base round), 'base'}
    where 'base' is a list of rounds {'linear': array, 'pattern': array, 'transition': array}."""
    lines = [l.rstrip('\n') for l in open(path)]
    info = {'name': None, 'rounds': None, 'params': {}}
    for l in lines:
        t = l.strip()
        if t.startswith('Design:'):
            info['name'] = t.split(':', 1)[1].strip()
        elif t.startswith('Rounds:'):
            info['rounds'] = int(t.split(':', 1)[1].split()[0])
        elif t.startswith('Parameters:'):
            info['params'] = {k: int(v) for k, v in re.findall(r'(\w)=(\d+)', t)}

    base, linear, i = [], None, 0
    while i < len(lines):
        h = _LAYER.match(lines[i].strip())
        i += 1
        if not h:
            continue
        if i < len(lines) and lines[i].strip() and set(lines[i].strip()) <= {'-'}:
            i += 1
        if h.group(2) == 'LINEAR':
            rows, i = _matrix(lines, i)
            linear = np.array(rows, dtype=int)
            continue
        pattern, transition = None, None
        while i < len(lines) and not _LAYER.match(lines[i].strip()):
            t = lines[i].strip()
            if t.startswith('Pattern:'):
                pattern = np.array([int(x) for x in t.split(':', 1)[1].split()], dtype=int)
            elif t.startswith('Transition matrix'):
                rows, i = _matrix(lines, i + 1)
                transition = np.array(rows, dtype=int)
                continue
            i += 1
        if linear is None or pattern is None or transition is None:
            raise ValueError(f"{path}: round {len(base) + 1} needs a LINEAR matrix, a Pattern and a Transition matrix")
        base.append({'linear': linear, 'pattern': pattern, 'transition': transition})
        linear = None
    if not base:
        raise ValueError(f"{path}: no rounds found")

    s = base[0]['linear'].shape[0]
    rows, cols = base[0]['transition'].shape
    r = rows - s
    m = cols - r
    for k, rd in enumerate(base, 1):
        if rd['linear'].shape != (s, s) or len(rd['pattern']) != s or rd['transition'].shape != (s + r, m + r):
            raise ValueError(f"{path}: base round {k} has inconsistent sizes (s={s}, m={m}, r={r})")
    w = [int(rd['pattern'].sum()) for rd in base]
    for k, v in info['params'].items():
        got = {'s': s, 'm': m, 'r': r, 'w': w[0]}.get(k)
        if got is not None and got != v:
            raise ValueError(f"{path}: Parameters line says {k}={v}, matrices give {k}={got}")
    return {'name': info['name'], 'rounds': info['rounds'], 's': s, 'm': m, 'r': r, 'w': w, 'base': base}


def build_cipher(desc, rounds, start=0):
    """Cipher of `rounds` rounds; round i uses base round ((i + start) mod period), i = 0..rounds-1."""
    c = Cipher(s=desc['s'], m=desc['m'], r=desc['r'])
    P = len(desc['base'])
    for i in range(rounds):
        rd = desc['base'][(i + start) % P]
        c.add_linear_layer(matrix=rd['linear'].copy())
        c.add_nonlinear_pattern(nonlinear_pattern=rd['pattern'].copy(), with_transition=True,
                                transition_matrix=rd['transition'].copy())
    return c
