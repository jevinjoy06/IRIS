// Weight-stationary systolic array for matrix-vector multiplication — Phase 2 of IRIS.
//
// Computation: result[c] = sum_{r=0}^{ROWS-1} w[r][c] * x[r]   (y = W*x)
//
// Architecture:
//   - COLS independent columns, each producing one output neuron y[c]
//   - ROWS PEs chained top-to-bottom within each column
//   - Activations are BROADCAST from the single act_in port to ALL rows of ALL columns
//   - valid_in fires row 0; valid propagates down the chain (each row fires one cycle later)
//   - Partial sums accumulate top-to-bottom within each column
//   - Output appears at the bottom row after ROWS cycles
//
// Timing (ROWS=4 example):
//   Cycle 0: Assert valid_in=1 for ONE cycle. Present x[0] on act_in.
//             Row 0 of every column fires: psum = w[0][c]*x[0]
//   Cycle 1: Present x[1] on act_in.
//             Row 0 valid_out=1 → Row 1 fires: psum = w[0][c]*x[0] + w[1][c]*x[1]
//   Cycle 2: Present x[2]. Row 2 fires. Psum grows.
//   Cycle 3: Present x[3]. Row 3 fires. Bottom row psum = sum_r w[r][c]*x[r]
//   Cycle 4: valid_out asserted, result[c] = y[c] for all c.
//
// User protocol:
//   1. Assert weight_load for one cycle with flat weights bus populated.
//   2. Present x[0] on act_in, assert valid_in for ONE cycle.
//   3. On each following cycle r=1..ROWS-1: present x[r] on act_in (valid_in = 0).
//   4. Read result[] when valid_out is asserted (ROWS+1 cycles after step 2).
//
// Weight bus layout (row-major):
//   weights[ (r*COLS + c)*DATA_WIDTH +: DATA_WIDTH ] = w[r][c]

`default_nettype none

module systolic_array #(
    parameter ROWS       = 4,   // dot-product length (number of input features per output)
    parameter COLS       = 4,   // number of parallel outputs (output neurons)
    parameter DATA_WIDTH = 16,  // activation and weight width (signed)
    parameter ACC_WIDTH  = 32   // partial sum and result width
)(
    input  wire                              clk,
    input  wire                              rst_n,        // active-low sync reset
    // Weight loading (one pulse loads all PEs simultaneously)
    input  wire                              weight_load,  // assert for one cycle
    input  wire [(ROWS*COLS*DATA_WIDTH)-1:0] weights,      // all weights, row-major
    // Computation
    input  wire [DATA_WIDTH-1:0]             act_in,       // broadcast activation x[r], presented each cycle
    input  wire                              valid_in,     // pulse once at cycle 0 to start the chain
    // Outputs
    output wire [(COLS*ACC_WIDTH)-1:0]       result,       // y[c] for each column, row-major
    output wire                              valid_out     // high for one cycle when result is ready
);

    // Internal wires: psum and valid between rows
    // psum_w[r][c]  = psum_out of PE[r][c]
    // valid_w[r][c] = valid_out of PE[r][c]
    wire [ACC_WIDTH-1:0]  psum_w  [0:ROWS-1][0:COLS-1];
    wire                  valid_w [0:ROWS-1][0:COLS-1];

    genvar r, c;
    generate
        for (r = 0; r < ROWS; r = r + 1) begin : gen_rows
            for (c = 0; c < COLS; c = c + 1) begin : gen_cols

                // Weight for PE[r][c] — row-major index
                wire [DATA_WIDTH-1:0] pe_weight;
                assign pe_weight = weights[(r*COLS + c)*DATA_WIDTH +: DATA_WIDTH];

                // psum_in: 0 at top row, previous row's psum_out elsewhere
                wire [ACC_WIDTH-1:0] psum_in_w;
                if (r == 0) begin : psum_seed
                    assign psum_in_w = {ACC_WIDTH{1'b0}};
                end else begin : psum_chain
                    assign psum_in_w = psum_w[r-1][c];
                end

                // valid_in: external at top row, previous row's valid_out otherwise
                wire valid_in_w;
                if (r == 0) begin : valid_seed
                    assign valid_in_w = valid_in;
                end else begin : valid_chain
                    assign valid_in_w = valid_w[r-1][c];
                end

                pe #(
                    .DATA_WIDTH(DATA_WIDTH),
                    .ACC_WIDTH (ACC_WIDTH)
                ) pe_inst (
                    .clk        (clk),
                    .rst_n      (rst_n),
                    .weight_load(weight_load),
                    .weight_in  (pe_weight),
                    .act_in     (act_in),       // broadcast: same value to every PE
                    .psum_in    (psum_in_w),
                    .valid_in   (valid_in_w),
                    .psum_out   (psum_w[r][c]),
                    .valid_out  (valid_w[r][c])
                );
            end
        end
    endgenerate

    // Result and valid come from the bottom row
    generate
        for (c = 0; c < COLS; c = c + 1) begin : gen_result
            assign result[c*ACC_WIDTH +: ACC_WIDTH] = psum_w[ROWS-1][c];
        end
    endgenerate

    // valid_out: all bottom-row columns fire simultaneously, use column 0 as representative
    assign valid_out = valid_w[ROWS-1][0];

endmodule

`default_nettype wire
