"""Simulador funcional, em nível de instrução, de um subconjunto de RV64I + RVV 1.0 + Zvtakum.

A máquina busca palavras de 32 bits na memória, decodifica (isa.decode) e executa.
Conta as instruções executadas por mnemônico e guarda o estado de CSR que cada
aritmética usa: vl e vtype (ambas), fcsr.fflags (só IEEE; o takum não tem flags
nem modos de arredondamento).

Simplificações: vstart = 0 sempre; cauda e elementos mascarados ficam inalterados;
só arredondamento para o mais próximo (frm = RNE).
"""
from collections import Counter

from . import formats as F
from . import isa

M64 = (1 << 64) - 1


def sx(v, bits=64):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


class Machine:
    def __init__(self, vlen=128, mem_size=1 << 20, fp=None, trace=False):
        self.vlen = vlen
        self.x = [0] * 32
        self.v = [0] * 32
        self.mem = bytearray(mem_size)
        self.pc = 0
        self.vl, self.vtype = 0, 0
        self.sew, self.lmul = 8, (1, 1)
        ie = F.ieee_set()
        self.fp = fp or {8: ie["FP8"], 16: ie["FP16"], 32: ie["FP32"], 64: ie["FP64"]}
        self.tk = {8: F.T8, 16: F.T16, 32: F.T32, 64: F.T64}
        self.count = Counter()
        self.trace = trace
        self.src = {}

    # ---- memória -----------------------------------------------------------
    def load(self, addr, nbytes):
        return int.from_bytes(self.mem[addr:addr + nbytes], "little")

    def store(self, addr, nbytes, val):
        self.mem[addr:addr + nbytes] = (val & ((1 << (8 * nbytes)) - 1)).to_bytes(nbytes, "little")

    def write_array(self, addr, values, nbytes):
        for i, v in enumerate(values):
            self.store(addr + i * nbytes, nbytes, v)

    def read_array(self, addr, n, nbytes):
        return [self.load(addr + i * nbytes, nbytes) for i in range(n)]

    def load_program(self, src, base=0):
        words, lines = isa.assemble(src, base)
        self.write_array(base, words, 4)
        self.src = {base + 4 * i: l for i, l in enumerate(lines)}
        return words

    # ---- registradores vetoriais (grupos: o elemento i pode cair em v[reg+k]) --
    def el(self, reg, i, eew):
        off = i * eew
        return (self.v[reg + off // self.vlen] >> (off % self.vlen)) & ((1 << eew) - 1)

    def set_el(self, reg, i, eew, val):
        off = i * eew
        r, sh = reg + off // self.vlen, off % self.vlen
        m = ((1 << eew) - 1) << sh
        self.v[r] = (self.v[r] & ~m) | ((val << sh) & m)

    def active(self, vm):
        """Índices dos elementos de corpo não mascarados."""
        return [i for i in range(self.vl) if vm or (self.v[0] >> i) & 1]

    @property
    def fflags(self):
        fl = 0
        for f in self.fp.values():
            fl |= f.flags
        return fl

    # ---- execução ----------------------------------------------------------------
    def run(self, pc=0, max_steps=50_000_000):
        self.pc = pc
        for _ in range(max_steps):
            if not self.step():
                return
        raise RuntimeError("limite de passos excedido")

    def step(self):
        w = self.load(self.pc, 4)
        mn, f = isa.decode(w)
        if self.trace:
            print(f"{self.pc:04x}: {w:08x}  {self.src.get(self.pc, mn)}")
        self.count[mn] += 1
        nxt = self.pc + 4
        x, sew = self.x, self.sew

        if mn == "ebreak":
            return False
        elif mn == "add":
            r = x[f["rs1"]] + x[f["rs2"]]
            x[f["rd"]] = r & M64
        elif mn == "sub":
            x[f["rd"]] = (x[f["rs1"]] - x[f["rs2"]]) & M64
        elif mn == "addi":
            x[f["rd"]] = (x[f["rs1"]] + f["imm"]) & M64
        elif mn == "slli":
            x[f["rd"]] = (x[f["rs1"]] << f["imm"]) & M64
        elif mn == "lui":
            x[f["rd"]] = f["imm"] & M64
        elif mn == "lw":
            x[f["rd"]] = sx(self.load((x[f["rs1"]] + f["imm"]) & M64, 4), 32) & M64
        elif mn in ("beq", "bne", "blt", "bge"):
            a, b = sx(x[f["rs1"]]), sx(x[f["rs2"]])
            if {"beq": a == b, "bne": a != b, "blt": a < b, "bge": a >= b}[mn]:
                nxt = self.pc + f["imm"]
        elif mn == "vsetvli":
            vt = f["vtype"]
            self.vtype, self.sew, self.lmul = vt, 8 << ((vt >> 3) & 7), isa.LMUL_VAL[vt & 7]
            vlmax = self.vlen * self.lmul[0] // (self.lmul[1] * self.sew)
            if f["rs1"]:
                self.vl = min(x[f["rs1"]], vlmax)
            elif f["rd"]:
                self.vl = vlmax
            x[f["rd"]] = self.vl
        elif mn.startswith("vle"):
            eew, base = f["eew"], x[f["rs1"]]
            for i in self.active(f["vm"]):
                self.set_el(f["vd"], i, eew, self.load(base + i * eew // 8, eew // 8))
        elif mn.startswith("vse"):
            eew, base = f["eew"], x[f["rs1"]]
            for i in self.active(f["vm"]):
                self.store(base + i * eew // 8, eew // 8, self.el(f["vs3"], i, eew))
        elif mn.startswith("vluxei"):
            base = x[f["rs1"]]
            for i in self.active(f["vm"]):
                self.set_el(f["vd"], i, sew, self.load(base + self.el(f["vs2"], i, f["eew"]), sew // 8))
        elif mn == "vmv.v.i":
            for i in range(self.vl):
                self.set_el(f["vd"], i, sew, f["imm"])
        elif mn == "vmv.s.x":
            if self.vl:
                self.set_el(f["vd"], 0, sew, x[f["rs1"]])
        elif mn in ("vfadd.vv", "vfsub.vv", "vfmul.vv", "vtadd.vv", "vtsub.vv", "vtmul.vv"):
            fmt = (self.tk if mn[1] == "t" else self.fp)[sew]
            op = getattr(fmt, mn[2:5])
            for i in self.active(f["vm"]):
                self.set_el(f["vd"], i, sew, op(self.el(f["vs2"], i, sew), self.el(f["vs1"], i, sew)))
        elif mn == "vfwmul.vv":
            n, w2 = self.fp[sew], self.fp[2 * sew]
            for i in self.active(f["vm"]):
                a, b = w2.cvt_from(n, self.el(f["vs2"], i, sew)), w2.cvt_from(n, self.el(f["vs1"], i, sew))
                self.set_el(f["vd"], i, 2 * sew, w2.mul(a, b))
        elif mn in ("vfredosum.vs", "vfwredosum.vs"):
            wide = mn == "vfwredosum.vs"
            ew = 2 * sew if wide else sew
            fmt = self.fp[ew]
            acc = self.el(f["vs1"], 0, ew)
            for i in self.active(f["vm"]):
                e = self.el(f["vs2"], i, sew)
                acc = fmt.add(acc, fmt.cvt_from(self.fp[sew], e) if wide else e)
            if self.vl:
                self.set_el(f["vd"], 0, ew, acc)
        elif mn == "vfncvt.f.f.w":
            for i in self.active(f["vm"]):
                self.set_el(f["vd"], i, sew, self.fp[sew].cvt_from(self.fp[2 * sew], self.el(f["vs2"], i, 2 * sew)))
        elif mn == "vtdot.vv":
            # vd[0] (2*SEW) += soma vs2[i] * vs1[i]; produtos e acúmulo em 2*SEW
            idx = self.active(f["vm"])
            acc = F.oracle.dot(self.el(f["vd"], 0, 2 * sew), [self.el(f["vs2"], i, sew) for i in idx],
                               [self.el(f["vs1"], i, sew) for i in idx], sew)
            if self.vl:
                self.set_el(f["vd"], 0, 2 * sew, acc)
        elif mn == "vncvt.t.t":
            for i in self.active(f["vm"]):
                self.set_el(f["vd"], i, sew, F.oracle.ncvt(self.el(f["vs2"], i, 2 * sew), sew))
        else:
            raise NotImplementedError(mn)
        x[0] = 0
        self.pc = nxt
        return True
