import math
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
