// takum_dot.v — núcleo do vtdot.vv para uma largura de elemento
//
//   acc_out = acc_in + soma_{i ativo} a[i] * b[i]
//
// Os produtos são formados em 2N bits (takum_wmul, exatos) e acumulados em
// ordem, i = 0, 1, ..., também em 2N bits: é o "acúmulo em precisão ampliada"
// da guideline. Só há arredondamento nas somas, e em 2N bits.
// Combinacional: LANES multiplicadores e LANES somadores em cadeia.

`timescale 1ns/1ps

module takum_dot #(
    parameter N     = 8,
    parameter LANES = 8
) (
    input  wire [LANES*N-1:0] a,
    input  wire [LANES*N-1:0] b,
    input  wire [LANES-1:0]   en,        // elemento i participa (i < vl e máscara)
    input  wire [2*N-1:0]     acc_in,
    output wire [2*N-1:0]     acc_out
);
    wire [2*N-1:0] acc [0:LANES];
    assign acc[0]  = acc_in;
    assign acc_out = acc[LANES];

    genvar i;
    generate
        for (i = 0; i < LANES; i = i + 1) begin : g
            wire [2*N-1:0] p, s;
            takum_wmul #(.N(N)) u_mul (.a(a[N*i +: N]), .b(b[N*i +: N]), .y(p));
            takum_alu #(.N(2*N), .MUL(0)) u_add (.a(acc[i]), .b(p), .op(2'd0), .y(s));
            assign acc[i+1] = en[i] ? s : acc[i];
        end
    endgenerate
endmodule
