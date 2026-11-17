# Matrizes de repositório público

Cinco matrizes esparsas reais, baixadas do repositório **Matrix Market** do NIST
(https://math.nist.gov/MatrixMarket/) em 16/11/2026, sem alterações. Quatro são da coleção
**Harwell-Boeing**; a quinta, `memplus`, é a matriz grande do experimento.
Formato: Matrix Market *coordinate real*, comprimido com gzip. São lidas por `sim/bench.py`.

| Arquivo | Nome no projeto | Conjunto | Dimensão | Origem |
|---|---|---|---|---|
| `nos4.mtx.gz` | `nos4` | LANPRO | 100 × 100, simétrica | análise estrutural (viga) |
| `494_bus.mtx.gz` | `bus494` | PSADMIT | 494 × 494, simétrica | rede elétrica de 494 barras |
| `west0479.mtx.gz` | `west0479` | CHEMWEST | 479 × 479 | engenharia química (coluna de destilação) |
| `bcsstk05.mtx.gz` | `bcsstk05` | BCSSTRUC1 | 153 × 153, simétrica | matriz de rigidez estrutural |
| `memplus.mtx.gz` | `memplus` | HAMM (coleção *misc*) | 17 758 × 17 758, 126 150 elementos | simulação de um circuito de memória |

Endereços de origem:

```
https://math.nist.gov/pub/MatrixMarket2/Harwell-Boeing/lanpro/nos4.mtx.gz
https://math.nist.gov/pub/MatrixMarket2/Harwell-Boeing/psadmit/494_bus.mtx.gz
https://math.nist.gov/pub/MatrixMarket2/Harwell-Boeing/chemwest/west0479.mtx.gz
https://math.nist.gov/pub/MatrixMarket2/Harwell-Boeing/bcsstruc1/bcsstk05.mtx.gz
https://math.nist.gov/pub/MatrixMarket2/misc/hamm/memplus.mtx.gz
```

Referências: I. S. Duff, R. G. Grimes e J. G. Lewis, "Sparse matrix test problems", *ACM Trans. Math.
Softw.*, 15(1), 1989; R. F. Boisvert et al., "Matrix Market: a web resource for test matrix
collections", 1997.

As matrizes simétricas guardam só o triângulo inferior; o leitor espelha os elementos fora da diagonal.
O vetor `x` do experimento é N(0, 1) com semente fixa.

A `memplus` guarda 27 003 zeros explícitos (posições estruturais do circuito); eles são mantidos.
Como ela tem muitas linhas, `results/spmv_errors.csv` e os arquivos `cdf_memplus_*.dat` guardam 500
postos igualmente espaçados do erro, não todas as linhas; o resumo usa todas.
