import dearpygui.dearpygui as dpg
import pyautogui
from pathlib import Path
import gdstk
import numpy as np
from functools import partial
import shutil

from colors import c_error, c_good, c_warn,get_c_layer, c_v_slider, c_h_slider, get_c_material
from materials import MATERIAL_LIST
from helpers_simulation import (SimulationData, SimulationBoundary, SimulationSource,
                                pywrite_lib_import, pywrite_gds_import, pywrite_geometry,
                                pywrite_source, pywrite_sim_call, pywrite_boundary,
                                pywrite_metadata, pyread_metadata,pywrite_additions)


gds_file_path = ''
DEFAULT_WL_NM = 1550 # default wavelength shown in app (in nm)


class Plot:
    pid : int = -1
    hax : int = -1
    vax : int = -1

class Layer:
    shapes : list[np.ndarray] = []
    color  : tuple            = ()


class Volume:
    def __init__(self, lid):
        self.lid      : int   = lid     # unique id for volume, used for plotting, XLY, where X is unique ID and Y is
                                        # layer on which volume is based
        self.ready    : bool  = False   # set to True if all info for volume is filled correctly
        self.layer    : str   = " "
        self.base     : float = 0
        self.height   : float = 0.001
        self.angle_deg: float = 0        # angle of prism cut, should be (-90, 90) (90 - angle between base and the
                                         # wall, for 0 the wall is vertical)
        self.material : str   = " "
        self.wavelength_nm : float = DEFAULT_WL_NM
        self.epsilon  : mp.Medium = None


plot_names = ['XY', 'XZ', 'YZ']
plots = {'XY': Plot(), 'XZ':Plot(), 'YZ':Plot()}
layers = {' ': None}
color_count = -1
volumes = []
simulation_data = SimulationData()

vol_tab = None  # tab with volumes
last_id = 0     # variable to set unique id for each volume (basically incremental, but gets restarted
                # when all volumes removed)

# slider positions for cross-section plotting:
h_slider_pos = 0
v_slider_pos = 0

# material and layer menu rendering
material_colors = {}
hidden_layers = set()
hidden_materials = set()

#
# cloude
# cache of the volume cross-section bounding box per plot, used as the
# lowest-priority fallback for axis zooming (updated each time volumes redraw)
_volume_bounds = {'XZ': None, 'YZ': None}
#

def save_info_err(err: str):
    dpg.configure_item("filepath_info", color=c_error)
    dpg.set_value("filepath_info", err)


def load_project():
    # gemini and me a lot also?
    """Loads metadata.txt from the specified project directory and populates all GUI parameters, volume tables, and simulation setups."""
    global gds_file_path, volumes, last_id, simulation_data, h_slider_pos, v_slider_pos

    save_path = dpg.get_value("save_path")  # path to the directory
    if not save_path or not str(save_path).strip():
        save_info_err("Please input path to project directory containing metadata.txt file.")
        return

    path = Path(save_path).resolve() / 'metadata.txt'
    if not path.exists():
        save_info_err("Metadata file does not exist in the specified directory or metadata corrupted.")
        return

    try:
        data = pyread_metadata(path)
    except Exception as e:
        save_info_err(f"Error reading metadata.txt: {e}")
        return

    # 1. Load GDS file if present
    saved_gds = data.get("gds_file_path", "")
    if saved_gds:
        dpg.set_value("filepath", saved_gds)
        load_gds()

    # 2. Reconstruct Volume instances
    volumes.clear()
    saved_volumes = data.get("volumes", [])
    max_id = 0
    for v_dict in saved_volumes:
        lid = v_dict.get("lid", 0)
        v = Volume(lid=lid)
        v.layer = str(v_dict.get("layer", " "))
        v.material = v_dict.get("material", " ")
        v.wavelength_nm = v_dict.get("wavelength_nm", DEFAULT_WL_NM)
        v.base = v_dict.get("base", 0.0)
        v.height = v_dict.get("height", 0.001)
        v.angle_deg = v_dict.get("angle_deg", 0)
        _check_volume(v)
        volumes.append(v)
        if lid >= max_id:
            max_id = lid + 1

    last_id = max_id
    _redraw_volumes()

    # 3. Restore SimulationData
    sim_dict = data.get("simulation_data", {})
    simulation_data.from_dict(sim_dict)

    # 4. Synchronize UI Inputs with loaded values
    if dpg.does_item_exist("sim_center_input"):
        dpg.set_value("sim_center_input", simulation_data.center)
    if dpg.does_item_exist("sim_range_input"):
        dpg.set_value("sim_range_input", simulation_data.range)
    if dpg.does_item_exist("sim_resolution_input"):
        dpg.set_value("sim_resolution_input", simulation_data.resolution)
    if dpg.does_item_exist("sim_boundary_type"):
        dpg.set_value("sim_boundary_type", simulation_data.boundary_type.value)
    if dpg.does_item_exist("sim_boundary_thickness_pml"):
        dpg.set_value("sim_boundary_thickness_pml", simulation_data.boundary_thickness)
    if dpg.does_item_exist("sim_boundary_thickness_absorber"):
        dpg.set_value("sim_boundary_thickness_absorber", simulation_data.boundary_thickness)
    if dpg.does_item_exist("sim_source_type"):
        dpg.set_value("sim_source_type", simulation_data.source_type.value)
    if dpg.does_item_exist("sim_source_wl"):
        dpg.set_value("sim_source_wl", simulation_data.source_wl)
    if dpg.does_item_exist("sim_gauss_center"):
        dpg.set_value("sim_gauss_center", simulation_data.gauss_center)
    if dpg.does_item_exist("gb_beam_kdir"):
        dpg.set_value("gb_beam_kdir", simulation_data.gauss_direction)
    if dpg.does_item_exist("gb_beam_E0"):
        dpg.set_value("gb_beam_E0", simulation_data.gauss_polarisation)
    if dpg.does_item_exist("gb_w0"):
        dpg.set_value("gb_w0", simulation_data.gauss_waist)

    # 5. Restore UI toggles and sliders
    ui_state = data.get("ui_state", {})
    h_slider_pos = ui_state.get("h_slider_pos", h_slider_pos)
    v_slider_pos = ui_state.get("v_slider_pos", v_slider_pos)
    if dpg.does_item_exist("h_slider"):
        dpg.set_value("h_slider", h_slider_pos)
    if dpg.does_item_exist("v_slider"):
        dpg.set_value("v_slider", v_slider_pos)

    if dpg.does_item_exist("show_sim_range") and "show_sim_range" in ui_state:
        dpg.set_value("show_sim_range", ui_state["show_sim_range"])
    if dpg.does_item_exist("show_gaussian") and "show_gaussian" in ui_state:
        dpg.set_value("show_gaussian", ui_state["show_gaussian"])
    if dpg.does_item_exist("show_sim_boundaries_pml") and "show_sim_boundaries_pml" in ui_state:
        dpg.set_value("show_sim_boundaries_pml", ui_state["show_sim_boundaries_pml"])
    if dpg.does_item_exist("show_sim_boundaries_absorber") and "show_sim_boundaries_absorber" in ui_state:
        dpg.set_value("show_sim_boundaries_absorber", ui_state["show_sim_boundaries_absorber"])
    if dpg.does_item_exist("show_sim_boundaries_pmetal") and "show_sim_boundaries_pmetal" in ui_state:
        dpg.set_value("show_sim_boundaries_pmetal", ui_state["show_sim_boundaries_pmetal"])

    # 6. Update options layout visibility
    for s_enum in SimulationSource:
        if dpg.does_item_exist(f"source_{s_enum.value}_options"):
            dpg.configure_item(f"source_{s_enum.value}_options", show=(s_enum == simulation_data.source_type))
    for b_enum in SimulationBoundary:
        if dpg.does_item_exist(f"source_{b_enum.value}_options"):
            dpg.configure_item(f"source_{b_enum.value}_options", show=(b_enum == simulation_data.boundary_type))

    # 7. Redraw visual cross-sections and simulation overlays
    _redraw_volume_plots()
    update_sim_plot()

    dpg.configure_item("filepath_info", color=c_good)
    dpg.set_value("filepath_info", "Project metadata successfully loaded.")


def save_project():
    # gemini, claude
    """Saves generated script, files, and project metadata in the target directory."""
    raw_path = dpg.get_value("save_path")
    if not raw_path or not str(raw_path).strip():
        save_info_err("Please input a valid save path.")
        return

    path = Path(raw_path).resolve()

    # 1. Directory creation & validation
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    elif not path.is_dir():
        save_info_err("Please provide path to a directory.")
        return

    # 2. Check for existing files (metadata & script allow overwrite upon confirmation)
    if any(path.iterdir()):
        current_msg = dpg.get_value("filepath_info") or ""
        if not current_msg.startswith("Directory not empty"):
            save_info_err("Directory not empty. Please click again to confirm (all existing files will be deleted).")
            return
        shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
        dpg.set_value("filepath_info", "")

    # 3. Create script file
    file_path = path / "script_fdtd.py"
    file_path.touch(exist_ok=True)

    # 4. Handle GDS file & script writing
    if gds_file_path:
        src_file = Path(gds_file_path)
        dest_file = path / "gds_file.gds"

        if not src_file.is_file():
            save_info_err("Source .gds file does not exist.")
            return

        material_wl_pairs = sorted({
            (v.material, v.wavelength_nm)
            for v in volumes
            if v.ready and v.material not in (None, " ")
        })
        try:
            pywrite_lib_import(file_path, materials=material_wl_pairs)
        except Exception as e:
            save_info_err("Error during writing to .py file, lib import section: "+ str(e))
            return

        try:
            shutil.copy2(src_file, dest_file)
            if Path('./materials.py').is_file():
                shutil.copy2('./materials.py',  path / 'materials.py')
        except Exception as e:
            save_info_err("Error during copying .gds or materials.py file: "+ str(e))
            return

        try:
            pywrite_gds_import(file_path, dest_file)
        except Exception as e:
            save_info_err("Error during writing to .py file, gds import section: "+ str(e))
            return

        try:
            pywrite_geometry(file_path, volumes=[v for v in volumes if v.ready], sim_data=simulation_data)
        except Exception as e:
            save_info_err("Error during writing to .py file, geometry section: "+ str(e))
            return
        try:
            pywrite_source(file_path, simulation_data)
        except Exception as e:
            save_info_err("Error during writing to .py file, source section: "+ str(e))
            return
        try:
            pywrite_boundary(file_path, simulation_data)
        except Exception as e:
            save_info_err("Error during writing to .py file, boundary section: "+ str(e))
            return
        try:
            pywrite_sim_call(file_path, simulation_data)
        except Exception as e:
            save_info_err("Error during writing to .py file, simulation call section: "+ str(e))
            return
        try:
            pywrite_additions(file_path,v_slider_pos,h_slider_pos, simulation_data)
        except Exception as e:
            save_info_err("Error during writing to .py file, additional section: "+ str(e))
            return

    # 5. Save metadata.txt
    try:
        ui_state = {
            "h_slider_pos": h_slider_pos,
            "v_slider_pos": v_slider_pos,
            "show_sim_range": dpg.get_value("show_sim_range") if dpg.does_item_exist("show_sim_range") else False,
            "show_gaussian": dpg.get_value("show_gaussian") if dpg.does_item_exist("show_gaussian") else False,
            "show_sim_boundaries_pml": dpg.get_value("show_sim_boundaries_pml") if dpg.does_item_exist("show_sim_boundaries_pml") else False,
            "show_sim_boundaries_absorber": dpg.get_value("show_sim_boundaries_absorber") if dpg.does_item_exist("show_sim_boundaries_absorber") else False,
            "show_sim_boundaries_pmetal": dpg.get_value("show_sim_boundaries_pmetal") if dpg.does_item_exist("show_sim_boundaries_pmetal") else False,
        }
        metadata_path = path / "metadata.txt"
        pywrite_metadata(metadata_path, gds_file_path, volumes, simulation_data, ui_state)
    except Exception as e:
        save_info_err("Error during writing metadata file: " + str(e))
        return

    dpg.configure_item("filepath_info", color=c_good)
    dpg.set_value("filepath_info", "Files successfully saved.")


def _sim_priority_bounds(plot_name):
    # claude
    """
    Bounding box (xmin, xmax, zmin, zmax) to zoom `plot_name` ('XZ' or 'YZ')
    to, chosen by priority:
      1) sim area, if 'show' is checked
      2) boundary, if shown (its outer edge is the same rectangle as the sim
         area, since thickness only ever cuts inward)
      3) gaussian source, if shown (only source type implemented)
      4) volume cross-sections (cached bounding box from the last redraw)
    Returns None if nothing applies (-> leave axis on auto).
    """
    cx, cy, cz = simulation_data.center
    rx, ry, rz = simulation_data.range
    c1, r1, c2, r2 = (cx, rx, cz, rz) if plot_name == 'XZ' else (cy, ry, cz, rz)

    if dpg.does_item_exist('show_sim_range') and dpg.get_value('show_sim_range'):
        half1, half2 = r1 / 2, r2 / 2
        return c1 - half1, c1 + half1, c2 - half2, c2 + half2

    boundary_type_str = dpg.get_value('sim_boundary_type') if dpg.does_item_exist('sim_boundary_type') else None
    boundary_show_tag = {
        SimulationBoundary.PML.value: 'show_sim_boundaries_pml',
        SimulationBoundary.ABSORBER.value: 'show_sim_boundaries_absorber',
        SimulationBoundary.PMETAL.value: 'show_sim_boundaries_pmetal',
    }.get(boundary_type_str)
    if boundary_show_tag and dpg.does_item_exist(boundary_show_tag) and dpg.get_value(boundary_show_tag):
        half1, half2 = r1 / 2, r2 / 2
        return c1 - half1, c1 + half1, c2 - half2, c2 + half2

    source_type_str = dpg.get_value('sim_source_type') if dpg.does_item_exist('sim_source_type') else None
    if (source_type_str == SimulationSource.GAUSS.value
            and dpg.does_item_exist('show_gaussian') and dpg.get_value('show_gaussian')):
        xs, ys, zs = simulation_data.gauss_center
        radius = simulation_data.gauss_waist / 2
        sc1, sc2 = (xs, zs) if plot_name == 'XZ' else (ys, zs)
        return sc1 - radius, sc1 + radius, sc2 - radius, sc2 + radius
    if (source_type_str == SimulationSource.FMODE.value
            and dpg.does_item_exist('show_fmod') and dpg.get_value('show_fmod')):
        xs, ys, zs = simulation_data.fmode_center
        rx, ry, rz = simulation_data.fmode_range
        sc1, sr1, sc2, sr2 = (xs, rx, zs, rz) if plot_name == 'XZ' else (ys, ry, zs, rz)
        half1, half2 = sr1 / 2, sr2 / 2
        return sc1 - half1, sc1 + half1, sc2 - half2, sc2 + half2
    return _volume_bounds.get(plot_name)


def _apply_axis_bounds(plot_name):
    # claude
    """
    Zooms `plot_name` to _sim_priority_bounds(), then releases the axis back
    to auto -- same 'force limits for a frame, then unlock' trick used
    before, just driven by the priority box instead of always the volume
    extents. Must be called BEFORE the corresponding series are (re)added,
    same as the old _apply_limits did.
    """
    hax, vax = plots[plot_name].hax, plots[plot_name].vax
    bounds = _sim_priority_bounds(plot_name)
    if bounds is None:
        dpg.set_axis_limits_auto(hax)
        dpg.set_axis_limits_auto(vax)
        return
    xmin, xmax, zmin, zmax = bounds
    pad_x = (xmax - xmin) * 0.05 or 1
    pad_z = (zmax - zmin) * 0.05 or 1
    dpg.set_axis_limits(hax, xmin - pad_x, xmax + pad_x)
    dpg.set_axis_limits(vax, zmin - pad_z, zmax + pad_z)
    dpg.split_frame()
    dpg.set_axis_limits_auto(hax)
    dpg.set_axis_limits_auto(vax)


def _rect_ring(c1, half1, c2, half2):
    # claude
    """Closed rectangle ring (5 pts, first==last) centered at (c1, c2)."""
    a0, a1 = c1 - half1, c1 + half1
    b0, b1 = c2 - half2, c2 + half2
    return [a0, a1, a1, a0, a0], [b0, b0, b1, b1, b0]


def _draw_sim_area(plot_name, c1, r1, c2, r2):
    # claude
    """White outline, unfilled rectangle representing the simulation box."""
    xs, ys = _rect_ring(c1, r1 / 2, c2, r2 / 2)
    _add_polygon_series(np.array(xs), np.array(ys), parent=plots[plot_name].vax,
                        label="sim area", fill_color=(255, 255, 255, 0),
                        outline_color=(255, 255, 255, 255), lengths=[5],
                        tag=f"sim_area_{plot_name}")


def _boundary_rings(c1, r1, c2, r2, thickness):
    # claude
    """
    thickness > 0: 4 strip-rectangles (left/right full-height, top/bottom
    filling the gap between them) that together tile a hollow frame from
    the outer sim box inward by `thickness`.
    thickness <= 0 (always true for PMETAL, which has no thickness
    control): a single outline ring, since a zero-thickness frame has no
    fillable area.
    """
    half1, half2 = r1 / 2, r2 / 2
    a0, a1 = c1 - half1, c1 + half1
    b0, b1 = c2 - half2, c2 + half2

    if thickness <= 0:
        xs, ys = _rect_ring(c1, half1, c2, half2)
        return [(xs, ys)], True

    t1 = min(thickness, half1)
    t2 = min(thickness, half2)
    ia0, ia1 = a0 + t1, a1 - t1
    ib0, ib1 = b0 + t2, b1 - t2

    rings = [
        ([a0, ia0, ia0, a0, a0], [b0, b0, b1, b1, b0]),
        ([ia1, a1, a1, ia1, ia1], [b0, b0, b1, b1, b0]),
        ([ia0, ia1, ia1, ia0, ia0], [b0, b0, ib0, ib0, b0]),
        ([ia0, ia1, ia1, ia0, ia0], [ib1, ib1, b1, b1, ib1]),
    ]
    return rings, False


def _draw_sim_boundary(plot_name, c1, r1, c2, r2, thickness):
    # claude
    """White boundary: alpha=0.3 filled frame, or outline only for metal (0 thickness)."""
    rings, outline_only = _boundary_rings(c1, r1, c2, r2, thickness)
    xs_all, ys_all, lengths = [], [], []
    for xs, ys in rings:
        xs_all.extend(xs)
        ys_all.extend(ys)
        lengths.append(len(xs))

    if outline_only:
        fill_color = (255, 255, 255, 0)
        outline_color = (255, 255, 255, 255)
    else:
        fill_color = (255, 255, 255, int(0.3 * 255))
        outline_color = (255, 255, 255, 0)

    _add_polygon_series(np.array(xs_all), np.array(ys_all), parent=plots[plot_name].vax,
                        label="sim boundary", fill_color=fill_color, outline_color=outline_color,
                        lengths=lengths, tag=f"sim_boundary_{plot_name}")


def _circle_ring(c1, c2, radius, n=48):
    # claude
    theta = np.linspace(0, 2 * np.pi, n)
    xs = c1 + radius * np.cos(theta)
    ys = c2 + radius * np.sin(theta)
    return xs.tolist(), ys.tolist()


def _make_source_callback(fill_color, circle_len, has_arrow, thickness=1.5):
    # claude
    """Draws the filled, borderless source circle plus an optional direction arrow."""
    def _callback(sender, app_data):
        tx = app_data[1]
        ty = app_data[2]
        dpg.delete_item(sender, children_only=True, slot=2)
        dpg.push_container_stack(sender)

        circle_pts = list(zip(tx[:circle_len], ty[:circle_len]))
        dpg.draw_polygon(circle_pts, fill=fill_color, color=(0, 0, 0, 0), thickness=0)

        if has_arrow:
            center = (tx[circle_len], ty[circle_len])
            tip = (tx[circle_len + 1], ty[circle_len + 1])
            dpg.draw_arrow(tip, center, color=(255, 255, 255, 255), thickness=2, size=8)

        dpg.pop_container_stack()
    return _callback


def _draw_sim_source(plot_name, c1, c2, d1, d2, waist):
    if plots[plot_name].vax == -1:
        return

    xs, ys = _circle_ring(c1, c2, waist / 2)
    circle_len = len(xs)

    has_arrow = False
    norm = float(np.hypot(d1, d2))
    if norm > 1e-9:
        has_arrow = True
        ux, uy = d1 / norm, d2 / norm
        arrow_len = waist * 0.75 if waist > 0 else 1.0
        xs = xs + [c1, c1 + arrow_len * ux]
        ys = ys + [c2, c2 + arrow_len * uy]

    fill_color = (255, 255, 255, int(0.7 * 255))
    dpg.add_custom_series(
        np.array(xs), np.array(ys), 2,
        label="gauss source",
        parent=plots[plot_name].vax,
        callback=_make_source_callback(fill_color, circle_len, has_arrow),
        tag=f"sim_source_{plot_name}"
    )

def _draw_sim_fmode(plot_name, c1, r1, c2, r2):
    # claude
    """White, unfilled rectangle outline for the find-mode (eigenmode)
    source cross-section -- the plane perpendicular to its direction."""
    xs, ys = _rect_ring(c1, r1 / 2, c2, r2 / 2)
    _add_polygon_series(np.array(xs), np.array(ys), parent=plots[plot_name].vax,
                        label="fmode source", fill_color=(255, 255, 255, 0),
                        outline_color=(255, 255, 255, 255), lengths=[5],
                        tag=f"sim_fmode_{plot_name}")


def update_sim_plot():
    # claude
    global simulation_data

    if not dpg.does_item_exist('sim_boundary_type'):    # sim menu not built yet
        return
    # 0) wipe any previously drawn sim-elements (leaves volume plots untouched):
    for tag in ("sim_area_XZ", "sim_area_YZ",
                "sim_boundary_XZ", "sim_boundary_YZ",
                "sim_source_XY", "sim_source_XZ", "sim_source_YZ",
                "sim_fmode_XY", "sim_fmode_XZ", "sim_fmode_YZ"):
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

    if plots['XZ'].vax == -1 or plots['YZ'].vax == -1:  # plots not built yet
        return

    _apply_axis_bounds('XZ')
    _apply_axis_bounds('YZ')

    cx, cy, cz = simulation_data.center
    rx, ry, rz = simulation_data.range

    if dpg.get_value('show_sim_range'):
        _draw_sim_area('XZ', cx, rx, cz, rz)
        _draw_sim_area('YZ', cy, ry, cz, rz)

    # 2) boundary (white, filled alpha=0.3; metal drawn as outline only) - XZ & YZ
    boundary_type_str = dpg.get_value('sim_boundary_type')
    boundary_show_tag = {
        SimulationBoundary.PML.value: 'show_sim_boundaries_pml',
        SimulationBoundary.ABSORBER.value: 'show_sim_boundaries_absorber',
        SimulationBoundary.PMETAL.value: 'show_sim_boundaries_pmetal',
    }.get(boundary_type_str)

    if boundary_show_tag and dpg.get_value(boundary_show_tag):
        thickness = 0.0 if boundary_type_str == SimulationBoundary.PMETAL.value else simulation_data.boundary_thickness
        _draw_sim_boundary('XZ', cx, rx, cz, rz, thickness)
        _draw_sim_boundary('YZ', cy, ry, cz, rz, thickness)

    # 3) source
    source_type_str = dpg.get_value('sim_source_type')
    if source_type_str == SimulationSource.GAUSS.value and dpg.get_value('show_gaussian'):
        xs, ys, zs = simulation_data.gauss_center
        dx, dy, dz = simulation_data.gauss_direction
        w0 = simulation_data.gauss_waist
        _draw_sim_source('XY', xs, ys, dx, dy, w0)
        _draw_sim_source('XZ', xs, zs, dx, dz, w0)
        _draw_sim_source('YZ', ys, zs, dy, dz, w0)
    elif source_type_str == SimulationSource.FMODE.value and dpg.get_value('show_fmod'):   # new
        xs, ys, zs = simulation_data.fmode_center
        rx, ry, rz = simulation_data.fmode_range
        _draw_sim_fmode('XY', xs, rx, ys, ry)
        _draw_sim_fmode('XZ', xs, rx, zs, rz)
        _draw_sim_fmode('YZ', ys, ry, zs, rz)


def _check_boundary_thickness():
    if not dpg.does_item_exist("sim_boundary_info"):
        return
    if dpg.get_value("sim_boundary_type") in (SimulationBoundary.PML.value, SimulationBoundary.ABSORBER.value):
        thickness = simulation_data.boundary_thickness
        if thickness*2 >= np.min(simulation_data.range):
            dpg.configure_item("sim_boundary_info", color=c_warn)
            dpg.set_value("sim_boundary_info", "Warning! Current boundary is thicker than simulation volume, this will cause MEEP to throw an error.")
        elif dpg.get_value("sim_boundary_info") != "":
            dpg.set_value("sim_boundary_info", "")


def update_sim_data(sender, app_data, data):
    global simulation_data
    user_data = data[0]
    info_data = data[1]
    # 1) update sim value
    res = simulation_data.set_property(sender, app_data, user_data)
    # 1.5) set info data to red color and to text from res
    dpg.configure_item(f"{info_data}", color=c_error)
    dpg.set_value(f"{info_data}", f"{res}")
    # 2) update layout (show/hide specific types modules)
    boundary_type = dpg.get_value('sim_boundary_type')
    source_type = dpg.get_value('sim_source_type')
    for i in SimulationSource:
        if i.value == source_type:
            dpg.configure_item(f"source_{i.value}_options", show=True)
        else:
            dpg.configure_item(f"source_{i.value}_options", show=False)
    for i in SimulationBoundary:
        if i.value == boundary_type:
            dpg.configure_item(f"source_{i.value}_options", show=True)
        else:
            dpg.configure_item(f"source_{i.value}_options", show=False)

    update_sim_plot()   # 3) update sim plots
    changed_prop = user_data.args[1] if isinstance(user_data, partial) else None
    if changed_prop in ("range", "boundary_type", "boundary_thickness"):
        _check_boundary_thickness()


def _set_fmode_range(sender, app_data, user_data):
    axis = ['X', 'Y', 'Z'].index(simulation_data.fmode_direction)
    for i in range(3):
        app_data[i] = 0.0 if i == axis else round(max(app_data[i], 0.001), 3)
    update_sim_data(sender, app_data, user_data)
    dpg.set_value("sim_fmode_range", app_data)


def _set_fmode_direction(sender, app_data, user_data):
    axis = ['X', 'Y', 'Z'].index(app_data)
    for i in range(3):
        simulation_data.fmode_range[i] = 0.0 if i == axis else round(max(simulation_data.fmode_range[i], 0.001), 3)
    update_sim_data(sender, simulation_data.fmode_range, [partial(setattr, simulation_data, 'fmode_range'), user_data[1]])
    dpg.set_value("sim_fmode_range", simulation_data.fmode_range)
    update_sim_data(sender, app_data, user_data)

def init_sim_menu():

    with dpg.child_window(height=140):
        with dpg.table(header_row=False, borders_innerH=False, borders_outerH=False,
                       borders_innerV=False, borders_outerV=False):
            dpg.add_table_column(width_fixed=True)
            dpg.add_table_column(width_stretch=True)

            with dpg.table_row():
                dpg.add_text("center (x₀,y₀,z₀):")
                dpg.add_input_floatx(size=3, default_value=simulation_data.center, format='%.3f', width=-1,
                                     callback=update_sim_data, user_data=[partial(setattr, simulation_data, 'center'), 'sim_range_info'],
                                     on_enter=True, tag="sim_center_input")

            with dpg.table_row():
                dpg.add_text("range (Δx,Δy,Δz):")
                dpg.add_input_floatx(size=3, default_value=simulation_data.range, min_value=0.001, format='%.3f',
                                     callback=update_sim_data, user_data=[partial(setattr, simulation_data, 'range'), 'sim_range_info'],
                                     min_clamped=True, width=-1, on_enter=True, tag="sim_range_input")

            with dpg.table_row():
                dpg.add_text("resolution (px/lu):")
                dpg.add_input_float(default_value=simulation_data.resolution, min_value=1, format='%.3f',
                                    callback=update_sim_data, user_data=[partial(setattr, simulation_data, 'resolution'), 'sim_range_info'],
                                    min_clamped=True, step=-1, width=120, max_value=1000, max_clamped=True, on_enter=True, tag="sim_resolution_input")
            #####

        with dpg.group(horizontal=True):
            dpg.add_text("show:")
            dpg.add_checkbox(label=" ", default_value=False, tag='show_sim_range', callback=lambda s, a, u: update_sim_plot())
            dpg.add_text(" ", tag='sim_range_info')
    with dpg.child_window(height=75):
        with dpg.group(horizontal=True):
            dpg.add_text("boundary type:")
            dpg.add_combo(tuple([s.value for s in SimulationBoundary]), default_value=simulation_data.boundary_type.value,
                          callback=update_sim_data, user_data=[partial(setattr, simulation_data, 'boundary_type'), 'sim_boundary_info'],
                          width=150, tag='sim_boundary_type')
            dpg.add_text(" ", tag='sim_boundary_info')
        with dpg.group(show=True, tag=f"source_{SimulationBoundary.PML.value}_options"):
            with dpg.group(horizontal=True):
                dpg.add_text("thickness: ")
                ### changed ###
                # Added tag="sim_boundary_thickness_pml"
                dpg.add_input_float(default_value=simulation_data.boundary_thickness, min_value=0.001, format='%.3f',
                                    callback=update_sim_data, user_data=[partial(setattr, simulation_data, 'boundary_thickness'), 'sim_boundary_info'],
                                    step=-1, width=150, min_clamped=True, on_enter=True, tag="sim_boundary_thickness_pml")
                #####
                dpg.add_text("show:")
                dpg.add_checkbox(label=" ", default_value=False, callback=lambda s, a, u: update_sim_plot(), tag='show_sim_boundaries_pml')
        with dpg.group(show=False, tag=f"source_{SimulationBoundary.ABSORBER.value}_options"):
            with dpg.group(horizontal=True):
                dpg.add_text("thickness: ")
                ### changed ###
                # Added tag="sim_boundary_thickness_absorber"
                dpg.add_input_float(default_value=simulation_data.boundary_thickness, min_value=0.001, format='%.3f',
                                    callback=update_sim_data, user_data=[partial(setattr, simulation_data, 'boundary_thickness'), 'sim_boundary_info'],
                                    step=-1, width=150, min_clamped=True, on_enter=True, tag="sim_boundary_thickness_absorber")
                #####
                dpg.add_text("show:")
                dpg.add_checkbox(label=" ", default_value=False, callback=lambda s, a, u: update_sim_plot(), tag='show_sim_boundaries_absorber')
        with dpg.group(show=False, tag=f"source_{SimulationBoundary.PMETAL.value}_options"):
            with dpg.group(horizontal=True):
                dpg.add_text("show:")
                dpg.add_checkbox(label=" ", default_value=False, callback=lambda s, a, u: update_sim_plot(), tag='show_sim_boundaries_pmetal')

    with dpg.child_window(height=135):
        with dpg.group(horizontal=True):
            dpg.add_text("source type:")
            dpg.add_combo(tuple([s.value for s in SimulationSource]), default_value=simulation_data.source_type.value,
                          callback=update_sim_data, user_data=[partial(setattr, simulation_data, 'source_type'), 'sim_source_info'],
                          width=150, tag='sim_source_type')
            dpg.add_text("wavelength:")

            dpg.add_input_float(default_value=simulation_data.source_wl, min_value=0.001, max_value=1000000,
                                callback=update_sim_data, user_data=[partial(setattr, simulation_data, 'source_wl'), 'sim_source_info'],
                                min_clamped=True, on_enter=True, max_clamped=True, step=-1, width=85, format='%.3f', tag="sim_source_wl")

            dpg.add_text("lu ")
            dpg.add_text(" ", tag='sim_source_info')

        with dpg.group(show=False, tag=f"source_{SimulationSource.GAUSS.value}_options"):
            with dpg.group(horizontal=True):
                dpg.add_text("center (xₛ,yₛ,zₛ): ")
                dpg.add_input_floatx(size=3, default_value=simulation_data.gauss_center, format='%.3f',
                                     callback=update_sim_data, user_data=[partial(setattr, simulation_data, 'gauss_center'), 'sim_source_info'],
                                     width=250, on_enter=True, tag="sim_gauss_center")

                dpg.add_text("direction (x,y,z): ")
                dpg.add_input_floatx(label='', size=3, default_value=simulation_data.gauss_direction,
                                     callback=update_sim_data, user_data=[partial(setattr, simulation_data, 'gauss_direction'), 'sim_source_info'],
                                     format='%.3f', width=250, on_enter=True, tag="gb_beam_kdir")
                dpg.add_text("polarisation (Ex,Ey,Ez): ")
                dpg.add_input_floatx(label="", size=3, default_value=simulation_data.gauss_polarisation,
                                     callback=update_sim_data, user_data=[partial(setattr, simulation_data, 'gauss_polarisation'), 'sim_source_info'],
                                     format='%.3f', width=250, tag="gb_beam_E0", on_enter=True)
            with dpg.group(horizontal=True):
                dpg.add_text("waist w₀: ")
                dpg.add_input_float(label="", default_value=simulation_data.gauss_waist, format='%.3f',
                                    callback=update_sim_data, user_data=[partial(setattr, simulation_data, 'gauss_waist'), 'sim_source_info'],
                                    min_value=0.001, min_clamped=True, width=60, step=-1, tag="gb_w0", on_enter=True)
                dpg.add_text("lu")

            with dpg.group(horizontal=True):
                dpg.add_text("show:")
                dpg.add_checkbox(label='', default_value=False, callback=lambda s, a, u: update_sim_plot(), tag='show_gaussian')

        with dpg.group(show=False, tag=f"source_{SimulationSource.PWAVE.value}_options"):
            dpg.add_text("not supported")

        with dpg.group(show=False, tag=f"source_{SimulationSource.FMODE.value}_options"):
            with dpg.group(horizontal=True):
                dpg.add_text("center (xₛ,yₛ,zₛ): ")
                dpg.add_input_floatx(size=3, default_value=simulation_data.fmode_center, format='%.3f',
                                     callback=update_sim_data,
                                     user_data=[partial(setattr, simulation_data, 'fmode_center'), 'sim_source_info'],
                                     width=250, on_enter=True, tag="sim_fmode_center")

                dpg.add_text("range (Δx,Δy,Δz): ")
                dpg.add_input_floatx(size=3, default_value=simulation_data.fmode_range, format='%.3f',
                                     callback=_set_fmode_range,                                    # changed
                                     user_data=[partial(setattr, simulation_data, 'fmode_range'), 'sim_source_info'],
                                     width=250, on_enter=True, tag="sim_fmode_range")
                dpg.add_text("direction (x,y,z): ")
                dpg.add_combo(tuple(["X", "Y","Z"]), default_value=simulation_data.fmode_direction,
                              callback=_set_fmode_direction,                                        # changed
                              user_data=[partial(setattr, simulation_data, 'fmode_direction'), 'sim_source_info'],
                              width=50, tag='fm_beam_kdir')
                dpg.add_text("band: ")
                dpg.add_input_int(width=75, tag="sim_fmode_band",callback=update_sim_data, default_value=simulation_data.fmode_band,
                                  user_data=[partial(setattr, simulation_data, 'fmode_band'), 'sim_source_info'],step=-1)

            with dpg.group(horizontal=True):
                dpg.add_text("show:")
                dpg.add_checkbox(label='', default_value=False, callback=lambda s, a, u: update_sim_plot(),
                                 tag='show_fmod')

        with dpg.group(show=True, tag=f"source_{SimulationSource.NONE.value}_options"):
            pass

    with dpg.child_window(height=45):
        with dpg.group(horizontal=True):
            dpg.add_text("Symmetry:")
            dpg.add_text("(not implemented yet)")


def create_table():
    global vol_tab
    vol_tab = dpg.add_table(width=-1, height=110, header_row=True, no_host_extendX=True,
                            borders_innerH=True, borders_outerH=True, borders_innerV=True,
                            borders_outerV=True, context_menu_in_body=True, row_background=True,
                            policy=dpg.mvTable_SizingFixedFit,
                            scrollY=True)
    with dpg.group(horizontal=True):
        dpg.add_button(label=" ADD VOLUME ", callback=_add_volume, tag="vol_add")
        dpg.add_button(label=" REMOVE ALL VOLUMES ", callback=_remove_volumes, tag="vol_remove")

    dpg.add_table_column(label="ID", parent=vol_tab)
    dpg.add_table_column(label="status", parent=vol_tab)
    dpg.add_table_column(label="layer", parent=vol_tab)
    dpg.add_table_column(label="material", parent=vol_tab)
    dpg.add_table_column(label="base position", parent=vol_tab)
    dpg.add_table_column(label="height", parent=vol_tab)
    dpg.add_table_column(label="prism angle (°)", parent=vol_tab)
    dpg.add_table_column(label="move up/down", parent=vol_tab)
    dpg.add_table_column(label="remove", parent=vol_tab)
    dpg.add_table_column(label=" ", parent=vol_tab)


def _redraw_volumes():
    global vol_tab, layers
    if vol_tab is None:
        return
    dpg.delete_item(vol_tab, children_only=True, slot=1)
    for v in volumes:
        with dpg.table_row(parent=vol_tab):
            dpg.add_text(f"{v.lid}")
            dpg.add_text("●", tag=f"ready_{v.lid}")
            if v.ready:
                dpg.configure_item(f"ready_{v.lid}", color=c_good)
            else:
                dpg.configure_item(f"ready_{v.lid}", color=c_error)

            with dpg.group(horizontal=True):
                dpg.add_combo(tuple(layers.keys()), callback=_set_layer, user_data=v, default_value=v.layer, width=100, label="")

            with dpg.group(horizontal=True):
                dpg.add_combo(tuple(MATERIAL_LIST.keys()), width=150, callback=_set_material, user_data=v, default_value=v.material, label="")
                dpg.add_input_float(on_enter=True, default_value=v.wavelength_nm, callback=_set_material_wl, user_data=v, format='%.2f', min_value=0.01,
                                    max_value=1000000, min_clamped=True, max_clamped=True, step=-1, width=85)
                dpg.add_text("nm")
            dpg.add_input_float(on_enter=True, default_value=v.base, callback=_set_volume_base, user_data=v, format='%.3f', step=-1, width=85)
            dpg.add_input_float(on_enter=True, default_value=v.height, callback=_set_volume_height, user_data=v, format='%.3f',
                                step=-1, width=85, tag=f"vol_height_{v.lid}")

            with dpg.group(horizontal=True):
                dpg.add_input_int(on_enter=True, default_value=v.angle_deg, min_value=-89, max_value=89, min_clamped=True,
                                  max_clamped=True, step=-1, width=40, callback=_set_volume_angle_deg, user_data=v)

            with dpg.group(horizontal=True):
                dpg.add_button(label="", callback=_move_volume, user_data=[True, v], arrow=True, direction=dpg.mvDir_Up)
                dpg.add_button(label="", callback=_move_volume, user_data=[False, v], arrow=True, direction=dpg.mvDir_Down)

            dpg.add_button(label="X", callback=_remove_volume, user_data=v)
            dpg.add_text(" ", tag=f"comment_{v.lid}")

def _check_volume(volume):
    if volume.material != " " and volume.layer != " ":
        if volume.layer in layers:
            try:
                MATERIAL_LIST[volume.material](volume.wavelength_nm / 1000).epsilon(1 / volume.wavelength_nm * 1000)
                if dpg.does_item_exist(f"comment_{volume.lid}"):
                    dpg.set_value(f"comment_{volume.lid}", f" ")
                volume.ready = True
                if dpg.does_item_exist(f"ready_{volume.lid}"):
                    dpg.configure_item(f"ready_{volume.lid}", color=c_good)
            except Exception as e:
                volume.ready = False
                if dpg.does_item_exist(f"ready_{volume.lid}"):
                    dpg.configure_item(f"ready_{volume.lid}", color=c_error)
                if dpg.does_item_exist(f"comment_{volume.lid}"):
                    dpg.configure_item(f"comment_{volume.lid}", color=c_error)
                    dpg.set_value(f"comment_{volume.lid}", f"Error: {e}")
                return
    else:
        volume.ready = False
        if dpg.does_item_exist(f"ready_{volume.lid}"):
            dpg.configure_item(f"ready_{volume.lid}", color=c_error)


def _scan_intervals(points, coord, axis):
    # claude
    """
    Scanline-slice ONE closed polygon ring (Nx2 array, first point == last
    point) with an infinite slicing line, using the even-odd edge-crossing
    rule.

    axis == 0 -> slicing line is VERTICAL   (x == coord), returns Y-intervals
    axis == 1 -> slicing line is HORIZONTAL (y == coord), returns X-intervals
    """
    crossings = []
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        a0, b0 = (x0, y0) if axis == 0 else (y0, x0)
        a1, b1 = (x1, y1) if axis == 0 else (y1, x1)
        if a0 == a1:
            continue    # edge parallel to the slicing line -> no crossing
        if (a0 <= coord < a1) or (a1 <= coord < a0):
            t = (coord - a0) / (a1 - a0)
            crossings.append(b0 + t * (b1 - b0))    # basically points on the axis where crossing occured, interpolated
                                                    # linearly based on the point location
    crossings.sort() # sorting, because we want points in order they occur in crossing, always

    # basically list of intervals for volume basis:
    return [(crossings[i], crossings[i + 1]) for i in range(0, len(crossings) - 1, 2)]


def _merge_intervals(intervals):
    # claude
    """Merge overlapping/touching (lo, hi) tuples into a minimal set."""
    # while _scan_intervals only works on one polygon, a layer can have multiple of them
    if not intervals:
        return []

    # protection agains overlapping polygons, shouldn't happen, but if polygons overlap I assume they are
    # one polygon, and when they only touch i assume they are separate
    intervals = sorted(intervals) # sorts intervals based on 1srt coordinate and then second
    merged = [list(intervals[0])] # puts 1st interval to the list of all intervals
    for lo, hi in intervals[1:]:
        if lo < merged[-1][1]: # if following interval starts before or at the previous interval ends...
            merged[-1][1] = max(merged[-1][1], hi) #...extend the previous interval if the next one finishes before it or do nothing
        else:
            merged.append([lo, hi]) #...else add this new, not overlapping material

    return [tuple(m) for m in merged]


def _layer_slice_intervals(layer_name, coord, axis):
    # claude
    """Union of slice intervals across every shape belonging to a GDS layer."""
    layer = layers.get(layer_name)
    if layer is None or not layer.shapes:
        return []
    intervals = []
    for shape in layer.shapes:
        intervals.extend(_scan_intervals(shape, coord, axis))
    return _merge_intervals(intervals)


def _get_material_color(material):
    # claude
    """Assigns/returns a stable color for a material name (same palette fn as layers use)."""
    if material not in material_colors:
        material_colors[material] = get_c_material(material)
    return material_colors[material]


def _volume_cross_section(volume, coord, axis):
    # crazy miz of me, claude, gemini
    base_intervals = _layer_slice_intervals(volume.layer, coord, axis) # retrieve intervals for given axis
    if not base_intervals:
        return np.array([]), np.array([]), []
    free_vals, z_vals, lengths = [], [], []
    for interval in base_intervals:
        half_base_length = (interval[1] - interval[0])/2
        length = 3
        free_vals.extend([interval[0], interval[1]])
        z_vals.extend([volume.base, volume.base])

        # 2) append top 1 or two points (trapezoid vs triangle)
        to_add = volume.height * np.tan(np.radians(volume.angle_deg))
        if -to_add >= half_base_length:
            free_vals.append((interval[0]+ interval[1])/2)
            new_height = half_base_length * np.tan(np.radians(90 + volume.angle_deg))
            z_vals.append(new_height+volume.base)
            length += 1
        else:
            free_vals.extend([interval[1]+to_add, interval[0]-to_add])
            z_vals.extend([volume.base+volume.height, volume.base+volume.height])
            length+=2
        # 3) repeat 1st base point
        free_vals.append(interval[0])
        z_vals.append(volume.base)
        # 4) set the length
        lengths.append(length)

    return np.array(free_vals), np.array(z_vals), lengths


def _toggle_legend_item(_, app_data, user_data):
    kind, name = user_data
    target = hidden_layers if kind == "layer" else hidden_materials
    if app_data:
        # row is now selected -> visible
        target.discard(name)
    else:
        # row was unselected -> hide
        target.add(name)
    _redraw_volume_plots()


def _redraw_legends():
    # claude
    """(Re)builds the two clickable legends shown under the XZ/YZ plots."""
    if not dpg.does_item_exist("layer_legend_group") or not dpg.does_item_exist("material_legend_group"):
        return

    dpg.delete_item("layer_legend_group", children_only=True)
    dpg.delete_item("material_legend_group", children_only=True)

    used_layers = sorted({v.layer for v in volumes if v.ready})
    used_materials = sorted({v.material for v in volumes if v.ready})

    for name in used_layers:
        color = layers[name].color if layers.get(name) else (255, 255, 255)
        visible = name not in hidden_layers
        with dpg.group(horizontal=True, parent="layer_legend_group"):
            dpg.add_text("●", color=(*color[:3], 255 if visible else 60))
            dpg.add_selectable(label=f"{name}", default_value=visible,
                               callback=_toggle_legend_item, user_data=("layer", name))

    for name in used_materials:
        color = _get_material_color(name)
        visible = name not in hidden_materials
        with dpg.group(horizontal=True, parent="material_legend_group"):
            dpg.add_text("●", color=(*color[:3], 255 if visible else 60))
            dpg.add_selectable(label=f"{name}", default_value=visible,
                               callback=_toggle_legend_item, user_data=("material", name))


def _redraw_volume_plots():
    if plots['XZ'].vax == -1 or plots['YZ'].vax == -1:
        return

    dpg.delete_item(plots['XZ'].vax, children_only=True)
    dpg.delete_item(plots['YZ'].vax, children_only=True)

    to_draw = []
    xz_x, xz_z, yz_x, yz_z = [], [], [], []

    for v in volumes[::-1]:
        if not v.ready or v.layer in hidden_layers or v.material in hidden_materials:
            continue
        layer_color = layers[v.layer].color if layers.get(v.layer) else (255, 255, 255)
        material_color = _get_material_color(v.material)
        fill_color = (*material_color[:3], 255)
        outline_color = (*layer_color[:3], 255)

        xs1, ys1, len1 = _volume_cross_section(v, h_slider_pos, axis=1)
        xs2, ys2, len2 = _volume_cross_section(v, v_slider_pos, axis=0)
        to_draw.append((xs1, ys1, len1, xs2, ys2, len2, fill_color, outline_color, v.lid))
        if len(xs1): xz_x.extend(xs1); xz_z.extend(ys1)
        if len(xs2): yz_x.extend(xs2); yz_z.extend(ys2)
    # cache volume-only bounding box (lowest-priority zoom fallback),
    # then zoom via priority (range > boundary > source > volume) instead of
    # always zooming to the volume extents
    _volume_bounds['XZ'] = (min(xz_x), max(xz_x), min(xz_z), max(xz_z)) if xz_x else None
    _volume_bounds['YZ'] = (min(yz_x), max(yz_x), min(yz_z), max(yz_z)) if yz_x else None
    _apply_axis_bounds('XZ')
    _apply_axis_bounds('YZ')

    _redraw_legends()
    update_sim_plot()

    for xs1, ys1, len1, xs2, ys2, len2, fill_color, outline_color, lid in to_draw:
        if len1:
            _add_polygon_series(xs1, ys1, parent=plots['XZ'].vax, label=f"vol {lid}",
                                 fill_color=fill_color, outline_color=outline_color, lengths=len1)
        if len2:
            _add_polygon_series(xs2, ys2, parent=plots['YZ'].vax, label=f"vol {lid}",
                                 fill_color=fill_color, outline_color=outline_color, lengths=len2)

    _redraw_legends()
    update_sim_plot()


def _set_material(_, material, volume):
    volume.material = material
    _check_volume(volume)
    _redraw_volume_plots()


def _set_material_wl(_, wavelength_nm, volume):
    volume.wavelength_nm = round(wavelength_nm, 2)
    _check_volume(volume)
    _redraw_volume_plots()


def _set_volume_base(_, base, volume):
    volume.base = round(base,3)
    _redraw_volume_plots()


def _set_volume_height(_, height, volume):
    height = round(height,3)
    if height == 0:
        height = 0.001
    volume.height = height
    dpg.set_value(f"vol_height_{volume.lid}", height)
    _redraw_volume_plots()

def _set_volume_angle_deg(_, angle_deg, volume):
    volume.angle_deg = angle_deg
    _redraw_volume_plots()

def _set_layer(_,layer,volume):
    volume.layer = layer
    _check_volume(volume)
    _redraw_volume_plots()

def _move_volume(_, __, args):
    up = args[0]
    volume = args[1]
    i = volumes.index(volume)
    n = len(volumes)
    j = (i - 1) % n if up else (i + 1) % n
    volumes[i], volumes[j] = volumes[j], volumes[i]
    _redraw_volumes()
    _redraw_volume_plots()


def _remove_volume(_,__,volume):
    volumes.remove(volume)
    _redraw_volumes()
    _redraw_volume_plots()


def _remove_volumes():
    global last_id
    volumes.clear()
    last_id = 0
    _redraw_volumes()
    _redraw_volume_plots()

def _add_volume():
    global last_id
    volumes.insert(0, Volume(lid=last_id))
    last_id += 1
    _redraw_volumes()

def _add_crosshair_sliders(plot_id):
    global h_slider_pos, v_slider_pos
    dpg.add_drag_line(
        parent=plot_id,
        color=c_v_slider,
        vertical=True,
        default_value=v_slider_pos,
        callback=slider_change,
        tag="v_slider"
    )
    dpg.add_drag_line(
        parent=plot_id,
        color=c_h_slider,
        vertical=False,
        default_value=h_slider_pos,
        callback=slider_change,
        tag="h_slider"
    )

def slider_change():
    global h_slider_pos, v_slider_pos
    dpg.configure_item("h_slider", callback=None)
    dpg.configure_item("v_slider", callback=None)

    v_slider_pos = dpg.get_value("v_slider")
    h_slider_pos = dpg.get_value("h_slider")
    _redraw_volume_plots()

    dpg.configure_item("h_slider", callback=slider_change)
    dpg.configure_item("v_slider", callback=slider_change)

def _make_polygon_callback(fill_color, outline_color, lengths, thickness=1.5):
    def _callback(sender, app_data):
        transformed_x = app_data[1]
        transformed_y = app_data[2]

        dpg.delete_item(sender, children_only=True, slot=2)
        dpg.push_container_stack(sender)

        idx = 0
        for length in lengths:
            xs_poly = transformed_x[idx:idx + length]
            ys_poly = transformed_y[idx:idx + length]
            points = list(zip(xs_poly, ys_poly))
            dpg.draw_polygon(points, fill=fill_color, color=outline_color, thickness=thickness)
            idx += length

        dpg.pop_container_stack()
    return _callback


def _add_polygon_series(xs, ys, parent, label, fill_color, outline_color, lengths, thickness=1.5, tag=0):
    return dpg.add_custom_series(
        xs, ys, 2,
        label=label,
        parent=parent,
        callback=_make_polygon_callback(fill_color, outline_color, lengths, thickness),
        tag=tag
    )

def init_plots():
    with dpg.subplots(1, 3, label="", width=-1, height=500, no_resize=True) as subplot_id:
        for i in range(3):
            with dpg.plot(label=f"{plot_names[i]}", no_title=False) as plot_id:
                plots[plot_names[i]].pid = plot_id
                plots[plot_names[i]].hax = dpg.add_plot_axis(dpg.mvXAxis, label=f"{plot_names[i][0]}", invert=(plot_names[i] == 'YZ'))
                plots[plot_names[i]].vax = dpg.add_plot_axis(dpg.mvYAxis, label=f"{plot_names[i][1]}")
                dpg.add_plot_legend(parent=plot_id)

    with dpg.collapsing_header(label="Volume Legend"):
        with dpg.group(horizontal=True):
            with dpg.group():
                dpg.add_text("Layers:")
                dpg.add_group(tag="layer_legend_group", width=150)
            with dpg.group():
                dpg.add_text("Materials:")
                dpg.add_group(tag="material_legend_group", width=150)


def load_gds():
    global layers, color_count, gds_file_path
    gds_file_path = ''
    dpg.set_value("filepath_info", "")
    path = Path(dpg.get_value("filepath"))

    if path.is_file() and path.suffix.lower() == ".gds":
        try:
            [dpg.delete_item(plots[pn].vax, children_only=True) for pn in plot_names]
            for tag in ("v_slider", "h_slider"):
                if dpg.does_item_exist(tag):
                    dpg.delete_item(tag)
            layers = {' ': None}
            color_count = 0
            shapes = gdstk.read_gds(path).top_level()[0]

            for poly in shapes.get_polygons():
                assert isinstance(poly.layer, int), "Unexpected: layer is not int"
                name = str(poly.layer)
                if name not in layers.keys():
                    layers[name] = Layer()
                    layers[name].shapes = []
                    color_count += 1
                    layers[name].color = get_c_layer(color_count)

                closed_pts = np.vstack([poly.points, poly.points[0]])
                layers[name].shapes.append(np.array(closed_pts))

            for name, layer in layers.items():
                if layer is None: continue
                combined_x = np.concatenate([s[:, 0] for s in layer.shapes])
                combined_y = np.concatenate([s[:, 1] for s in layer.shapes])
                lengths = [len(s) for s in layer.shapes]

                _add_polygon_series(
                    combined_x, combined_y, parent=plots['XY'].vax,
                    label=f"layer {name}",
                    fill_color=(*layer.color, 30),
                    outline_color=(*layer.color, 255),
                    lengths=lengths
                )

            dpg.fit_axis_data(plots['XY'].hax)
            dpg.fit_axis_data(plots['XY'].vax)

            _add_crosshair_sliders(plots['XY'].pid)
            gds_file_path = dpg.get_value("filepath")
        except Exception as e:
            dpg.configure_item("filepath_info", color=c_error)
            dpg.set_value("filepath_info", f"Error during processing the file: {e}")
            return
        for v in volumes:
            _check_volume(v)
        _redraw_volume_plots()
        _redraw_volumes()

    else:
        dpg.configure_item("filepath_info", color=c_error)
        dpg.set_value("filepath_info", "Please give absolute path to gds file")


def init_dpg():
    screen_w, screen_h = pyautogui.size()
    width, height = screen_w//2, int(screen_h//1.7)

    dpg.create_viewport(title="GDStoMEEP", width=width, height=height)
    dpg.set_viewport_small_icon("./icon.png")
    dpg.set_viewport_large_icon("./icon.png")
    dpg.setup_dearpygui()
    dpg.set_viewport_pos([(screen_w - width) // 2, (screen_h - height) // 2])
    dpg.show_viewport()

    dpg.set_primary_window("Primary Window", True)

    dpg.start_dearpygui()
    dpg.destroy_context()