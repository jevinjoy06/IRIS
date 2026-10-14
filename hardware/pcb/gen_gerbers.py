#!/usr/bin/env python3
"""
Generate Gerber manufacturing files and BOM from IRIS mic PMOD PCB.

Uses KiCad 10.0 pcbnew API to:
1. Load the KiCad PCB file
2. Generate Gerber files for all manufacturing layers
3. Generate drill files (PTH and NPTH)
4. Generate BOM CSV

Output directory: hardware/pcb/iris_mic_pmod/gerbers/
"""

import sys
import os
import csv
from pathlib import Path
from collections import defaultdict

# Add KiCad 10.0 to path
KICAD_PATH = "C:/Program Files/KiCad/10.0"
KICAD_BIN = os.path.join(KICAD_PATH, "bin")
KICAD_PYTHON = os.path.join(KICAD_PATH, "lib/python3.11/site-packages")

if KICAD_BIN not in sys.path:
    sys.path.insert(0, KICAD_BIN)
if KICAD_PYTHON not in sys.path:
    sys.path.insert(0, KICAD_PYTHON)

try:
    import pcbnew
except ImportError as e:
    print(f"ERROR: Failed to import pcbnew. Ensure KiCad 10.0 is installed.")
    print(f"Attempted paths: {KICAD_BIN}, {KICAD_PYTHON}")
    sys.exit(1)


def main():
    # Paths
    script_dir = Path(__file__).parent
    pcb_dir = script_dir / "iris_mic_pmod"
    pcb_file = pcb_dir / "iris_mic_pmod.kicad_pcb"
    gerber_dir = pcb_dir / "gerbers"
    bom_file = pcb_dir / "bom.csv"

    # Validate PCB file exists
    if not pcb_file.exists():
        print(f"ERROR: PCB file not found: {pcb_file}")
        sys.exit(1)

    print(f"Loading PCB: {pcb_file}")
    board = pcbnew.LoadBoard(str(pcb_file))
    if board is None:
        print(f"ERROR: Failed to load board from {pcb_file}")
        sys.exit(1)

    # Create output directory
    gerber_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {gerber_dir}")

    # Track created files
    created_files = []

    # ========== GERBER FILE GENERATION ==========
    print("\n--- Generating Gerber Files ---")

    try:
        controller = pcbnew.PLOT_CONTROLLER(board)

        # Configure plot options
        options = controller.GetPlotOptions()
        options.SetOutputDirectory(str(gerber_dir))
        options.SetUseGerberProtelExtensions(True)
        options.SetUseGerberAttributes(True)
        options.SetCreateGerberJobFile(True)
        options.SetPlotFrameRef(False)
        options.SetMirror(False)
        options.SetDrillMarksType(pcbnew.DRILL_MARKS_NO_DRILL_SHAPE)

        # Define layers to plot
        layers = [
            (pcbnew.F_Cu, "F.Cu"),
            (pcbnew.B_Cu, "B.Cu"),
            (pcbnew.F_SilkS, "F.SilkS"),
            (pcbnew.B_SilkS, "B.SilkS"),
            (pcbnew.F_Mask, "F.Mask"),
            (pcbnew.B_Mask, "B.Mask"),
            (pcbnew.Edge_Cuts, "Edge.Cuts"),
        ]

        for layer_id, layer_name in layers:
            controller.SetLayer(layer_id)
            try:
                controller.OpenPlotfile(layer_name, pcbnew.PLOT_FORMAT_GERBER)
                controller.PlotLayer()
                controller.ClosePlot()
                # Actual filename uses Protel extension based on layer
                filename = controller.GetPlotFileName()
                filepath = Path(filename)
                created_files.append(filepath)
                print(f"  ✓ {layer_name:12} -> {filepath.name}")
            except Exception as e:
                print(f"  ✗ {layer_name:12} -> ERROR: {e}")
                controller.ClosePlot()

    except Exception as e:
        print(f"ERROR during Gerber generation: {e}")
        sys.exit(1)

    # ========== DRILL FILE GENERATION ==========
    print("\n--- Generating Drill Files ---")

    try:
        # Create EXCELLON writer for PTH (plated through-holes)
        writer = pcbnew.EXCELLON_WRITER(board)
        writer.SetOptions(False, False, pcbnew.VECTOR2I(0, 0), False)  # mirror, minHeader, offset, mergeNPTH
        writer.CreateDrillandMapFilesSet(str(gerber_dir), True, False)
        pth_file = gerber_dir / "iris_mic_pmod-PTH.drl"
        npth_file = gerber_dir / "iris_mic_pmod-NPTH.drl"
        created_files.append(pth_file)
        created_files.append(npth_file)
        print(f"  ✓ PTH Drill     -> iris_mic_pmod-PTH.drl")
        print(f"  ✓ NPTH Drill    -> iris_mic_pmod-NPTH.drl")

    except Exception as e:
        print(f"ERROR during drill file generation: {e}")
        sys.exit(1)

    # ========== BOM GENERATION ==========
    print("\n--- Generating Bill of Materials ---")

    try:
        bom_data = generate_bom(board)
        write_bom_csv(bom_file, bom_data)
        created_files.append(bom_file)
        print(f"  ✓ BOM            -> bom.csv ({len(bom_data)} unique components)")

    except Exception as e:
        print(f"ERROR during BOM generation: {e}")
        sys.exit(1)

    # ========== SUMMARY ==========
    print("\n--- Summary ---")
    print(f"Total files created: {len(created_files)}")
    for fpath in sorted(created_files):
        if fpath.exists():
            size = fpath.stat().st_size
            print(f"  {fpath.name:30} ({size:,} bytes)")
        else:
            print(f"  {fpath.name:30} (not found)")

    print(f"\nGerber files ready at: {gerber_dir.resolve()}")


def generate_bom(board):
    """
    Generate BOM data from board footprints.

    Returns list of dicts with keys: Reference, Value, Footprint, Quantity
    """
    components = defaultdict(list)

    # Iterate through all footprints
    for footprint in board.GetFootprints():
        ref = footprint.GetReference()
        value = footprint.GetValue()
        fp_name = str(footprint.GetFPID().GetLibNickname()) if hasattr(
            footprint.GetFPID(), "GetLibNickname"
        ) else "Unknown"

        # Group by (Value, Footprint)
        key = (value, fp_name)
        components[key].append(ref)

    # Build BOM entries
    bom_data = []
    for (value, fp_name), refs in sorted(components.items()):
        refs.sort()
        bom_data.append(
            {
                "Reference": ", ".join(refs),
                "Value": value,
                "Footprint": fp_name,
                "Quantity": len(refs),
            }
        )

    return bom_data


def write_bom_csv(filepath, bom_data):
    """Write BOM data to CSV file."""
    if not bom_data:
        print("  WARNING: No components found in BOM")
        return

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Reference", "Value", "Footprint", "Quantity"])
        writer.writeheader()
        writer.writerows(bom_data)

    print(f"  Wrote {len(bom_data)} component groups to {filepath}")


if __name__ == "__main__":
    main()
