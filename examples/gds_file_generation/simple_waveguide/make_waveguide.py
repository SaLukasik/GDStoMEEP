import gdsfactory as gf
from kfactory.kcell import save_layout_options


gf.gpdk.PDK.activate()

layers = {
    "LiNbO3_core":  (0, 0),
    "SiO2_matrix":  (1, 0),
    "SiO2_clad":    (2, 0),
}

CHIP_LENGTH = 50
CHIP_WIDTH = 30
WV_WIDTH = 1
CLAD_WIDTH = 1.2
chip = gf.Component("chip")

# crossections
linbo3_cs = gf.cross_section.cross_section(width=WV_WIDTH, layer=layers["LiNbO3_core"])
sio2_cs   = gf.cross_section.cross_section(width=WV_WIDTH+CLAD_WIDTH*2, layer=layers["SiO2_clad"])

# elements
waveguide = gf.components.straight(length=CHIP_LENGTH, cross_section=linbo3_cs)
cladding  = gf.components.straight(length=CHIP_LENGTH, cross_section=sio2_cs)
matrix      = gf.components.rectangle(size=(CHIP_LENGTH,CHIP_WIDTH), layer=layers["SiO2_matrix"],centered=True)

# placing
chip << matrix
wg1 = chip << waveguide
wgclad = chip << cladding

wg1.dcenter = (0, 0)
wgclad.dcenter = (0,0)

chip.flatten() # important to GDStoMEEP!

options = save_layout_options(write_context_info=False)
chip.write_gds("waveguide.gds", save_options=options)
chip.show() # gds plugin has to be installed into Klayout

