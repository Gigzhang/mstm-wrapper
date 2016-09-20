# Copyright 2011-2013, 2016 Vinothan N. Manoharan, Thomas G. Dimiduk,
# Rebecca W. Perry, Jerome Fung, Ryan McGorty, Anna Wang, Annie Stephenson, and
# Victoria Hwang
#
# This file is part of the mstm-wrapper project.
#
# This package is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This package is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this package.  If not, see <http://www.gnu.org/licenses/>.

"""
This package provides a python wrapper around the MSTM fortran-90 code
(http://www.eng.auburn.edu/~dmckwski/scatcodes/) written by Daniel Mackowski.
It produces input files, sends them to the mstm executable, parses the
output files, and calculates quantities of interest for static light scattering
measurements.  The mstm executable should be located in the user's path.

Based on work that was originally part of HoloPy
(https://github.com/manoharan-lab/holopy).

.. moduleauthor:: Anna Wang <annawang@seas.harvard.edu>
.. moduleauthor:: Annie Stephenson <stephenson@g.harvard.edu>
.. moduleauthor:: Victoria Hwang <vhwang@g.harvard.edu>
.. moduleauthor:: Vinothan N. Manoharan <vnm@seas.harvard.edu>
"""

from __future__ import division
import subprocess
import tempfile
import glob
import os
import shutil
import numpy as np


def separate_exponent(num):
    """
    ADD DOCSTRING
    """
    b, e = num/10**(np.floor(np.log10(np.abs(num)))), np.floor(np.log10(np.abs(num)))
    b = np.nan_to_num(b)
    e[np.isneginf(e)] = 0
    e = e.astype(int)
    return b, e


def calc_scat_matrix(target, incident, theta, phi, delete=True):
    """
    Calculate the first row of the mueller scattering matrix as a function of
    theta, phi, and wavelength.

    Parameters
    ----------
    target: an object of the Target class
    incident: an object of the Incident class
    theta: numpy array of values for the polar scattering angle theta for scattering
        matrix computations, in degrees (must be 0-180)
    phi: numpy array of values for the azimuth angle theta for scattering matrix
        computations, in degrees (must be 0-360)
    delete: binary to determine if the input and output files
        generated by the MSTM fortran code should be deleted after running

    Returns
    -------
    numpy array:
        first row of scattering matrix
        corresponding theta
        corresponding phi
        corresponging wavelength
    """

    # put input files in a temp directory
    temp_dir = tempfile.mkdtemp()
    current_directory = os.getcwd()
    path, _ = os.path.split(os.path.abspath(__file__))
    #temp_dir = path # comment after debugging
    mstmlocation = os.path.join(path, 'mstm_ubuntu.exe')
    templatelocation = os.path.join(path, 'input_template.txt')
    shutil.copy(mstmlocation, temp_dir)
    shutil.copy(templatelocation, temp_dir)
    os.chdir(temp_dir)

    # make angles file
    angfile_name = 'angles.dat'
    angfile = os.path.join(temp_dir, angfile_name)
    thetatot = np.repeat(theta, len(phi))
    phitot = np.tile(phi, len(theta))
    angs = np.vstack((thetatot, phitot))
    angs = angs.transpose()
    np.savetxt(angfile, angs, '%5.2f')

    # prepare input file for fortran code
    output_name = 'mstm_out.dat'
    length_scl_factor = 2*np.pi/incident.wavelength
    lsf_start = length_scl_factor[0]
    lsf_end = length_scl_factor[len(length_scl_factor)-1]
    length_scl_factor_info = [lsf_start, lsf_end, lsf_end-lsf_start]
    polarization_angle = np.arctan2(incident.jones_vec[1], incident.jones_vec[0])*180/np.pi
    parameters = (target.num_spheres, target.index_spheres, target.index_matrix, polarization_angle)

    # have to make sure we don't print any e's into the text file.
    radb, rade = separate_exponent(target.radii)
    xb, xe = separate_exponent(target.x-np.mean(target.x))
    yb, ye = separate_exponent(target.y-np.mean(target.y))
    zb, ze = separate_exponent(target.z-np.mean(target.z))
    g = ''
    for k in range(target.num_spheres):
        g += '{0:20} {1:20} {2:20} {3:3}'.format(str(radb[k])+'d'+str(rade[k]),\
                                                str(xb[k])+'d'+str(xe[k]), \
                                                str(yb[k])+'d'+str(ye[k]), \
                                                str(zb[k])+'d'+str(ze[k])+'\n')
    with open(templatelocation, 'r') as infile:
        InF = infile.read()
    InF = InF.format(parameters, g, output_name, angfile_name, len(angs), length_scl_factor_info)
    input_file = file(os.path.join(temp_dir, 'mstm.inp'), 'w')
    input_file.write(InF)
    input_file.close()

    # run MSTM fortran executable
    cmd = ['./mstm_ubuntu.exe', 'mstm.inp']
    subprocess.check_call(cmd, cwd=temp_dir)

    # Read scattering matrix from results file
    scat_mat_data = np.zeros([len(incident.wavelength), len(thetatot), 18])
    result_file = glob.glob(os.path.join(temp_dir, 'mstm_out.dat'))[0]
    with open(result_file, "r") as myfile:
        mstm_result = myfile.readlines()
    mstm_result = [line.replace('\n', '') for line in mstm_result]
    mstm_result = [line.replace('\t', '') for line in mstm_result]
    mstm_result = filter(None, mstm_result)
    scat_mat_el_row = [i for i, j in enumerate(mstm_result) if j == ' scattering matrix elements']
    for m in range(len(scat_mat_el_row)):
        smdata = mstm_result[scat_mat_el_row[m] + 2 : scat_mat_el_row[m] + 2 + len(angs)]
        for i in range(len(angs)):
            a = smdata[i].split(' ')
            a = filter(None, a)
            smdata[i] = [float(j) for j in a]
        scat_mat_data[m][:][:] = smdata

    # delete temp files
    os.chdir(current_directory)
    if delete:
        shutil.rmtree(temp_dir)

    return scat_mat_data

def calc_intensity(target, incident, theta, phi):
    """
    Calculate the intensity of light scattered from a structure as a function
    of theta, phi, and wavelength.

    Parameters
    ----------
    target: an object of the Target class
    incident: an object of the Incident class
    theta: numpy array of values for the polar scattering angle theta for scattering
        matrix computations, in degrees (must be 0-180)
    phi: numpy array of values for the azimuth angle theta for scattering matrix
        computations, in degrees (must be 0-360)

    Returns
    -------
    numpy array:
        intensity_data
    """
    scat_mat_data = calc_scat_matrix(target, incident, theta, phi)
    intensity_data = np.zeros([len(incident.wavelength), len(theta)*len(phi), 3])
    prefactor = 1/((2*np.pi*target.index_matrix/incident.wavelength)**2)
    intensity_data[:][:][0] = scat_mat_data[:][:][0]
    intensity_data[:][:][1] = scat_mat_data[:][:][1]
    intensity_data[:][:][2] = prefactor*(scat_mat_data[:][:][2]*incident.stokes_vec[0] +
                                         scat_mat_data[:][:][3]*incident.stokes_vec[1] +
                                         scat_mat_data[:][:][4]*incident.stokes_vec[2] +
                                         scat_mat_data[:][:][5]*incident.stokes_vec[3])
    return intensity_data

class Target:
    """
    ADD CLASS DOCSTRING
    """
    def __init__(self, x, y, z, radii, index_matrix, index_spheres, num_spheres):
        """
        Initialize object of the Target class. Target objects represent the sphere
        assemblies that scatter light

        Parameters
        ----------
        x: x-coordinates of spheres in assembly
        y: y-coordinates of spheres in assembly
        z: z-coordinates of spheres in assembly
        radii: radii of spheres in assembly
        index_matrix: refractive index of medium surrounding spheres
        index_spheres: refractive index of spheres
        num_spheres: number of spheres in assembly

        Returns
        -------
        Target object

        Notes
        -----
        x, y, z, and radii must be in same units, and must also match units of
        wavelength of incident light, which is defined in Incident class
        """
        self.x = x
        self.y = y
        self.z = z
        self.radii = radii
        self.index_matrix = index_matrix
        self.index_spheres = index_spheres
        self.num_spheres = num_spheres

class Incident:
    """
    ADD CLASS DOCSTRING
    """
    def __init__(self, jones_vec, stokes_vec, wavelength):
        """
        Initialize object of the Incident class. Incident objects represent the
        incident light which is scattered from sphere assemblies.

        Parameters
        ----------
        jones_vec: Jones vector of the incident light
        stokes_vec: Stokes vector of the incident light
        wavelength: numpy array of wavelength of the incident light

        Returns
        -------
        Incident object

        Notes
        -----
        wavelength units must match those of x, y, z, and radii defined in the
        Target class
        """
        self.jones_vec = jones_vec # jones vector
        self.stokes_vec = stokes_vec # stokes vector
        self.wavelength = wavelength # um

if __name__ == "__main__":
    t = Target(np.array([1, 1]), np.array([1, 1]), np.array([0, 1]),
               np.array([0.125, 0.125]), 1.4, 1, 2)
    # wavelengths must be in decreasing order
    inci = Incident((1, 0), [1, 1, 0, 0], np.array([0.41, 0.4, 0.39]))
    scat_mat_dat = calc_scat_matrix(t, inci, np.arange(0, 11, 1), [0])

# todo
# - make changes so that wavelengths do not have to be in decreasing order
# - figure out why ending wavelength is not included in calculations
# - test and debig intensity calc function
# - put test in separate file
# - update docstrings



