#!/usr/bin/env python
import numpy as np
import sys
Vsun = -26.74
Rsat = 1.0                      # Radius of the satellite orbit in AU.
Rsun = 1.0                      # Radius of the Earth orbit in AU.
Rneo = 1.3                      # Radius of the maximum perihelion in AU.
Albd = 0.13                     # Albedo of the NEO surface.
AU   = 1.496e11                 # Astromonical Unit in meter.
try:
    Dneo = eval(sys.argv[1])
except:
    Dneo = 140.0                # Diameter of the NEO in meter.
Vneo = -2.5*np.log10((Albd*(Dneo/(Rneo*AU))**2.0)/(16.0*(Rneo-Rsat)**2.0))+Vsun
print Vneo
