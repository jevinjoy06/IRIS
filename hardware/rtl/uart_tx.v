// UART TX module — 8N1 serial transmitter
//
// Clock: parameterized frequency (default 100 MHz)
// Baud: parameterized rate (default 115200)
// Divider: CLK_FREQ / BAUD_RATE (e.g., 100_000_000 / 115_200 ≈ 868 cycles per bit)
//
// Interface:
//   - clk: input clock
//   - rst_n: active-low reset
//   - send: pulse high for 1 cycle to initiate transmission
//   - data_in[7:0]: byte to transmit (held stable during transmission)
//   - tx: serial output (idle=1, start bit=0, data LSB first, stop=1)
//   - busy: high while transmitting (10 bits: 1 start + 8 data + 1 stop)
//
// FSM: IDLE → START → DATA (shift out 8 bits) → STOP → IDLE
// Timing: one bit period per 868 clk cycles (at 100 MHz / 115200 baud)
//

`default_nettype none

module uart_tx #(
    parameter CLK_FREQ = 100_000_000,
    parameter BAUD_RATE = 115_200
)(
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] data_in,
    input  wire       send,
    output reg        tx,
    output reg        busy
);

    // Calculate clock divider for the baud rate
    localparam CLK_DIV = CLK_FREQ / BAUD_RATE;
    localparam CLK_DIV_WIDTH = $clog2(CLK_DIV);

    // FSM states
    localparam [2:0]
        IDLE  = 3'd0,
        START = 3'd1,
        DATA  = 3'd2,
        STOP  = 3'd3;

    reg [2:0] state;
    reg [CLK_DIV_WIDTH-1:0] clk_div_counter;
    reg [3:0] bit_counter;     // counts 0..7 for data bits
    reg [7:0] data_reg;        // holds data during transmission

    wire clk_div_done = (clk_div_counter == CLK_DIV - 1);

    always @(posedge clk) begin
        if (!rst_n) begin
            state            <= IDLE;
            clk_div_counter  <= {CLK_DIV_WIDTH{1'b0}};
            bit_counter      <= 4'd0;
            data_reg         <= 8'd0;
            tx               <= 1'b1;  // idle high
            busy             <= 1'b0;
        end else begin
            case (state)
                // --------- IDLE ---------
                // Wait for send pulse. When asserted, load data and go to START.
                IDLE: begin
                    tx <= 1'b1;
                    if (send) begin
                        data_reg          <= data_in;
                        clk_div_counter   <= {CLK_DIV_WIDTH{1'b0}};
                        state             <= START;
                        busy              <= 1'b1;
                    end
                end

                // --------- START ---------
                // Transmit start bit (tx=0) for one bit period.
                // Count down clock divider; when done, move to DATA.
                START: begin
                    tx <= 1'b0;  // start bit = low
                    if (clk_div_done) begin
                        clk_div_counter <= {CLK_DIV_WIDTH{1'b0}};
                        bit_counter     <= 4'd0;
                        state           <= DATA;
                    end else begin
                        clk_div_counter <= clk_div_counter + 1;
                    end
                end

                // --------- DATA ---------
                // Transmit 8 data bits, LSB first.
                // Shift out one bit per bit period.
                DATA: begin
                    tx <= data_reg[0];  // LSB first
                    if (clk_div_done) begin
                        clk_div_counter <= {CLK_DIV_WIDTH{1'b0}};
                        if (bit_counter == 3'd7) begin
                            // All 8 bits sent; move to STOP
                            state <= STOP;
                        end else begin
                            data_reg    <= {1'b0, data_reg[7:1]};  // shift right
                            bit_counter <= bit_counter + 1;
                        end
                    end else begin
                        clk_div_counter <= clk_div_counter + 1;
                    end
                end

                // --------- STOP ---------
                // Transmit stop bit (tx=1) for one bit period.
                // Then return to IDLE.
                STOP: begin
                    tx <= 1'b1;  // stop bit = high
                    if (clk_div_done) begin
                        clk_div_counter <= {CLK_DIV_WIDTH{1'b0}};
                        state           <= IDLE;
                        busy            <= 1'b0;
                    end else begin
                        clk_div_counter <= clk_div_counter + 1;
                    end
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule

`default_nettype wire
