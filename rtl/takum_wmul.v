// takum_wmul.v — multiplicação com alargamento: T(N) x T(N) -> T(2N)
//
// O produto dos significandos tem 2(N-4) bits e cabe inteiro na fração do takum
// de 2N bits, então o resultado é EXATO sempre que o expoente não satura
// (|ea + eb| dentro de [-255, 254]). É o primeiro estágio do vtdot.vv.

`timescale 1ns/1ps

module takum_wmul #(
    parameter N = 8
) (
    input  wire [N-1:0]   a,
    input  wire [N-1:0]   b,
    output wire [2*N-1:0] y
);
    localparam W = N - 4;                    // significando {1, frac}

    wire              za, na, sa, zb, nb, sb;
    wire signed [8:0] ea, eb;
    wire [N-6:0]      fa, fb;
    takum_decoder #(.N(N)) u_da (.t(a), .is_zero(za), .is_nar(na), .sign(sa), .exp(ea), .frac(fa));
    takum_decoder #(.N(N)) u_db (.t(b), .is_zero(zb), .is_nar(nb), .sign(sb), .exp(eb), .frac(fb));

    wire [2*W-1:0] prod   = {1'b1, fa} * {1'b1, fb};
    wire           p_hi   = prod[2*W-1];                    // produto >= 2
    wire [2*W-1:0] p_norm = p_hi ? prod : (prod << 1);      // bit 1 na posição 2W-1
    wire signed [10:0] exp = $signed({{2{ea[8]}}, ea}) + $signed({{2{eb[8]}}, eb}) + (p_hi ? 11'sd1 : 11'sd0);

    // fração do encoder de 2N bits: 2N-3 bits; o produto ocupa 2W-1 = 2N-9, sobram 6 zeros
    wire [2*N-4:0] frac = {p_norm[2*W-2:0], 6'b0};

    takum_encoder #(.N(2*N)) u_enc (.is_zero(za | zb), .is_nar(na | nb), .sign(sa ^ sb),
                                    .exp(exp), .frac(frac), .sticky(1'b0), .t(y));
endmodule
