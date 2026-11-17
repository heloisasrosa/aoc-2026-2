// tb_vec.v - validacao da alu vetorial contra vetores de teste
// Formato de cada linha: vs2 vs1 vd_old op vl vm v0 vd (hexadecimal)
// op: 0 vtadd, 1 vtsub, 2 vtmul, 3 vtdot, 4 vncvt.t.t

`timescale 1ns/1ps
module tb_vec;
    parameter SEW = 8;
    parameter NV = 1;
    parameter FILE = "vec.hex";

    reg  [63:0] vs2, vs1, old;
    reg  [2:0]  op;
    reg  [7:0]  vl;
    reg         vm;
    reg  [7:0]  v0;
    integer     per_op [0:4];
    wire [63:0] vd;
    takum_vec_alu #(.VLEN(64)) dut (.vs2(vs2), .vs1(vs1), .vd_old(old), .op(op),
                                    .sew(SEW == 8 ? 2'd0 : SEW == 16 ? 2'd1 : 2'd2), .vl(vl), .vm(vm), .v0(v0), .vd(vd));

    integer fd, rc, n, errors;
    reg [63:0] x2, x1, xo, xd;
    reg [31:0] xop, xvl, xvm, xv0;

    initial begin
        errors = 0; n = 0;
        per_op[0] = 0; per_op[1] = 0; per_op[2] = 0; per_op[3] = 0; per_op[4] = 0;
        fd = $fopen(FILE, "r");
        if (fd == 0) begin $display("ERRO: não abriu %0s", FILE); $finish; end
        while (!$feof(fd) && n < NV) begin
            rc = $fscanf(fd, "%h %h %h %h %h %h %h %h\n", x2, x1, xo, xop, xvl, xvm, xv0, xd);
            if (rc == 8) begin
                vs2 = x2; vs1 = x1; old = xo; op = xop[2:0]; vl = xvl[7:0]; vm = xvm[0]; v0 = xv0[7:0];
                per_op[op] = per_op[op] + 1;
                #1;
                if (vd !== xd) begin
                    errors = errors + 1;
                    if (errors <= 10)
                        $display("ERRO vec SEW=%0d: vs2=%h vs1=%h old=%h op=%0d vl=%0d vm=%b v0=%h obtido=%h esperado=%h",
                                 SEW, vs2, vs1, old, op, vl, vm, v0, vd, xd);
                end
                n = n + 1;
            end
        end
        $fclose(fd);
        if (errors == 0) $display("PASS vec SEW=%0d: %0d vetores (add %0d, sub %0d, mul %0d, dot %0d, ncvt %0d)", SEW, n,
                                  per_op[0], per_op[1], per_op[2], per_op[3], per_op[4]);
        else             $display("FAIL vec SEW=%0d: %0d divergências em %0d vetores", SEW, errors, n);
        $finish;
    end
endmodule
