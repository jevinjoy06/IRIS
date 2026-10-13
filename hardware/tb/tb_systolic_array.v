`timescale 1ns / 1ps

// Testbench for systolic_array — Phase 2 IRIS hardware accelerator.
//
// Tests the computation: result[c] = sum_{r} w[r][c] * x[r]  (y = W*x)
//
// Protocol:
//   1. Load weights: assert weight_load=1 for one cycle.
//   2. Start inference: present x[0] on act_in, assert valid_in=1 for ONE cycle.
//   3. On each subsequent cycle r=1..ROWS-1: present x[r] on act_in, valid_in=0.
//   4. One cycle after step 3 completes: valid_out asserts, result[] is valid.
//
// Test cases:
//   TC1 — positive integers  (4x4, y = [90, 100, 110, 120])
//   TC2 — signed activations (same W, x = [-1,2,-3,4], y = [34, 36, 38, 40])
//   TC3 — zero activations   (y = all zeros)
//   TC4 — identity weights   (y = x = [5, 7, 11, 13])
//   TC5 — back-to-back       (second inference with same weights, x = [-8,3,0,100])
//   TC6 — negative weights   (y = [-28, -32, -36, -40])

module tb_systolic_array;

    localparam ROWS       = 4;
    localparam COLS       = 4;
    localparam DATA_WIDTH = 16;
    localparam ACC_WIDTH  = 32;

    // -------------------------------------------------------------- DUT ports
    reg                              clk;
    reg                              rst_n;
    reg                              weight_load;
    reg [(ROWS*COLS*DATA_WIDTH)-1:0] weights;
    reg  [DATA_WIDTH-1:0]            act_in;   // single broadcast activation
    reg                              valid_in;
    wire [(COLS*ACC_WIDTH)-1:0]      result;
    wire                             valid_out;

    systolic_array #(
        .ROWS       (ROWS),
        .COLS       (COLS),
        .DATA_WIDTH (DATA_WIDTH),
        .ACC_WIDTH  (ACC_WIDTH)
    ) dut (
        .clk        (clk),
        .rst_n      (rst_n),
        .weight_load(weight_load),
        .weights    (weights),
        .act_in     (act_in),
        .valid_in   (valid_in),
        .result     (result),
        .valid_out  (valid_out)
    );

    // ----------------------------------------------------------- Clock: 100 MHz
    initial clk = 0;
    always #5 clk = ~clk;

    // -------------------------------------------------- Golden-model storage
    integer gw [0:ROWS-1][0:COLS-1];   // weight matrix
    integer gx [0:ROWS-1];             // activation vector
    integer ge [0:COLS-1];             // expected outputs

    // ---------------------------------------------- Task: load_weights
    task load_weights;
        integer r, c;
        begin
            @(posedge clk); #1;
            for (r = 0; r < ROWS; r = r + 1)
                for (c = 0; c < COLS; c = c + 1)
                    weights[(r*COLS+c)*DATA_WIDTH +: DATA_WIDTH] =
                        gw[r][c][DATA_WIDTH-1:0];
            weight_load = 1;
            @(posedge clk); #1;
            weight_load = 0;
        end
    endtask

    // ---------------------------------------------- Task: run_inference
    // Streams gx[], waits for valid_out, checks against golden expected.
    integer tc_pass;

    task run_inference;
        input [127:0] label;
        integer r, c, acc, got;
        begin
            // Compute golden expected
            for (c = 0; c < COLS; c = c + 1) begin
                acc = 0;
                for (r = 0; r < ROWS; r = r + 1)
                    acc = acc + gw[r][c] * gx[r];
                ge[c] = acc;
            end

            // Present x[0] with valid_in=1 (single pulse)
            @(posedge clk); #1;
            act_in   = gx[0][DATA_WIDTH-1:0];
            valid_in = 1;

            // Present x[1..ROWS-1] with valid_in=0
            for (r = 1; r < ROWS; r = r + 1) begin
                @(posedge clk); #1;
                act_in   = gx[r][DATA_WIDTH-1:0];
                valid_in = 0;
            end

            // One more cycle for the last MAC stage to register output
            @(posedge clk); #1;
            valid_in = 0;

            // Check valid_out and results
            tc_pass = 1;
            if (!valid_out) begin
                $display("FAIL [%s]: valid_out not asserted at expected cycle", label);
                tc_pass = 0;
            end else begin
                for (c = 0; c < COLS; c = c + 1) begin
                    got = $signed(result[c*ACC_WIDTH +: ACC_WIDTH]);
                    if (got !== ge[c]) begin
                        $display("FAIL [%s] col %0d: got %0d, expected %0d",
                                 label, c, got, ge[c]);
                        tc_pass = 0;
                    end
                end
                if (tc_pass)
                    $display("PASS [%s]: all %0d outputs correct  (y[0]=%0d, y[1]=%0d, y[2]=%0d, y[3]=%0d)",
                             label, COLS, ge[0], ge[1], ge[2], ge[3]);
            end
        end
    endtask

    // ---------------------------------------------------------------- Stimulus
    integer r, c;

    initial begin
        $dumpfile("hardware/sim/tb_systolic_array.vcd");
        $dumpvars(0, tb_systolic_array);

        // Reset
        rst_n = 0; weight_load = 0; weights = 0; act_in = 0; valid_in = 0;
        #25; rst_n = 1;

        // ==============================================================
        // TC1 — positive integers
        //   W[r][c] = r*COLS + c + 1  (1 to 16, row-major)
        //   x = [1, 2, 3, 4]
        //   y = [90, 100, 110, 120]
        // ==============================================================
        for (r = 0; r < ROWS; r = r + 1)
            for (c = 0; c < COLS; c = c + 1)
                gw[r][c] = r*COLS + c + 1;
        gx[0]=1; gx[1]=2; gx[2]=3; gx[3]=4;
        load_weights;
        run_inference("TC1_pos_ints  ");

        // ==============================================================
        // TC2 — signed activations (same W)
        //   x = [-1, 2, -3, 4]
        //   y = [34, 36, 38, 40]
        // ==============================================================
        gx[0]=-1; gx[1]=2; gx[2]=-3; gx[3]=4;
        run_inference("TC2_signed_act");

        // ==============================================================
        // TC3 — zero activations  (y must be all zeros)
        // ==============================================================
        gx[0]=0; gx[1]=0; gx[2]=0; gx[3]=0;
        run_inference("TC3_zero_act  ");

        // ==============================================================
        // TC4 — identity weights
        //   W[r][c] = (r==c) ? 1 : 0
        //   x = [5, 7, 11, 13]  →  y = x
        // ==============================================================
        for (r = 0; r < ROWS; r = r + 1)
            for (c = 0; c < COLS; c = c + 1)
                gw[r][c] = (r == c) ? 1 : 0;
        gx[0]=5; gx[1]=7; gx[2]=11; gx[3]=13;
        load_weights;
        run_inference("TC4_identity_W");

        // ==============================================================
        // TC5 — back-to-back with same weights, different x
        //   x = [-8, 3, 0, 100]  →  y = x  (identity still loaded)
        // ==============================================================
        gx[0]=-8; gx[1]=3; gx[2]=0; gx[3]=100;
        run_inference("TC5_back2back ");

        // ==============================================================
        // TC6 — negative weights
        //   W[r][c] = -(r*COLS + c + 1)
        //   x = [1, 1, 1, 1]
        //   y[c] = -(4c + 28)  →  [-28, -32, -36, -40]
        // ==============================================================
        for (r = 0; r < ROWS; r = r + 1)
            for (c = 0; c < COLS; c = c + 1)
                gw[r][c] = -(r*COLS + c + 1);
        gx[0]=1; gx[1]=1; gx[2]=1; gx[3]=1;
        load_weights;
        run_inference("TC6_neg_weights");

        $display("Testbench complete.");
        $finish;
    end

endmodule
