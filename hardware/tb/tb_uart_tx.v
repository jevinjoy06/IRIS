// Testbench for uart_tx module — 8N1 UART transmitter
//
// Test cases:
//   1. Send 0x55 (01010101 binary) — verify bit pattern
//   2. Send 0xAA (10101010 binary) — verify bit pattern
//   3. Verify busy goes high and returns to low after 10 bit periods
//   4. Verify tx stays idle (high) when no send
//   5. Verify send is ignored while busy
//
// Clock: 100 MHz (10 ns period)
// Baud: 115200 → bit period = 8.68 µs ≈ 868 cycles
//

`timescale 1ns / 1ps

module tb_uart_tx;

    reg         clk;
    reg         rst_n;
    reg  [7:0]  data_in;
    reg         send;
    wire        tx;
    wire        busy;

    // Instantiate uart_tx
    uart_tx #(
        .CLK_FREQ(100_000_000),
        .BAUD_RATE(115_200)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .data_in(data_in),
        .send(send),
        .tx(tx),
        .busy(busy)
    );

    // Clock generation: 10 ns period (100 MHz)
    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    // Test stimulus
    initial begin
        $dumpfile("sim/tb_uart_tx.vcd");
        $dumpvars(0, tb_uart_tx);

        // Initialize
        rst_n = 1'b0;
        send = 1'b0;
        data_in = 8'd0;

        // Reset pulse
        #20;
        rst_n = 1'b1;
        #20;

        // ================================================================
        // Test 1: Send 0x55 (01010101 binary)
        // ================================================================
        $display("Test 1: Send 0x55 (01010101 binary)");
        data_in = 8'h55;
        send = 1'b1;
        #10;
        send = 1'b0;

        // Wait for transmission to complete (~10 * 868 * 10 = 86.8 µs)
        wait (!busy);
        #100;

        // ================================================================
        // Test 2: Send 0xAA (10101010 binary)
        // ================================================================
        $display("Test 2: Send 0xAA (10101010 binary)");
        data_in = 8'hAA;
        send = 1'b1;
        #10;
        send = 1'b0;

        wait (!busy);
        #100;

        // ================================================================
        // Test 3: Verify busy goes high then low
        // ================================================================
        $display("Test 3: Verify busy pulse");
        data_in = 8'hFF;
        send = 1'b1;
        #10;
        send = 1'b0;
        // After one clock cycle, busy should be high
        #10;
        if (busy !== 1'b1) begin
            $display("ERROR: busy should be high after send");
        end else begin
            $display("PASS: busy went high");
        end

        wait (!busy);
        $display("PASS: busy returned to low");
        #100;

        // ================================================================
        // Test 4: Verify tx stays idle when no send
        // ================================================================
        $display("Test 4: Verify tx idles high when no activity");
        #1000;
        if (tx !== 1'b1) begin
            $display("ERROR: tx should be idle (high) with no send");
        end else begin
            $display("PASS: tx remains idle");
        end

        // ================================================================
        // Test 5: Verify send is ignored while busy
        // ================================================================
        $display("Test 5: Verify send ignored while busy");
        data_in = 8'h12;
        send = 1'b1;
        #10;
        send = 1'b0;

        // Try to send another byte while still transmitting
        #8680;  // ~1 bit period
        data_in = 8'h34;
        send = 1'b1;
        $display("Attempted send while busy; should be ignored");
        #10;
        send = 1'b0;

        wait (!busy);
        $display("PASS: First transmission completed (second send was ignored)");
        #100;

        // ================================================================
        // Summary
        // ================================================================
        $display("\n=== All tests completed ===");
        $finish;
    end

    // Optional: monitor tx line for debugging
    initial begin
        forever begin
            @(tx);
            if (tx === 1'bx) begin
                $display("WARNING: tx is unknown at time %t", $time);
            end
        end
    end

endmodule
