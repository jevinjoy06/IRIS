## Basys 3 master constraints — Artix-7 XC7A35T
## Uncomment pins as modules are added.

# --- Clock ---
set_property PACKAGE_PIN W5      [get_ports clk]
set_property IOSTANDARD LVCMOS33 [get_ports clk]
create_clock -add -name sys_clk_pin -period 10.00 -waveform {0 5} [get_ports clk]

# --- Reset (BTNC, active-high on board; mac_unit uses active-low rst_n — invert in top) ---
set_property PACKAGE_PIN U18     [get_ports rst_btn]
set_property IOSTANDARD LVCMOS33 [get_ports rst_btn]

# --- UART (USB-to-serial, for IRIS wake trigger over UART) ---
# TX: FPGA → host
set_property PACKAGE_PIN A18     [get_ports uart_tx]
set_property IOSTANDARD LVCMOS33 [get_ports uart_tx]
# RX: host → FPGA (not needed for wake-trigger-only use)
#set_property PACKAGE_PIN B18    [get_ports uart_rx]
#set_property IOSTANDARD LVCMOS33 [get_ports uart_rx]

# --- 7-segment display (optional debug) ---
# Segments (active-low)
#set_property PACKAGE_PIN W7     [get_ports {seg[0]}]   # CA
#set_property PACKAGE_PIN W6     [get_ports {seg[1]}]   # CB
#set_property PACKAGE_PIN U8     [get_ports {seg[2]}]   # CC
#set_property PACKAGE_PIN V8     [get_ports {seg[3]}]   # CD
#set_property PACKAGE_PIN U5     [get_ports {seg[4]}]   # CE
#set_property PACKAGE_PIN V5     [get_ports {seg[5]}]   # CF
#set_property PACKAGE_PIN U7     [get_ports {seg[6]}]   # CG
# Anodes (active-low)
#set_property PACKAGE_PIN U2     [get_ports {an[0]}]
#set_property PACKAGE_PIN U4     [get_ports {an[1]}]
#set_property PACKAGE_PIN V4     [get_ports {an[2]}]
#set_property PACKAGE_PIN W4     [get_ports {an[3]}]
