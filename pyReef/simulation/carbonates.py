##~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~##
##                                                                                   ##
##  This file forms part of the pyReef carbonate platform modelling application.     ##
##                                                                                   ##
##  For full license and copyright information, please refer to the LICENSE.md file  ##
##  located at the project root, or contact the authors.                             ##
##                                                                                   ##
##~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~##
"""
This module encapsulates functions related to carbonate production and disintegration in pyReef model.
"""

import time
import math
import numpy
import pandas as pd
import skfuzzy as fuzz
import mpi4py.MPI as mpi
from scipy import interpolate
from scipy.interpolate import interpn
from scipy.ndimage.filters import gaussian_filter

from pyReef.libUtils  import simswan as swan
from pyReef.libUtils  import diffusion as diffu

from scipy import interpolate
from scipy.ndimage.filters import gaussian_filter

class carbonates:

    def __init__(self, input, partIDs):
        """
        Constructor.
        """

        self.rank = mpi.COMM_WORLD.rank
        self.size = mpi.COMM_WORLD.size
        self.comm = mpi.COMM_WORLD
        self.fcomm = mpi.COMM_WORLD.py2f()

        self.partIDs = partIDs

        if self.rank == 0:
            self.i1 = self.partIDs[self.rank,0]+1
        else:
            self.i1 = self.partIDs[self.rank,0]
        if self.rank == self.size-1:
            self.i2 = self.partIDs[self.rank,1]
        else:
            self.i2 = self.partIDs[self.rank,1]+1

        self.faciesNb = int(input.faciesNb/2)

        # Read and allocate membership functions
        # Depth related MBF
        self.mbfDepthNb = input.mbfDepthNb
        self.mbfDepthName = input.mbfDepthName
        self.MBFdepth = []
        self.MBFdepthFuzz = []
        for m in range(self.mbfDepthNb):
            df = pd.read_csv(input.mbfDepthFile[m], sep=' ', header=None, names=['X','Y'])
            self.MBFdepth.append(df['X'].values)
            self.MBFdepthFuzz.append(df['Y'].values)
        # Wave related MBF
        self.mbfWaveNb = input.mbfWaveNb
        self.mbfWaveName = input.mbfWaveName
        self.MBFwave = []
        self.MBFwaveFuzz = []
        for m in range(self.mbfWaveNb):
            df = pd.read_csv(input.mbfWaveFile[m], sep=' ', header=None, names=['X','Y'])
            self.MBFwave.append(df['X'].values)
            self.MBFwaveFuzz.append(df['Y'].values)
        # Sedimentation related MBF
        self.mbfSedNb = input.mbfSedNb
        self.mbfSedName = input.mbfSedName
        self.MBFsed = []
        self.MBFsedFuzz = []
        for m in range(self.mbfSedNb):
            df = pd.read_csv(input.mbfSedFile[m], sep=' ', header=None, names=['X','Y'])
            self.MBFsed.append(df['X'].values)
            self.MBFsedFuzz.append(df['Y'].values)
        # Production related MBF
        self.mbfProdNb = input.mbfProdNb
        self.mbfProdName = input.mbfProdName
        self.MBFprodFuzz = []
        for m in range(self.mbfProdNb):
            df = pd.read_csv(input.mbfProdFile[m], sep=' ', header=None, names=['X','Y'])
            self.MBFprod = df['X']
            self.MBFprodFuzz.append(df['Y'].values)
        # Disintegration related MBF
        self.mbfDisNb = input.mbfDisNb
        self.mbfDisName = input.mbfDisName
        self.MBFdisFuzz = []
        for m in range(self.mbfDisNb):
            df = pd.read_csv(input.mbfDisFile[m], sep=' ', header=None, names=['X','Y'])
            self.MBFdis = df['X']
            self.MBFdisFuzz.append(df['Y'].values)

        # Define fuzzy rules
        self.fuzzNb = input.fuzzNb
        self.fuzzHabitat = input.fuzzHabitat
        self.fuzzDepth = input.fuzzDepth
        self.fuzzWave = input.fuzzWave
        self.fuzzSed = input.fuzzSed
        self.fuzzProd = input.fuzzProd
        self.fuzzDis = input.fuzzDis

        return

    def interpret_MBF(self, elev, wave, sed):
        """
        Based on the membership functions, we define the fuzzy relationship between input and output variables.

        Parameters
        ----------

        variable : elev
            Elevation data from pyReef simulation grid.

        variable : wave
            Average wave energy data obtained from climatic forcing.

        variable : sed
            Sedimentation since last call.
        """

        shape = elev.shape
        prod = numpy.zeros(shape[0],shape[1],self.faciesNb)
        dis = numpy.zeros(shape[0],shape[1],self.faciesNb)
        for i in range(self.i1,self.i2):
           for j in range(1,shape[1]-1):
               depthIM = numpy.zeros(self.mbfDepthNb)
               waveIM = numpy.zeros(self.mbfDepthNb)
               sedIM = numpy.zeros(self.mbfDepthNb)
               for m in range(self.mbfDepthNb):
                   if -elev[i,j] > self.MBFdepth[m].max():
                       depthIM[m] = fuzz.interp_membership(self.MBFdepth[m], self.MBFwaveFuzz[m], self.MBFdepth[m].max())
                   elif -elev[i,j] < self.MBFdepth[m].min():
                       depthIM[m] = fuzz.interp_membership(self.MBFdepth[m], self.MBFwaveFuzz[m], self.MBFdepth[m].min())
                   else:
                       depthIM[m] = fuzz.interp_membership(self.MBFdepth[m], self.MBFwaveFuzz[m], -elev[i,j])

               for m in range(self.mbfWaveNb):
                   if wave[i,j] > self.MBFwave[m].max():
                       waveIM[m] = fuzz.interp_membership(self.MBFwave[m], self.MBFwaveFuzz[m], self.MBFwave[m].max())
                   elif wave[i,j] < self.MBFwave[m].min():
                       waveIM[m] = fuzz.interp_membership(self.MBFwave[m], self.MBFwaveFuzz[m], self.MBFwave[m].min())
                   else:
                       waveIM[m] = fuzz.interp_membership(self.MBFwave[m], self.MBFwaveFuzz[m], wave[i,j])

               for m in range(self.mbfSedNb):
                   if sed[i,j] > self.MBFsed[m].max():
                       sedIM[m] = fuzz.interp_membership(self.MBFsed[m], self.MBFsedFuzz[m], self.MBFsed[m].max())
                   elif sed[i,j] < self.MBFsed[m].min():
                       sedIM[m] = fuzz.interp_membership(self.MBFsed[m], self.MBFsedFuzz[m], self.MBFsed[m].min())
                   else:
                       sedIM[m] = fuzz.interp_membership(self.MBFsed[m], self.MBFsedFuzz[m], sed[i,j])

               prod[i,j,:],dis[i,j,:] = self._fuzzyRules_activation(depthIM, waveIM, sedIM)

        tmp = prod.reshape(shape[0]*shape[1]*self.faciesNb)
        self.comm.Allreduce(mpi.IN_PLACE, tmp, op=mpi.MAX)
        self.prod = tmp.reshape(shape[0],shape[1],sedNb)

        tmp = dis.reshape(shape[0]*shape[1]*self.faciesNb)
        self.comm.Allreduce(mpi.IN_PLACE, tmp, op=mpi.MAX)
        self.dis = tmp.reshape(shape[0]*shape[1]*self.faciesNb)

        return

    def _fuzzyRules_activation(self, depthIM, waveIM, sedIM):
        """
        Compute fuzzy logic rules.

        Parameters
        ----------

        variable : depthIM
            Membership function interpreted depth value.

        variable : wave
            Membership function interpreted wave value.

        variable : sed
            Membership function interpreted sedimentation value.
        """

        tmp_prod = numpy.zeros(int(self.faciesNb))
        tmp_dis = numpy.zeros(int(self.faciesNb))
        for s in range(int(self.faciesNb)):
            dislist = []
            prodlist = []
            rule = []
            for r in range(self.fuzzNb):
                d = -1
                if self.fuzzHabitat[r] == s:
                    if self.fuzzDepth[r]>=0:
                        d = 0
                        tmp_active = depthIM[self.fuzzDepth[r]]
                    if self.fuzzWave[r]>=0:
                        if d == -1:
                            tmp_active = waveIM[self.fuzzWave[r]]
                            d = 0
                        else:
                            tmp_active = numpy.fmin(tmp_active,waveIM[self.fuzzWave[r]])
                    if self.fuzzSed[r]>=0:
                        if d == -1:
                            tmp_active = sedIM[self.fuzzSed[r]]
                            d = 0
                        else:
                            tmp_active = numpy.fmin(tmp_active,sedIM[self.fuzzSed[r]])
                    if self.fuzzProd[r] >= 0:
                        prodlist.append(r)
                        rule.append(numpy.fmin(tmp_active,self.MBFprodFuzz[self.fuzzProd[r]]))
                    else:
                        distlist.append(r)
                        rule.append(numpy.fmin(tmp_active,self.MBFdistFuzz[self.fuzzDis[r]]))

            # With the activity of each output membership function known, all output membership functions
            #  must be combined. This step is also known as aggregation.
            if len(prodlist) > 0:
                ruleID = prodlist[0]
                tmp_aggregate = rule[ruleID]
                id = 0
                for l in range(len(prodlist)):
                    if id == 0:
                        tmp_aggregate = rule[l]
                        id = 1
                    else:
                        tmp_aggregate = numpy.fmax(rule[l],tmp_aggregate)
                tmp_prod[s] = fuzz.defuzz(self.MBFprod, tmp_aggregate, 'centroid')

            if len(dislist) > 0:
                ruleID = dislist[0]
                tmp_aggregate = rule[ruleID]
                id = 0
                for l in range(len(dislist)):
                    if id == 0:
                        tmp_aggregate = rule[l]
                        id = 1
                    else:
                        tmp_aggregate = numpy.fmax(rule[l],tmp_aggregate)
                tmp_dis[s] = fuzz.defuzz(self.MBFdis, tmp_aggregate, 'centroid')

            return tmp_prod,tmp_dis
