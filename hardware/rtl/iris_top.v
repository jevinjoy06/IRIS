// IRIS top-level module — wake-word detector with UART TX trigger
//
// Wraps the 2-layer neural network + UART transmitter.
// Detects wake word (class_out == 1) and sends 0x57 ('W') over UART.
// Lights LED[0] when wake is detected.
//
// Ports:
//   - clk: 100 MHz system clock
//   - rst_btn: active-high reset button (BTNC on Basys 3)
//   - act_in[0:IN_FEATURES-1]: feature inputs from audio front-end (stub for now)
//   - start: pulse high to begin inference
//   - uart_tx: serial output to USB-UART (pin A18)
//   - led_wake: LED[0] output (lights on wake detection)
//
// Parameters:
//   - DATA_WIDTH: width of weights/activations (default 16)
//   - IN_FEATURES: input vector length (default 4)
//   - HIDDEN_SIZE: hidden layer neurons (default 4)
//   - CLASSES: output classes (default 2)
//

`default_nettype none

module iris_top #(
    parameter DATA_WIDTH   = 16,
    parameter IN_FEATURES  = 40,
    parameter HIDDEN_SIZE  = 64,
    parameter CLASSES      = 2,
    parameter ACC_WIDTH    = 32,
    parameter WEIGHT_FILE_W1 = "rtl/weights/w1.mem",
    parameter WEIGHT_FILE_W2 = "rtl/weights/w2.mem"
)(
    input  wire clk,
    input  wire rst_btn,     // active-high button
    input  wire [(IN_FEATURES*DATA_WIDTH)-1:0] act_in,
    input  wire start,
    output wire uart_tx,
    output reg  led_wake
);

    // Invert reset button (active-high → active-low for internal logic)
    wire rst_n = ~rst_btn;

    // ------------------------------------------------------------------
    // Input features are already packed into act_in
    // ------------------------------------------------------------------
    wire [(IN_FEATURES*DATA_WIDTH)-1:0] x_in = act_in;

    // ------------------------------------------------------------------
    // Weight matrices loaded from memory files at initialization
    // ------------------------------------------------------------------
    reg signed [DATA_WIDTH-1:0] weights_l1_mem [0:IN_FEATURES*HIDDEN_SIZE-1];
    reg signed [DATA_WIDTH-1:0] weights_l2_mem [0:HIDDEN_SIZE*CLASSES-1];

    initial begin
        $readmemh(WEIGHT_FILE_W1, weights_l1_mem);
        $readmemh(WEIGHT_FILE_W2, weights_l2_mem);
    end

    // Flatten weight arrays into buses for systolic arrays.
    // Use always @(*) + integer loop rather than 2560-instance generate assigns.
    // The generate approach triggers O(N^2) events in iverilog when $readmemh
    // loads N elements (each element change re-evaluates all N pe_weight assigns).
    // The always @(*) block coalesces to a single O(N) evaluation per delta cycle.
    // Both forms synthesise identically (direct wires, no logic).
    reg [(IN_FEATURES*HIDDEN_SIZE*DATA_WIDTH)-1:0] weights_l1;
    reg [(HIDDEN_SIZE*CLASSES*DATA_WIDTH)-1:0]     weights_l2;

    integer wi, wj;
    always @(*) begin
        for (wi = 0; wi < IN_FEATURES * HIDDEN_SIZE; wi = wi + 1)
            weights_l1[wi*DATA_WIDTH +: DATA_WIDTH] = weights_l1_mem[wi];
    end
    always @(*) begin
        for (wj = 0; wj < HIDDEN_SIZE * CLASSES; wj = wj + 1)
            weights_l2[wj*DATA_WIDTH +: DATA_WIDTH] = weights_l2_mem[wj];
    end

    // ------------------------------------------------------------------
    // Neural network inference
    // ------------------------------------------------------------------
    wire [(CLASSES*ACC_WIDTH)-1:0] logits_out;
    wire [$clog2(CLASSES)-1:0]     class_out;
    wire                           valid_out;

    nn_2layer #(
        .IN_FEATURES(IN_FEATURES),
        .HIDDEN_SIZE(HIDDEN_SIZE),
        .CLASSES(CLASSES),
        .DATA_WIDTH(DATA_WIDTH),
        .ACC_WIDTH(ACC_WIDTH)
    ) nn_inst (
        .clk(clk),
        .rst_n(rst_n),
        .start(start),
        .weights_l1(weights_l1),
        .weights_l2(weights_l2),
        .x_in(x_in),
        .logits_out(logits_out),
        .argmax_class(class_out),
        .valid_out(valid_out)
    );

    // ------------------------------------------------------------------
    // Wake detection: valid_out && (class_out == 1)
    // ------------------------------------------------------------------
    wire wake = valid_out && (class_out == 1'b1);

    // Edge detector for wake signal (rising edge only)
    reg wake_r;
    wire wake_pulse = wake && !wake_r;

    always @(posedge clk) begin
        if (!rst_n) begin
            wake_r <= 1'b0;
        end else begin
            wake_r <= wake;
        end
    end

    // ------------------------------------------------------------------
    // UART TX: send 0x57 ('W') on wake detection
    // ------------------------------------------------------------------
    uart_tx #(
        .CLK_FREQ(100_000_000),
        .BAUD_RATE(115_200)
    ) uart_inst (
        .clk(clk),
        .rst_n(rst_n),
        .data_in(8'h57),    // 'W'
        .send(wake_pulse),
        .tx(uart_tx),
        .busy()             // unused
    );

    // ------------------------------------------------------------------
    // LED wake indicator: latch on detection, clear on reset
    // ------------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            led_wake <= 1'b0;
        end else if (wake_pulse) begin
            led_wake <= 1'b1;
        end
    end

endmodule

`default_nettype wire
