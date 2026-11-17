#!/usr/bin/env python3
"""Gera vetores de teste da ALU (a b op y) e do módulo vetorial, em hexadecimal.

uso: gen_vectors.py alu  N   QTD ARQUIVO   (N = 8: todos os pares; senão amostra com bordas)
     gen_vectors.py vec  SEW QTD ARQUIVO   (vtadd, vtsub, vtmul, vtdot, vncvt.t.t, com vl e máscara)
     gen_vectors.py ncvt N   QTD ARQUIVO   (T2N -> TN; N = 8: todos os 65 536 padrões)
     gen_vectors.py wmul N   QTD ARQUIVO   (TN x TN -> T2N; N = 8: todos os pares)
     gen_vectors.py dec  N   QTD ARQUIVO   (padrão -> valor; N <= 16: todos os padrões)
"""
import random
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import takum_oracle as o


def interesting(n):
    """Padrões de borda: zero, NaR, menor/maior, perto de 1, de cada regime, vizinhos."""
    s = {0, o.nar(n), 1, (1 << (n - 1)) - 1, (1 << n) - 1, o.nar(n) + 1, o.nar(n) - 1}
    for r in range(8):
        for d in (0, 1):
            for br in (r, 7 - r):
                top = (d << (n - 2)) | (br << (n - 5))
                for low in (0, 1, (1 << (n - 5)) - 1, 1 << (n - 6)):
                    for sg in (0, 1 << (n - 1)):
                        v = (sg | top | low) & ((1 << n) - 1)
                        s.add(v)
                        s.add((-v) & ((1 << n) - 1))
    for k in (1.0, 2.0, 0.5, 3.0, 0.25):
        s.add(o.encode(__import__("fractions").Fraction(k), n))
    return sorted(s)


def gen_alu(n, count, out):
    rng = random.Random(2026)
    pairs = []
    if n == 8:
        pairs = [(a, b) for a in range(256) for b in range(256)]
    else:
        edge = interesting(n)
        pairs = [(a, b) for a in edge[::max(1, len(edge) // 90)] for b in edge[::max(1, len(edge) // 90)]]
        top = 1 << n
        for _ in range(count):
            a = rng.randrange(top)
            kind = rng.random()
            if kind < 0.25:                      # b = vizinho de a (cancelamento na soma)
                b = (a + rng.randint(-3, 3)) % top
            elif kind < 0.5:                     # b = -a (+- ruído)
                b = (-a + rng.randint(-2, 2)) % top
            else:
                b = rng.randrange(top)
            pairs.append((a, b))
    with open(out, "w") as f:
        for a, b in pairs:
            for op in (0, 1, 2):
                f.write(f"{a:0{(n+3)//4}x} {b:0{(n+3)//4}x} {op} {o.alu(a, b, op, n):0{(n+3)//4}x}\n")
    print(f"{out}: {len(pairs) * 3} vetores")


VLEN = 64
ADD, SUB, MUL, DOT, NCVT = range(5)


def vec_model(op, sew, vl, vm, v0, vs2, vs1, old):
    """Modelo da takum_vec_alu (VLEN = 64). É a mesma semântica usada pelo simulador RVV."""
    m = (1 << sew) - 1
    lanes = VLEN // sew
    el = lambda v, i, w=sew: (v >> (i * w)) & ((1 << w) - 1)
    on = [i < vl and (vm or (v0 >> i) & 1) for i in range(lanes)]
    if op == DOT:
        acc = old & ((1 << (2 * sew)) - 1)
        idx = [i for i in range(lanes) if on[i]]
        acc = o.dot(acc, [el(vs2, i) for i in idx], [el(vs1, i) for i in idx], sew)
        return (old >> (2 * sew) << (2 * sew)) | acc
    vd = 0
    for i in range(lanes):
        if op == NCVT:
            ok = on[i] and i < lanes // 2
            r = o.ncvt(el(vs2, i, 2 * sew), sew) if ok else el(old, i)
        else:
            r = o.alu(el(vs2, i), el(vs1, i), op, sew) if on[i] else el(old, i)
        vd |= (r & m) << (i * sew)
    return vd


def gen_vec(sew, count, out):
    rng = random.Random(7 + sew)
    lanes = VLEN // sew
    edge = interesting(sew)
    edge2 = interesting(2 * sew)
    with open(out, "w") as f:
        for _ in range(count):
            op = rng.randrange(5)
            vl = rng.randint(0, lanes // 2 if op == NCVT else lanes)
            vm = rng.randrange(2)
            v0 = rng.randrange(1 << lanes)
            def word(w=sew, e=edge):
                return sum((rng.choice(e) if rng.random() < 0.3 else rng.randrange(1 << w)) << (i * w)
                           for i in range(VLEN // w))
            vs2, vs1, old = word(), word(), word()
            if op == NCVT:                       # origem em 2*SEW
                vs2 = word(2 * sew, edge2)
                if rng.random() < 0.3:           # empates e quase-empates do arredondamento
                    half = 1 << (sew - 1)
                    vs2 = sum((((vs2 >> (i * 2 * sew + sew)) << sew) | ((half + rng.randint(-1, 1)) % (1 << sew)))
                              % (1 << (2 * sew)) << (i * 2 * sew) for i in range(VLEN // (2 * sew)))
            if op == DOT and rng.random() < 0.5:  # acumulador com valor "normal", perto dos produtos
                acc = o.dot(0, [rng.choice(edge)], [rng.choice(edge)], sew) if rng.random() < 0.5 else rng.choice(edge2)
                old = (old >> (2 * sew) << (2 * sew)) | acc
            vd = vec_model(op, sew, vl, vm, v0, vs2, vs1, old)
            f.write(f"{vs2:016x} {vs1:016x} {old:016x} {op} {vl:x} {vm} {v0:02x} {vd:016x}\n")
    print(f"{out}: {count} vetores")


def gen_ncvt(n, count, out):
    rng = random.Random(11 + n)
    h = (2 * n + 3) // 4
    if n == 8:
        pats = range(1 << 16)
    else:
        top, half = 1 << (2 * n), 1 << (n - 1)
        pats = list(interesting(2 * n))
        for _ in range(count):
            t = rng.randrange(top)
            if rng.random() < 0.5:               # empate ou vizinho de empate
                t = ((t >> n) << n) | ((half + rng.randint(-1, 1)) % (1 << n))
            pats.append(t)
    k = 0
    with open(out, "w") as f:
        for t in pats:
            f.write(f"{t:0{h}x} {o.ncvt(t, n):0{h // 2}x}\n")
            k += 1
    print(f"{out}: {k} vetores")


def gen_wmul(n, count, out):
    rng = random.Random(13 + n)
    h = (n + 3) // 4
    if n == 8:
        pairs = [(a, b) for a in range(256) for b in range(256)]
    else:
        edge = interesting(n)
        e = edge[::max(1, len(edge) // 90)]
        pairs = [(a, b) for a in e for b in e] + [(rng.randrange(1 << n), rng.randrange(1 << n)) for _ in range(count)]
    with open(out, "w") as f:
        for a, b in pairs:
            f.write(f"{a:0{h}x} {b:0{h}x} {o.wmul(a, b, n):0{2 * h}x}\n")
    print(f"{out}: {len(pairs)} vetores")


def gen_dec(n, count, out):
    """Padrão -> valor exato (hexadecimal de ponto flutuante), para conferir a decodificação."""
    rng = random.Random(17 + n)
    pats = range(1 << n) if n <= 16 else sorted(set(interesting(n)) | {rng.randrange(1 << n) for _ in range(count)})
    k = 0
    with open(out, "w") as f:
        for t in pats:
            v = o.decode(t, n)
            f.write(f"{t:0{n // 4}x} {'nan' if v is None else float(v).hex()}\n")   # exato: <= 27 bits de fração
            k += 1
    print(f"{out}: {k} vetores")


if __name__ == "__main__":
    kind, n, count, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    {"alu": gen_alu, "vec": gen_vec, "ncvt": gen_ncvt, "wmul": gen_wmul, "dec": gen_dec}[kind](n, count, out)
