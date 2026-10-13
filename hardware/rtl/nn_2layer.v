// 2-layer fully-connected neural network — Phase 3 of IRIS.
//
// Architecture:
//   Layer 1: IN_FEATURES → HIDDEN_SIZE  (systolic array, ReLU activation)
//   Layer 2: HIDDEN_SIZE → CLASSES      (systolic array, raw logits out)
//
// Computation: logits = W2 * ReLU(W1 * x)
//
// Interface:
//   - Assert start=1 for one cycle to begin inference.
//   - Hold weights_l1, weights_l2, x_in stable throughout inference.
//   - valid_out pulses high for one cycle when logits_out and argmax_class are ready.
//
// Weight bus layout (row-major, same as systolic_array):
//   weights_l1[(r*HIDDEN_SIZE + c)*DATA_WIDTH +: DATA_WIDTH] = W1[r][c]
//   weights_l2[(r*CLASSES     + c)*DATA_WIDTH +: DATA_WIDTH] = W2[r][c]
//
// x_in layout:
//   x_in[r*DATA_WIDTH +: DATA_WIDTH] = x[r]
//
// FSM states and timing (default 4-4-2, 100 MHz):
//   IDLE       → L1_LOAD (1 cy) → L1_STREAM (IN_FEATURES cy)
//             → L1_DRAIN (≤2 cy, exits on l1_valid_out)
//             → L2_LOAD (1 cy) → L2_STREAM (HIDDEN_SIZE cy)
//             → L2_DRAIN (≤2 cy, exits on l2_valid_out)
//             → OUTPUT (1 cy) → IDLE
//   Total ≈ 15 cycles from start pulse to valid_out.

`default_nettype none

module nn_2layer #(
    parameter IN_FEATURES = 4,    // input vector length
    parameter HIDDEN_SIZE = 4,    // hidden layer neurons
    parameter CLASSES     = 2,    // output classes
    parameter DATA_WIDTH  = 16,   // signed weight/activation width
    parameter ACC_WIDTH   = 32    // accumulator width
)(
    input  wire clk,
    input  wire rst_n,   // active-low synchronous reset
    input  wire start,   // pulse high for one cycle to begin inference

    // Weight matrices (held stable while inference is running)
    input  wire [(IN_FEATURES*HIDDEN_SIZE*DATA_WIDTH)-1:0] weights_l1,
    input  wire [(HIDDEN_SIZE*CLASSES*DATA_WIDTH)-1:0]     weights_l2,

    // Input vector (held stable while inference is running)
    input  wire [(IN_FEATURES*DATA_WIDTH)-1:0] x_in,

    // Outputs (valid when valid_out=1)
    output wire [(CLASSES*ACC_WIDTH)-1:0]  logits_out,
    output wire [$clog2(CLASSES)-1:0]      argmax_class,
    output reg                             valid_out
);

    // ------------------------------------------------------------------
    // FSM state encoding
    // ------------------------------------------------------------------
    localparam [2:0]
        IDLE      = 3'd0,
        L1_LOAD   = 3'd1,
        L1_STREAM = 3'd2,
        L1_DRAIN  = 3'd3,
        L2_LOAD   = 3'd4,
        L2_STREAM = 3'd5,
        L2_DRAIN  = 3'd6,
        OUTPUT    = 3'd7;

    reg [2:0] state;
    reg [7:0] counter;  // 8-bit: supports IN_FEATURES/HIDDEN_SIZE up to 255

    // ------------------------------------------------------------------
    // Layer 1 systolic array  (IN_FEATURES × HIDDEN_SIZE)
    // ------------------------------------------------------------------
    reg                   l1_weight_load;
    reg  [DATA_WIDTH-1:0] l1_act_in;
    reg                   l1_valid_in;
    wire [(HIDDEN_SIZE*ACC_WIDTH)-1:0] l1_result;
    wire                  l1_valid_out;

    systolic_array #(
        .ROWS      (IN_FEATURES),
        .COLS      (HIDDEN_SIZE),
        .DATA_WIDTH(DATA_WIDTH),
        .ACC_WIDTH (ACC_WIDTH)
    ) l1_sa (
        .clk        (clk),
        .rst_n      (rst_n),
        .weight_load(l1_weight_load),
        .weights    (weights_l1),
        .act_in     (l1_act_in),
        .valid_in   (l1_valid_in),
        .result     (l1_result),
        .valid_out  (l1_valid_out)
    );

    // ------------------------------------------------------------------
    // ReLU + saturation between Layer 1 and Layer 2
    // ------------------------------------------------------------------
    wire [(HIDDEN_SIZE*DATA_WIDTH)-1:0] hidden_relu;

    genvar h;
    generate
        for (h = 0; h < HIDDEN_SIZE; h = h + 1) begin : gen_hidden_relu
            relu #(
                .ACC_WIDTH(ACC_WIDTH),
                .OUT_WIDTH(DATA_WIDTH)
            ) relu_inst (
                .acc_in  (l1_result[h*ACC_WIDTH +: ACC_WIDTH]),
                .relu_out(hidden_relu[h*DATA_WIDTH +: DATA_WIDTH])
            );
        end
    endgenerate

    // Registered hidden layer (captures hidden_relu when l1_valid_out fires)
    reg [(HIDDEN_SIZE*DATA_WIDTH)-1:0] hidden_reg;

    // ------------------------------------------------------------------
    // Layer 2 systolic array  (HIDDEN_SIZE × CLASSES)
    // ------------------------------------------------------------------
    reg                   l2_weight_load;
    reg  [DATA_WIDTH-1:0] l2_act_in;
    reg                   l2_valid_in;
    wire [(CLASSES*ACC_WIDTH)-1:0] l2_result;
    wire                  l2_valid_out;

    systolic_array #(
        .ROWS      (HIDDEN_SIZE),
        .COLS      (CLASSES),
        .DATA_WIDTH(DATA_WIDTH),
        .ACC_WIDTH (ACC_WIDTH)
    ) l2_sa (
        .clk        (clk),
        .rst_n      (rst_n),
        .weight_load(l2_weight_load),
        .weights    (weights_l2),
        .act_in     (l2_act_in),
        .valid_in   (l2_valid_in),
        .result     (l2_result),
        .valid_out  (l2_valid_out)
    );

    // ------------------------------------------------------------------
    // Output registers and combinational outputs
    // ------------------------------------------------------------------
    reg [(CLASSES*ACC_WIDTH)-1:0] logits_reg;
    assign logits_out = logits_reg;

    // Argmax: combinational comparison of the two logits (CLASSES=2)
    assign argmax_class = ($signed(logits_reg[ACC_WIDTH +: ACC_WIDTH]) >
                           $signed(logits_reg[0       +: ACC_WIDTH])) ? 1'b1 : 1'b0;

    // ------------------------------------------------------------------
    // FSM
    // ------------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            state          <= IDLE;
            counter        <= 8'd0;
            valid_out      <= 1'b0;
            l1_weight_load <= 1'b0;
            l1_valid_in    <= 1'b0;
            l1_act_in      <= {DATA_WIDTH{1'b0}};
            l2_weight_load <= 1'b0;
            l2_valid_in    <= 1'b0;
            l2_act_in      <= {DATA_WIDTH{1'b0}};
            hidden_reg     <= {(HIDDEN_SIZE*DATA_WIDTH){1'b0}};
            logits_reg     <= {(CLASSES*ACC_WIDTH){1'b0}};
        end else begin
            // Default: deassert all one-cycle pulses
            l1_weight_load <= 1'b0;
            l1_valid_in    <= 1'b0;
            l2_weight_load <= 1'b0;
            l2_valid_in    <= 1'b0;
            valid_out      <= 1'b0;

            case (state)
                // -------------------------------------------------------
                IDLE: begin
                    if (start)
                        state <= L1_LOAD;
                end

                // -------------------------------------------------------
                // Pulse weight_load; weights are latched by systolic array
                // on the following posedge (first cycle of L1_STREAM).
                // -------------------------------------------------------
                L1_LOAD: begin
                    l1_weight_load <= 1'b1;
                    counter        <= 8'd0;
                    state          <= L1_STREAM;
                end

                // -------------------------------------------------------
                // Stream x[0..IN_FEATURES-1] one element per cycle.
                // valid_in is asserted only at counter=0 (single pulse);
                // the valid chain in the systolic array propagates it.
                // At counter r: act_in = x[r], fires row r one cycle later.
                // -------------------------------------------------------
                L1_STREAM: begin
                    l1_act_in  <= x_in[counter*DATA_WIDTH +: DATA_WIDTH];
                    l1_valid_in <= (counter == 8'd0) ? 1'b1 : 1'b0;
                    if (counter == IN_FEATURES - 1) begin
                        state <= L1_DRAIN;
                    end else begin
                        counter <= counter + 8'd1;
                    end
                end

                // -------------------------------------------------------
                // Wait for l1_valid_out (fires ~2 cycles after last stream
                // cycle). Capture post-ReLU hidden values into hidden_reg.
                // -------------------------------------------------------
                L1_DRAIN: begin
                    if (l1_valid_out) begin
                        hidden_reg <= hidden_relu;
                        state      <= L2_LOAD;
                    end
                end

                // -------------------------------------------------------
                L2_LOAD: begin
                    l2_weight_load <= 1'b1;
                    counter        <= 8'd0;
                    state          <= L2_STREAM;
                end

                // -------------------------------------------------------
                // Stream hidden[0..HIDDEN_SIZE-1] from the registered values.
                // -------------------------------------------------------
                L2_STREAM: begin
                    l2_act_in  <= hidden_reg[counter*DATA_WIDTH +: DATA_WIDTH];
                    l2_valid_in <= (counter == 8'd0) ? 1'b1 : 1'b0;
                    if (counter == HIDDEN_SIZE - 1) begin
                        state <= L2_DRAIN;
                    end else begin
                        counter <= counter + 8'd1;
                    end
                end

                // -------------------------------------------------------
                L2_DRAIN: begin
                    if (l2_valid_out) begin
                        logits_reg <= l2_result;
                        state      <= OUTPUT;
                    end
                end

                // -------------------------------------------------------
                OUTPUT: begin
                    valid_out <= 1'b1;
                    state     <= IDLE;
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule

`default_nettype wire
