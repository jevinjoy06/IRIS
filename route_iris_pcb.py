#!/usr/bin/env python3
"""
Script to route the IRIS microphone PMOD PCB.
Routes the 6 nets with simple straight-line paths.
"""

import sys
import os

# Add KiCad to path
sys.path.insert(0, 'C:/Program Files/KiCad/10.0/bin')
sys.path.insert(0, 'C:/Program Files/KiCad/10.0/lib/python3.11/site-packages')

import pcbnew

# Load the board
board_path = 'C:/Users/jevin/Documents/IRIS/hardware/pcb/iris_mic_pmod/iris_mic_pmod.kicad_pcb'
board = pcbnew.LoadBoard(board_path)

# Define the nets to route
nets = {
    'GND': {
        'pads': [('U1', 1), ('C1', 2), ('C2', 2), ('R1', 2), ('J1', 9), ('J1', 10)],
        'width': pcbnew.FromMM(0.5),
    },
    '+3V3': {
        'pads': [('U1', 3), ('C1', 1), ('C2', 1), ('J1', 11), ('J1', 12)],
        'width': pcbnew.FromMM(0.5),
    },
    'I2S_DATA': {
        'pads': [('U1', 5), ('J1', 1)],
        'width': pcbnew.FromMM(0.25),
    },
    'I2S_CLK': {
        'pads': [('U1', 2), ('J1', 3)],
        'width': pcbnew.FromMM(0.25),
    },
    'I2S_WS': {
        'pads': [('U1', 6), ('J1', 5)],
        'width': pcbnew.FromMM(0.25),
    },
    'L_R': {
        'pads': [('U1', 4), ('R1', 1)],
        'width': pcbnew.FromMM(0.25),
    },
}

# Get the front copper layer
front_layer = pcbnew.F_Cu

print("Processing nets...")
for net_name, net_data in nets.items():
    print(f"  Routing net: {net_name}")
    
    # Get the net object
    net = board.FindNet(net_name)
    if not net:
        print(f"    ERROR: Net '{net_name}' not found!")
        continue
    
    net_code = net.GetNetCode()
    
    # Get pad coordinates
    pads = []
    for ref, pad_num in net_data['pads']:
        footprint = board.FindFootprintByReference(ref)
        if not footprint:
            print(f"    ERROR: Footprint {ref} not found!")
            continue
        
        pad = footprint.FindPadByNumber(str(pad_num))
        if not pad:
            print(f"    ERROR: Pad {ref}/{pad_num} not found!")
            continue
        
        pads.append((ref, pad_num, pad.GetPosition()))
    
    if len(pads) < 2:
        print(f"    WARNING: Net {net_name} has fewer than 2 pads, skipping")
        continue
    
    # Create simple star routing from first pad to all others
    first_pad = pads[0]
    first_x, first_y = first_pad[2].x, first_pad[2].y
    
    for i in range(1, len(pads)):
        curr_pad = pads[i]
        curr_x, curr_y = curr_pad[2].x, curr_pad[2].y
        
        # Create a track segment
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I(int(first_x), int(first_y)))
        track.SetEnd(pcbnew.VECTOR2I(int(curr_x), int(curr_y)))
        track.SetWidth(int(net_data['width']))
        track.SetLayer(front_layer)
        track.SetNet(net_code)
        
        board.Add(track)
        print(f"    Added track: {first_pad[0]}/{first_pad[1]} -> {curr_pad[0]}/{curr_pad[1]}")

# Save the board
print(f"\nSaving board to {board_path}...")
board.Save(board_path)
print("Done!")
