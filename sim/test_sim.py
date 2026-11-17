#!/usr/bin/env python3
"""Autotestes do simulador.   uso: python3 -m sim.test_sim

1. IEEE: binary16/32/64 do modelo contra o ponto flutuante nativo (struct / float).
2. Montador: decode(encode(i)) reproduz todas as instruções dos kernels.
3. Zvtakum no simulador contra os vetores que verificam o RTL (build/vec*.hex):
   a mesma instrução, executada pela máquina a partir da palavra de 32 bits,
   tem de dar o mesmo vd que a takum_vec_alu.
4. vl, cauda e máscara nas instruções IEEE; laço com vsetvli.
"""
import math
import os
import random
import struct
import sys
from fractions import Fraction

from . import formats as F
from . import isa, kernels
from .rvv import Machine

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
fails = 0


def check(name, ok, detail=""):
    global fails
    print(f"{'PASS' if ok else 'FAIL'} sim {name}{': ' + detail if detail else ''}")
    fails += not ok


def test_ieee(n=20000):
    s = F.ieee_set()
    rng = random.Random(5)
    bad = 0
    # conversão: binary64 -> binary16 / binary32 contra struct
    for fmt, code in ((s["FP16"], "<e"), (s["FP32"], "<f")):
        size = fmt.n // 8
        for _ in range(n):
            v = rng.choice((1, -1)) * 2.0 ** rng.uniform(-40 if size == 2 else -160, 20 if size == 2 else 130)
            try:
                want = int.from_bytes(struct.pack(code, v), "little")
            except OverflowError:
                want = fmt.inf_bits | ((v < 0) << (fmt.n - 1))
            bad += fmt.enc(Fraction(v)) != want
    check("IEEE conversão (binary16, binary32 x struct)", bad == 0, f"{2 * n} casos")
    # operações: binary32 contra double arredondado (inócuo para + - *), binary64 contra float
    bad = 0
    f32, f64 = s["FP32"], s["FP64"]
    r32 = lambda v: struct.unpack("<f", struct.pack("<f", v))[0]
    b32 = lambda v: int.from_bytes(struct.pack("<f", v), "little")
    b64 = lambda v: int.from_bytes(struct.pack("<d", v), "little")
    for _ in range(n):
        a = r32(rng.gauss(0, 1) * 2.0 ** rng.randint(-30, 30))
        b = r32(rng.gauss(0, 1) * 2.0 ** rng.randint(-30, 30))
        if rng.random() < 0.2:
            b = r32(-a * (1 + rng.choice((0, 1e-7, -1e-7))))
        for op, py in (("add", a + b), ("sub", a - b), ("mul", a * b)):
            bad += getattr(f32, op)(b32(a), b32(b)) != b32(py)
            bad += getattr(f64, op)(b64(a), b64(b)) != b64(py)
    check("IEEE add/sub/mul (binary32, binary64 x nativo)", bad == 0, f"{6 * n} casos")
    # especiais
    f16 = s["FP16"]
    inf, big = f16.inf_bits, f16.enc(Fraction(65504))
    ok = (f16.add(big, big) == inf and f16.sub(inf, inf) == f16.nan_bits and f16.mul(inf, 0) == f16.nan_bits
          and f16.mul(f16.enc(Fraction(1, 2 ** 20)), f16.enc(Fraction(1, 2 ** 20))) == 0
          and f16.flags & F.OF and f16.flags & F.NV and f16.flags & F.UF)
    check("IEEE especiais (overflow -> inf, inf - inf -> NaN, underflow, fflags)", bool(ok))


def test_asm():
    n = 0
    for variant in ("takum", "ieee", "ieee_w"):
        for sew in (8, 16, 32):
            words, lines = isa.assemble(kernels.spmv(variant, sew))
            for w, line in zip(words, lines):
                mn, f = isa.decode(w)
                assert mn == line.split()[0], (mn, line)
                n += 1
    extra = ["vtadd.vv v1, v2, v3", "vtsub.vv v1, v2, v3, v0.t", "vtmul.vv v31, v30, v29", "vfadd.vv v1, v2, v3",
             "vfwredosum.vs v1, v2, v3", "vmv.v.i v1, -3"]
    for line in extra:
        w = isa.assemble(line)[0][0]
        mn, f = isa.decode(w)
        assert mn == line.split()[0]
        if "v0.t" in line:
            assert f["vm"] == 0
        n += 1
    w = isa.assemble("vtadd.vv v1, v2, v3")[0][0]
    ok = (w & 0x7F) == isa.OP_T and (w >> 26) == 0 and ((w >> 12) & 7) == 1
    check("montador: encode/decode", ok, f"{n} instruções")


def test_rtl_vectors():
    """Roda cada vetor do RTL como uma instrução Zvtakum na máquina (VLEN = 64)."""
    names = ["vtadd.vv v3, v2, v1", "vtsub.vv v3, v2, v1", "vtmul.vv v3, v2, v1", "vtdot.vv v3, v2, v1",
             "vncvt.t.t v3, v2"]
    for sew in (8, 16, 32):
        path = os.path.join(ROOT, "build", f"vec{sew}.hex")
        if not os.path.exists(path):
            print(f"SKIP sim x vetores do RTL SEW={sew}: rode 'make vec' antes")
            continue
        m = Machine(vlen=64, mem_size=4096)
        prog = {}
        for op, line in enumerate(names):
            for vm in (0, 1):
                prog[(op, vm)] = isa.assemble(line + ("" if vm else ", v0.t"))[0][0]
        bad = n = 0
        for row in open(path):
            vs2, vs1, old, op, vl, vm, v0, vd = (int(t, 16) for t in row.split())
            m.x[5] = vl
            m.write_array(0, [isa.assemble(f"vsetvli zero, t0, e{sew}, m1, ta, ma")[0][0], prog[(op, vm)], 0x00100073], 4)
            m.v[0], m.v[1], m.v[2], m.v[3] = v0, vs1, vs2, old
            m.run()
            bad += m.v[3] != vd
            n += 1
        check(f"Zvtakum x vetores do RTL SEW={sew}", bad == 0, f"{n} vetores" if not bad else f"{bad} divergências")


def test_vector_semantics():
    m = Machine(vlen=128, mem_size=1 << 16)
    f32 = m.fp[32]
    enc = lambda v: f32.enc(Fraction(v))
    m.write_array(0x1000, [enc(v) for v in (1.5, 2.0, -3.0, 4.0, 5.0, 6.0, 7.0)], 4)
    m.write_array(0x2000, [enc(v) for v in (2.0, 0.5, 1.0, 0.25, 2.0, 1.0, 1.0)], 4)
    m.load_program("""
        li   a0, 7
        li   a1, 0x1000
        li   a2, 0x2000
        li   a3, 0x3000
        li   s1, 1
        vsetvli zero, s1, e32, m1, ta, ma
        vmv.s.x v4, zero
    loop:
        vsetvli t0, a0, e32, m1, ta, ma
        vle32.v v1, (a1)
        vle32.v v2, (a2)
        vfmul.vv v3, v1, v2
        vfredosum.vs v4, v3, v4
        slli t1, t0, 2
        add  a1, a1, t1
        add  a2, a2, t1
        sub  a0, a0, t0
        bnez a0, loop
        vsetvli zero, s1, e32, m1, ta, ma
        vse32.v v4, (a3)
        ebreak
    """)
    m.run()
    got = f32.dec(m.load(0x3000, 4))
    check("laço com vsetvli (produto escalar IEEE, 7 elementos, VLEN=128)", got == Fraction(25), f"= {float(got)}")
    # máscara e cauda
    m = Machine(vlen=64, mem_size=4096)
    m.v[0] = 0b0101
    m.v[1] = sum(F.T8.enc(Fraction(1)) << (8 * i) for i in range(8))
    m.v[2] = sum(F.T8.enc(Fraction(i)) << (8 * i) for i in range(8))
    m.v[3] = 0
    m.x[5] = 6
    m.load_program("vsetvli zero, t0, e8, m1, ta, ma\nvtadd.vv v3, v2, v1, v0.t\nebreak")
    m.run()
    got = [F.T8.dec((m.v[3] >> (8 * i)) & 255) for i in range(8)]
    check("máscara v0.t e cauda (vtadd.vv)", got == [1, 0, 3, 0, 0, 0, 0, 0])


if __name__ == "__main__":
    test_ieee()
    test_asm()
    test_rtl_vectors()
    test_vector_semantics()
    print("==> SIMULADOR OK" if not fails else f"==> {fails} FALHA(S) NO SIMULADOR")
    sys.exit(1 if fails else 0)
