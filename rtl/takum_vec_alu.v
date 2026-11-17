// takum_vec_alu.v — Unidade vetorial Zvtakum
//
//   op  instrução    semântica (i < vl e elemento não mascarado)
//   0   vtadd.vv     vd[i] = vs2[i] + vs1[i]
//   1   vtsub.vv     vd[i] = vs2[i] - vs1[i]
//   2   vtmul.vv     vd[i] = vs2[i] * vs1[i]
//   3   vtdot.vv     vd[0] (2*SEW bits) += soma_i vs2[i] * vs1[i], produtos e acúmulo em 2*SEW
//   4   vncvt.t.t    vd[i] (SEW bits) = arredonda(vs2[i] de 2*SEW bits)
//
// sew: 0 = 8, 1 = 16, 2 = 32 bits. No vncvt.t.t, sew é a largura de DESTINO.
// Elementos com i >= vl (cauda) ou mascarados (vm = 0 e v0[i] = 0) mantêm vd_old.
// No vtdot.vv, só vd[0] é escrito; com vl = 0 nada muda (como nas reduções do RVV).

`timescale 1ns/1ps

module takum_vec_alu #(
    parameter VLEN = 64
) (
    input  wire [VLEN-1:0] vs2,
    input  wire [VLEN-1:0] vs1,
    input  wire [VLEN-1:0] vd_old,
    input  wire [2:0]      op,
    input  wire [1:0]      sew,
    input  wire [7:0]      vl,        // nº de elementos ativos
    input  wire            vm,        // 1 = sem máscara
    input  wire [VLEN/8-1:0] v0,      // máscara: bit i vale para o elemento i
    output wire [VLEN-1:0] vd
);
    localparam L8 = VLEN/8, L16 = VLEN/16, L32 = VLEN/32;

    wire [1:0] aop = op[1:0];

    // ---- elemento i ativo: i < vl e (vm ou v0[i]) -----------------------------
    reg [L8-1:0] en;
    integer k;
    always @* begin
        for (k = 0; k < L8; k = k + 1)
            en[k] = (k < vl) & (vm | v0[k]);
    end

    // ---- vtadd / vtsub / vtmul ------------------------------------------------
    wire [VLEN-1:0] r8, r16, r32;
    // ---- vncvt.t.t: origem 2*SEW em vs2, destino SEW na metade de baixo -------
    wire [VLEN-1:0] n8, n16, n32;
    assign n8 [VLEN-1:VLEN/2] = {(VLEN/2){1'b0}};
    assign n16[VLEN-1:VLEN/2] = {(VLEN/2){1'b0}};
    assign n32[VLEN-1:VLEN/2] = {(VLEN/2){1'b0}};
    // ---- vtdot.vv -------------------------------------------------------------
    wire [15:0] d8;
    wire [31:0] d16;
    wire [63:0] d32;

    genvar i;
    generate
        for (i = 0; i < L8; i = i + 1) begin : g8
            takum_alu #(.N(8)) u (.a(vs2[8*i +: 8]), .b(vs1[8*i +: 8]), .op(aop), .y(r8[8*i +: 8]));
        end
        for (i = 0; i < L16; i = i + 1) begin : g16
            takum_alu #(.N(16)) u (.a(vs2[16*i +: 16]), .b(vs1[16*i +: 16]), .op(aop), .y(r16[16*i +: 16]));
        end
        for (i = 0; i < L32; i = i + 1) begin : g32
            takum_alu #(.N(32)) u (.a(vs2[32*i +: 32]), .b(vs1[32*i +: 32]), .op(aop), .y(r32[32*i +: 32]));
        end
        for (i = 0; i < L16; i = i + 1) begin : gn8
            takum_ncvt #(.N(8)) u (.t(vs2[16*i +: 16]), .y(n8[8*i +: 8]));
        end
        for (i = 0; i < L32; i = i + 1) begin : gn16
            takum_ncvt #(.N(16)) u (.t(vs2[32*i +: 32]), .y(n16[16*i +: 16]));
        end
        for (i = 0; i < VLEN/64; i = i + 1) begin : gn32
            takum_ncvt #(.N(32)) u (.t(vs2[64*i +: 64]), .y(n32[32*i +: 32]));
        end
    endgenerate

    takum_dot #(.N(8),  .LANES(L8))  u_d8  (.a(vs2), .b(vs1), .en(en[L8-1:0]),  .acc_in(vd_old[15:0]), .acc_out(d8));
    takum_dot #(.N(16), .LANES(L16)) u_d16 (.a(vs2), .b(vs1), .en(en[L16-1:0]), .acc_in(vd_old[31:0]), .acc_out(d16));
    takum_dot #(.N(32), .LANES(L32)) u_d32 (.a(vs2), .b(vs1), .en(en[L32-1:0]), .acc_in(vd_old[63:0]), .acc_out(d32));

    // ---- seleção por op e sew -------------------------------------------------
    wire is_dot  = (op == 3'd3);
    wire is_ncvt = (op == 3'd4);

    wire [VLEN-1:0] res_el = is_ncvt ? ((sew == 2'd0) ? n8 : (sew == 2'd1) ? n16 : n32)
                                     : ((sew == 2'd0) ? r8 : (sew == 2'd1) ? r16 : r32);

    // máscara de bits dos elementos ativos
    reg [VLEN-1:0] act;
    integer b, w;
    always @* begin
        w = (sew == 2'd0) ? 8 : (sew == 2'd1) ? 16 : 32;
        for (b = 0; b < VLEN; b = b + 1)
            act[b] = en[b / w] & ~(is_ncvt & (b >= VLEN/2));   // vncvt só tem VLEN/(2*SEW) elementos
    end

    wire [VLEN-1:0] vd_el = (res_el & act) | (vd_old & ~act);

    // vtdot: escreve só o elemento 0, de 2*SEW bits
    reg [VLEN-1:0] vd_dot;
    always @* begin
        vd_dot = vd_old;
        case (sew)
            2'd0:    vd_dot[15:0] = d8;
            2'd1:    vd_dot[31:0] = d16;
            default: vd_dot[63:0] = d32;
        endcase
    end

    assign vd = is_dot ? vd_dot : vd_el;
endmodule
