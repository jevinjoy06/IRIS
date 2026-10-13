`timescale 1ns / 1ps

// Testbench for nn_2layer — Phase 3 IRIS hardware accelerator.
//
// Tests the 2-layer FC network: logits = W2 * ReLU(W1 * x)
//
// TC1 — positive weights, unit activations
//   W1[r][c] = r*4+c+1  (1..16 row-major, 4x4)
//   x = [1, 1, 1, 1]
//   h_raw[c] = sum_r W1[r][c]*1 = (0+1+2+3)*4 + 4c + 4 = 28 + 4c
//           → h_raw = [28, 32, 36, 40]
//   After ReLU (all positive, all < 32767): hidden = [28, 32, 36, 40]
//   W2: 50 on diagonal for rows 0 and 1 only (4x2 matrix)
//     W2[0][0]=50, W2[1][1]=50, all others 0
//   logit[0] = 50*28 = 1400
//   logit[1] = 50*32 = 1600
//   argmax   = 1
//
// TC2 — signed activations (negative x values)
//   Same W1; x = [-1, -1, -1, -1]
//   h_raw[c] = -(28+4c)  → all negative → ReLU clips to 0
//   hidden = [0, 0, 0, 0]
//   logits  = [0, 0]
//   argmax  = 0 (tie → logit[1] not strictly greater)
//
// TC3 — negative weights with positive x
//   W1[r][c] = -(r*4+c+1)  (all negative)
//   x = [1, 1, 1, 1]
//   h_raw = [-28, -32, -36, -40] → ReLU → [0, 0, 0, 0]
//   logits = [0, 0], argmax = 0

module tb_nn_2layer;

    localparam IN_FEATURES = 4;
    localparam HIDDEN_SIZE = 4;
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

    // Golden-model storage
    integer gw1 [0:IN_FEATURES-1][0:HIDDEN_SIZE-1];
    integer gw2 [0:HIDDEN_SIZE-1][0:CLASSES-1];
    integer gx  [0:IN_FEATURES-1];

    integer pass_count;
    integer r, c, acc;

    // ----------------------------------------------------------------
    // Helper: pack weight arrays into flat buses
    // ----------------------------------------------------------------
    task pack_weights;
        integer pr, pc;
        begin
            for (pr = 0; pr < IN_FEATURES; pr = pr + 1)
                for (pc = 0; pc < HIDDEN_SIZE; pc = pc + 1)
                    weights_l1[(pr*HIDDEN_SIZE+pc)*DATA_WIDTH +: DATA_WIDTH] =
                        gw1[pr][pc][DATA_WIDTH-1:0];
            for (pr = 0; pr < HIDDEN_SIZE; pr = pr + 1)
                for (pc = 0; pc < CLASSES; pc = pc + 1)
                    weights_l2[(pr*CLASSES+pc)*DATA_WIDTH +: DATA_WIDTH] =
                        gw2[pr][pc][DATA_WIDTH-1:0];
        end
    endtask

    // ----------------------------------------------------------------
    // Helper: pack x vector into flat bus
    // ----------------------------------------------------------------
    task pack_x;
        integer px;
        begin
            for (px = 0; px < IN_FEATURES; px = px + 1)
                x_in[px*DATA_WIDTH +: DATA_WIDTH] = gx[px][DATA_WIDTH-1:0];
        end
    endtask

    // ----------------------------------------------------------------
    // Helper: run one inference and check against expected logits
    // ----------------------------------------------------------------
    task run_check;
        input [127:0]  label;
        input integer  exp_l0, exp_l1, exp_argmax;
        integer        got_l0, got_l1, got_argmax;
        integer        timeout;
        begin
            // Pulse start
            @(posedge clk); #1;
            start = 1;
            @(posedge clk); #1;
            start = 0;

            // Wait for valid_out (timeout after 100 cycles)
            timeout = 0;
            while (!valid_out && timeout < 100) begin
                @(posedge clk); #1;
                timeout = timeout + 1;
            end

            if (!valid_out) begin
                $display("FAIL [%s]: valid_out never asserted (timeout)", label);
            end else begin
                got_l0    = $signed(logits_out[0 +: ACC_WIDTH]);
                got_l1    = $signed(logits_out[ACC_WIDTH +: ACC_WIDTH]);
                got_argmax = argmax_class;

                if (got_l0 === exp_l0 && got_l1 === exp_l1 && got_argmax === exp_argmax) begin
                    $display("PASS [%s]: logits=[%0d,%0d] argmax=%0d",
                             label, got_l0, got_l1, got_argmax);
                    pass_count = pass_count + 1;
                end else begin
                    $display("FAIL [%s]: logits=[%0d,%0d] (exp [%0d,%0d])  argmax=%0d (exp %0d)",
                             label, got_l0, got_l1, exp_l0, exp_l1, got_argmax, exp_argmax);
                end
            end
        end
    endtask

    // ================================================================
    // Stimulus
    // ================================================================
    initial begin
        $dumpfile("hardware/sim/tb_nn_2layer.vcd");
        $dumpvars(0, tb_nn_2layer);

        pass_count  = 0;
        start       = 0;
        weights_l1  = 0;
        weights_l2  = 0;
        x_in        = 0;
        rst_n       = 0;
        #25; rst_n  = 1;

        // ==============================================================
        // TC1 — positive weights and activations
        //   W1[r][c] = r*4+c+1, x=[1,1,1,1]
        //   expected: logits=[1400,1600], argmax=1
        // ==============================================================
        for (r = 0; r < IN_FEATURES; r = r + 1)
            for (c = 0; c < HIDDEN_SIZE; c = c + 1)
                gw1[r][c] = r*HIDDEN_SIZE + c + 1;

        // W2: 50 on diagonal for rows 0 and 1
        for (r = 0; r < HIDDEN_SIZE; r = r + 1)
            for (c = 0; c < CLASSES; c = c + 1)
                gw2[r][c] = ((r < CLASSES) && (r == c)) ? 50 : 0;

        gx[0]=1; gx[1]=1; gx[2]=1; gx[3]=1;

        pack_weights;
        pack_x;

        run_check("TC1_basic      ", 1400, 1600, 1);

        // ==============================================================
        // TC2 — negative x: ReLU should zero all hidden units
        //   x=[-1,-1,-1,-1] → h_raw all negative → hidden=[0,0,0,0]
        //   logits=[0,0], argmax=0 (tie, logit[1] not strictly greater)
        // ==============================================================
        gx[0]=-1; gx[1]=-1; gx[2]=-1; gx[3]=-1;
        pack_x;

        run_check("TC2_relu_zero  ", 0, 0, 0);

        // ==============================================================
        // TC3 — negative weights: ReLU zeros all hidden units
        //   W1[r][c] = -(r*4+c+1), x=[1,1,1,1]
        //   h_raw all negative → hidden=[0,0,0,0] → logits=[0,0]
        // ==============================================================
        for (r = 0; r < IN_FEATURES; r = r + 1)
            for (c = 0; c < HIDDEN_SIZE; c = c + 1)
                gw1[r][c] = -(r*HIDDEN_SIZE + c + 1);
        gx[0]=1; gx[1]=1; gx[2]=1; gx[3]=1;
        pack_weights;
        pack_x;

        run_check("TC3_neg_weights", 0, 0, 0);

        // ==============================================================
        // TC4 — identity W1 and W2=1: logits = ReLU(x)
        //   W1=identity (4x4), W2[r][c]=(r==c)?1:0 for r<2
        //   x=[5,7,0,3]
        //   hidden = ReLU([5,7,0,3]) = [5,7,0,3]
        //   logit[0] = W2[0][0]*5 = 5
        //   logit[1] = W2[1][1]*7 = 7
        //   argmax = 1
        // ==============================================================
        for (r = 0; r < IN_FEATURES; r = r + 1)
            for (c = 0; c < HIDDEN_SIZE; c = c + 1)
                gw1[r][c] = (r == c) ? 1 : 0;
        for (r = 0; r < HIDDEN_SIZE; r = r + 1)
            for (c = 0; c < CLASSES; c = c + 1)
                gw2[r][c] = ((r < CLASSES) && (r == c)) ? 1 : 0;
        gx[0]=5; gx[1]=7; gx[2]=0; gx[3]=3;
        pack_weights;
        pack_x;

        run_check("TC4_identity   ", 5, 7, 1);

        $display("Testbench complete. %0d/4 passed.", pass_count);
        $finish;
    end

endmodule
