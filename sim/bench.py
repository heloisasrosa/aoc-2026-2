#!/usr/bin/env python3
"""Fase 3: y = A x com matrizes esparsas, takum x IEEE 754, no simulador RVV.

Nove matrizes: quatro sintéticas (geradas aqui) e cinco reais, do repositório
Matrix Market do NIST (data/matrixmarket/), uma delas com 17 758 linhas.

Para cada matriz e cada formato:
  1. A e x (reais, gerados em binary64) são arredondados para o formato;
  2. o kernel em assembly (sim/kernels.py) roda no simulador;
  3. cada y[i] é comparado com a referência, calculada em binary128 (Float128)
     a partir dos dados originais: erro relativo |y - ref| / |ref|.

Saídas em results/: erros por linha, resumo, CDFs para os gráficos e contagem
de instruções.   uso: python3 -m sim.bench [--quick]
"""
import csv
import gzip
import math
import os
import random
import sys
import time
from fractions import Fraction

from . import formats as F
from . import kernels
from .rvv import Machine

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "results")
BASE = 0x10000
MAXPTS = 500          # pontos por curva guardados em results/ (matrizes com mais linhas são amostradas)


# ---- matrizes de teste (CSR) -------------------------------------------------------

def _csr(rows):
    rowptr, cols, vals = [0], [], []
    for r in rows:
        for c, v in sorted(r.items()):
            cols.append(c)
            vals.append(v)
        rowptr.append(len(cols))
    return rowptr, cols, vals


def poisson(g=16):
    """Laplaciano 2D de 5 pontos em malha g x g; x = modo suave. Forte cancelamento."""
    rows = []
    for i in range(g):
        for j in range(g):
            r = {i * g + j: 4.0}
            for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                if 0 <= i + di < g and 0 <= j + dj < g:
                    r[(i + di) * g + j + dj] = -1.0
            rows.append(r)
    x = [math.sin(math.pi * (i + 1) / (g + 1)) * math.sin(math.pi * (j + 1) / (g + 1))
         for i in range(g) for j in range(g)]
    return _csr(rows), x


def _random(n, m, per_row, val, xval, seed):
    rng = random.Random(seed)
    rows = [{c: val(rng) for c in rng.sample(range(m), per_row)} for _ in range(n)]
    return _csr(rows), [xval(rng) for _ in range(m)]


def gauss(n=256):
    """Esparsa aleatória, valores N(0, 1): faixa dinâmica estreita."""
    return _random(n, n, 10, lambda r: r.gauss(0, 1), lambda r: r.gauss(0, 1), 1)


def wide(n=256):
    """Esparsa aleatória, magnitudes log-uniformes: |a| em 2^[-10, 10], |x| em 2^[-6, 6]."""
    sg = lambda r: r.choice((-1.0, 1.0))
    return _random(n, n, 10, lambda r: sg(r) * 2.0 ** r.uniform(-10, 10), lambda r: sg(r) * 2.0 ** r.uniform(-6, 6), 2)


def mlp(n=256, m=512, per_row=51):
    """Camada densa podada (90% de zeros): pesos N(0, 2/fan_in), entrada pós-ReLU."""
    s = math.sqrt(2.0 / per_row)
    return _random(n, m, per_row, lambda r: r.gauss(0, s), lambda r: max(0.0, r.gauss(0, 1)), 3)


# ---- matrizes reais: coleção Harwell-Boeing, do repositório Matrix Market (NIST) --------
# Arquivos em data/matrixmarket/ (ver o LEIAME de lá). x = N(0, 1) com semente fixa.

def read_mm(fname):
    """Lê um .mtx.gz (coordinate real, general ou symmetric) -> (linhas, colunas, lista de dicionários)."""
    with gzip.open(os.path.join(ROOT, "data", "matrixmarket", fname), "rt") as f:
        head = f.readline().split()
        assert head[:4] == ["%%MatrixMarket", "matrix", "coordinate", "real"], head
        sym = head[4] == "symmetric"
        body = [l.split() for l in f if not l.startswith("%")]
    n, m, _ = (int(t) for t in body[0])
    rows = [dict() for _ in range(n)]
    for i, j, v in body[1:]:
        i, j, v = int(i) - 1, int(j) - 1, float(v)
        rows[i][j] = v
        if sym and i != j:
            rows[j][i] = v
    return n, m, rows


def _real(fname, seed):
    def gen():
        n, m, rows = read_mm(fname)
        rng = random.Random(seed)
        return _csr(rows), [rng.gauss(0, 1) for _ in range(m)]
    return gen


SYNTHETIC = {"poisson": poisson, "gauss": gauss, "wide": wide, "mlp": mlp}
REAL = {
    "nos4": _real("nos4.mtx.gz", 11),          # estrutural (viga), 100 x 100
    "bus494": _real("494_bus.mtx.gz", 12),     # rede elétrica de 494 barras
    "west0479": _real("west0479.mtx.gz", 13),  # engenharia química, 479 x 479
    "bcsstk05": _real("bcsstk05.mtx.gz", 14),  # matriz de rigidez estrutural, 153 x 153
    "memplus": _real("memplus.mtx.gz", 15),    # circuito de memória, 17 758 x 17 758 (a grande)
}
MATRICES = {**SYNTHETIC, **REAL}


# ---- execução ------------------------------------------------------------------------

def run_spmv(variant, sew, fmt, csr, x, vlen=128, fp=None, trace=False):
    """Roda o kernel no simulador. Devolve (padrões de y, máquina)."""
    rowptr, cols, vals = csr
    nb = sew // 8
    a_rp = BASE
    a_off = a_rp + 4 * len(rowptr)
    a_val = a_off + 4 * len(cols)
    a_x = a_val + nb * len(vals) + 64
    a_y = a_x + nb * len(x) + 64
    m = Machine(vlen=vlen, fp=fp, trace=trace, mem_size=max(1 << 20, a_y + nb * len(rowptr) + 4096))
    m.load_program(kernels.spmv(variant, sew))
    m.write_array(a_rp, rowptr, 4)
    m.write_array(a_off, [c * nb for c in cols], 4)
    m.write_array(a_val, [fmt.enc(Fraction(v)) for v in vals], nb)
    m.write_array(a_x, [fmt.enc(Fraction(v)) for v in x], nb)
    n = len(rowptr) - 1
    m.x[10:16] = [n, a_rp, a_off, a_val, a_x, a_y]
    for f in m.fp.values():          # os flags contam só o que as instruções levantam,
        f.flags = f.flag_events = 0  # não a conversão dos dados de entrada
    m.run()
    m.flag_events = sum(f.flag_events for f in m.fp.values())
    m.fflags_end = m.fflags
    return m.read_array(a_y, n, nb), m


def direct(fmt, csr, x, wide=None):
    """Mesma conta sem o simulador (conferência e ablação). wide: formato do acúmulo."""
    rowptr, cols, vals = csr
    a = [fmt.enc(Fraction(v)) for v in vals]
    xs = [fmt.enc(Fraction(v)) for v in x]
    w = wide or fmt
    out = []
    for i in range(len(rowptr) - 1):
        acc = 0
        for k in range(rowptr[i], rowptr[i + 1]):
            if wide:
                p = w.mul(w.cvt_from(fmt, a[k]), w.cvt_from(fmt, xs[cols[k]]))
            else:
                p = fmt.mul(a[k], xs[cols[k]])
            acc = w.add(acc, p)
        out.append(fmt.cvt_from(w, acc) if wide else acc)
    return out


def reference(csr, x):
    """y em binary128, a partir dos dados originais (sem arredondar as entradas)."""
    q = F.ieee_set()["FP128"]
    rowptr, cols, vals = csr
    a = [q.enc(Fraction(v)) for v in vals]
    xs = [q.enc(Fraction(v)) for v in x]
    out = []
    for i in range(len(rowptr) - 1):
        acc = 0
        for k in range(rowptr[i], rowptr[i + 1]):
            acc = q.add(acc, q.mul(a[k], xs[cols[k]]))
        out.append(q.dec(acc))
    return out


def rel_errors(fmt, ybits, ref):
    errs = []
    for b, r in zip(ybits, ref):
        if r == 0:
            continue
        v = fmt.dec(b)
        errs.append(float(abs(v - r) / abs(r)) if F.finite(v) else math.inf)
    return errs


def pct(sorted_e, p):
    return sorted_e[min(len(sorted_e) - 1, int(p * len(sorted_e)))]


# configurações: rótulo -> (formato, variante, sew)
def configs():
    ie = F.ieee_set
    c = []
    for sew, t in ((8, F.T8), (16, F.T16), (32, F.T32)):
        c.append((f"T{sew}", "takum", sew, lambda t=t: (t, None)))
    for sew, nm in ((8, "FP8"), (16, "FP16"), (32, "FP32")):
        for var, suf in (("ieee", ""), ("ieee_w", "w")):
            def mk(sew=sew, nm=nm):
                s = ie()
                fp = {8: s["FP8"], 16: s["FP16"], 32: s["FP32"], 64: s["FP64"]}
                return fp[sew], fp
            c.append((nm + suf, var, sew, mk))
    for sew, nm in ((8, "E5M2"), (16, "BF16")):
        def mk(sew=sew, nm=nm):
            s = ie()
            fp = {8: s["FP8"], 16: s["FP16"], 32: s["FP32"], 64: s["FP64"]}
            fp[sew] = s[nm]
            return fp[sew], fp
        c.append((nm, "ieee", sew, mk))
    return c


def main():
    quick = "--quick" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    summary, instr, rows_out, info = [], [], [], []
    for mname, gen in MATRICES.items():
        if quick and mname in SYNTHETIC:
            csr, x = gen(8) if mname == "poisson" else gen(32)
        else:
            csr, x = gen()
        nrows, nnz = len(csr[0]) - 1, len(csr[1])
        ref = reference(csr, x)
        mags = [abs(v) for v in csr[2] if v != 0]
        info.append(dict(matrix=mname, source="Matrix Market" if mname in REAL else "sintética",
                         rows=nrows, cols=len(x), nnz=nnz, nnz_per_row=f"{nnz / nrows:.1f}",
                         log2_min=f"{math.log2(min(mags)):.1f}", log2_max=f"{math.log2(max(mags)):.1f}"))
        print(f"== {mname}: {nrows} linhas, {nnz} não nulos, |a| de 2^{math.log2(min(mags)):.0f} a 2^{math.log2(max(mags)):.0f}")
        for label, variant, sew, mk in configs():
            t0 = time.time()
            fmt, fp = mk()
            ybits, m = run_spmv(variant, sew, fmt, csr, x, fp=fp)
            nnz_ops = 2 * nnz                       # um produto e uma soma por não nulo
            # conferência: o kernel em assembly dá o mesmo que a conta direta
            if variant == "takum":
                chk = direct(fmt, csr, x, wide=F.Takum(2 * sew))
            elif variant == "ieee_w":
                chk = direct(fmt, csr, x, wide=fp[2 * sew])
            else:
                chk = direct(fmt, csr, x)
            assert chk == ybits, f"simulador != conta direta em {mname}/{label}"
            errs = sorted(rel_errors(fmt, ybits, ref))
            record(summary, rows_out, mname, label, errs)
            total = sum(m.count.values())
            vec = sum(v for k, v in m.count.items() if k.startswith("v"))
            flag_ev = m.flag_events if fp else 0
            instr.append(dict(matrix=mname, config=label, sew=sew, variant=variant, total=total, vector=vec,
                              per_nnz=f"{total / nnz:.3f}", fflags=f"{m.fflags_end if fp else 0:05b}",
                              flag_events=flag_ev, fp_ops=nnz_ops,
                              **{k: m.count[k] for k in ("vsetvli", "vtdot.vv", "vfmul.vv", "vfwmul.vv",
                                                         "vfredosum.vs", "vncvt.t.t", "vfncvt.f.f.w")}))
            print(f"   {label:6s} mediana={pct(errs, .5):9.3e} max={errs[-1]:9.3e} instr={total:6d} ({time.time() - t0:.1f}s)")
        # ablações sem o simulador
        for sew, t in ((8, F.T8), (16, F.T16), (32, F.T32)):
            errs = sorted(rel_errors(t, direct(t, csr, x), ref))          # takum sem precisão ampliada
            record(summary, rows_out, mname, f"T{sew}s", errs)
        for nm, fmt in [("T8", F.T8), ("T16", F.T16), ("T32", F.T32)] + \
                       [(k, v) for k, v in F.ieee_set().items() if k in ("FP8", "FP16", "FP32")]:
            best = [fmt.enc(r) for r in ref]                              # melhor resposta possível no formato
            record(summary, rows_out, mname, nm + "opt", sorted(rel_errors(fmt, best, ref)))

    wr("spmv_errors.csv", rows_out, ["matrix", "config", "rank", "relerr"])
    wr("spmv_summary.csv", summary, list(summary[0]))
    wr("spmv_instr.csv", instr, list(instr[0]))
    wr("matrices.csv", info, list(info[0]))
    vlen_sweep()
    print(f"resultados em {os.path.relpath(OUT)}/")


def record(summary, rows_out, mname, label, errs):
    fin = [e for e in errs if math.isfinite(e)]
    summary.append(dict(matrix=mname, config=label, rows=len(errs),
                        median=f"{pct(errs, .5):.3e}", p90=f"{pct(errs, .9):.3e}", max=f"{errs[-1]:.3e}",
                        nonfinite=len(errs) - len(fin),
                        over100pct=sum(e >= 1.0 for e in errs)))
    # matrizes grandes: guarda MAXPTS postos igualmente espaçados (inclui o menor e o maior erro)
    n = len(errs)
    ranks = range(n) if n <= MAXPTS else sorted({round(i * (n - 1) / (MAXPTS - 1)) for i in range(MAXPTS)})
    for k in ranks:
        rows_out.append(dict(matrix=mname, config=label, rank=k, relerr=f"{errs[k]:.6e}"))
    # CDF para o pgfplots: erro (com piso, para o eixo log) x fração acumulada
    with open(os.path.join(OUT, f"cdf_{mname}_{label}.dat"), "w") as f:
        f.write("err frac\n")
        for k in ranks:
            f.write(f"{min(max(errs[k], 1e-11), 1e3):.6e} {(k + 1) / n:.5f}\n")


def vlen_sweep():
    """Instruções executadas por variante e VLEN (não depende dos valores: usa a matriz mlp)."""
    csr, x = mlp()
    nnz = len(csr[1])
    out = []
    for vlen in (64, 128, 256, 512):
        for sew, t, nm in ((8, F.T8, "FP8"), (16, F.T16, "FP16"), (32, F.T32, "FP32")):
            row = dict(vlen=vlen, sew=sew)
            for variant in ("takum", "ieee", "ieee_w"):
                if variant == "takum":
                    fmt, fp = t, None
                else:
                    s = F.ieee_set()
                    fp = {8: s["FP8"], 16: s["FP16"], 32: s["FP32"], 64: s["FP64"]}
                    fmt = fp[sew]
                _, m = run_spmv(variant, sew, fmt, csr, x, vlen=vlen, fp=fp)
                row[variant] = sum(m.count.values())
            row["save_vs_ieee_w"] = f"{100 * (1 - row['takum'] / row['ieee_w']):.1f}"
            row["save_vs_ieee"] = f"{100 * (1 - row['takum'] / row['ieee']):.1f}"
            out.append(row)
            print(f"   VLEN={vlen:3d} SEW={sew:2d}: takum={row['takum']} ieee={row['ieee']} ieee_w={row['ieee_w']}")
    wr("instr_vlen.csv", out, list(out[0]))


def wr(name, rows, fields):
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
