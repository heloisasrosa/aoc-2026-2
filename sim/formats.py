"""Formatos numéricos do simulador: takum linear e ponto flutuante IEEE 754.

Todos os formatos têm a mesma interface, sobre padrões de bits (int):

    dec(bits) -> Fraction, ou float (nan / +-inf) quando não é finito
    enc(valor) -> bits        (arredonda para o mais próximo, empate para o par)
    add, sub, mul(a, b) -> bits

A aritmética é exata (Fraction) até o arredondamento final, então cada operação
devolve o resultado corretamente arredondado. O takum usa o oráculo de
tb/takum_oracle.py, o mesmo que verifica o RTL.
"""
import math
import os
import sys
from fractions import Fraction

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tb"))
import takum_oracle as oracle  # noqa: E402

NAN = float("nan")
# fflags do RISC-V
NX, UF, OF, DZ, NV = 1, 2, 4, 8, 16


def finite(v):
    return isinstance(v, Fraction)


class Format:
    name = "?"
    n = 0
    flags = 0            # fflags acumulados (só o IEEE levanta)
    flag_events = 0      # nº de operações que levantaram algum flag

    def _ops(self, a, b, f):
        x, y = self.dec(a), self.dec(b)
        if finite(x) and finite(y):
            return self.enc(f(x, y))
        return self.enc(self._special(x, y, f))

    def add(self, a, b):
        return self._ops(a, b, lambda x, y: x + y)

    def sub(self, a, b):
        return self._ops(a, b, lambda x, y: x - y)

    def mul(self, a, b):
        return self._ops(a, b, lambda x, y: x * y)

    def cvt_from(self, other, bits):
        """Converte um padrão de outro formato para este (arredondando)."""
        return self.enc(other.dec(bits))

    def _special(self, x, y, f):
        return NAN


class Takum(Format):
    """Takum linear de n bits. Um único valor especial (NaR), nenhum flag."""

    def __init__(self, n):
        self.n, self.name = n, f"T{n}"

    def dec(self, bits):
        v = oracle.decode(bits, self.n)
        return NAN if v is None else v

    def enc(self, v):
        return oracle.encode(v if finite(v) else None, self.n)


class IEEE(Format):
    """Formato binário no estilo IEEE 754: 1 bit de sinal, ebits de expoente, mbits de fração.

    Tem subnormais, infinitos e NaN; arredonda para o mais próximo, empate para o par.
    Simplificações: o zero negativo não é modelado (todo zero é +0) e só há um NaN (quiet).
    """

    def __init__(self, name, ebits, mbits):
        self.name, self.ebits, self.mbits = name, ebits, mbits
        self.n = 1 + ebits + mbits
        self.bias = (1 << (ebits - 1)) - 1
        self.emin = 1 - self.bias
        self.inf_bits = ((1 << ebits) - 1) << mbits
        self.nan_bits = self.inf_bits | (1 << (mbits - 1))

    def dec(self, bits):
        s = bits >> (self.n - 1)
        e = (bits >> self.mbits) & ((1 << self.ebits) - 1)
        m = bits & ((1 << self.mbits) - 1)
        if e == (1 << self.ebits) - 1:
            return NAN if m else (-math.inf if s else math.inf)
        if e == 0:
            v = Fraction(m) * Fraction(2) ** (self.emin - self.mbits)
        else:
            v = Fraction((1 << self.mbits) | m) * Fraction(2) ** (e - self.bias - self.mbits)
        return -v if s else v

    def enc(self, v):
        if not finite(v):
            if v != v:
                self._raise(NV)
                return self.nan_bits
            return self.inf_bits | ((v < 0) << (self.n - 1))
        if v == 0:
            return 0
        s = v < 0
        m = -v if s else v
        e = m.numerator.bit_length() - m.denominator.bit_length()
        if Fraction(2) ** e > m:
            e -= 1
        sub = e < self.emin
        scaled = m / Fraction(2) ** ((self.emin if sub else e) - self.mbits)
        q = scaled.numerator // scaled.denominator
        rem = scaled - q
        inexact = rem != 0
        if rem > Fraction(1, 2) or (rem == Fraction(1, 2) and q & 1):
            q += 1
        bits = q if sub else ((e + self.bias) << self.mbits) + (q - (1 << self.mbits))
        fl = NX if inexact else 0
        if sub and inexact:
            fl |= UF
        if bits >= self.inf_bits:
            bits, fl = self.inf_bits, fl | OF | NX
        if fl:
            self._raise(fl)
        return bits | (s << (self.n - 1))

    def _raise(self, fl):
        self.flags |= fl
        self.flag_events += 1

    def _special(self, x, y, f):
        # inf e NaN: deixa o float do Python decidir (inf - inf, 0 * inf -> nan)
        p = lambda v: float(v) if not finite(v) else (0.0 if v == 0 else (1.0 if v > 0 else -1.0))
        return f(p(x), p(y))


T8, T16, T32, T64 = Takum(8), Takum(16), Takum(32), Takum(64)


def ieee_set():
    """Instâncias novas (os flags são por instância)."""
    return {
        "FP8": IEEE("FP8", 4, 3),            # minifloat E4M3 no estilo IEEE
        "E5M2": IEEE("E5M2", 5, 2),
        "FP16": IEEE("FP16", 5, 10),         # binary16
        "BF16": IEEE("BF16", 8, 7),          # bfloat16
        "FP32": IEEE("FP32", 8, 23),         # binary32
        "FP64": IEEE("FP64", 11, 52),        # binary64
        "FP128": IEEE("FP128", 15, 112),     # binary128 (referência)
    }
