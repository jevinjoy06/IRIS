`timescale 1ns / 1ps

module tb_mac_unit;
    parameter DATA_WIDTH = 16;
    parameter ACC_WIDTH  = 32;

    reg                   clk;
    reg                   rst_n;
    reg                   en;
    reg  [DATA_WIDTH-1:0] a;
    reg  [DATA_WIDTH-1:0] b;
    reg  [ACC_WIDTH-1:0]  acc_in;
    wire [ACC_WIDTH-1:0]  acc_out;
    wire                  valid;

    mac_unit #(
        .DATA_WIDTH(DATA_WIDTH),
        .ACC_WIDTH(ACC_WIDTH)
    ) dut (
        .clk(clk), .rst_n(rst_n), .en(en),
        .a(a), .b(b), .acc_in(acc_in),
        .acc_out(acc_out), .valid(valid)
    );

    initial clk = 0;
    always #5 clk = ~clk; // 100 MHz

    task apply_mac;
        input [DATA_WIDTH-1:0] op_a, op_b;
        input [ACC_WIDTH-1:0]  acc;
        input [ACC_WIDTH-1:0]  expected;
        begin
            @(posedge clk); #1;
            a = op_a; b = op_b; acc_in = acc; en = 1;
            @(posedge clk); #1;
            en = 0;
            @(posedge clk); #1;
            if (valid && acc_out === expected)
                $display("PASS: %0d * %0d + %0d = %0d", op_a, op_b, acc, acc_out);
            else
                $display("FAIL: %0d * %0d + %0d => got %0d, expected %0d",
                         op_a, op_b, acc, acc_out, expected);
        end
    endtask

    initial begin
        rst_n = 0; en = 0; a = 0; b = 0; acc_in = 0;
        #20 rst_n = 1;

        apply_mac(16'd3,  16'd4,  32'd0,  32'd12);  // 3*4+0   = 12
        apply_mac(16'd3,  16'd4,  32'd5,  32'd17);  // 3*4+5   = 17
        apply_mac(16'd0,  16'd99, 32'd7,  32'd7);   // 0*99+7  = 7
        apply_mac(16'd255, 16'd255, 32'd0, 32'd65025); // 255*255 = 65025

        $display("Testbench complete.");
        $finish;
    end

    initial begin
        $dumpfile("tb_mac_unit.vcd");
        $dumpvars(0, tb_mac_unit);
    end
endmodule
