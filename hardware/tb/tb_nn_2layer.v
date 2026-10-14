`timescale 1ns / 1ps

// Testbench for nn_2layer — Phase 3 IRIS hardware accelerator.
//
// Tests the 2-layer FC network: logits = W2 * ReLU(W1 * x)
// Scaled to IN_FEATURES=40, HIDDEN_SIZE=64, CLASSES=2
//
// Smoke tests (no hand-computed golden values for large net):
// TC1 — Reset check: verify valid_out is low after reset
// TC2 — Single inference: verify valid_out pulses high
// TC3 — Sequential inferences: two consecutive inferences both complete
// TC4 — Valid output range: argmax_class is 0 or 1

module tb_nn_2layer;

    localparam IN_FEATURES = 40;
    localparam HIDDEN_SIZE = 64;
    localparam CLASSES     = 2;
    localparam DATA_WIDTH  = 16;
    localparam ACC_WIDTH   = 32;

    // DUT ports
    reg  clk, rst_n, start;
    reg  [(IN_FEATURES*HIDDEN_SIZE*DATA_WIDTH)-1:0] weights_l1;
    reg  [(HIDDEN_SIZE*CLASSES*DATA_WIDTH)-1:0]     weights_l2;
    reg  [(IN_FEATURES*DATA_WIDTH)-1:0]             x_in;
    wire [(CLASSES*ACC_WIDTH)-1:0]                  logits_out;
    wire [$clog2(CLASSES)-1:0]                      argmax_class;
    wire                                             valid_out;

    nn_2layer #(
        .IN_FEATURES(IN_FEATURES),
        .HIDDEN_SIZE(HIDDEN_SIZE),
        .CLASSES    (CLASSES),
        .DATA_WIDTH (DATA_WIDTH),
        .ACC_WIDTH  (ACC_WIDTH)
    ) dut (
        .clk        (clk),
        .rst_n      (rst_n),
        .start      (start),
        .weights_l1 (weights_l1),
        .weights_l2 (weights_l2),
        .x_in       (x_in),
        .logits_out (logits_out),
        .argmax_class(argmax_class),
        .valid_out  (valid_out)
    );

    // 100 MHz clock
    initial clk = 0;
    always #5 clk = ~clk;

    integer pass_count;
    integer i, j, timeout;

    // ----------------------------------------------------------------
    // Helper: run one inference and verify completion (smoke test)
    // ----------------------------------------------------------------
    task run_inference;
        input [127:0] label;
        integer got_argmax;
        begin
            // Pulse start
            @(posedge clk); #1;
            start = 1;
            @(posedge clk); #1;
            start = 0;

            // Wait for valid_out (timeout after 500 cycles, enough for 40+64+overhead)
            timeout = 0;
            while (!valid_out && timeout < 500) begin
                @(posedge clk); #1;
                timeout = timeout + 1;
            end

            if (!valid_out) begin
                $display("FAIL [%s]: valid_out never asserted (timeout after %0d cycles)", label, timeout);
            end else begin
                got_argmax = argmax_class;
                if (got_argmax == 0 || got_argmax == 1) begin
                    $display("PASS [%s]: valid_out asserted at cycle %0d, argmax=%0d (valid range)",
                             label, timeout, got_argmax);
                    pass_count = pass_count + 1;
                end else begin
                    $display("FAIL [%s]: argmax=%0d (out of valid range [0,1])", label, got_argmax);
                end
            end
        end
    endtask

    // ================================================================
    // Stimulus
    // ================================================================
    initial begin
        $dumpfile("sim/tb_nn_2layer.vcd");
        $dumpvars(0, tb_nn_2layer);

        pass_count  = 0;
        start       = 0;
        weights_l1  = 0;
        weights_l2  = 0;
        x_in        = 0;
        rst_n       = 0;
        #25; rst_n  = 1;

        // ==============================================================
        // TC1 — Reset check: valid_out should be 0 after reset
        // ==============================================================
        #10;
        if (valid_out !== 1'b0) begin
            $display("FAIL [TC1_reset]: valid_out should be 0 after reset");
        end else begin
            $display("PASS [TC1_reset]: valid_out is 0 after reset");
            pass_count = pass_count + 1;
        end

        // ==============================================================
        // TC2 — Single inference with zero weights and activations
        //   Should complete without errors
        // ==============================================================
        run_inference("TC2_single_infer");

        // ==============================================================
        // TC3 — Two sequential inferences
        //   Both should complete successfully
        // ==============================================================
        #50;  // Wait between tests
        run_inference("TC3_second_infer");

        // ==============================================================
        // TC4 — Verify argmax is in valid range [0,1]
        //   (Previous tests should have validated this)
        // ==============================================================
        #50;
        run_inference("TC4_argmax_valid");

        $display("\nTestbench complete. %0d/4 passed.", pass_count);
        $finish;
    end

endmodule
