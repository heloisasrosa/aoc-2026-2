"""Montador, codificação e decodificação do subconjunto RISC-V usado no projeto.

Cobre o mínimo de RV64I para escrever laços, o subconjunto de RVV 1.0 usado nos
kernels (configuração, cargas/armazenamentos, ponto flutuante vetorial) e a
proposta Zvtakum.

Codificação do Zvtakum: mesmo layout do OP-V,

    31    26 25 24  20 19  15 14 12 11  7 6     0
    funct6   vm  vs2    vs1   funct3  vd   opcode

com opcode custom-2 (1011011), funct3 = 001 (como OPFVV) e o funct6 da instrução
de ponto flutuante equivalente, para o decodificador poder ser compartilhado:

    vtadd.vv   000000      (vfadd.vv)
    vtsub.vv   000010      (vfsub.vv)
    vtmul.vv   100100      (vfmul.vv)
    vtdot.vv   111001      (sem equivalente direto: vfwmul + redução)
    vncvt.t.t  010010, vs1 = 10100   (vfncvt.f.f.w)
"""
import re

OP_V, OP_T = 0x57, 0x5B          # OP-V e custom-2 (Zvtakum)
LOAD_FP, STORE_FP = 0x07, 0x27

_ABI = ("zero ra sp gp tp t0 t1 t2 s0 s1 a0 a1 a2 a3 a4 a5 a6 a7 "
        "s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 t3 t4 t5 t6").split()
XREG = {n: i for i, n in enumerate(_ABI)}
XREG.update({f"x{i}": i for i in range(32)})
VREG = {f"v{i}": i for i in range(32)}

# nome: (opcode, funct6, funct3)       operandos: vd, vs2, vs1 [, v0.t]
VV = {
    "vfadd.vv":      (OP_V, 0b000000, 1),
    "vfsub.vv":      (OP_V, 0b000010, 1),
    "vfmul.vv":      (OP_V, 0b100100, 1),
    "vfwmul.vv":     (OP_V, 0b111000, 1),
    "vfredosum.vs":  (OP_V, 0b000011, 1),
    "vfwredosum.vs": (OP_V, 0b110011, 1),
    "vtadd.vv":      (OP_T, 0b000000, 1),
    "vtsub.vv":      (OP_T, 0b000010, 1),
    "vtmul.vv":      (OP_T, 0b100100, 1),
    "vtdot.vv":      (OP_T, 0b111001, 1),
}
# nome: (opcode, funct6, funct3, vs1 fixo)   operandos: vd, vs2 [, v0.t]
VUN = {
    "vfncvt.f.f.w":  (OP_V, 0b010010, 1, 0b10100),
    "vncvt.t.t":     (OP_T, 0b010010, 1, 0b10100),
}
ZVTAKUM = ("vtadd.vv", "vtsub.vv", "vtmul.vv", "vtdot.vv", "vncvt.t.t")

_R = {"add": (0, 0x00), "sub": (0, 0x20)}
_B = {"beq": 0, "bne": 1, "blt": 4, "bge": 5}
_WIDTH = {8: 0b000, 16: 0b101, 32: 0b110, 64: 0b111}
_WIDTH_INV = {v: k for k, v in _WIDTH.items()}
_SEW = {8: 0, 16: 1, 32: 2, 64: 3}
_LMUL = {"m1": 0, "m2": 1, "m4": 2, "m8": 3, "mf8": 5, "mf4": 6, "mf2": 7}
LMUL_VAL = {0: (1, 1), 1: (2, 1), 2: (4, 1), 3: (8, 1), 5: (1, 8), 6: (1, 4), 7: (1, 2)}


def _sx(v, bits):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def _mem(arg):
    m = re.fullmatch(r"(-?\w*)\((\w+)\)", arg)
    if not m:
        raise ValueError(f"operando de memória inválido: {arg}")
    return (int(m.group(1), 0) if m.group(1) else 0), XREG[m.group(2)]


def _vfields(op, f6, vm, vs2, vs1, f3, vd):
    return (f6 << 26) | (vm << 25) | (vs2 << 20) | (vs1 << 15) | (f3 << 12) | (vd << 7) | op


def encode(mn, a, pc=0, labels=None):
    """Uma instrução (mnemônico + lista de operandos em texto) -> palavra de 32 bits."""
    vm = 1
    if a and a[-1] == "v0.t":
        vm, a = 0, a[:-1]
    tgt = lambda s: (labels[s] - pc) if labels and s in labels else int(s, 0)
    if mn in VV:
        op, f6, f3 = VV[mn]
        return _vfields(op, f6, vm, VREG[a[1]], VREG[a[2]], f3, VREG[a[0]])
    if mn in VUN:
        op, f6, f3, vs1 = VUN[mn]
        return _vfields(op, f6, vm, VREG[a[1]], vs1, f3, VREG[a[0]])
    if mn in _R:
        f3, f7 = _R[mn]
        return (f7 << 25) | (XREG[a[2]] << 20) | (XREG[a[1]] << 15) | (f3 << 12) | (XREG[a[0]] << 7) | 0x33
    if mn == "addi":
        return ((int(a[2], 0) & 0xFFF) << 20) | (XREG[a[1]] << 15) | (XREG[a[0]] << 7) | 0x13
    if mn == "slli":
        return ((int(a[2], 0) & 0x3F) << 20) | (XREG[a[1]] << 15) | (1 << 12) | (XREG[a[0]] << 7) | 0x13
    if mn == "lui":
        return ((int(a[1], 0) & 0xFFFFF) << 12) | (XREG[a[0]] << 7) | 0x37
    if mn == "lw":
        imm, rs1 = _mem(a[1])
        return ((imm & 0xFFF) << 20) | (rs1 << 15) | (2 << 12) | (XREG[a[0]] << 7) | 0x03
    if mn in _B:
        o = tgt(a[2])
        return (((o >> 12) & 1) << 31) | (((o >> 5) & 0x3F) << 25) | (XREG[a[1]] << 20) | (XREG[a[0]] << 15) | \
               (_B[mn] << 12) | (((o >> 1) & 0xF) << 8) | (((o >> 11) & 1) << 7) | 0x63
    if mn == "ebreak":
        return 0x00100073
    if mn == "vsetvli":
        vt = _LMUL[a[3]] | (_SEW[int(a[2][1:])] << 3) | (("ta" in a[4:]) << 6) | (("ma" in a[4:]) << 7)
        return (vt << 20) | (XREG[a[1]] << 15) | (7 << 12) | (XREG[a[0]] << 7) | OP_V
    if mn == "vmv.v.i":
        return _vfields(OP_V, 0b010111, 1, 0, int(a[1], 0) & 0x1F, 3, VREG[a[0]])
    if mn == "vmv.s.x":
        return _vfields(OP_V, 0b010000, 1, 0, XREG[a[1]], 6, VREG[a[0]])
    m = re.fullmatch(r"v(l|s)e(\d+)\.v", mn)
    if m:
        imm, rs1 = _mem(a[1])
        op = LOAD_FP if m.group(1) == "l" else STORE_FP
        return (vm << 25) | (rs1 << 15) | (_WIDTH[int(m.group(2))] << 12) | (VREG[a[0]] << 7) | op
    m = re.fullmatch(r"vluxei(\d+)\.v", mn)
    if m:
        imm, rs1 = _mem(a[1])
        return (0b01 << 26) | (vm << 25) | (VREG[a[2]] << 20) | (rs1 << 15) | (_WIDTH[int(m.group(1))] << 12) | \
               (VREG[a[0]] << 7) | LOAD_FP
    raise ValueError(f"instrução desconhecida: {mn}")


_VV_INV = {(op, f6, f3): n for n, (op, f6, f3) in VV.items()}
_VUN_INV = {(op, f6, f3, v1): n for n, (op, f6, f3, v1) in VUN.items()}
_R_INV = {v: k for k, v in _R.items()}
_B_INV = {v: k for k, v in _B.items()}


def decode(w):
    """Palavra de 32 bits -> (mnemônico, dicionário de campos)."""
    op, rd, f3, rs1, rs2 = w & 0x7F, (w >> 7) & 31, (w >> 12) & 7, (w >> 15) & 31, (w >> 20) & 31
    f6, vm = w >> 26, (w >> 25) & 1
    if w == 0x00100073:
        return "ebreak", {}
    if op == 0x33:
        return _R_INV[(f3, w >> 25)], dict(rd=rd, rs1=rs1, rs2=rs2)
    if op == 0x13:
        if f3 == 0:
            return "addi", dict(rd=rd, rs1=rs1, imm=_sx(w >> 20, 12))
        if f3 == 1:
            return "slli", dict(rd=rd, rs1=rs1, imm=(w >> 20) & 0x3F)
    if op == 0x37:
        return "lui", dict(rd=rd, imm=_sx(w >> 12, 20) << 12)
    if op == 0x03 and f3 == 2:
        return "lw", dict(rd=rd, rs1=rs1, imm=_sx(w >> 20, 12))
    if op == 0x63:
        o = (((w >> 31) & 1) << 12) | (((w >> 7) & 1) << 11) | (((w >> 25) & 0x3F) << 5) | (((w >> 8) & 0xF) << 1)
        return _B_INV[f3], dict(rs1=rs1, rs2=rs2, imm=_sx(o, 13))
    if op in (LOAD_FP, STORE_FP):
        eew = _WIDTH_INV[f3]
        if op == STORE_FP:
            return f"vse{eew}.v", dict(vs3=rd, rs1=rs1, vm=vm, eew=eew)
        if (w >> 26) & 3 == 1:
            return f"vluxei{eew}.v", dict(vd=rd, rs1=rs1, vs2=rs2, vm=vm, eew=eew)
        return f"vle{eew}.v", dict(vd=rd, rs1=rs1, vm=vm, eew=eew)
    if op == OP_V and f3 == 7 and not (w >> 31):
        vt = (w >> 20) & 0x7FF
        return "vsetvli", dict(rd=rd, rs1=rs1, vtype=vt)
    if op in (OP_V, OP_T):
        if (op, f6, f3, rs1) in _VUN_INV:
            return _VUN_INV[(op, f6, f3, rs1)], dict(vd=rd, vs2=rs2, vm=vm)
        if (op, f6, f3) in _VV_INV:
            return _VV_INV[(op, f6, f3)], dict(vd=rd, vs2=rs2, vs1=rs1, vm=vm)
        if op == OP_V and f6 == 0b010111 and f3 == 3:
            return "vmv.v.i", dict(vd=rd, imm=_sx(rs1, 5))
        if op == OP_V and f6 == 0b010000 and f3 == 6:
            return "vmv.s.x", dict(vd=rd, rs1=rs1)
    raise ValueError(f"palavra não reconhecida: {w:08x}")


def assemble(src, base=0):
    """Texto -> (lista de palavras, lista de linhas-fonte). Aceita rótulos e as
    pseudo-instruções li, mv, bnez, beqz e j."""
    items, labels, pc = [], {}, base
    for raw in src.splitlines():
        line = raw.split("#")[0].strip()
        while ":" in line:
            lab, line = line.split(":", 1)
            labels[lab.strip()] = pc
            line = line.strip()
        if not line:
            continue
        mn, _, rest = line.partition(" ")
        a = [x.strip() for x in rest.split(",")] if rest.strip() else []
        # operando de memória com vírgula interna não existe na nossa sintaxe
        if mn == "li":
            v = int(a[1], 0)
            if -2048 <= v < 2048:
                exp = [("addi", [a[0], "zero", str(v)])]
            else:
                lo = _sx(v, 12)
                exp = [("lui", [a[0], str(((v - lo) >> 12) & 0xFFFFF)]), ("addi", [a[0], a[0], str(lo)])]
        elif mn == "mv":
            exp = [("addi", [a[0], a[1], "0"])]
        elif mn == "bnez":
            exp = [("bne", [a[0], "zero", a[1]])]
        elif mn == "beqz":
            exp = [("beq", [a[0], "zero", a[1]])]
        elif mn == "j":
            exp = [("beq", ["zero", "zero", a[0]])]
        else:
            exp = [(mn, a)]
        for m2, a2 in exp:
            items.append((pc, m2, a2, line))
            pc += 4
    words = [encode(mn, a, pc, labels) for pc, mn, a, _ in items]
    return words, [f"{mn} {', '.join(a)}" for _, mn, a, _ in items]
