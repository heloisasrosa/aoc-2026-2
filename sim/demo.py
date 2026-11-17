#!/usr/bin/env python3
"""Demonstração: produto escalar de dois vetores T16 com vtdot.vv, mostrando o rastro.

uso: python3 -m sim.demo
"""
from fractions import Fraction

from . import formats as F
from .rvv import Machine

# 1e6 + 3 - 1e6 + 0.5 + ...: em 16 bits o 3 some ao lado de 1e6; em 32 bits não
X = [1000.0, 1.5, -1000.0, 2.0, 0.75, 4.0, -3.0, 0.5, 6.0, 1.25]
Y = [1000.0, 2.0, 1000.0, 0.25, 4.0, 0.5, 1.0, 8.0, 0.125, 2.0]

SRC = """
    li   a0, {n}                    # nº de elementos
    li   a1, 0x1000                 # &x
    li   a2, 0x2000                 # &y
    li   a3, 0x3000                 # &resultado
    li   s1, 1
    vsetvli zero, s1, e64, m1, ta, ma
    vmv.s.x v4, zero                # acumulador (T32) = 0
loop:
    vsetvli t0, a0, e16, m1, ta, ma
    vle16.v v1, (a1)
    vle16.v v2, (a2)
    vtdot.vv v4, v1, v2             # v4[0] += soma v1[i]*v2[i], em T32
    slli t1, t0, 1
    add  a1, a1, t1
    add  a2, a2, t1
    sub  a0, a0, t0
    bnez a0, loop
    vsetvli zero, s1, e16, m1, ta, ma
    vncvt.t.t v5, v4                # T32 -> T16
    vse16.v v5, (a3)
    ebreak
"""


def main():
    t16, t32 = F.T16, F.T32
    m = Machine(vlen=128, mem_size=1 << 16, trace=True)
    m.write_array(0x1000, [t16.enc(Fraction(v)) for v in X], 2)
    m.write_array(0x2000, [t16.enc(Fraction(v)) for v in Y], 2)
    words = m.load_program(SRC.format(n=len(X)))
    print(f"programa: {len(words)} palavras, VLEN = {m.vlen}\n")
    m.run()
    exact = sum(Fraction(a) * Fraction(b) for a, b in zip(X, Y))
    acc = m.el(4, 0, 32)
    res = m.load(0x3000, 2)
    plain = 0
    for a, b in zip(X, Y):
        plain = t16.add(plain, t16.mul(t16.enc(Fraction(a)), t16.enc(Fraction(b))))
    print(f"\ninstruções executadas: {sum(m.count.values())}  ({dict(m.count)})")
    print(f"exato (dados em binary64)       = {float(exact):.9f}")
    print(f"acumulador T32  (0x{acc:08x})    = {float(t32.dec(acc)):.9f}")
    print(f"resultado T16   (0x{res:04x})        = {float(t16.dec(res)):.9f}   <- vtdot.vv + vncvt.t.t")
    print(f"T16 sem ampliar (0x{plain:04x})        = {float(t16.dec(plain)):.9f}   <- vtmul + vtadd em 16 bits")


if __name__ == "__main__":
    main()
