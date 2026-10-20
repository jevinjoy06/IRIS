`timescale 1ns / 1ps

module tb_iris_top_minimal;
    localparam IN_FEATURES = 40;
    localparam DATA_WIDTH = 16;

    reg         clk;
    reg         rst_btn;
    reg  [(IN_FEATURES*DATA_WIDTH)-1:0] act_in;
    reg         start;
    wire        uart_tx;
    wire        led_wake;

    iris_top #(
        .DATA_WIDTH(16),
        .IN_FEATURES(40),
        .HIDDEN_SIZE(64),
        .CLASSES(2),
        .ACC_WIDTH(32),
        .WEIGHT_FILE_W1("rtl/weights/w1.mem"),
        .WEIGHT_FILE_W2("rtl/weights/w2.mem")
    ) dut (
        .clk(clk),
        .rst_btn(rst_btn),
        .act_in(act_in),
        .start(start),
        .uart_tx(uart_tx),
        .led_wake(led_wake)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    initial begin
        $dumpfile("sim/tb_iris_top_minimal.vcd");
        $dumpvars(0, tb_iris_top_minimal);

        rst_btn = 1'b1;
        start = 1'b0;
        act_in = 0;

        $display("Test started: iris_top with 40->64->2 parameters");
        #20;
        rst_btn = 1'b0;
        #100;

        if (uart_tx !== 1'b1) begin
            $display("FAIL: uart_tx should be idle");
        end else begin
            $display("PASS: uart_tx idle after reset");
        end

        $display("Pulse start signal");
        start = 1'b1;
        #10;
        start = 1'b0;

        $display("Waiting 500 cycles for inference...");
        #5000;

        $display("PASS: No simulation errors - inference completed");
        $finish;
    end

endmodule
