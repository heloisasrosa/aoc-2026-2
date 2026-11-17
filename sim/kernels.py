"""Kernels em assembly: y = A x com A esparsa em CSR.

Convenção de chamada (todos os kernels):
    a0 = nº de linhas          a1 = &rowptr[0]  (int32)
    a2 = &off[0]   (int32: índice da coluna * tamanho do elemento, em bytes)
    a3 = &val[0]               a4 = &x[0]               a5 = &y[0]

Três variantes, que só diferem no miolo do laço interno e no fecho da linha:

    takum      vtdot.vv (produtos e acúmulo em 2*SEW) e vncvt.t.t no fim
    ieee       vfmul.vv + vfredosum.vs, tudo em SEW (o SpMV usual em RVV)
    ieee_w     vfwmul.vv + vfredosum.vs em 2*SEW e vfncvt.f.f.w no fim: a mesma
               precisão ampliada do vtdot, feita com as instruções IEEE do RVV
"""

_HEAD = """
    li   s1, 1
row:
    lw   t0, 0(a1)                  # rowptr[i]
    lw   t1, 4(a1)                  # rowptr[i+1]
    sub  t2, t1, t0                 # nnz da linha
    vsetvli zero, s1, e64, m1, ta, ma
    vmv.s.x v4, zero                # acumulador = 0
    beqz t2, done
inner:
    vsetvli t3, t2, e{sew}, {lmul}, ta, ma
    vle32.v v8, (a2)                # deslocamentos das colunas
    vle{sew}.v v1, (a3)             # valores da linha
    vluxei32.v v2, (a4), v8         # x[col]: carga indexada (gather)
"""

_TAIL = """
    slli t4, t3, 2
    add  a2, a2, t4
    slli t4, t3, {lg}
    add  a3, a3, t4
    sub  t2, t2, t3
    bnez t2, inner
done:
    vsetvli zero, s1, e{sew}, {lmul}, ta, ma
{close}    vse{sew}.v v{res}, (a5)
    addi a5, a5, {bytes}
    addi a1, a1, 4
    addi a0, a0, -1
    bnez a0, row
    ebreak
"""

_BODY = {
    "takum": ("    vtdot.vv v4, v1, v2            # v4[0] (2*SEW) += soma v1[i]*v2[i]\n",
              "    vncvt.t.t v5, v4\n", 5, "m1"),
    "ieee": ("    vfmul.vv v3, v1, v2\n"
             "    vfredosum.vs v4, v3, v4\n",
             "", 4, "m1"),
    "ieee_w": ("    vfwmul.vv v6, v1, v2           # produtos em 2*SEW (grupo v6, v7)\n"
               "    vsetvli zero, t3, e{sew2}, m2, ta, ma\n"
               "    vfredosum.vs v4, v6, v4\n",
               "    vfncvt.f.f.w v12, v4\n", 12, "m1"),
}


def spmv(variant, sew):
    body, close, res, lmul = _BODY[variant]
    lg = {8: 0, 16: 1, 32: 2}[sew]
    k = dict(sew=sew, sew2=2 * sew, lg=lg, bytes=sew // 8, close=close, res=res, lmul=lmul)
    return (_HEAD + body + _TAIL).format(**k)
