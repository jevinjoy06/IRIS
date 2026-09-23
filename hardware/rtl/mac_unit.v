// Multiply-accumulate unit — Phase 1 of the IRIS wake-word accelerator.
// Parameterized width; fixed-point format is TBD (see open questions in iris-project.md).
// Targets Artix-7 DSP48E1 slices on the Basys 3.

module mac_unit #(
    parameter DATA_WIDTH = 16,   // input operand width
    parameter ACC_WIDTH  = 32    // accumulator width (must be >= 2*DATA_WIDTH)
)(
    input  wire                  clk,
    input  wire                  rst_n,  // active-low sync reset
    input  wire                  en,
    input  wire [DATA_WIDTH-1:0] a,
    input  wire [DATA_WIDTH-1:0] b,
    input  wire [ACC_WIDTH-1:0]  acc_in,
    output reg  [ACC_WIDTH-1:0]  acc_out,
    output reg                   valid
);
    wire [2*DATA_WIDTH-1:0] product;
    assign product = a * b;

    always @(posedge clk) begin
        if (!rst_n) begin
            acc_out <= {ACC_WIDTH{1'b0}};
            valid   <= 1'b0;
        end else if (en) begin
            acc_out <= acc_in + {{(ACC_WIDTH - 2*DATA_WIDTH){product[2*DATA_WIDTH-1]}}, product};
            valid   <= 1'b1;
        end else begin
            valid <= 1'b0;
        end
    end
endmodule
