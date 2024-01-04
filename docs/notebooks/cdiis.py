import logging

import numpy as np
import scipy.linalg
from scipy.linalg import solve_triangular
from setup import prepare_argument_dict, prepare_grid_and_dens, print_results

from horton_part import LinearISAWPart, check_pro_atom_parameters, compute_quantities

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:    %(message)s")
logger = logging.getLogger(__name__)


def cdiis_algo(
    bs_funcs,
    rho,
    propars,
    points,
    weights,
    threshold,
    density_cutoff,
    # parameters for CDIIS
    tol=1e-08,
    maxiter=50,
    mode="R-CDIIS",
    adaptative=False,
    sizediis=8,
    cstAdapt=1e-05,
    minrestart=1,
    modeQR="full",
    param=0.1,
    booldiis=True,
    slidehole=False,
    log=logging.DEBUG,
    name="",
):
    """
    CDiis algorithm
    --------------

    CDIIS algorithm. Multiple variations of the algorithm are implemented.
    The core of the function is to implement the restarted CDIIS (R-CDIIS) and the Adaptive-Depth CDIIS (AD-CDIIS) compared to the Fixed-Depth CDIIS (FD-CDIIS)

    Parameters
    ----------
    param : float
        default value : 0:1
        tau parameter for the R-CDIIS algorithm
        delta parameter for the AD-CDIIS algorithm
    tol : float
       default value : 1e-08
       tolerence parameter for convergence test on residual (commutator)
    maxiter : integer
       default value : 50
       maximal number of iterations allowed
    mode : string
       default value : "R-CDIIS"
       four modes available : "R-CDIIS", "AD-CDIIS", "FD-CDIIS", "Roothaan"
    adaptative : boolean
       default value : False
       adaptative mode for the tau parameter
    sizediis : integer
       default value : 8
       size of the window of stored previous iterates in the FD-CDIIS algorithm
       this dimension is also used for the adaptative algorithm
    cstAdapt : float
       default value : 1e-05
       constant part for the adaptative parameter (delta or tau)
    minrestart : integer
       default value : 1
       number of iterates we keep when a restart occurs
    modeQR : string
       default value : "full"
       mode to build the QR decomposition of the matrix of residuals differences
       - full to compute the qr decomposition with scipy.linalg.qr
       - economic to use the economic mode of scipy.linalg.qr
       - otherwise : compute the qr decomposition with scipy.linalg.qr_insert and scipy.linalg.qr_delete
    slidehole : boolean
       default value : False
       if True : allows hole in the AD-CDIIS algorithm
    name : string
        default value ""
        name of the computation (to identify the log file : diis_namevalue.log)

    Outputs
    -------
    conv : boolean
       if convergence, True, else, False
    rnormlist : numpy.array
       list of norm of r_k
    mklist : numpy.array
       list of m_k value at each step
    cnormlist : numpy.array
       list of the iterates of the norm of the c_i coefficients
    dmlast : numpy.array
       last computed density matrix
    """

    def func_g(x):
        """The objective fixed-point equation."""
        pro_shells, _, _, ratio, _ = compute_quantities(rho, x, bs_funcs, density_cutoff)
        return np.einsum("ip,p->i", pro_shells * ratio, weights)

    def error(x):
        """The residual."""
        return func_g(x) - x

    # booldiis : boolean
    # default value : True
    # if False : Roothann algorithm
    # if True : one of the CDIIS algorithm
    print(mode)
    if mode == "Roothaan":
        booldiis = False
    else:
        booldiis = True

    logger.info("\n\n\n-----------------------------------------\nCDIIS like program")
    logger.info("---- Mode: " + str(mode))
    if mode == "R-CDIIS" or mode == "AD-CDIIS":
        logger.info("---- param value: " + str(param))
    if mode == "FD-CDIIS" or adaptative:
        logger.info("---- sizediis: " + str(sizediis))

    ## compute the initial values
    # the initial values are x0
    dm = propars

    # commutator : residual
    r = error(propars)  # residual

    # lists to save the iterates
    dmlist = [dm]
    rlist = [r]  # iterates of the current residual
    # rlistIter = []  # the residuals family we keep at iteration k
    slist = []  # difference of residual (depending on the choice of CDIIS)
    rnormlist = []  # iterates of the current residual norm
    restartIt = []  # list of the iterations k when the R-CDIIS algorithm restarts
    mklist = []  # list of mk
    cnormlist = []

    # init
    gamma = 1.0
    mk = 0
    nbiter = 1
    # boolean to manage the first step
    notfirst = 0
    restart = True  # boolean to manage the QR decomposition when restart occurs

    # for the reader of the paper
    if mode == "R-CDIIS":
        tau = param
    elif mode == "AD-CDIIS":
        delta = param

    Cs = None
    # while the residual is not small enough
    # TODO: why r[-1]?
    while np.linalg.norm(rlist[-1]) > tol and nbiter < maxiter:
        # rlistIter.append(rlist)
        rnormlist.append(np.linalg.norm(r))
        mklist.append(mk)

        logger.info("======================")
        logger.info("iteration: " + str(nbiter))
        logger.info("mk value: " + str(mk))
        logger.info("||r(k)|| = " + str(np.linalg.norm(rlist[-1])))

        if mk > 0 and booldiis:  # if there exist previous iterates and diis mode
            logger.info("size of Cs: " + str(np.shape(Cs)))
            if mode == "R-CDIIS":
                if modeQR == "full":
                    if mk == 1 or restart is True:  # if Q,R does not exist yet
                        restart = False
                        Q, R = scipy.linalg.qr(Cs)
                    else:  # update Q,R from previous one
                        Q, R = scipy.linalg.qr_insert(Q, R, Cs[:, -1], mk - 1, "col")
                elif modeQR == "economic":  # modeQR="economic"
                    Q, R = scipy.linalg.qr(Cs, mode="economic")

            elif mode == "AD-CDIIS":
                Q, R = scipy.linalg.qr(Cs, mode="economic")

            elif mode == "FD-CDIIS":
                if modeQR == "full":
                    if mk == 1:  # if Q,R does not exist yet
                        Q, R = scipy.linalg.qr(Cs)
                    elif mk < sizediis:  # we only add a column
                        Q, R = scipy.linalg.qr_insert(Q, R, Cs[:, -1], mk - 1, "col")
                    else:
                        if notfirst:  # of not the first time we reach the size
                            Q, R = scipy.linalg.qr_delete(
                                Q, R, 0, which="col"
                            )  # we remove the first column
                        Q, R = scipy.linalg.qr_insert(
                            Q, R, Cs[:, -1], mk - 1, "col"
                        )  # we add a column
                        notfirst = 1

                elif modeQR == "economic":  # modeQR="economic"
                    Q, R = scipy.linalg.qr(Cs, mode="economic")

            Q1 = Q[:, 0:mk]  # the orthonormal basis as the subpart of Q denoted Q1

            ## solve the LS equation R1 gamma = -Q_1^T r^(k-mk) or -Q_1^T r^(k)
            ## depending on the choice of algorithm, the RHS is not the same (last or oldest element)
            if mode == "AD-CDIIS" or mode == "FD-CDIIS":
                rhs = -np.dot(Q.T, np.reshape(rlist[-1], (-1, 1)))  # last : r^{k}

            elif mode == "R-CDIIS":
                rhs = -np.dot(Q.T, np.reshape(rlist[0], (-1, 1)))  # oldest : r^{k-m_k}

            # compute gamma solution of R_1 gamma = RHS
            # TODO: this is problematic if sizediis is larger than the size
            gamma = solve_triangular(R[0:mk, 0:mk], rhs[0:mk], lower=False)
            # Note: gamma has the same shape as rhs which is 2D array.
            gamma = gamma.flatten()
            # compute c_i coefficients
            c = np.zeros(mk + 1)
            # the function gamma to c depends on the algorithm choice
            if mode == "AD-CDIIS" or mode == "FD-CDIIS":
                logger.info(
                    "size of c: " + str(np.shape(c)[0]) + ", size of gamma: " + str(np.shape(gamma))
                )
                # c_0 = -gamma_1 (c_0, ... c_mk) and (gamma_1,...,gamma_mk)
                c[0] = -gamma[0]
                for i in range(1, mk):  # 1... mk-1
                    c[i] = gamma[i - 1] - gamma[i]  # c_i=gamma_i-gamma_i+1
                c[mk] = 1.0 - np.sum(c[0:mk])

            else:  # restart
                c[0] = 1.0 - np.sum(gamma)
                for i in range(1, mk + 1):
                    c[i] = gamma[i - 1]
            # dmtilde
            dmtilde = 0.0 * dm.copy()  # init
            for i in range(mk + 1):
                dmtilde = dmtilde + c[i] * dmlist[i]
            cnormlist.append(np.linalg.norm(c, np.inf))
        else:  #  ROOTHAAN (if booldiis==False) or first iteration of cdiis
            dmtilde = dm.copy()
            cnormlist.append(1.0)

        # computation of the new dm k+1 from dmtilde
        dm = func_g(dmtilde)
        dmlist.append(dm)
        # residual
        r = error(dm)
        logger.info("||r_{k+1}|| = " + str(np.linalg.norm(r)))

        # compute the s^k vector
        if mode == "AD-CDIIS" or mode == "FD-CDIIS":
            #  as the difference between the r^{k+1} and the last r^{k}
            s = r - rlist[-1]
        elif mode == "R-CDIIS":
            # as the difference between the r^k and the older r^{k-mk}
            s = r - rlist[0]
        elif mode == "Roothaan":
            s = r.copy()

        rlist.append(r)
        slist.append(s)

        if mk == 0 or not booldiis:  # we build the matrix of the s vector
            Cs = np.reshape(s, (-1, 1))
        else:
            Cs = np.hstack((Cs, np.reshape(s, (-1, 1))))

        if mode == "R-CDIIS":
            if mk > 0:
                logger.info(
                    "tau*||s^(k)|| = "
                    + str(tau * np.linalg.norm(Cs[:, -1]))
                    + "   >?  ||s^(k)-Q*Q.T*s^(k)|| = "
                    + str(np.linalg.norm(Cs[:, -1] - np.dot(Q1, np.dot(Q1.T, Cs[:, -1]))))
                )

                # Cs[:, -1] - np.dot(Q1, np.dot(Q1.T, Cs[:, -1]))
                if tau * np.linalg.norm(Cs[:, -1]) > np.linalg.norm(
                    Cs[:, -1] - Q1 @ Q1.T @ Cs[:, -1]
                ):
                    # logger.info("********* Restart ***********")
                    restartIt.append(nbiter)
                    mk = minrestart - 1
                    # reinitialization
                    Cs = Cs[:, -minrestart:]
                    # print Cs
                    slist = slist[-minrestart:]
                    rlist = rlist[-minrestart:]
                    dmlist = dmlist[-minrestart:]
                    restart = True
                else:
                    mk = mk + 1
            else:  # if mk==0
                mk = mk + 1

        if mode == "AD-CDIIS":
            # mode Adaptive-Depth
            mk = mk + 1
            outNbr = 0
            indexList = []

            for l in range(0, mk - 1):
                # print l,np.linalg.norm(rlist[-1]),delta*np.linalg.norm(rlist[l])
                if np.linalg.norm(rlist[-1]) < (delta * np.linalg.norm(rlist[l])):
                    outNbr = outNbr + 1
                    indexList.append(l)
                else:
                    if slidehole is False:
                        break

            if indexList != []:
                mk = mk - outNbr
                logger.info("Indexes out :" + str(indexList))
                # delete the corresponding s vectores
                Cs = np.delete(Cs, indexList, axis=1)
                for ll in sorted(indexList, reverse=True):
                    # delete elements of each lists
                    slist.pop(ll)
                    rlist.pop(ll)
                    dmlist.pop(ll)

        elif mode == "FD-CDIIS":  # keep only sizediis iterates
            if mk == sizediis:
                logger.info(str(np.shape(Cs)))
                Cs = Cs[:, 1 : mk + 1]
                logger.info(str(np.shape(Cs)))
                dmlist.pop(0)
                slist.pop(0)
                rlist.pop(0)

            if mk < sizediis:
                mk = mk + 1

        nbiter = nbiter + 1
        dmlast = dm

    if np.linalg.norm(r[-1]) > tol and nbiter == maxiter:
        conv = False
    else:
        conv = True

    # return conv, nbiter - 1, rnormlist, mklist, cnormlist, dmlast
    check_pro_atom_parameters(dmlast)
    if not conv:
        raise RuntimeError("Not converged!")
    return dmlast


if __name__ == "__main__":
    import os

    fchk_path = "/Users/yingxing/Projects/ISA-benchmark/latest-draft/dataset/fchk"

    for name in ["H2S"]:
        # for name in ["H2S", "SiH4", "H2O", "C8H18"]:
        mol, grid, rho = prepare_grid_and_dens(os.path.join(fchk_path, f"{name}_LDA.fchk"))
        kwargs = prepare_argument_dict(mol, grid, rho)
        kwargs["solver"] = cdiis_algo
        # four modes available : "R-CDIIS", "AD-CDIIS", "FD-CDIIS", "Roothaan"
        kwargs["solver_options"] = {
            "mode": "R-CDIIS",
            "maxiter": 100000,
            "sizediis": 8,
        }
        part = LinearISAWPart(**kwargs)
        part.do_all()
        print_results(part)
        print()