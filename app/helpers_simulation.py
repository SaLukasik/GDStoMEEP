from enum import Enum
from pathlib import Path
from materials import MATERIAL_LIST
import numpy as np
import json

class SimulationBoundary(Enum):
    PML = 'PML'
    ABSORBER  = 'absorber'
    PMETAL = "perfect metal"

class SimulationSource(Enum):
    NONE =  ''
    GAUSS = 'Gaussian'
    PWAVE = 'plain wave'
    FMODE = 'find mode'

class SimulationData:
    def __init__(self):
        self.center = [0.,0.,0.]
        self.range = [1.,1.,1.]
        self.resolution = 100
        self.boundary_type = SimulationBoundary.PML
        self.boundary_thickness = 0.001
        self.source_type = SimulationSource.NONE
        self.source_wl = 1.55

        ### gaussian source data
        self.gauss_center = [0., 0.,0.]
        self.gauss_direction = [1., 0., 0.]
        self.gauss_polarisation =  [0., 1., 0.]
        self.gauss_waist = 0.1

        ### Eigenmode source data
        self.fmode_center = [0., 0.,0.]
        self.fmode_direction = "X"
        self.fmode_range = [0,0.1,0.1]
        self.fmode_band = 1


    def to_dict(self):
        # simulation params
        return {
            "center": self.center,
            "range": self.range,
            "resolution": self.resolution,
            "boundary_type": self.boundary_type.value,
            "boundary_thickness": self.boundary_thickness,
            "source_type": self.source_type.value,
            "source_wl": self.source_wl,
            "gauss_center": self.gauss_center,
            "gauss_direction": self.gauss_direction,
            "gauss_polarisation": self.gauss_polarisation,
            "gauss_waist": self.gauss_waist,
        }

    def from_dict(self, d: dict):
        if not d:
            return
        self.center = d.get("center", self.center)
        self.range = d.get("range", self.range)
        self.resolution = d.get("resolution", self.resolution)
        if "boundary_type" in d:
            try:
                self.boundary_type = SimulationBoundary(d["boundary_type"])
            except ValueError:
                pass
        self.boundary_thickness = d.get("boundary_thickness", self.boundary_thickness)
        if "source_type" in d:
            try:
                self.source_type = SimulationSource(d["source_type"])
            except ValueError:
                pass
        self.source_wl = d.get("source_wl", self.source_wl)
        self.gauss_center = d.get("gauss_center", self.gauss_center)
        self.gauss_direction = d.get("gauss_direction", self.gauss_direction)
        self.gauss_polarisation = d.get("gauss_polarisation", self.gauss_polarisation)
        self.gauss_waist = d.get("gauss_waist", self.gauss_waist)


    def set_property(self, sender, app_data, user_data):
        try:
            if isinstance(app_data, list):
                app_data = [round(v, 3) for v in app_data[:3]]
            elif isinstance(app_data, float):
                app_data = round(app_data, 3)
            elif isinstance(app_data, str):
                for enum_cls in (SimulationBoundary, SimulationSource):
                    try:
                        app_data = enum_cls(app_data)
                        break
                    except ValueError:
                        pass
            user_data(app_data)
            return ""
        except Exception as e:
            return "Error: "+str(e)

#### Gemini ####
def _fmt_wl(wl_nm):
    """Helper for creating names: 1550.0 -> '1550', 1550.5 -> '1550p5' (dots aren't legal in identifiers)."""
    return str(int(wl_nm)) if float(wl_nm).is_integer() else str(wl_nm).replace(".", "p")

#### Gemini ####
def pywrite_metadata(filepath, gds_path, volumes, sim_data: SimulationData, ui_state=None):
    """Writes all project configuration, structure volume definitions, and simulation parameters to metadata.txt"""
    vol_list = []
    for v in volumes:
        vol_list.append({
            "lid": v.lid,
            "layer": v.layer,
            "material": v.material,
            "wavelength_nm": v.wavelength_nm,
            "base": v.base,
            "height": v.height,
            "angle_deg": v.angle_deg,
            "ready": v.ready
        })

    data = {
        "gds_file_path": str(gds_path) if gds_path else "",
        "volumes": vol_list,
        "simulation_data": sim_data.to_dict(),
        "ui_state": ui_state or {}
    }

    with Path(filepath).open(mode="w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


#### Gemini ####
def pyread_metadata(filepath):
    """Reads metadata.txt and returns parsed dictionary."""
    with Path(filepath).open(mode="r", encoding="utf-8") as f:
        return json.load(f)




#### Claude ####
def pywrite_lib_import(filepath, materials):
    """
    Writes material section of the simulation, for it to work it requires material info that
    matches materials.py content.
    materials: iterable of (material_name, wavelength_nm) pairs, e.g.
        {("LiNbO3_z", 1550), ("SiO2", 1550), ("Si", 980)}
    """
    content = (
        "# LIB IMPORT SECTION #################################\n"
        "import gdstk                           # reading .gds\n"
        "import meep as mp                      # MEEP\n"
        "import numpy as np                     # saving field data\n"
        "import matplotlib.pyplot as plt        # plotting\n"
        "import os\n"
        "from pathlib import Path               # universal path manipulation\n"
        "from helpers import add_mesh           # geometry helpers needed for reliable tapering\n\n"
    )

    if materials:
        material_names = sorted({name for name, _ in materials})
        func_names = {
            name: MATERIAL_LIST[name].__name__
            for name in material_names
            if MATERIAL_LIST.get(name) is not None
        }

        import_list = ", ".join(sorted(set(func_names.values())))
        content += f"from materials import {import_list}\n"

        content += "\n# material instances:\n"
        for name, wl_nm in sorted(materials):
            if name not in func_names:
                continue
            wl_um = wl_nm / 1000
            var_name = f"{name}_{_fmt_wl(wl_nm)}nm"
            content += f"{var_name} = {func_names[name]}(wl_um={wl_um})\n"

    content += "######################################################\n\n"

    with Path(filepath).open(mode="a", encoding="utf-8") as f:
        f.write(content)

def pywrite_gds_import(filepath, gds_path):
    content = ("# GDS IMPORT SECTION #################################\n"
               f"""GDS_FILE_PATH = "./gds_file.gds"\n"""
               """SIM_STATE_DIR = "./simulation_state"\n"""
               """SAVE_SIM   = True\n"""
               """path = Path(GDS_FILE_PATH)\n"""
               """spath = Path(SIM_STATE_DIR)\n"""
               "shapes = gdstk.read_gds(path).top_level()[0]\n"
               "######################################################\n\n")

    with Path(filepath).open(mode="a", encoding="utf-8") as f:
        f.write(content)


# Helper code that is copied verbatim into the generated script's GEOMETRY SECTION.
_HELPERS_HEADER = '''import math
import os
import warnings
import numpy as np
import meep as mp
import cadquery as cq                  # generating tapered shapes
from shapely.geometry import Polygon   # simplifying base polygons (speeds up mesh rendering)
from shapely.geometry.polygon import orient

# This file is a work-around the faulty geometry libraries that were failing during tapering of the waveguide at different points in time.
# I'll keep looking for better solution but for now it was the easiest to write and test functions for this operations, stable for most
# popular shapes.

# Tapered structures are built as a ruled loft between the base outline and a top outline.
# If height is negative, the structure will be pulled downwards. If angle is positive, the top will be wider than bottom.
# If the offset is too large for the outline (top face would collapse), the structure is cut at the height where
# it collapses (the cross-section becomes a triangle instead of a trapezoid).
'''



_GEOMETRY_HELPERS = '''
#### Claude ####
def _miter_offset(pts, s):
    p = np.asarray(pts, float)
    e1 = p - np.roll(p, 1, 0)
    e2 = np.roll(p, -1, 0) - p
    e1 /= np.linalg.norm(e1, axis=1)[:, None]
    e2 /= np.linalg.norm(e2, axis=1)[:, None]
    n1 = np.stack([-e1[:, 1], e1[:, 0]], 1)   
    n2 = np.stack([-e2[:, 1], e2[:, 0]], 1)
    denom = np.clip(1 + (n1 * n2).sum(1), 0.05, None)   # clamp very sharp corners
    return p + s * (n1 + n2) / denom[:, None]

#### Claude ####
def _offset_ok(simp, pts, s):
    """True if the vertex offset by s is a clean polygon that agrees with shapely's robust mitred buffer."""
    try:
        T = Polygon(_miter_offset(pts, s))
        if T.is_empty or not T.is_valid:
            return False
        ref = simp.buffer(-s, join_style=2, mitre_limit=10)
        if ref.is_empty or ref.geom_type != 'Polygon' or len(ref.interiors) > 0:
            return False    # collapsed, split into pieces, or closed a pocket
        return abs(T.area - ref.area) <= 0.01 * ref.area
    except Exception:
        return False

#### Claude ####
def _max_offset(simp, pts, s_req, n=50):
    """Largest offset (same sign as s_req, |.| <= |s_req|) that is still clean."""
    if _offset_ok(simp, pts, s_req):
        return s_req
    lo, hi = 0.0, 1.0
    for k in range(1, n + 1):
        if not _offset_ok(simp, pts, s_req * k / n):
            lo, hi = (k - 1) / n, k / n
            break
    for _ in range(30):
        mid = (lo + hi) / 2
        if _offset_ok(simp, pts, s_req * mid):
            lo = mid
        else:
            hi = mid
    return s_req * lo

def add_mesh(geometry, shapes, tol, layer, material, base_z, height, angle_deg, fname='temp.stl'):
    offset = height * math.tan(math.radians(angle_deg))  
    for i, pg in enumerate(shapes.get_polygons(layer=layer, datatype=0)):
        tag = f"layer {layer} #{i}"
        poly = Polygon(np.asarray(pg.points, dtype=float)) # creating polygon object, used for simplification which shortens simulaiton initiation time
        simp = orient(Polygon(poly.simplify(tol, preserve_topology=True).exterior), 1.0)  
        pts = np.asarray(simp.exterior.coords)[:-1]                                         # dropping repeated closing point 
        # pts = pts[np.r_[True, np.linalg.norm(np.diff(pts, axis=0), axis=1) > 1e-9]]       # dropping duplicate vertices, should not be needed, left for debugging

        h = height
        s = -offset                                  
        if s != 0.0:
            s_ok = _max_offset(simp, pts, s)
            if abs(s_ok) < abs(s):                   # too steep: cut where the outline collapses
                s = 0.995 * s_ok                     # stay just before collapse so the top face stays valid
                h = height * abs(s / (-offset))
        if abs(h) < 1e-6:
            continue

        top_pts = _miter_offset(pts, s) if s != 0.0 else pts
        allp = np.vstack([pts, top_pts])
        cx = (allp[:, 0].min() + allp[:, 0].max()) / 2.0
        cy = (allp[:, 1].min() + allp[:, 1].max()) / 2.0

        base = cq.Workplane('XY').polyline([tuple(p) for p in pts]).close().wires().val()
        top = (cq.Workplane('XY').workplane(offset=h)
               .polyline([tuple(p) for p in top_pts]).close().wires().val())
        body = cq.Workplane('XY').add(cq.Solid.makeLoft([base, top], ruled=True))
        cq.exporters.export(body, fname)
        with warnings.catch_warnings(record=True) as _:
            warnings.simplefilter("always")
            mesh = mp.Mesh.from_file(fname, material=material, center=mp.Vector3(cx, cy, base_z + h / 2))

        geometry.append(mesh)
    if os.path.exists(fname):
        os.remove(fname)
'''


def pywrite_geometry(filepath, volumes, sim_data):
    helpers_path = Path(filepath).parent / "helpers.py" # I really wanted to avoid generating additional file, but it every single library for 3D object manipulation failed tapering tests.
    with helpers_path.open(mode="w", encoding="utf-8") as f:
        f.write(_HELPERS_HEADER + _GEOMETRY_HELPERS)

    content = "# GEOMETRY SECTION ###################################\n"
    content += f"RESOLUTION = {sim_data.resolution}\n"
    content += "geometry = []\n"
    content += "tol = 1/RESOLUTION/2 # polygons from .gds file will be simplified to match the requested resolution, it saves initiation time\n"
    for v in volumes[::-1]:
        mat_var = f"{v.material}_{_fmt_wl(v.wavelength_nm)}nm"
        layer_num = int(v.layer)
        content += (f"add_mesh(geometry, shapes, tol, layer={layer_num}, material={mat_var}, "
                    f"base_z={v.base}, height={v.height}, angle_deg={v.angle_deg})\n")

    content += "######################################################\n\n"

    with Path(filepath).open(mode="a", encoding="utf-8") as f:
        f.write(content)

def pywrite_source(filepath, sim_data:SimulationData):
    content = "# SOURCE SECTION ######################################\n"
    content += f"# You can add more sources by simply adding them to this list\n"

    match sim_data.source_type:
        case SimulationSource.GAUSS:
            direction = np.array(sim_data.gauss_direction, dtype=float)
            direction = direction / np.linalg.norm(direction)
            polarisation = np.array(sim_data.gauss_polarisation, dtype=float)
            polarisation = polarisation / np.linalg.norm(polarisation)
            w0 = sim_data.gauss_waist
            source_size = np.ones(3)*6*w0   # rule of thumb, might need to be set to bigger/smaller value depending on needs,
                                            # basically this parameter says how big should be the plain with current generating source
            dir_argmax = np.argmax(np.abs(direction))
            source_size[dir_argmax]=0   # sets plane as current source, direction of plane is set to generate a smallest tilt
            source_dir = np.zeros(3)
            source_dir[dir_argmax] = 1
            argmin1, argmin2 = [i for i in range(3) if i != dir_argmax]

            dirflat1, dirflat2 = direction.copy(), direction.copy()
            dirflat1[argmin1], dirflat2[argmin2] = 0,0
            source_size[argmin2] =np.abs(source_size[argmin2]/ np.dot(dirflat1, source_dir) / (np.linalg.norm(dirflat1) * np.linalg.norm(source_dir)))
            source_size[argmin1] =np.abs(source_size[argmin1]/ np.dot(dirflat2, source_dir) / (np.linalg.norm(dirflat2) * np.linalg.norm(source_dir)))
            content += (f"# Gaussian source will generate gaussian beam centered at 'center'. The 2D area of source oscillations is set by 'size' \n"
                        f"# (always in XY, XZ or YZ plane). This specific plane was chosen to minimize the angle between the source plane and outgoing beam.\n")
            content += f"sources = [mp.GaussianBeamSource(src=mp.ContinuousSource(wavelength={sim_data.source_wl}),\n"
            content += f"                                                         center=mp.Vector3({sim_data.gauss_center[0]},{sim_data.gauss_center[1]},{sim_data.gauss_center[2]}),\n"
            content += f"                                                         size=mp.Vector3({source_size[0]},{source_size[1]},{source_size[2]}),\n"
            content += f"                                                         beam_kdir=mp.Vector3({direction[0]},{direction[1]},{direction[2]}),\n"
            content += f"                                                         beam_w0={w0},\n"
            content += f"                                                         beam_E0=mp.Vector3({polarisation[0]},{polarisation[1]},{polarisation[2]}))]\n"
        case SimulationSource.FMODE:
            content += (f"# EigenMode source will generate gaussian beam centered at 'center'.\n "
                        f"# The 2D area of source oscillations is set by 'size' (always in XY, XZ or YZ plane).\n "
                        f"# This specific plane was chosen to minimize the angle between the source plane and outgoing beam.\n"
                        f"# MEEP will use the MPB library (FDE) to find guided modes in this space.\n")

            content += f"sources = [mp.EigenModeSource(src=mp.ContinuousSource(wavelength={sim_data.source_wl}),\n"
            content += f"                                                      center=mp.Vector3({sim_data.fmode_center[0]},{sim_data.fmode_center[1]},{sim_data.fmode_center[2]}),\n"
            content += f"                                                      size=mp.Vector3({sim_data.fmode_range[0]},{sim_data.fmode_range[1]},{sim_data.fmode_range[2]}),\n"
            content += f"                                                      direction=mp.{sim_data.fmode_direction},\n"
            content += f"                                                      eig_band={sim_data.fmode_band})]\n"

        case _:
            content += f"sources = []\n"

    content += "######################################################\n\n"

    with Path(filepath).open(mode="a", encoding="utf-8") as f:
        f.write(content)


def pywrite_boundary(filepath, sim_data:SimulationData):
    content = "# BOUNDARY SECTION ####################################\n"
    content += f"# You can add more boundaries by simply adding them to this list\n"

    match sim_data.boundary_type:
        case SimulationBoundary.ABSORBER:
            content += f"boundaries = [mp.Absorber(thickness={sim_data.boundary_thickness})]\n"
        case SimulationBoundary.PML:
            content += f"boundaries = [mp.PML(thickness={sim_data.boundary_thickness})]\n"
        case SimulationBoundary.PMETAL:
            content += f"boundaries = [] # perfect metal is a default boundary\n"
        case _:
            content += f"boundaries = []\n"

    content += "######################################################\n\n"
    with Path(filepath).open(mode="a", encoding="utf-8") as f:
        f.write(content)


def pywrite_sim_call(filepath, sim_data: SimulationData):
    content = "# SIMULATION CALL SECTION #############################\n"
    content += "sim_kwargs = dict(\n"
    content += f"    cell_size=mp.Vector3({sim_data.range[0]},{sim_data.range[1]},{sim_data.range[2]}),\n"
    content += f"    resolution=RESOLUTION,\n"
    content += "    geometry=None,\n"
    content += f"    geometry_center=mp.Vector3({sim_data.center[0]},{sim_data.center[1]},{sim_data.center[2]}),\n"
    content += "    boundary_layers=boundaries,\n"
    content += "    sources=sources,\n"
    content += "    default_material=mp.air, # you might want to change it to mp.vacuum, this material will be used where no other is defined\n"
    content += "    eps_averaging=False,   # setting to True slows down simulation strongly, set True when high accuracy matters\n"
    content += "    Courant = 0.3,         # should be min(refractive index)/(n dim), I assume min n = 1\n"

    content += ")\n\n"
    content += "sim = mp.Simulation(**sim_kwargs)\n"

    content += "# To save time, if your structure was initiated before here you can simply upload it.\n"
    content += "# (!!!) There is unfixed bug in MEEP that causes loading to fail for unspecific grids settings.\n"
    content += "# There is no simple fix and if it happens to your simulation please set SAVE_SIM to False or try \n"
    content += "# running simulation with slightly different resolution (prime numbers often work but it's rule of thumb).\n"
    content += "# You can use .load() and .dump() function to run simulation in batches.\n"


    content += "if SAVE_SIM and os.path.exists(spath):\n"
    content += "    sim.load(str(spath))\n"
    content += "else:\n"
    content += "    sim.geometry = geometry\n"
    content += "    sim.init_sim()\n"
    content += "    sim.dump(str(spath))\n"
    content += "######################################################\n\n"
    with Path(filepath).open(mode="a", encoding="utf-8") as f:
        f.write(content)


def pywrite_additions(filepath,ax, ay, sim_data:SimulationData):
    pols = ["mp.Ex","mp.Ey","mp.Ez"]
    pol  = pols[np.argmax(np.abs(sim_data.gauss_polarisation))]
    content = "# RUNNING, PLOTTING, OTHER SECTION ####################\n"
    content += "# uncomment to run simulation for n periods:\n"
    content += '"""\n'
    content += "n_periods = 5\n"
    content += "sim.run(until=n_periods)\n"
    content += '"""\n\n'
    content += "# uncomment to plot the results (crossections chosen based on from cursor axes in app, top view from absolute top, polarization same as source):\n"
    content += "# make sure plotting area is not completely outside of simulation, otherwise error will be thrown\n"
    content += "# (plotting area completely outside the simulation throws error, make sure in app cursor axes are within it):\n"
    content += '"""\n'
    content += "sim.geometry = geometry # has to be set here for plotting function to read from from\n"
    content += f"sim.plot2D(output_plane=mp.Volume(center=mp.Vector3({sim_data.center[0]},{sim_data.center[1]},{sim_data.center[2]+sim_data.range[2]/2*0.999-sim_data.boundary_thickness}),size=mp.Vector3({sim_data.range[0]}, {sim_data.range[1]}, 0)),\n"
    content += f"""           fields={pol},field_parameters={{'alpha': 0.3,'interpolation':'none',}})\n"""
    content += "plt.show()\n"
    content += f"sim.plot2D(output_plane=mp.Volume(center=mp.Vector3({sim_data.center[0]},{ay},{sim_data.center[2]}),size=mp.Vector3({sim_data.range[0]}, 0, {sim_data.range[2]})),\n"
    content += f"""           fields={pol},field_parameters={{'alpha': 0.3,'interpolation':'none',}})\n"""
    content += "plt.show()\n"
    content += f"sim.plot2D(output_plane=mp.Volume(center=mp.Vector3({ax},{sim_data.center[1]},{sim_data.center[2]}),size=mp.Vector3(0, {sim_data.range[1]}, {sim_data.range[2]})),\n"
    content += f"""           fields={pol},field_parameters={{'alpha': 0.3,'interpolation':'none',}})\n"""
    content += "plt.show()\n"
    content += '"""\n'
    content += "# uncomment to save field state:\n"
    content += "# (below example saves field from whole simulation volume, adjust to save space)\n"
    content += "# (also ypu can add more components: Ey,Ez,Hx,Hy,Hz)\n"
    content += '"""\n'
    content += "os.makedirs(SIM_STATE_DIR, exist_ok=True)\n"
    content += f"field_vol = mp.Volume(center=mp.Vector3({sim_data.center[0]},{sim_data.center[1]},{sim_data.center[2]}), size=mp.Vector3({sim_data.range[0]}, {sim_data.range[1]}, {sim_data.range[2]})) \n"
    content += "fields = {'Ex': sim.get_array(vol=field_vol, component=mp.Ex)}\n"
    content += "np.savez(os.path.join(SIM_STATE_DIR, 'field_data.npz'), **fields)\n"
    content += '"""\n'
    content += "######################################################\n\n"
    with Path(filepath).open(mode="a", encoding="utf-8") as f:
        f.write(content)


