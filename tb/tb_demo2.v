// =============================================================================
// tb_demo2.v — Demonstração da Fase 2 para VER AS ONDAS
// -----------------------------------------------------------------------------
// Não é um teste de aprovação: percorre casos escolhidos a dedo, um a cada
// 10 ns, e grava build/demo2.vcd. As figuras são desenhadas por tb/waves.py
// (make waves2), sem precisar do GTKWave.
//
//   Parte 1 (0–80 ns):    vncvt.t.t  T16 -> T8: truncar, arredondar, empates, saturar
//   Parte 2 (80–120 ns):  produto em 8 bits (takum_alu) x produto alargado (takum_wmul)
//   Parte 3 (120–190 ns): vtdot.vv na unidade vetorial (SEW = 8), variando vl e a
//                         máscara, seguido de vncvt.t.t
// =============================================================================

`timescale 1ns/1ps
module tb_demo2;
    // ---- parte 1: vncvt.t.t -------------------------------------------------
    reg  [15:0] t16;
    wire [7:0]  y8;
    takum_ncvt #(.N(8)) u_ncvt (.t(t16), .y(y8));

    // ---- parte 2: produto normal x produto alargado ----------------------------
    reg  [7:0]  a, b;
    wire [7:0]  y_mul;
    wire [15:0] y_wmul;
    takum_alu  #(.N(8)) u_alu  (.a(a), .b(b), .op(2'd2), .y(y_mul));
    takum_wmul #(.N(8)) u_wmul (.a(a), .b(b), .y(y_wmul));

    // ---- parte 3: unidade vetorial ---------------------------------------------
    reg  [63:0] vs2, vs1, vd_old;
    reg  [2:0]  op;
    reg  [7:0]  vl;
    reg         vm;
    reg  [7:0]  v0;
    wire [63:0] vd;
    takum_vec_alu #(.VLEN(64)) u_vec (.vs2(vs2), .vs1(vs1), .vd_old(vd_old), .op(op), .sew(2'd0),
                                      .vl(vl), .vm(vm), .v0(v0), .vd(vd));
    wire [15:0] acc = vd[15:0];              // acumulador do vtdot: elemento 0, em T16
    wire [7:0]  y_dot;                       // vncvt.t.t do acumulador
    takum_ncvt #(.N(8)) u_fim (.t(acc), .y(y_dot));

    initial begin
        $dumpfile("build/demo2.vcd");
        $dumpvars(0, tb_demo2);

        // valores neutros para o que não está em uso
        a = 8'h40; b = 8'h40;
        vs2 = 64'h0; vs1 = 64'h0; vd_old = 64'h0; op = 3'd3; vl = 8'd0; vm = 1'b1; v0 = 8'h00;

        // ---- parte 1 ---------------------------------------------------------
        t16 = 16'h5130; #10;    // 12,75: cortado 0x30, abaixo da metade -> 12
        t16 = 16'h51C0; #10;    // 15: cortado 0xC0, acima da metade -> 16
        t16 = 16'h5180; #10;    // 14: empate, palavra ímpar (0x51) -> sobe para 16
        t16 = 16'h5080; #10;    // 10: empate, palavra par (0x50) -> fica em 8
        t16 = 16'h7FFF; #10;    // o vai-um chegaria ao sinal -> satura no maior
        t16 = 16'h0001; #10;    // quase zero -> menor positivo, nunca zero
        t16 = 16'hAE40; #10;    // -15 -> -16 (simétrico ao caso positivo)
        t16 = 16'h8000; #10;    // NaR continua NaR

        // ---- parte 2 ---------------------------------------------------------
        t16 = 16'h4000;
        a = 8'h4D; b = 8'h4A; #10;   // 5 x 3: em 8 bits dá 16; alargado dá 15, exato
        a = 8'h44; b = 8'h44; #10;   // 1,5 x 1,5: em 8 bits dá 2; alargado dá 2,25
        a = 8'h4A; b = 8'hB6; #10;   // 3 x (-3): -8 em 8 bits; -9 alargado
        a = 8'h4A; b = 8'h80; #10;   // qualquer coisa x NaR = NaR

        // ---- parte 3: vtdot.vv, x = [1, 2, 3, 5], y = [1, 1, 1, 3] ------------
        a = 8'h40; b = 8'h40;
        vs2 = 64'h00000000_4D4A4840;
        vs1 = 64'h00000000_4A404040;
        vl = 8'd0; #10;              // vl = 0: nada muda
        vl = 8'd1; #10;              // 1
        vl = 8'd2; #10;              // 1 + 2 = 3
        vl = 8'd3; #10;              // + 3 = 6
        vl = 8'd4; #10;              // + 5 x 3 = 21
        vm = 1'b0; v0 = 8'b0000_0101; #10;   // máscara: só os elementos 0 e 2 -> 1 + 3 = 4
        vm = 1'b1; vd_old = 64'h00000000_00005A00; #10;   // acumulador de entrada = 512 -> 532 (533 não cabe em T16)
        $finish;
    end
endmodule
