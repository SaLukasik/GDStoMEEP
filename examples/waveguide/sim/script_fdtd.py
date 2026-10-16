# LIB IMPORT SECTION #################################
import gdstk                           # reading .gds
import meep as mp                      # MEEP
import numpy as np                     # saving field data
import matplotlib.pyplot as plt        # plotting
import os
from pathlib import Path               # universal path manipulation
from helpers import add_mesh           # geometry helpers needed for reliable tapering

from materials import medium_linbo3_z, medium_sio2

# material instances:
LiNbO3_z_1550nm = medium_linbo3_z(wl_um=1.55)
SiO2_1550nm = medium_sio2(wl_um=1.55)
######################################################

# GDS IMPORT SECTION #################################
GDS_FILE_PATH = "./gds_file.gds"
SIM_STATE_DIR = "./simulation_state"
SAVE_SIM   = True
path = Path(GDS_FILE_PATH)
spath = Path(SIM_STATE_DIR)
shapes = gdstk.read_gds(path).top_level()[0]
######################################################

# GEOMETRY SECTION ###################################
RESOLUTION = 40.0
geometry = []
tol = 1/RESOLUTION/2 # polygons from .gds file will be simplified to match the requested resolution, it saves initiation time
add_mesh(geometry, shapes, tol, layer=1, material=SiO2_1550nm, base_z=-5.0, height=15.0, angle_deg=0)
add_mesh(geometry, shapes, tol, layer=2, material=LiNbO3_z_1550nm, base_z=0.0, height=1.0, angle_deg=-10)
######################################################

# SOURCE SECTION ######################################
# You can add more sources by simply adding them to this list
# Gaussian source will generate gaussian beam centered at 'center'. The 2D area of source oscillations is set by 'size' 
# (always in XY, XZ or YZ plane). This specific plane was chosen to minimize the angle between the source plane and outgoing beam.
sources = [mp.GaussianBeamSource(src=mp.ContinuousSource(wavelength=1.55),
                                                         center=mp.Vector3(0.0,0.0,0.5),
                                                         size=mp.Vector3(0.0,2.4000000000000004,2.4000000000000004),
                                                         beam_kdir=mp.Vector3(1.0,0.0,0.0),
                                                         beam_w0=0.4,
                                                         beam_E0=mp.Vector3(0.0,1.0,0.0))]
######################################################

# BOUNDARY SECTION ####################################
# You can add more boundaries by simply adding them to this list
boundaries = [mp.PML(thickness=0.5)]
######################################################

# SIMULATION CALL SECTION #############################
sim_kwargs = dict(
    cell_size=mp.Vector3(4.0,6.0,5.0),
    resolution=RESOLUTION,
    geometry=None,
    geometry_center=mp.Vector3(0.0,0.0,0.5),
    boundary_layers=boundaries,
    sources=sources,
    default_material=mp.air, # you might want to change it to mp.vacuum, this material will be used where no other is defined
    eps_averaging=False,   # setting to True slows down simulation strongly, set True when high accuracy matters
    Courant = 0.3,         # should be min(refractive index)/(n dim), I assume min n = 1
)

sim = mp.Simulation(**sim_kwargs)
# To save time, if your structure was initiated before here you can simply upload it.
# (!!!) There is unfixed bug in MEEP that causes loading to fail for unspecific grids settings.
# There is no simple fix and if it happens to your simulation please set SAVE_SIM to False or try 
# running simulation with slightly different resolution (prime numbers often work but it's rule of thumb).
# You can use .load() and .dump() function to run simulation in batches.
if SAVE_SIM and os.path.exists(spath):
    sim.load(str(spath))
else:
    sim.geometry = geometry
    sim.init_sim()
    sim.dump(str(spath))
######################################################

# RUNNING, PLOTTING, OTHER SECTION ####################
# uncomment to run simulation for n periods:
"""
n_periods = 5
sim.run(until=n_periods)
"""

# uncomment to plot the results (crossections chosen based on from cursor axes in app, top view from absolute top, polarization same as source):
# make sure plotting area is not completely outside of simulation, otherwise error will be thrown
# !!!!!! (plotting area completely outside the simulation throws error, make sure in app cursor axes are within it):
"""
sim.geometry = geometry # has to be set here for plotting function to read from from
sim.plot2D(output_plane=mp.Volume(center=mp.Vector3(0.0,0.0,2.4975),size=mp.Vector3(4.0, 6.0, 0)),
           fields=mp.Ey,field_parameters={'alpha': 0.3,'interpolation':'none',})
plt.show()
sim.plot2D(output_plane=mp.Volume(center=mp.Vector3(0.0,-0.14893640410882014,0.5),size=mp.Vector3(4.0, 0, 5.0)),
           fields=mp.Ey,field_parameters={'alpha': 0.3,'interpolation':'none',})
plt.show()
sim.plot2D(output_plane=mp.Volume(center=mp.Vector3(15.271036230588841,0.0,0.5),size=mp.Vector3(0, 6.0, 5.0)),
           fields=mp.Ey,field_parameters={'alpha': 0.3,'interpolation':'none',})
plt.show()
"""
# uncomment to save field state:
# (below example saves field from whole simulation volume, adjust to save space)
# (also ypu can add more components: Ey,Ez,Hx,Hy,Hz)
"""
os.makedirs(SIM_STATE_DIR, exist_ok=True)
field_vol = mp.Volume(center=mp.Vector3(0.0,0.0,0.5), size=mp.Vector3(4.0, 6.0, 5.0)) 
fields = {'Ex': sim.get_array(vol=field_vol, component=mp.Ex)}
np.savez(os.path.join(SIM_STATE_DIR, 'field_data.npz'), **fields)
"""
######################################################

