#!/usr/bin/env python3
"""Desenha os esquemáticos dos módulos Verilog (Yosys + netlistsvg).

Para cada módulo: o Yosys elabora em nível RTL (somadores, deslocadores, muxes),
SEM achatar a hierarquia, de modo que os submódulos aparecem como caixas; o
netlistsvg desenha; o rsvg-convert gera PNG e PDF (o PDF é vetorial, para o LaTeX).

uso: python3 tb/schematics.py [pasta de saída]        (padrão: docs/img)
requer: yosys, netlistsvg (npm install -g netlistsvg) e rsvg-convert (librsvg)
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RTL = [f"rtl/{m}.v" for m in ("takum_hdr_dec", "takum_decoder", "takum_encoder", "takum_alu",
                               "takum_ncvt", "takum_wmul", "takum_dot", "takum_vec_alu")]
# módulo de topo e parâmetros. Larguras pequenas: o desenho é o mesmo, só mais legível.
CONFIGS = [
    ("takum_hdr_dec", {}),
    ("takum_decoder", {"N": 8}),
    ("takum_encoder", {"N": 8}),
    ("takum_ncvt", {"N": 8}),
    ("takum_wmul", {"N": 8}),
    ("takum_alu", {"N": 8}),
    ("takum_dot", {"N": 8, "LANES": 2}),
]


def run(cmd, **kw):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)
    if r.returncode:
        sys.exit(f"falhou: {' '.join(cmd)}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r.stdout


def clean(name):
    r"""$paramod\takum_decoder\N=s32'...1000  ->  takum_decoder (N=8)"""
    m = re.match(r"\$paramod(?:\$[0-9a-f]+)?\\(\w+)(.*)", name)
    if not m:
        return name
    pars = [f"{k}={int(v, 2)}" for k, v in re.findall(r"\\(\w+)=s32'([01]+)", m.group(2))]
    return m.group(1) + (f" ({', '.join(pars)})" if pars else "")


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "img")
    work = os.path.join(ROOT, "build", "sch")
    os.makedirs(work, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    for tool in ("yosys", "netlistsvg", "rsvg-convert"):
        if not shutil.which(tool):
            sys.exit(f"ferramenta não encontrada: {tool}")
    for top, pars in CONFIGS:
        chp = ("chparam " + " ".join(f"-set {k} {v}" for k, v in pars.items()) + f" {top}; ") if pars else ""
        js = os.path.join(work, f"{top}.json")
        run(["yosys", "-q", "-p", f"read_verilog {' '.join(RTL)}; {chp}hierarchy -top {top}; prep; "
                                  f"opt_clean -purge; write_json {js}"])
        d = json.load(open(js))
        # só o módulo de topo, com os nomes dos submódulos limpos
        key = next(k for k, v in d["modules"].items() if v.get("attributes", {}).get("top"))
        mod = d["modules"][key]
        for c in mod["cells"].values():
            c["type"] = clean(c["type"])
        json.dump({"modules": {top: mod}}, open(js, "w"))
        svg = os.path.join(out, f"{top}.svg")
        run(["netlistsvg", js, "-o", svg])
        run(["rsvg-convert", "-f", "pdf", "-o", svg[:-4] + ".pdf", svg])
        run(["rsvg-convert", "-z", "2", "-b", "white", "-o", svg[:-4] + ".png", svg])
        subs = sorted({c["type"] for c in mod["cells"].values() if not c["type"].startswith("$")})
        print(f"{os.path.relpath(svg, ROOT)}: {len(mod['cells'])} células" + (f"; submódulos: {', '.join(subs)}" if subs else ""))


if __name__ == "__main__":
    main()
