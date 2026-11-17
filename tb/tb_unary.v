// tb_unary.v - testa takum_ncvt (KIND = 0) e takum_wmul (KIND = 1) contra vetores do oráculo
// Formato: ncvt: t(2N) y(N)      wmul: a(N) b(N) y(2N)      (hexadecimal)

`timescale 1ns/1ps
module tb_unary;
    parameter N = 8;
    parameter KIND = 0;
    parameter FILE = "v.hex";

    reg  [2*N-1:0] t;
    reg  [N-1:0]   a, b;
    wire [N-1:0]   yn;
    wire [2*N-1:0] yw;
    takum_ncvt #(.N(N)) u_n (.t(t), .y(yn));
    takum_wmul #(.N(N)) u_w (.a(a), .b(b), .y(yw));

    integer fd, rc, n, errors;
    reg [63:0] x0, x1, x2;

    initial begin
        errors = 0; n = 0;
        fd = $fopen(FILE, "r");
        if (fd == 0) begin $display("ERRO: não abriu %0s", FILE); $finish; end
        while (!$feof(fd)) begin
            if (KIND == 0) begin
                rc = $fscanf(fd, "%h %h\n", x0, x1);
                if (rc == 2) begin
                    t = x0[2*N-1:0]; #1; n = n + 1;
                    if (yn !== x1[N-1:0]) begin
                        errors = errors + 1;
                        if (errors <= 10) $display("ERRO ncvt T%0d->T%0d: t=%h obtido=%h esperado=%h", 2*N, N, t, yn, x1[N-1:0]);
                    end
                end
            end else begin
                rc = $fscanf(fd, "%h %h %h\n", x0, x1, x2);
                if (rc == 3) begin
                    a = x0[N-1:0]; b = x1[N-1:0]; #1; n = n + 1;
                    if (yw !== x2[2*N-1:0]) begin
                        errors = errors + 1;
                        if (errors <= 10) $display("ERRO wmul T%0d: a=%h b=%h obtido=%h esperado=%h", N, a, b, yw, x2[2*N-1:0]);
                    end
                end
            end
        end
        $fclose(fd);
        if (KIND == 0) begin
            if (errors == 0) $display("PASS ncvt T%0d->T%0d: %0d vetores", 2*N, N, n);
            else             $display("FAIL ncvt T%0d->T%0d: %0d divergências em %0d vetores", 2*N, N, errors, n);
        end else begin
            if (errors == 0) $display("PASS wmul T%0d->T%0d: %0d vetores", N, 2*N, n);
            else             $display("FAIL wmul T%0d->T%0d: %0d divergências em %0d vetores", N, 2*N, errors, n);
        end
        $finish;
    end
endmodule
