/* libtakum_check.c — confere os vetores de teste do projeto contra a libtakum,
 * a implementação de referência de takum do autor do formato (Laslo Hunhold):
 * https://github.com/takum-arithmetic/libtakum   (licença ISC)
 *
 * Os arquivos conferidos são os mesmos que verificam o RTL (gerados pelo oráculo
 * em Python). Assim há três implementações independentes: o Verilog, o oráculo
 * com frações exatas e a libtakum.
 *
 *   libtakum_check alu  N arquivo    linhas "a b op y"   (op: 0 soma, 1 subtrai, 2 multiplica)
 *   libtakum_check ncvt N arquivo    linhas "t y"        (T2N -> TN)
 *   libtakum_check wmul N arquivo    linhas "a b y"      (TN x TN -> T2N)
 *   libtakum_check dec  N arquivo    linhas "t valor"    (valor em hexadecimal de ponto flutuante, ou nan)
 *
 * A libtakum faz as contas em double. Onde isso não é exato (produto em T32, que
 * precisa de 56 bits, e tudo o que envolve T64 em máquinas cujo long double é um
 * double), ela pode arredondar duas vezes; essas divergências são listadas para
 * análise por tb/libtakum_report.py, que decide com aritmética exata quem tem razão.
 */
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "takum.h"

static uint64_t mask(int n) { return n == 64 ? UINT64_MAX : ((UINT64_C(1) << n) - 1); }

static uint64_t op(int n, int o, uint64_t a, uint64_t b)
{
	switch (n) {
	case 8: {
		takum8 x = (takum8)a, y = (takum8)b;
		return (uint8_t)(o == 0 ? takum8_addition(x, y) : o == 1 ? takum8_subtraction(x, y) : takum8_multiplication(x, y));
	}
	case 16: {
		takum16 x = (takum16)a, y = (takum16)b;
		return (uint16_t)(o == 0 ? takum16_addition(x, y) : o == 1 ? takum16_subtraction(x, y) : takum16_multiplication(x, y));
	}
	case 32: {
		takum32 x = (takum32)a, y = (takum32)b;
		return (uint32_t)(o == 0 ? takum32_addition(x, y) : o == 1 ? takum32_subtraction(x, y) : takum32_multiplication(x, y));
	}
	default: {
		takum64 x = (takum64)a, y = (takum64)b;
		return (uint64_t)(o == 0 ? takum64_addition(x, y) : o == 1 ? takum64_subtraction(x, y) : takum64_multiplication(x, y));
	}
	}
}

static uint64_t narrow(int n, uint64_t t)       /* T2N -> TN */
{
	switch (n) {
	case 8:  return (uint8_t)takum8_from_takum16((takum16)t);
	case 16: return (uint16_t)takum16_from_takum32((takum32)t);
	default: return (uint32_t)takum32_from_takum64((takum64)t);
	}
}

static uint64_t widen(int n, uint64_t t)        /* TN -> T2N */
{
	switch (n) {
	case 8:  return (uint16_t)takum16_from_takum8((takum8)t);
	case 16: return (uint32_t)takum32_from_takum16((takum16)t);
	default: return (uint64_t)takum64_from_takum32((takum32)t);
	}
}

static double value(int n, uint64_t t)
{
	switch (n) {
	case 8:  return takum8_to_float64((takum8)t);
	case 16: return takum16_to_float64((takum16)t);
	default: return takum32_to_float64((takum32)t);
	}
}

static uint64_t from_value(int n, double v)
{
	switch (n) {
	case 8:  return (uint8_t)takum8_from_float64(v);
	case 16: return (uint16_t)takum16_from_float64(v);
	default: return (uint32_t)takum32_from_float64(v);
	}
}

int main(int argc, char *argv[])
{
	FILE *f;
	char kind[8], vtxt[64];
	uint64_t a, b, y, got;
	unsigned o;
	long total = 0, diff = 0;
	int n;

	if (argc != 4 || !(f = fopen(argv[3], "r"))) {
		fprintf(stderr, "uso: %s alu|ncvt|wmul|dec N arquivo\n", argv[0]);
		return 2;
	}
	strncpy(kind, argv[1], sizeof(kind) - 1);
	kind[sizeof(kind) - 1] = '\0';
	n = atoi(argv[2]);

	if (!strcmp(kind, "alu")) {
		while (fscanf(f, "%" SCNx64 " %" SCNx64 " %u %" SCNx64, &a, &b, &o, &y) == 4) {
			got = op(n, (int)o, a, b) & mask(n);
			total++;
			if (got != y) {
				diff++;
				printf("DIFF alu %d %" PRIx64 " %" PRIx64 " %u projeto=%" PRIx64 " libtakum=%" PRIx64 "\n", n, a, b, o, y, got);
			}
		}
	} else if (!strcmp(kind, "ncvt")) {
		while (fscanf(f, "%" SCNx64 " %" SCNx64, &a, &y) == 2) {
			got = narrow(n, a) & mask(n);
			total++;
			if (got != y) {
				diff++;
				printf("DIFF ncvt %d %" PRIx64 " projeto=%" PRIx64 " libtakum=%" PRIx64 "\n", n, a, y, got);
			}
		}
	} else if (!strcmp(kind, "wmul")) {
		while (fscanf(f, "%" SCNx64 " %" SCNx64 " %" SCNx64, &a, &b, &y) == 3) {
			got = op(2 * n, 2, widen(n, a), widen(n, b)) & mask(2 * n);
			total++;
			if (got != y) {
				diff++;
				printf("DIFF wmul %d %" PRIx64 " %" PRIx64 " projeto=%" PRIx64 " libtakum=%" PRIx64 "\n", n, a, b, y, got);
			}
		}
	} else if (!strcmp(kind, "dec")) {
		while (fscanf(f, "%" SCNx64 " %63s", &a, vtxt) == 2) {
			double want = strtod(vtxt, NULL), v = value(n, a);
			int same = (isnan(want) && isnan(v)) || want == v;
			total++;
			/* ida: mesmo valor; volta: o valor recodifica no mesmo padrão */
			if (!same || (from_value(n, v) & mask(n)) != a) {
				diff++;
				printf("DIFF dec %d %" PRIx64 " projeto=%s libtakum=%a volta=%" PRIx64 "\n", n, a, vtxt, v, from_value(n, v) & mask(n));
			}
		}
	} else {
		fprintf(stderr, "tipo desconhecido: %s\n", kind);
		return 2;
	}
	fclose(f);
	printf("TOTAL %s %d %ld %ld\n", kind, n, total, diff);
	return 0;
}
