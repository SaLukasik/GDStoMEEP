import colorsys
import zlib

# File with helpers responsible for color handling in the app, for example colors of info messages.

c_warn = (255,255,0)
c_error = (255,0,0)
c_good  = (0,255,0)
c_v_slider = (0,255,0)
c_h_slider = (0,255,0)

#### Claude ####
def get_c_layer(i: int) -> tuple[int, int, int]:
    """
    Return a unique, colorblind-friendly RGB color tuple for a given index.
    Uses the Okabe-Ito palette (colorblind-safe, minus black) for the first
    7 colors, then falls back to procedurally generated hues for indices
    beyond that — kept saturated/bright so nothing drifts toward gray.
    """
    okabe_ito = [
        (0, 158, 115),    # bluish green
        (230, 159, 0),    # orange
        (86, 180, 233),   # sky blue
        (240, 228, 66),   # yellow
        (0, 114, 178),    # blue
        (213, 94, 0),     # vermillion
        (204, 121, 167),  # reddish purple
    ]

    if i < len(okabe_ito):
        return okabe_ito[i]

    golden_angle = 0.6180339887498949
    idx = i - len(okabe_ito)
    cycle = idx // 12

    hue = (idx * golden_angle) % 1.0
    sat = 0.75 + 0.15 * (cycle % 2)          # stays high — avoids gray/pastel
    val = 0.90 - 0.10 * ((cycle // 2) % 2)   # stays bright — avoids muddy/dark

    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return (int(r * 255), int(g * 255), int(b * 255))


#### Claude ####
def get_c_material(m: str) -> tuple[int, int, int]:
    """
    Hashing function that generates unique color based on string. Designed to
    avoid non-saturated colors. Hashing designed to support ~50 unique
    materials.
    """
    # 1. Deterministic hashing (consistent across Python executions)
    hash_val = zlib.crc32(m.encode("utf-8"))

    # 2. Map hash through Golden Ratio for optimal hue distribution
    golden_ratio = 0.6180339887498949
    hue = (hash_val * golden_ratio) % 1.0

    # 3. Derive Saturation (0.70 - 0.95) and Value (0.80 - 1.00) from higher bits
    # Keeps colors vibrant while adding variance so similar hues stay distinct
    sat = 0.70 + ((hash_val >> 8) % 26) / 100.0
    val = 0.80 + ((hash_val >> 16) % 21) / 100.0

    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return (int(r * 255), int(g * 255), int(b * 255))