// ReLU activation with saturation quantization — Phase 3 of IRIS.
//
// Computes: relu_out = clamp(acc_in, 0, 2^(OUT_WIDTH-1)-1)
//   - Negative inputs clamp to 0 (ReLU)
//   - Inputs above signed max of OUT_WIDTH saturate to that max
//   - Otherwise take the lower OUT_WIDTH bits
//
// Intended use: 32-bit ACC_WIDTH accumulator → 16-bit DATA_WIDTH activation
// between Layer 1 and Layer 2 of nn_2layer.

`default_nettype none

module relu #(
    parameter ACC_WIDTH = 32,   // input accumulator width (signed)
    parameter OUT_WIDTH = 16    // output activation width
)(
    input  wire [ACC_WIDTH-1:0] acc_in,
    output reg  [OUT_WIDTH-1:0] relu_out
);
    // Maximum positive value representable in OUT_WIDTH signed: 2^(OUT_WIDTH-1) - 1
    // For OUT_WIDTH=16: 32767 = 16'h7FFF
    localparam signed [ACC_WIDTH-1:0] SAT_MAX =
        {{(ACC_WIDTH - OUT_WIDTH + 1){1'b0}}, {(OUT_WIDTH-1){1'b1}}};

    always @(*) begin
        if ($signed(acc_in) <= 0)
            relu_out = {OUT_WIDTH{1'b0}};
        else if ($signed(acc_in) > SAT_MAX)
            relu_out = SAT_MAX[OUT_WIDTH-1:0];
        else
            relu_out = acc_in[OUT_WIDTH-1:0];
    end
endmodule

`default_nettype wire
