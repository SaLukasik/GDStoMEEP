import meep as mp
import numpy as np
from meep.materials import LiNbO3, SiO2
import refidx as rd

# File with functions defying optical properties of the media.
# TO add new medium, define it as a function of wavelength that returns MEEP medium* object AND
# remember to add it to the MATERIAL_LIST at the end of the file (see examples below).
# Function name will be used in the app as material name. Fun fact: material color is generated based on it's name
# with a having function, so if you don't like it, you can change the name a little and see if new one suits you better.

# *Example of MEEP medium. Frequency is defined as 1/wl in the medium, wl is given in local units, same as volumes:
#LINBO3_MEDIUM = mp.Medium(epsilon_diag=mp.Vector3(*[LiNbO3.epsilon(freq)[i][i].real for i in range(3)]))

def medium_linbo3_z(wl_um=1.55):
    return mp.Medium(epsilon_diag=mp.Vector3(*[LiNbO3.epsilon(1/wl_um)[i][i].real for i in range(3)]))


def medium_linbo3_x(wl_um=1.55):
    diag = [LiNbO3.epsilon(1/wl_um)[i][i].real for i in range(3)]
    diag[0], diag[2] = diag[2], diag[0]
    return mp.Medium(epsilon_diag=mp.Vector3(*diag))


def medium_linbo3_y(wl_um=1.55):
    diag = [LiNbO3.epsilon(1/wl_um)[i][i].real for i in range(3)]
    diag[1], diag[2] = diag[2], diag[1]
    return mp.Medium(epsilon_diag=mp.Vector3(*diag))


def medium_sio2(wl_um=1.55):
    return mp.Medium(epsilon_diag=mp.Vector3(*[SiO2.epsilon(1/wl_um)[i][i].real for i in range(3)]))


def medium_si(wl_um=1.55):
    si = rd.DataBase().materials["main"]["Si"]["Franta"]
    si_eps = np.real(si.get_index(wl_um)**2)
    return mp.Medium(epsilon_diag=mp.Vector3(si_eps,si_eps,si_eps))


MATERIAL_LIST = {" ":None,"LiNbO3_z": medium_linbo3_z, "LiNbO3_y":medium_linbo3_y, "LiNbO3_x": medium_linbo3_x, "SiO2": medium_sio2, "Si": medium_si}

