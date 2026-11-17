#!/usr/bin/env python3
"""Gera docs/artigo/numbers.tex (e numbers-pt.tex, com vírgula decimal) a partir de results/ (e build/synth*.txt, se existirem).

Todas as tabelas e números citados no artigo saem daqui, para não haver transcrição à mão.
uso: python3 -m sim.paper_numbers      (depois de make bench, make synth e make synth2)
"""
import csv
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RES = os.path.join(ROOT, "results")
SYN = ["poisson", "gauss", "wide", "mlp"]
REAL = ["nos4", "bus494", "west0479", "bcsstk05", "memplus"]
MATS = SYN + REAL


def rows(name):
    with open(os.path.join(RES, name)) as f:
        return list(csv.DictReader(f))


def sci(v):
    """1.397e-08 -> $1.4\\times10^{-8}$; inf -> texto."""
    v = float(v)
    if v == float("inf"):
        return r"$\infty$"
    m, e = f"{v:.1e}".split("e")
    return rf"${m}\times10^{{{int(e)}}}$"


def synth():
    """LUT6 por (módulo, N). Junta build/synth.txt e build/synth2.txt em results/synth.txt."""
    parts = [os.path.join(ROOT, "build", n) for n in ("synth.txt", "synth2.txt")]
    keep = os.path.join(RES, "synth.txt")
    if all(os.path.exists(p) for p in parts):
        with open(keep, "w") as out:
            for p in parts:
                out.write(open(p).read())
    lut = {}
    if os.path.exists(keep):
        for line in open(keep):
            m = re.match(r"(\w+)\s+\(?N?=?(\d+)", line)
            l6 = re.search(r"LUT6=(\d+)", line)
            if m and l6:
                lut[(m.group(1), int(m.group(2)))] = int(l6.group(1))
    return lut


def main():
    summ = {(r["matrix"], r["config"]): r for r in rows("spmv_summary.csv")}
    instr = {(r["matrix"], r["config"]): r for r in rows("spmv_instr.csv")}
    med = lambda m, c: float(summ[(m, c)]["median"])
    out = []
    macro = lambda name, val: out.append(rf"\newcommand{{\{name}}}{{{val}}}")

    # ---- tabelas de erro mediano: todas, só as sintéticas, só as reais ------------------
    def errtable(mats):
        lines = []
        for n in (8, 16, 32):
            for cfg in (f"T{n}", f"FP{n}", f"FP{n}w"):
                cells = []
                for m in mats:
                    best = min(med(m, c) for c in (f"T{n}", f"FP{n}", f"FP{n}w"))
                    s = sci(med(m, cfg))
                    if med(m, cfg) == best and best != float("inf"):
                        s = rf"\boldmath{s}"
                    cells.append(s)
                lines.append(f"{cfg} & " + " & ".join(cells) + r"\\")
            if n != 32:
                lines.append(r"\midrule")
        return "\n".join(lines)

    macro("ERRTABLE", errtable(MATS))
    macro("ERRTABLESYN", errtable(SYN))
    macro("ERRTABLEREAL", errtable(REAL))

    r32 = [med(m, "FP32w") / med(m, "T32") for m in MATS]
    macro("RATA", f"{min(r32):.1f}")
    macro("RATB", f"{max(r32):.0f}")
    macro("WIDET", sci(med("wide", "T16")))
    macro("WIDEF", sci(med("wide", "FP16w")))
    macro("BUST", sci(med("bus494", "T16")))
    macro("BUSF", sci(med("bus494", "FP16w")))
    macro("WIDETEIGHT", sci(med("wide", "T8")))
    macro("BCSTEIGHT", sci(med("bcsstk05", "T8")))
    macro("BCSTSIXTEEN", sci(med("bcsstk05", "T16")))
    nf = lambda m, c: summ[(m, c)]["nonfinite"]
    macro("FPEIGHTBAD", nf("wide", "FP8w"))                 # FP8w, não finitos
    macro("NFBUS", nf("bus494", "FP8w"))
    macro("NFWEST", nf("west0479", "FP8w"))
    macro("NFBCS", nf("bcsstk05", "FP8w"))
    macro("NFWESTH", nf("west0479", "FP16w"))               # FP16w
    macro("NFBCSH", nf("bcsstk05", "FP16w"))
    for key, m in (("MEM", "memplus"),):
        for suf, c in (("TE", "T8"), ("FE", "FP8w"), ("TS", "T16"), ("FS", "FP16w"), ("TT", "T32"), ("FT", "FP32w")):
            macro(f"{key}{suf}", sci(med(m, c)))
            macro(f"{key}{suf}BAD", f"{int(summ[(m, c)]['over100pct']):,}".replace(",", r"\,"))
        macro(f"{key}ROWS", f"{int(summ[(m, 'T8')]['rows']):,}".replace(",", r"\,"))
    assert all(nf(m, c) == "0" for m in MATS for c in ("T8", "T16", "T32", "FP32", "FP32w"))
    assert all(med(m, "T32") < min(med(m, "FP32"), med(m, "FP32w")) for m in MATS)

    # ---- matrizes de teste ------------------------------------------------------------
    info = {r["matrix"]: r for r in rows("matrices.csv")}
    lines = []
    for m in MATS:
        r = info[m]
        lo, hi = round(float(r["log2_min"])), round(float(r["log2_max"]))
        lines.append(rf"{m} & {r['rows']}$\times${r['cols']} & {int(r['nnz']):,} & {r['nnz_per_row']} & "
                     rf"$2^{{{lo}}}$ -- $2^{{{hi}}}$\\".replace(",", r"\,"))
        if m == SYN[-1]:
            lines.append(r"\midrule")
    macro("MATTABLE", "\n".join(lines))

    # ---- instruções executadas, SEW = 16 (wide tem a mesma estrutura de gauss) ----------
    lines = []
    for m in MATS:
        if m == "wide":
            continue
        t, f, w = (int(instr[(m, c)]["total"]) for c in ("T16", "FP16", "FP16w"))
        lines.append(rf"{m} & {info[m]['nnz_per_row']} & {t:,} & {f:,} & {w:,} & {100 * (1 - t / f):.1f}\% & "
                     rf"{100 * (1 - t / w):.1f}\%\\".replace(",", r"\,"))
        if m == SYN[-1]:
            lines.append(r"\midrule")
    macro("INSTRTABLE", "\n".join(lines))
    sv = [100 * (1 - int(instr[(m, f"T{n}")]["total"]) / int(instr[(m, f"FP{n}{v}")]["total"]))
          for m in MATS for n in (8, 16, 32) for v in ("w",)]
    sp = [100 * (1 - int(instr[(m, f"T{n}")]["total"]) / int(instr[(m, f"FP{n}")]["total"]))
          for m in MATS for n in (8, 16, 32)]
    macro("SAVEWLO", f"{min(sv):.1f}")
    macro("SAVEWHI", f"{max(sv):.1f}")
    macro("SAVEPHI", f"{max(sp):.1f}")
    assert min(sp) == 0

    # ---- flags ------------------------------------------------------------------------
    worst = max((r for r in instr.values() if r["variant"] != "takum"),
                key=lambda r: int(r["flag_events"]) / int(r["fp_ops"]))
    macro("FLAGPCT", f"{100 * int(worst['flag_events']) / int(worst['fp_ops']):.0f}")
    macro("FLAGWHERE", rf"\emph{{{worst['matrix']}}}, {worst['config']}")
    assert all(int(r["flag_events"]) == 0 for r in instr.values() if r["variant"] == "takum")

    # ---- síntese ------------------------------------------------------------------------
    lut = synth()
    for key, mod in (("DEC", "takum_decoder"), ("ENC", "takum_encoder"), ("ALU", "takum_alu"),
                     ("NC", "takum_ncvt"), ("WM", "takum_wmul"), ("DOT", "takum_dot")):
        for suf, n in zip("ABC", (8, 16, 32)):
            v = lut.get((mod, n))
            macro(f"HW{key}{suf}", f"{v:,}".replace(",", r"\,") if v else "--")
    macro("HWHDR", lut.get(("takum_hdr_dec", 12), "--"))

    head = "% Gerado por: python3 -m sim.paper_numbers (não editar à mão)\n"
    path = os.path.join(ROOT, "docs", "artigo", "numbers.tex")
    with open(path, "w") as f:
        f.write(head + "\n".join(out) + "\n")
    # versão com vírgula decimal, para os documentos em português
    with open(os.path.join(ROOT, "docs", "artigo", "numbers-pt.tex"), "w") as f:
        f.write(head + re.sub(r"(\d)\.(\d)", r"\1{,}\2", "\n".join(out)) + "\n")
    print(f"{os.path.relpath(path)} e numbers-pt.tex: {len(out)} macros")
    for line in out:
        if "TABLE" not in line and "HW" not in line:
            print("  ", line)


if __name__ == "__main__":
    main()
