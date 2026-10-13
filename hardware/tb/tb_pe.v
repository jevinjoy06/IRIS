`timescale 1ns / 1ps

// Testbench for pe.v — Phase 2 IRIS.
//
// Verifies a single PE computes psum_out = weight * act_in + psum_in
// and that the valid_in → valid_out pipeline latency is exactly 1 cycle.
//
// The PE no longer has an act_out port; activations are broadcast externally.

module tb_pe;

    parameter DATA_WIDTH = 16;
    parameter ACC_WIDTH  = 32;

    reg                  clk, rst_n, weight_load;
    reg  [DATA_WIDTH-1:0] weight_in, act_in;
    reg  [ACC_WIDTH-1:0]  psum_in;
    reg                   valid_in;
    wire [ACC_WIDTH-1:0]  psum_out;
    wire                  valid_out;

    pe #(
        .DATA_WIDTH(DATA_WIDTH),
        .ACC_WIDTH (ACC_WIDTH)
    ) dut (
        .clk        (clk),
        .rst_n      (rst_n),
        .weight_load(weight_load),
        .weight_in  (weight_in),
        .act_in     (act_in),
        .psum_in    (psum_in),
        .valid_in   (valid_in),
        .psum_out   (psum_out),
        .valid_out  (valid_out)
    );

    initial clk = 0;
    always #5 clk = ~clk;

    task check;
        input [31:0]  expected_psum;
        input         expected_valid;
        input [127:0] label;
        begin
            if ($signed(psum_out) === $signed(expected_psum) && valid_out === expected_valid)
                $display("PASS [%s]: psum_out=%0d, valid_out=%b",
                         label, $signed(psum_out), valid_out);
            else
                $display("FAIL [%s]: psum_out=%0d (expected %0d), valid_out=%b (expected %b)",
                         label, $signed(psum_out), $signed(expected_psum),
                         valid_out, expected_valid);
        end
    endtask

    initial begin
        $dumpfile("hardware/sim/tb_pe.vcd");
        $dumpvars(0, tb_pe);

        rst_n = 0; weight_load = 0; weight_in = 0;
        act_in = 0; psum_in = 0; valid_in = 0;
        #20 rst_n = 1;

        // --- Load weight = 3 ---
        @(posedge clk); #1;
        weight_in   = 16'd3;
        weight_load = 1;
        @(posedge clk); #1;
        weight_load = 0;

        // --- TC1: 3 * 4 + 0 = 12, valid_in=1, expect valid_out=1 next cycle ---
        act_in   = 16'd4;
        psum_in  = 32'd0;
        valid_in = 1;
        @(posedge clk); #1;
        valid_in = 0;
        check(32'd12, 1'b1, "TC1_3x4+0=12  ");

        // --- TC2: valid_in=0, psum_out should stay (held), valid_out=0 ---
        @(posedge clk); #1;
        check(32'd12, 1'b0, "TC2_hold_psum ");

        // --- TC3: 3 * 5 + 10 = 25 ---
        act_in   = 16'd5;
        psum_in  = 32'd10;
        valid_in = 1;
        @(posedge clk); #1;
        valid_in = 0;
        check(32'd25, 1'b1, "TC3_3x5+10=25 ");

        // --- TC4: signed — 3 * (-2) + 0 = -6 ---
        act_in   = 16'hFFFE;   // -2 in two's complement
        psum_in  = 32'd0;
        valid_in = 1;
        @(posedge clk); #1;
        valid_in = 0;
        check(32'hFFFFFFFA, 1'b1, "TC4_3x-2=-6   ");

        // --- TC5: reload weight = -1, then (-1)*(-1)+0 = 1 ---
        weight_in   = 16'hFFFF;  // -1
        weight_load = 1;
        @(posedge clk); #1;
        weight_load = 0;
        act_in   = 16'hFFFF;    // -1
        psum_in  = 32'd0;
        valid_in = 1;
        @(posedge clk); #1;
        valid_in = 0;
        check(32'd1, 1'b1, "TC5_-1x-1=1   ");

        $display("PE testbench complete.");
        $finish;
    end

endmodule
