import gdsfactory as gf
from kfactory.kcell import save_layout_options

# This script generates simple layout of two waveguides with cladding.

gf.gpdk.PDK.activate()

layers = {
    "Chip_area":      (0, 0),
    "WG_core_bottom": (1, 0),
    "WG_core_top":    (2, 0),
    "WG_clad_bottom": (3, 0),
    "WG_clad_top":    (4, 0),
    "WG_full":        (5, 0),
}

# parameters of the waveguide
WG_DIST     = 0.2   # edge-to-edge gap between waveguides
TOP_WIDTH   = 1.3   # width of cores
CLAD        = 1.2   # thickness of cladding
CHIP_LENGTH = 200.0 # total length of the chip
CHIP_WIDTH  = 20.0  # total width of the chip

CLAD_WIDTH = TOP_WIDTH + 2 * CLAD
FULL_WIDTH = 2 * TOP_WIDTH + 2 * CLAD + WG_DIST
CENTER_OFFSET = (TOP_WIDTH + WG_DIST) / 2

# cross-sections
core_bottom_cs = gf.cross_section.strip(width=TOP_WIDTH, radius=10, layer=layers["WG_core_bottom"])
core_top_cs    = gf.cross_section.strip(width=TOP_WIDTH, radius=10, layer=layers["WG_core_top"])

clad_bottom_cs = gf.cross_section.strip(width=CLAD_WIDTH, radius=10, layer=layers["WG_clad_bottom"])
clad_top_cs    = gf.cross_section.strip(width=CLAD_WIDTH, radius=10, layer=layers["WG_clad_top"])

full_cs        = gf.cross_section.strip(width=FULL_WIDTH, radius=10, layer=layers["WG_full"])

core_wg_bottom = gf.components.straight(length=CHIP_LENGTH, cross_section=core_bottom_cs)
core_wg_top    = gf.components.straight(length=CHIP_LENGTH, cross_section=core_top_cs)

clad_wg_bottom = gf.components.straight(length=CHIP_LENGTH, cross_section=clad_bottom_cs)
clad_wg_top    = gf.components.straight(length=CHIP_LENGTH, cross_section=clad_top_cs)

full_wg_comp   = gf.components.straight(length=CHIP_LENGTH, cross_section=full_cs)

chip = gf.Component("dual_wg_chip")

# placing the elements
wg1 = chip.add_ref(core_wg_bottom)
wg1.movey(-CENTER_OFFSET)
wg1_clad = chip.add_ref(clad_wg_bottom)
wg1_clad.movey(-CENTER_OFFSET)
wg2 = chip.add_ref(core_wg_top)
wg2.movey(CENTER_OFFSET)
wg2_clad = chip.add_ref(clad_wg_top)
wg2_clad.movey(CENTER_OFFSET)
full_wg = chip.add_ref(full_wg_comp)

chip.center = (0, 0)

chip_area = gf.components.rectangle(
    size=(CHIP_LENGTH, CHIP_WIDTH),
    layer=layers["Chip_area"],
    centered=True,
)
chip.add_ref(chip_area)

chip.flatten() # important for GDStoMEEP!


options = save_layout_options(write_context_info=False)
chip.write_gds("waveguides.gds", save_options=options)
chip.show() # enable by running KLayout