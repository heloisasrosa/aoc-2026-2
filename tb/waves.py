#!/usr/bin/env python3
"""Desenha formas de onda a partir de um VCD, sem GTKWave.

Lê build/demo2.vcd (gerado por tb/tb_demo2.v) e grava, em docs/img/, uma figura
por parte da demonstração, em SVG, PDF (vetorial, para o LaTeX) e PNG. Os
barramentos que guardam takums são anotados com o valor decodificado pelo oráculo
(tb/takum_oracle.py), por exemplo "51C0 = 15".

uso: python3 tb/waves.py [arquivo.vcd] [pasta de saída]
requer: rsvg-convert (librsvg) para PDF e PNG; sem ele, só o SVG é gravado
"""
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
import takum_oracle as o  # noqa: E402


# ---- leitura do VCD ------------------------------------------------------------------

def read_vcd(path):
    """-> ({nome: [(tempo_ns, valor int ou None), ...]}, tempo final em ns)"""
    ids, widths, scale = {}, {}, 1.0
    changes, t, scope = {}, 0.0, []
    unit = {"s": 1e9, "ms": 1e6, "us": 1e3, "ns": 1.0, "ps": 1e-3, "fs": 1e-6}
    text = open(path).read()
    m = re.search(r"\$timescale\s+(\d+)\s*(\w+)\s+\$end", text)
    if m:
        scale = int(m.group(1)) * unit[m.group(2)]
    head, _, body = text.partition("$enddefinitions")
    for tok in re.finditer(r"\$scope\s+\w+\s+(\S+)\s+\$end|\$upscope|\$var\s+\w+\s+(\d+)\s+(\S+)\s+(\S+)", head):
        if tok.group(1):
            scope.append(tok.group(1))
        elif tok.group(0) == "$upscope":
            scope.pop()
        elif len(scope) == 1:                       # só os sinais do testbench
            ids.setdefault(tok.group(3), []).append(tok.group(4))
            widths[tok.group(4)] = int(tok.group(2))
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("#"):
            t = int(line[1:]) * scale
        elif line[:1] in "01xzXZ" and line[1:] in ids:
            v = None if line[0] in "xzXZ" else int(line[0])
            for n in ids[line[1:]]:
                changes.setdefault(n, []).append((t, v))
        elif line[:1] in "bB":
            bits, _, code = line[1:].partition(" ")
            if code in ids:
                v = None if re.search("[xzXZ]", bits) else int(bits, 2)
                for n in ids[code]:
                    changes.setdefault(n, []).append((t, v))
    return changes, widths, t


# ---- formatação dos valores ---------------------------------------------------------

def num(v):
    """Fraction -> texto curto com vírgula decimal."""
    if v is None:
        return "NaR"
    f = float(v)
    if f != 0 and (abs(f) >= 1e6 or abs(f) < 1e-3):
        m, e = f"{f:.1e}".split("e")
        return f"{m.replace('.', ',')}e{int(e)}"
    return f"{f:.6g}".replace(".", ",")


def fmt(value, kind, width):
    if value is None:
        return "x"
    if kind == "bit":
        return str(value)
    if kind == "dec":
        return str(value)
    if kind == "bin":
        return f"{value:0{width}b}"
    if kind.startswith("takum"):
        n = int(kind[5:])
        return f"{value:0{n // 4}X} = {num(o.decode(value, n))}"
    if kind.startswith("vec"):                     # vec8x4: os 4 elementos de baixo, como takum8
        n, k = (int(t) for t in kind[3:].split("x"))
        return "[" + "; ".join(num(o.decode((value >> (n * i)) & ((1 << n) - 1), n)) for i in range(k)) + "]"
    return f"{value:0{(width + 3) // 4}X}"


# ---- desenho -------------------------------------------------------------------------

ROW, GAP, LABEL, PX, TOP = 30, 12, 205, 13.0, 34     # px; PX = pixels por ns
FONT = "font-family='Menlo, DejaVu Sans Mono, Courier New, monospace'"
C_BUS, C_FILL, C_GRID, C_TXT, C_NOTE = "#1b4f9c", "#eaf1fb", "#d5d9e0", "#1a1a1a", "#8a4b00"


def segments(ch, t0, t1):
    """Trechos de valor constante dentro de [t0, t1]."""
    out, cur = [], None
    for t, v in ch:
        if t <= t0:
            cur = v
        elif t < t1:
            out.append((t, v))
    pts = [(t0, cur)] + out
    return [(a, (pts[i + 1][0] if i + 1 < len(pts) else t1), v) for i, (a, v) in enumerate(pts)
            if i + 1 >= len(pts) or pts[i + 1][1] != v or True]


def merge(segs):
    out = []
    for a, b, v in segs:
        if out and out[-1][2] == v:
            out[-1] = (out[-1][0], b, v)
        else:
            out.append((a, b, v))
    return out


def draw(changes, widths, title, t0, t1, rows, step=10):
    w = LABEL + (t1 - t0) * PX + 34
    h = TOP + len(rows) * (ROW + GAP) + 26
    x = lambda t: LABEL + (t - t0) * PX
    s = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{w:.0f}' height='{h:.0f}' viewBox='0 0 {w:.0f} {h:.0f}'>",
         f"<rect width='100%' height='100%' fill='white'/>",
         f"<text x='10' y='20' {FONT} font-size='14' font-weight='bold' fill='{C_TXT}'>{title}</text>"]
    t = t0
    while t <= t1 + 1e-9:                             # grade e eixo de tempo
        s.append(f"<line x1='{x(t):.1f}' y1='{TOP - 4}' x2='{x(t):.1f}' y2='{h - 22}' stroke='{C_GRID}' stroke-width='1'/>")
        s.append(f"<text x='{x(t):.1f}' y='{h - 8}' {FONT} font-size='10' fill='#666' text-anchor='middle'>{t:g} ns</text>")
        t += step
    for i, (label, sig, kind) in enumerate(rows):
        y = TOP + i * (ROW + GAP)
        mid = y + ROW / 2
        color = C_NOTE if kind == "note" else C_TXT
        s.append(f"<text x='{LABEL - 10}' y='{mid + 4:.1f}' {FONT} font-size='12' fill='{color}' text-anchor='end'>{label}</text>")
        if kind == "note":                            # linha de comentários: um texto por caso
            for k, txt in enumerate(sig):
                xc = x(t0 + (k + 0.5) * step)
                s.append(f"<text x='{xc:.1f}' y='{mid + 4:.1f}' {FONT} font-size='11' font-style='italic' fill='{C_NOTE}' text-anchor='middle'>{txt}</text>")
            continue
        segs = merge(segments(changes[sig], t0, t1))
        if kind == "bit":
            pts, prev = [], None
            for a, b, v in segs:
                yy = y + 4 if v else y + ROW - 4
                if prev is not None and prev != yy:
                    pts.append((x(a), prev))
                pts += [(x(a), yy), (x(b), yy)]
                prev = yy
                s.append(f"<text x='{(x(a) + x(b)) / 2:.1f}' y='{mid + 4:.1f}' {FONT} font-size='11' fill='#555' text-anchor='middle'>{fmt(v, kind, 1)}</text>")
            s.append("<polyline fill='none' stroke='%s' stroke-width='1.6' points='%s'/>" % (C_BUS, " ".join(f"{a:.1f},{b:.1f}" for a, b in pts)))
            continue
        for a, b, v in segs:                          # barramento: caixas com as pontas chanfradas
            xa, xb, d = x(a), x(b), 4
            pts = [(xa, mid), (xa + d, y + 2), (xb - d, y + 2), (xb, mid), (xb - d, y + ROW - 2), (xa + d, y + ROW - 2)]
            s.append("<polygon fill='%s' stroke='%s' stroke-width='1.3' points='%s'/>" % (C_FILL, C_BUS, " ".join(f"{p:.1f},{q:.1f}" for p, q in pts)))
            txt = fmt(v, kind, widths[sig])
            size = 12 if len(txt) * 7.3 < (xb - xa) - 10 else 10
            if len(txt) * 6.1 > (xb - xa) - 6:
                txt = txt.split(" = ")[-1]
            s.append(f"<text x='{(xa + xb) / 2:.1f}' y='{mid + 4:.1f}' {FONT} font-size='{size}' fill='{C_TXT}' text-anchor='middle'>{txt}</text>")
    s.append("</svg>")
    return "\n".join(s)


# ---- as figuras da demonstração da Fase 2 -----------------------------------------------

FIGS = [
    ("ondas-fase2-ncvt", "vncvt.t.t: takum de 16 bits para 8 bits (takum_ncvt)", 0, 80, [
        ("t (T16, entrada)", "t16", "takum16"),
        ("y (T8, saída)", "y8", "takum8"),
        ("o que acontece", ["trunca", "arredonda", "empate: ímpar sobe", "empate: par fica", "satura", "nunca vira zero",
                            "negativo", "NaR"], "note"),
    ]),
    ("ondas-fase2-wmul", "Produto em 8 bits (takum_alu) e produto alargado (takum_wmul)", 80, 120, [
        ("a (T8)", "a", "takum8"),
        ("b (T8)", "b", "takum8"),
        ("a x b em T8", "y_mul", "takum8"),
        ("a x b em T16", "y_wmul", "takum16"),
        ("o que acontece", ["15 não cabe em T8", "2,25 não cabe em T8", "sinais diferentes", "NaR contamina"], "note"),
    ]),
    ("ondas-fase2-vtdot", "vtdot.vv na unidade vetorial (SEW = 8), seguido de vncvt.t.t", 120, 190, [
        ("vs2 (4 elementos)", "vs2", "vec8x4"),
        ("vs1 (4 elementos)", "vs1", "vec8x4"),
        ("vl", "vl", "dec"),
        ("vm (1 = sem máscara)", "vm", "bit"),
        ("v0 (máscara)", "v0", "bin"),
        ("acumulador de entrada", "vd_old", "dec16"),
        ("vd[0] (T16)", "acc", "takum16"),
        ("vncvt.t.t (T8)", "y_dot", "takum8"),
        ("o que acontece", ["vl = 0: nada", "1x1", "+ 2x1", "+ 3x1", "+ 5x3", "só elem. 0 e 2", "512 + 21 (arred.)"], "note"),
    ]),
]


def main():
    vcd = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "demo2.vcd")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "docs", "img")
    changes, widths, _ = read_vcd(vcd)
    os.makedirs(out, exist_ok=True)
    conv = shutil.which("rsvg-convert")
    for name, title, t0, t1, rows in FIGS:
        rows = [(l, s, "takum16" if k == "dec16" else k) for l, s, k in rows]
        if any(s == "vd_old" for _, s, _ in rows):     # o acumulador de entrada é o elemento 0 de vd_old
            changes["vd_old"] = [(t, None if v is None else v & 0xFFFF) for t, v in changes["vd_old"]]
            widths["vd_old"] = 16
        svg = os.path.join(out, name + ".svg")
        open(svg, "w").write(draw(changes, widths, title, t0, t1, rows))
        if conv:
            subprocess.run([conv, "-f", "pdf", "-o", svg[:-4] + ".pdf", svg], check=True)
            subprocess.run([conv, "-z", "2", "-b", "white", "-o", svg[:-4] + ".png", svg], check=True)
        print(os.path.relpath(svg, ROOT) + (" (+ .pdf, .png)" if conv else ""))


if __name__ == "__main__":
    main()
