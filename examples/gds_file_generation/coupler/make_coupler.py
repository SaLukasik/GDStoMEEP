import gdsfactory as gf
from kfactory.kcell import save_layout_options

# This script generates simple layout of coupler with cladding.

gf.gpdk.PDK.activate()

layers = {
    "Chip_area":    (0, 0),
    "LiNbO3_core":  (1, 0),
    "SiO2_clad":    (2, 0),
    "SiO2_matrix":  (3, 0),
    "Source":       (4, 0)
}

CORE_WIDTH   = 1.3                    # width of the core waveguide
CLAD = 1.2                            # width of the cladding
CLAD_WIDTH   = CORE_WIDTH + 2 * CLAD
CPL_GAP      = 0.2                    # edge-to-edge gap of the CORES in the coupling section
CPL_PITCH    = CORE_WIDTH + CPL_GAP   # centre-to-centre distance = 1.5
CPL_LENGTH   = 20                     # length of the coupling segment
CPL_DX       = 30                     # horizontal length of each S-bend branch
CPL_DY       = 20                     # centre-to-centre separation of the branches at the ports
WG_LENGTH    = 2                      # straight stubs attached to the ports
W_STRECH     = 1.5                    # chip height = bbox height * W_STRECH
BEND_RADIUS  = 10


def make_coupler_chip(name, width, gap, layer):
    xs = gf.cross_section.strip(width=width, radius=BEND_RADIUS, layer=layer)
    cpl = gf.components.couplers.coupler(gap=gap,
                                         length=CPL_LENGTH,
                                         dy=CPL_DY,
                                         dx=CPL_DX,
                                         cross_section=xs,
                                         bend=gf.components.bend_s)
    wg = gf.components.straight(length=WG_LENGTH, cross_section=xs)

    c = gf.Component(name)
    c.add_ref(cpl)
    for p in ["o1", "o2", "o3", "o4"]:
        wg_ref = c.add_ref(wg)
        wg_ref.connect("o1", cpl.ports[p])
    return c

core = make_coupler_chip("core", CORE_WIDTH, CPL_GAP, layers["LiNbO3_core"])
clad = make_coupler_chip("clad", CLAD_WIDTH, CPL_PITCH - CLAD_WIDTH, layers["SiO2_clad"])

chip = gf.Component("chip")
chip.add_ref(core)
chip.add_ref(clad)
chip.center = (0, 0)

core_bbox = core.bbox()
core_half_w, core_half_h = core_bbox.width() / 2, core_bbox.height() / 2

bbox = chip.bbox()
chip_width, chip_height = bbox.right - bbox.left, (bbox.top - bbox.bottom) * W_STRECH

chip_area = gf.components.rectangle(size=(chip_width, chip_height),
                                    layer=layers["Chip_area"], centered=True)
chip.add_ref(chip_area)

matrix = gf.components.rectangle(size=(chip_width, chip_height),
                                 layer=layers["SiO2_matrix"], centered=True)
chip.add_ref(matrix)


chip.add_port(name="source",
              width=CORE_WIDTH,
              layer=layers["Source"],
              center=(-core_half_w + WG_LENGTH / 2, core_half_h - CORE_WIDTH / 2))

chip.flatten()  # Important! Needed for GUI.

options = save_layout_options(write_context_info=False)
chip.write_gds("coupler.gds", save_options=options)
chip.show() # plots the chip with KLayout
