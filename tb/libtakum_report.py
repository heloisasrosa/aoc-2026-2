#!/usr/bin/env python3
"""Lê a saída de tb/libtakum_check e decide, com aritmética exata, cada divergência.

A libtakum faz as operações em double. O produto de dois T32 precisa de até 56 bits
e o double tem 53: ela arredonda duas vezes (para double, depois para takum) e pode
errar o último bit. Para cada divergência, este script calcula o resultado exato
(Fraction) e vê qual dos dois candidatos está mais perto.

uso: python3 tb/libtakum_report.py build/libtakum.log
Sai com erro se alguma divergência der razão à libtakum.
"""
import sys
from fractions import Fraction

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import takum_oracle as o

OPS = {0: lambda a, b: a + b, 1: lambda a, b: a - b, 2: lambda a, b: a * b}
NAMES = {"dec": "decodificação e codificação", "alu": "soma, subtração, produto", "ncvt": "vncvt.t.t",
         "wmul": "produto alargado"}


def main():
    totals, diffs = [], {}
    for line in open(sys.argv[1]):
        t = line.split()
        if t[0] == "TOTAL":
            totals.append((t[1], int(t[2]), int(t[3]), int(t[4])))
        elif t[0] == "DIFF":
            diffs.setdefault((t[1], int(t[2])), []).append(t[3:])
    bad = 0
    for kind, n, total, nd in totals:
        label = f"libtakum T{n} {NAMES[kind]}"
        if nd == 0:
            print(f"PASS {label}: {total} vetores idênticos")
            continue
        ours_better = same = theirs_better = 0
        for d in diffs[(kind, n)]:
            if kind != "alu":
                theirs_better += 1          # não há arredondamento duplo possível aqui: é erro de alguém
                continue
            a, b, op = int(d[0], 16), int(d[1], 16), int(d[2])
            mine, theirs = int(d[3].split("=")[1], 16), int(d[4].split("=")[1], 16)
            exact = OPS[op](o.decode(a, n), o.decode(b, n))
            dm, dt = abs(o.decode(mine, n) - exact), abs(o.decode(theirs, n) - exact)
            if dm < dt:
                ours_better += 1
            elif dm == dt:
                same += 1
            else:
                theirs_better += 1
        if theirs_better == 0 and same == 0:
            print(f"PASS {label}: {total - nd} idênticos; {nd} divergências, e em todas o resultado exato "
                  f"está mais perto do valor do projeto (arredondamento duplo da libtakum em double)")
        else:
            bad += 1
            print(f"FAIL {label}: {nd} divergências em {total}: projeto mais perto em {ours_better}, "
                  f"empate em {same}, libtakum mais perto em {theirs_better}")
    print("==> CONFERE COM A LIBTAKUM" if not bad else "==> HÁ DIVERGÊNCIAS NÃO EXPLICADAS")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
