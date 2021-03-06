##~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~##
##                                                                                   ##
##  This file forms part of the pyReef carbonate platform modelling application.     ##
##                                                                                   ##
##  For full license and copyright information, please refer to the LICENSE.md file  ##
##  located at the project root, or contact the authors.                             ##
##                                                                                   ##
##~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~#~##
"""
This module encapsulates functions related to the creation of regular pyReef surface
output.
"""

import os
import h5py
import numpy
import pandas
import os.path
import mpi4py.MPI as mpi

class outputGrid:

    def __init__(self, surf, folder, h5file, xmffile, xdmffile):
        """
        Constructor.
        """

        # Initialise MPI communications
        self.comm = mpi.COMM_WORLD
        self.rank = self.comm.Get_rank()
        self.size = self.comm.Get_size()

        self.ny = surf.ny - 2
        self.j1 = 1
        self.j2 = surf.ny-1

        self.nx = numpy.zeros(self.size,dtype=int)
        for s in range(self.size):
            self.nx[s] = surf.partIDs[s,1]-surf.partIDs[s,0]+1
        self.nx[0] -= 1
        self.nx[self.size-1] -= 1

        if self.rank == 0:
            self.i1 = surf.partIDs[self.rank,0]+1
        else:
            self.i1 = surf.partIDs[self.rank,0]
        if self.rank == self.size-1:
            self.i2 = surf.partIDs[self.rank,1]
        else:
            self.i2 = surf.partIDs[self.rank,1]+1

        self.nbPts = (self.j2-self.j1)*(self.i2-self.i1)
        xv, yv = numpy.meshgrid(surf.regX[self.i1:self.i2], surf.regY[self.j1:self.j2], sparse=False, indexing='ij')
        self.x = xv.T.flatten()
        self.y = yv.T.flatten()

        self.folder = folder
        self.h5file = h5file
        self.xmffile = xmffile
        self.xdmffile = xdmffile

        self.partID = surf.partIDs

        xy5file = 'h5/xycoords.p'+str(self.rank)+'.hdf5'
        with h5py.File(self.folder+'/'+xy5file, "w") as f:
            # Write node coordinates
            f.create_dataset('x',shape=(self.nbPts,1), dtype='float32', compression='gzip')
            f["x"][:,0] = self.x
            # Write node coordinates
            f.create_dataset('y',shape=(self.nbPts,1), dtype='float32', compression='gzip')
            f["y"][:,0] = self.y

        return

    def write_hdf5_grid(self, elev, force, time, outstep):
        """
        This function writes for each processor the HDF5 file containing sub-surface information.

        Parameters
        ----------

        variable : elev
            Elevation at current time step.

        variable: force
            Forcings conditions.

        variable : time
            Simulation current time step.

        variable : outstep
            Output time step.
        """

        sh5file = self.folder+'/'+self.h5file+str(outstep)+'.p'+str(self.rank)+'.hdf5'
        with h5py.File(sh5file, "w") as f:

            # Write node elevations
            f.create_dataset('z',shape=(self.nbPts,1), dtype='float32', compression='gzip')
            f["z"][:,0] = numpy.ravel(elev[self.i1:self.i2,self.j1:self.j2],order='F')
            if force.wclim > 0:
                for p in range(force.wclim):
                    # Write bottom current along X
                    st = 'wu'+str(p)
                    f.create_dataset(st,shape=(self.nbPts,1), dtype='float32', compression='gzip')
                    f[st][:,0] = numpy.ravel(force.wavU[force.wclim-1][self.i1:self.i2,self.j1:self.j2],order='F')
                    # Write bottom current velocity along Y
                    st = 'wv'+str(p)
                    f.create_dataset(st,shape=(self.nbPts,1), dtype='float32', compression='gzip')
                    f[st][:,0] = numpy.ravel(force.wavV[force.wclim-1][self.i1:self.i2,self.j1:self.j2],order='F')
                    # Write wave height
                    st = 'wh'+str(p)
                    f.create_dataset(st,shape=(self.nbPts,1), dtype='float32', compression='gzip')
                    f[st][:,0] = numpy.ravel(force.wavH[force.wclim-1][self.i1:self.i2,self.j1:self.j2],order='F')

        self.comm.Barrier()

        if self.rank == 0:
            self._write_xmf(time, outstep, force.sealevel, force.wclim)

        return

    def _write_xdmf(self, step):
        """
        This function writes the XDmF file which is calling the XmF file.

        Parameters
        ----------

        variable: step
            Output visualisation step.
        """

        f= open(self.folder+'/'+self.xdmffile,'w')

        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<!DOCTYPE Xdmf SYSTEM "Xdmf.dtd">\n')
        f.write('<Xdmf Version="2.0" xmlns:xi="http://www.w3.org/2001/XInclude">\n')
        f.write(' <Domain>\n')
        f.write('    <Grid GridType="Collection" CollectionType="Temporal">\n')
        for p in range(step+1):
            xfile = self.xmffile+str(p)+'.xmf'
            f.write('      <xi:include href="%s" xpointer="xpointer(//Xdmf/Domain/Grid)"/>\n' %xfile)
        f.write('    </Grid>\n')
        f.write(' </Domain>\n')
        f.write('</Xdmf>\n')
        f.close()

        return

    def _write_xmf(self, time, step, sl, wclim):
         """
         This function writes the XmF file which is calling each HFD5 file.

         Parameters
         ----------

        variable : time
            Simulation current time step.

         variable: step
             Output visualisation step.

         variable: sl
            Sealevel elevation.

         variable: wclim
            Wave climates number to be outputed.
         """

         xmf_file = self.folder+'/'+self.xmffile+str(step)+'.xmf'
         f= open(str(xmf_file),'w')

         f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
         f.write('<!DOCTYPE Xdmf SYSTEM "Xdmf.dtd">\n')
         f.write('<Xdmf Version="2.0" xmlns:xi="http://www.w3.org/2001/XInclude">\n')
         f.write(' <Domain>\n')
         f.write('    <Grid GridType="Collection" CollectionType="Spatial">\n')
         f.write('      <Time Type="Single" Value="%s"/>\n'%time)

         for p in range(self.size):
             xy5file = 'h5/xycoords.p'+str(p)+'.hdf5'
             datfile = self.h5file+str(step)+'.p'+str(p)+'.hdf5'
             f.write('      <Grid Name="Block.%s">\n' %(str(p)))
             f.write('         <Topology TopologyType="3DSMesh" NumberOfElements="1 %d %d"/>\n'%(self.ny,self.nx[p]))
             f.write('         <Geometry GeometryType="X_Y_Z">\n')
             f.write('            <DataItem Dimensions="%d %d 1" Format="HDF" NumberType="Float" Precision="4" '%(self.nx[p],self.ny))
             f.write('>%s:/x</DataItem>\n'%(xy5file))
             f.write('            <DataItem Dimensions="%d %d 1" Format="HDF" NumberType="Float" Precision="4" '%(self.nx[p],self.ny))
             f.write('>%s:/y</DataItem>\n'%(xy5file))
             f.write('            <DataItem Dimensions="%d %d 1" Format="HDF" NumberType="Float" Precision="4" '%(self.nx[p],self.ny))
             f.write('>%s:/z</DataItem>\n'%(datfile))
             f.write('         </Geometry>\n')
             f.write('         <Attribute Type="Scalar" Center="Node" Name="Elevation">\n')
             f.write('            <DataItem Format="HDF" NumberType="Float" Precision="4" Dimensions="%d %d 1" '%(self.nx[p],self.ny))
             f.write('>%s:/z</DataItem>\n'%(datfile))
             f.write('         </Attribute>\n')
             if wclim > 0:
                 f.write('         <Attribute Type="Scalar" Center="Node" Name="Ux">\n')
                 f.write('            <DataItem Format="HDF" NumberType="Float" Precision="4" Dimensions="%d %d 1" '%(self.nx[p],self.ny))
                 f.write('>%s:/wu0</DataItem>\n'%(datfile))
                 f.write('         </Attribute>\n')
                 f.write('         <Attribute Type="Scalar" Center="Node" Name="Uy">\n')
                 f.write('            <DataItem Format="HDF" NumberType="Float" Precision="4" Dimensions="%d %d 1" '%(self.nx[p],self.ny))
                 f.write('>%s:/wv0</DataItem>\n'%(datfile))
                 f.write('         </Attribute>\n')
                 f.write('         <Attribute Type="Scalar" Center="Node" Name="wH">\n')
                 f.write('            <DataItem Format="HDF" NumberType="Float" Precision="4" Dimensions="%d %d 1" '%(self.nx[p],self.ny))
                 f.write('>%s:/wh0</DataItem>\n'%(datfile))
                 f.write('         </Attribute>\n')
                #  f.write('         <Attribute Type="Scalar" Center="Node" Name="LongshoreD">\n')
                #  f.write('            <DataItem Format="HDF" NumberType="Float" Precision="4" Dimensions="%d %d 1" '%(self.nx[p],self.ny))
                #  f.write('>%s:/ld</DataItem>\n'%(datfile))
                #  f.write('         </Attribute>\n')
                #  f.write('         <Attribute Type="Scalar" Center="Node" Name="WaveL">\n')
                #  f.write('            <DataItem Format="HDF" NumberType="Float" Precision="4" Dimensions="%d %d 1" '%(self.nx[p],self.ny))
                #  f.write('>%s:/wl</DataItem>\n'%(datfile))
                #  f.write('         </Attribute>\n')
             f.write('         <Attribute Type="Scalar" Center="Node" Name="Sealevel">\n')
             f.write('          <DataItem ItemType="Function" Function="$0 * 0.00000000001 + %f" Dimensions="%d %d 1">\n'%(sl,self.nx[p],self.ny))
             f.write('           <DataItem Format="HDF" NumberType="Float" Precision="4" ')
             f.write('Dimensions="%d %d 1">%s:/z</DataItem>\n'%(self.nx[p],self.ny,datfile))
             f.write('          </DataItem>\n')
             f.write('         </Attribute>\n')
             f.write('      </Grid>\n')

         f.write('    </Grid>\n')
         f.write(' </Domain>\n')
         f.write('</Xdmf>\n')
         f.close()

         self._write_xdmf(step)

         return
