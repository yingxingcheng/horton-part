#!/usr/bin/env python

import numpy as np
from horton_part import log
from iodata import load_one
from gbasis.evals.eval import evaluate_basis
from gbasis.wrappers import from_iodata
from horton_part import MBISWPart
from grid import ExpRTransform, UniformInteger, BeckeWeights, MolGrid
from utils import load_fchk


# Load the Gaussian output from file from HORTON's test data directory.
fn_fchk = load_fchk("water_sto3g_hf_g03")

# Replace the previous line with any other fchk file, e.g. fn_fchk = 'yourfile.fchk'.
mol = load_one(fn_fchk)

# Specify the integration grid
rtf = ExpRTransform(5e-4, 2e1, 120 - 1)
uniform_grid = UniformInteger(120)
rgrid = rtf.transform_1d_grid(uniform_grid)
becke = BeckeWeights()
grid = MolGrid.from_preset(
    mol.atnums, mol.atcoords, rgrid, "fine", becke, rotate=False, store=True
)

# # Get the spin-summed density matrix
one_rdm = mol.one_rdms.get("post_scf", mol.one_rdms.get("scf"))
basis, coord_types = from_iodata(mol)
basis_grid = evaluate_basis(basis, grid.points, coord_type=coord_types)
rho = np.einsum("ab,bp,ap->p", one_rdm, basis_grid, basis_grid, optimize=True)

nelec = grid.integrate(rho)
log("nelec = {}".format(nelec))

kwargs = {
    "coordinates": mol.atcoords,
    "numbers": mol.atnums,
    "pseudo_numbers": mol.atnums,
    "grid": grid,
    "moldens": rho,
    "lmax": 3,
    "maxiter": 1000,
}

part = MBISWPart(**kwargs)
part.do_all()

print(part.cache["charges"])
