// takum_ncvt.v — vncvt.t.t: reduz um takum de 2N bits para N bits
//
// Como os campos S D R C F ficam sempre no topo da palavra e o takum é monótono,
// estreitar é só arredondar a cadeia de bits: sem decodificar nem recodificar.
// Mesma regra do takum_encoder: vizinho mais próximo, empate para o par, na
// palavra; um valor não nulo nunca vira 0 nem NaR (satura).

`timescale 1ns/1ps

module takum_ncvt #(
    parameter N = 8                 // largura de destino; a origem tem 2N bits
) (
    input  wire [2*N-1:0] t,
    output wire [N-1:0]   y
);
    localparam [N-1:0] MAXPOS = {1'b0, {(N-1){1'b1}}};
    localparam [N-1:0] MINPOS = {{(N-1){1'b0}}, 1'b1};
    localparam [N-1:0] NAR    = {1'b1, {(N-1){1'b0}}};

    wire rest_zero = ~|t[2*N-2:0];
    wire is_zero   = ~t[2*N-1] & rest_zero;
    wire is_nar    =  t[2*N-1] & rest_zero;
    wire sign      =  t[2*N-1];

    // magnitude (complemento de dois nega o valor)
    wire [2*N-1:0] u = sign ? (~t + 1'b1) : t;

    wire [N-1:0] w     = u[2*N-1:N];
    wire         guard = u[N-1];
    wire         stk   = |u[N-2:0];
    wire         rnd   = guard & (stk | w[0]);
    wire [N-1:0] w_rnd = w + {{(N-1){1'b0}}, rnd};

    wire [N-1:0] mag = w_rnd[N-1]          ? MAXPOS :      // "vai-um" chegou ao sinal
                       (w_rnd == {N{1'b0}}) ? MINPOS :      // nunca vira zero
                                              w_rnd;

    assign y = is_nar  ? NAR :
               is_zero ? {N{1'b0}} :
               sign    ? (~mag + 1'b1) : mag;
endmodule
