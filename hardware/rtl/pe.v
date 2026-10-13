// Processing Element for weight-stationary systolic array — Phase 2 of IRIS.
// Each PE stores one weight and performs MAC with a broadcast activation.
//
// Architecture (weight-stationary, broadcast activation):
// - Weight register: loaded once via weight_load pulse
// - Activation input: broadcast directly from the top-level input (not propagated between rows)
// - Partial sum: accumulated from the row above, product added here, result passed to row below
// - valid_in propagates to valid_out via the mac_unit (1-cycle latency per PE)
//
// Dataflow in column (correct y = W*x computation):
//   Each row r fires one cycle after row r-1 (valid_in chain).
//   The top-level presents x[r] on the broadcast act_in at the cycle row r fires.
//   Partial sum from row r-1 arrives exactly when row r fires (pipeline naturally aligned).
//
//   Cycle 0: valid_in=1 → row 0 fires: psum = w[0][c]*x[0]
//   Cycle 1: row 0 valid_out=1 → row 1 fires: psum = w[0][c]*x[0] + w[1][c]*x[1]
//   Cycle r: psum at bottom = sum_{i=0}^{r} w[i][c]*x[i]
//   Cycle ROWS-1: final result = sum_{r} w[r][c]*x[r] = y[c]  ✓

module pe #(
    parameter DATA_WIDTH = 16,    // activation and weight width
    parameter ACC_WIDTH  = 32     // accumulator and partial sum width
)(
    input  wire                  clk,
    input  wire                  rst_n,        // active-low sync reset
    input  wire                  weight_load,  // pulse to load weight_reg
    input  wire [DATA_WIDTH-1:0] weight_in,    // weight value to load
    input  wire [DATA_WIDTH-1:0] act_in,       // activation input (broadcast from top level, NOT from row above)
    input  wire [ACC_WIDTH-1:0]  psum_in,      // partial sum input (from row above, or 0 at row 0)
    input  wire                  valid_in,     // input valid signal (from row above, or external at row 0)
    output wire [ACC_WIDTH-1:0]  psum_out,     // partial sum output (to row below or final result)
    output wire                  valid_out     // output valid signal (to row below)
);

    // Weight storage
    reg [DATA_WIDTH-1:0] weight_reg;

    // MAC unit instance
    wire [ACC_WIDTH-1:0] mac_out;
    wire                 mac_valid;

    mac_unit #(
        .DATA_WIDTH(DATA_WIDTH),
        .ACC_WIDTH(ACC_WIDTH)
    ) mac (
        .clk(clk),
        .rst_n(rst_n),
        .en(valid_in),       // MAC enabled when this row's turn arrives
        .a(weight_reg),      // stored weight
        .b(act_in),          // broadcast activation (x[r] at cycle r)
        .acc_in(psum_in),    // incoming partial sum from row above
        .acc_out(mac_out),
        .valid(mac_valid)
    );

    // Weight loading
    always @(posedge clk) begin
        if (!rst_n) begin
            weight_reg <= {DATA_WIDTH{1'b0}};
        end else if (weight_load) begin
            weight_reg <= weight_in;
        end
    end

    assign psum_out  = mac_out;
    assign valid_out = mac_valid;

endmodule
