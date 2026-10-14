set vcd [open tb_systolic_array.vcd r]
# Just inspect the first part of the VCD
while {[gets $vcd line] >= 0} {
    puts $line
    if {[string match "*valid_out*" $line]} {
        # Found the signal definition
        break
    }
}
close $vcd
