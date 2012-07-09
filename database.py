'''
Module to integrate jasp with sqlite
'''
import apsw, os, pickle, time
import numpy as np
from Cheetah.Template import Template
from jasp import *

printsql = False

DB = 'db.sqlite'

setup_sql='''
CREATE TABLE vasp (
     id INTEGER PRIMARY KEY,
     path TEXT,
     -- unit cell parameters
     uc_a FLOAT,
     uc_b FLOAT,
     uc_c FLOAT,
     uc_alpha FLOAT,
     uc_beta FLOAT,
     uc_gamma FLOAT,
     constraints TEXT,
     -- calculated properties
     total_energy FLOAT,
     sxx FLOAT,
     syy FLOAT,
     szz FLOAT,
     sxz FLOAT,
     syz FLOAT,
     sxy FLOAT,
     -- Calculation parameters below
     snl INTEGER,
     isym INTEGER,
     maxmix INTEGER,
     fnmin INTEGER,
     ispin INTEGER,
     nbands INTEGER,
     ngzf INTEGER,
     ichain INTEGER,
     ismear INTEGER,
     vdwgr INTEGER,
     ngxf INTEGER,
     nelm INTEGER,
     nelmin INTEGER,
     istart INTEGER,
     nupdown INTEGER,
     nwrite INTEGER,
     ialgo INTEGER,
     voskown INTEGER,
     icharg INTEGER,
     nfree INTEGER,
     nblk INTEGER,
     lorbit INTEGER,
     nsw INTEGER,
     ngx INTEGER,
     ngy INTEGER,
     ngz INTEGER,
     nelmdl INTEGER,
     iniwav INTEGER,
     nkredx INTEGER,
     nkredy INTEGER,
     nkredz INTEGER,
     nbmod INTEGER,
     ibrion INTEGER,
     ngyf INTEGER,
     npar INTEGER,
     iwavpr INTEGER,
     nkred INTEGER,
     lbfgsmem INTEGER,
     idipol INTEGER,
     ldautype INTEGER,
     nsim INTEGER,
     isif INTEGER,
     lmaxmix INTEGER,
     ldauprint INTEGER,
     iopt INTEGER,
     smass INTEGER,
     vdwrn INTEGER,
     emax FLOAT,
     falphadec FLOAT,
     encut FLOAT,
     enaug FLOAT,
     timestep FLOAT,
     maxmove FLOAT,
     ebreak FLOAT,
     nelect FLOAT,
     bmix FLOAT,
     sdr FLOAT,
     invcurve FLOAT,
     ddr FLOAT,
     hfscreen FLOAT,
     ftimeinc FLOAT,
     dfnmax FLOAT,
     sdalpha FLOAT,
     pomass FLOAT,
     jacobian FLOAT,
     zab_vdw FLOAT,
     param2 FLOAT,
     amix_mag FLOAT,
     aexx FLOAT,
     encutfock FLOAT,
     aggac FLOAT,
     ftimemax FLOAT,
     aldac FLOAT,
     drotmax FLOAT,
     zval FLOAT,
     deper FLOAT,
     bmix_mag FLOAT,
     aggax FLOAT,
     stol FLOAT,
     amin FLOAT,
     emin FLOAT,
     falpha FLOAT,
     weimin FLOAT,
     ftimedec FLOAT,
     dfnmin FLOAT,
     amix FLOAT,
     param1 FLOAT,
     time FLOAT,
     sigma FLOAT,
     potim FLOAT,
     teend TEXT,
     prec TEXT,
     system TEXT,
     gga TEXT,
     algo TEXT,
     tebeg TEXT,
     lcorr BOOLEAN,
     lclimb BOOLEAN,
     lcharg BOOLEAN,
     lnebcell BOOLEAN,
     lplane BOOLEAN,
     lhfcalc BOOLEAN,
     lasync BOOLEAN,
     lvdw BOOLEAN,
     ltangentold BOOLEAN,
     ldau BOOLEAN,
     lsepb BOOLEAN,
     ldneb BOOLEAN,
     lsepk BOOLEAN,
     lasph BOOLEAN,
     addgrid BOOLEAN,
     ldiag BOOLEAN,
     lelf BOOLEAN,
     loptics BOOLEAN,
     luse_vdw BOOLEAN,
     lglobal BOOLEAN,
     ldipol BOOLEAN,
     lvhar BOOLEAN,
     lvtot BOOLEAN,
     lscalu BOOLEAN,
     llineopt BOOLEAN,
     lpard BOOLEAN,
     lthomas BOOLEAN,
     lwave BOOLEAN,
     lscalapack BOOLEAN,
     laechg BOOLEAN,
     -- special parameters that don't have a simple database representation
     -- we use strings that python can eval to get the values
     ediff TEXT,
     symprec TEXT,
     ediffg TEXT,
     fdstep TEXT,
     magmom TEXT,
     ropt TEXT,
     kpuse TEXT,
     eint TEXT,
     ferdo TEXT,
     ldaul TEXT,
     ldauj TEXT,
     iband TEXT,
     ldauu TEXT,
     ferwe TEXT,
     rwigs TEXT,
     dipol TEXT,
     ldau_luj TEXT,
     lreal TEXT,
     setups TEXT,
     xc TEXT,
     kpts TEXT,
     txt TEXT,
     gamma TEXT);

-- this table holds the positions of each atom and the forces on each atom
CREATE TABLE positions (
	id INTEGER PRIMARY KEY,
	vasp_id INTEGER references vasp(id) on delete cascade deferrable initially deferred,
	atom_index INTEGER, -- index in the atoms object
	chemical_symbol TEXT,
    tag INTEGER,
	x FLOAT,
	y FLOAT,
	z FLOAT,
    fx FLOAT, -- force in x-direction
    fy FLOAT, -- force in y-direction
    fz FLOAT,  -- force in z-direction
    potential TEXT, -- which USPP or PAW was used
    magnetic_moment FLOAT
	);'''

if not os.path.exists(DB):
    # we need to initialize a database
    conn = apsw.Connection(DB)
    with conn:
        c = conn.cursor()
        c.execute(setup_sql)
else:
    conn = apsw.Connection(DB)

def insert_database_entry(calc):
    '''
    adds an entry to the database
    '''

    data = {}

    data['path'] = calc.dir

    # collect all data into data dictionary
    data.update(calc.int_params)
    data.update(calc.float_params)
    data.update(calc.string_params)
    data.update(calc.bool_params)

    #handle special dictionaries
    for key in calc.exp_params:
        data[key] = repr(calc.exp_params[key])
    for key in calc.list_params:
        data[key] = repr(calc.list_params[key])
    for key in calc.dict_params:
        data[key] = repr(calc.dict_params[key])
    for key in calc.special_params:
        data[key] = repr(calc.special_params[key])
    for key in calc.input_params:
        data[key] = repr(calc.input_params[key])

    # unit cell geometry
    atoms = calc.get_atoms()
    cell = atoms.get_cell()

    # get a,b,c,alpha,beta,gamma
    from Scientific.Geometry import Vector
    A,B,C = [Vector(x) for x in cell]

    radian = 1
    degree = 2*np.pi*radian/360

    data['uc_a'] = A.length()
    data['uc_b'] = B.length()
    data['uc_c'] = C.length()
    data['uc_alpha'] = B.angle(C)/degree
    data['uc_beta'] =  A.angle(C)/degree
    data['uc_gamma'] = A.angle(B)/degree

    constraints = atoms._get_constraints()
    if constraints != []:
        data['constraints'] = pickle.dumps(constraints)
    else:
        data['constraints'] = None

    # get calculated quantities if they exist
    # here we only get the unit cell quantities: energy and stress
    # we get forces later in the Atoms table
    converged = calc.read_convergence()
    if converged:
        data['TotalEnergy'] = atoms.get_potential_energy()

        stress = atoms.get_stress()
        if stress is not None:
            data['sxx'] = stress[0]
            data['syy'] = stress[1]
            data['szz'] = stress[2]
            data['syz'] = stress[3]
            data['sxz'] = stress[4]
            data['sxy'] = stress[5]
        else:
            data['sxx'] = None
            data['syy'] = None
            data['szz'] = None
            data['syz'] = None
            data['sxz'] = None
            data['sxy'] = None

    data['id']=None

    with conn:
        db = conn.cursor()
        db.execute('pragma foreign_keys=on;')

        db.execute('''
insert into vasp (id,
                  path,
                  uc_a, uc_b, uc_c, uc_alpha, uc_beta, uc_gamma,
                  constraints,
                  total_energy,
                  sxx,syy,szz,sxz,syz,sxy,
                  snl,
                  isym,
                  maxmix,
                  fnmin,
                  ispin,
                  nbands,
                  ngzf,
                  ichain,
                  ismear,
                  vdwgr,
                  ngxf,
                  nelm,
                  nelmin,
                  istart,
                  nupdown,
                  nwrite,
                  ialgo,
                  voskown,
                  icharg,
                  nfree,
                  nblk,
                  lorbit,
                  nsw,
                  ngx,
                  ngy,
                  ngz,
                  nelmdl,
                  iniwav,
                  nkredx,
                  nkredy,
                  nkredz,
                  nbmod,
                  ibrion,
                  ngyf,
                  npar,
                  iwavpr,
                  nkred,
                  lbfgsmem,
                  idipol,
                  ldautype,
                  nsim,
                  isif,
                  lmaxmix,
                  ldauprint,
                  iopt,
                  smass,
                  vdwrn,
                  emax,
                  falphadec,
                  encut,
                  enaug,
                  timestep,
                  maxmove,
                  ebreak,
                  nelect,
                  bmix,
                  sdr,
                  invcurve,
                  ddr,
                  hfscreen,
                  ftimeinc,
                  dfnmax,
                  sdalpha,
                  pomass,
                  jacobian,
                  zab_vdw,
                  param2,
                  amix_mag,
                  aexx,
                  encutfock,
                  aggac,
                  ftimemax,
                  aldac,
                  drotmax,
                  zval,
                  deper,
                  bmix_mag,
                  aggax,
                  stol,
                  amin,
                  emin,
                  falpha,
                  weimin,
                  ftimedec,
                  dfnmin,
                  amix,
                  param1,
                  time,
                  sigma,
                  potim,
                  teend,
                  prec,
                  system,
                  gga,
                  algo,
                  tebeg,
                  lcorr,
                  lclimb,
                  lcharg,
                  lnebcell,
                  lplane,
                  lhfcalc,
                  lasync,
                  lvdw,
                  ltangentold,
                  ldau,
                  lsepb,
                  ldneb,
                  lsepk,
                  lasph,
                  addgrid,
                  ldiag,
                  lelf,
                  loptics,
                  luse_vdw,
                  lglobal,
                  ldipol,
                  lvhar,
                  lvtot,
                  lscalu,
                  llineopt,
                  lpard,
                  lthomas,
                  lwave,
                  lscalapack,
                  laechg,
                  ediff,
                  symprec,
                  ediffg,
                  fdstep,
                  magmom,
                  ropt,
                  kpuse,
                  eint,
                  ferdo,
                  ldaul,
                  ldauj,
                  iband,
                  ldauu,
                  ferwe,
                  rwigs,
                  dipol,
                  ldau_luj,
                  lreal,
                  setups,
                  xc,
                  kpts,
                  txt,
                  gamma)
                  values (
                  :id,
                  :path,
                  :uc_a,
                  :uc_b,
                  :uc_c,
                  :uc_alpha,
                  :uc_beta,
                  :uc_gamma,
                  :constraints,
                  :total_energy,
                  :sxx,:syy,:szz,:sxz,:syz,:sxy,
                  :snl,
                  :isym,
                  :maxmix,
                  :fnmin,
                  :ispin,
                  :nbands,
                  :ngzf,
                  :ichain,
                  :ismear,
                  :vdwgr,
                  :ngxf,
                  :nelm,
                  :nelmin,
                  :istart,
                  :nupdown,
                  :nwrite,
                  :ialgo,
                  :voskown,
                  :icharg,
                  :nfree,
                  :nblk,
                  :lorbit,
                  :nsw,
                  :ngx,
                  :ngy,
                  :ngz,
                  :nelmdl,
                  :iniwav,
                  :nkredx,
                  :nkredy,
                  :nkredz,
                  :nbmod,
                  :ibrion,
                  :ngyf,
                  :npar,
                  :iwavpr,
                  :nkred,
                  :lbfgsmem,
                  :idipol,
                  :ldautype,
                  :nsim,
                  :isif,
                  :lmaxmix,
                  :ldauprint,
                  :iopt,
                  :smass,
                  :vdwrn,
                  :emax,
                  :falphadec,
                  :encut,
                  :enaug,
                  :timestep,
                  :maxmove,
                  :ebreak,
                  :nelect,
                  :bmix,
                  :sdr,
                  :invcurve,
                  :ddr,
                  :hfscreen,
                  :ftimeinc,
                  :dfnmax,
                  :sdalpha,
                  :pomass,
                  :jacobian,
                  :zab_vdw,
                  :param2,
                  :amix_mag,
                  :aexx,
                  :encutfock,
                  :aggac,
                  :ftimemax,
                  :aldac,
                  :drotmax,
                  :zval,
                  :deper,
                  :bmix_mag,
                  :aggax,
                  :stol,
                  :amin,
                  :emin,
                  :falpha,
                  :weimin,
                  :ftimedec,
                  :dfnmin,
                  :amix,
                  :param1,
                  :time,
                  :sigma,
                  :potim,
                  :teend,
                  :prec,
                  :system,
                  :gga,
                  :algo,
                  :tebeg,
                  :lcorr,
                  :lclimb,
                  :lcharg,
                  :lnebcell,
                  :lplane,
                  :lhfcalc,
                  :lasync,
                  :lvdw,
                  :ltangentold,
                  :ldau,
                  :lsepb,
                  :ldneb,
                  :lsepk,
                  :lasph,
                  :addgrid,
                  :ldiag,
                  :lelf,
                  :loptics,
                  :luse_vdw,
                  :lglobal,
                  :ldipol,
                  :lvhar,
                  :lvtot,
                  :lscalu,
                  :llineopt,
                  :lpard,
                  :lthomas,
                  :lwave,
                  :lscalapack,
                  :laechg,
                  :ediff,
                  :symprec,
                  :ediffg,
                  :fdstep,
                  :magmom,
                  :ropt,
                  :kpuse,
                  :eint,
                  :ferdo,
                  :ldaul,
                  :ldauj,
                  :iband,
                  :ldauu,
                  :ferwe,
                  :rwigs,
                  :dipol,
                  :ldau_luj,
                  :lreal,
                  :setups,
                  :xc,
                  :kpts,
                  :txt,
                  :gamma
                  );''',data)

    db.execute('select last_insert_rowid()')
    vasp_id = db.fetchall()[0][0]

    # Now we need to populate the positions table
    ppplist = calc.get_pseudopotentials()
    ppp = {}
    for sym,pp in ppplist:
        ppp[sym] = pp

    for i,atom in enumerate(atoms):
        atom_data = {}
        atom_data['vasp_id'] = vasp_id
        atom_data['atom_index'] = i
        atom_data['chemical_symbol'] = atom.symbol.strip()
        if atom.tag is not None:
           atom_data['tag'] = int(atom.tag)
        else:
            atom_data['tag'] = None

        x,y,z = float(atom.x),float(atom.y),float(atom.z)
        atom_data['x'] = x
        atom_data['y'] = y
        atom_data['z'] = z

        if converged:
            forces = atoms.get_forces()
            force =  forces[i]
            atom_data['fx'] = force[0]
            atom_data['fy'] = force[1]
            atom_data['fz'] = force[2]
        else:
            atom_data['fx'] = None
            atom_data['fy'] = None
            atom_data['fz'] = None

        magmom = atom.magmom
        if magmom is not None:
            atom_data['magnetic_moment'] = float(atom.magmom)
        else:
            atom_data['magnetic_moment'] = None

        atom_data['potential'] = ppp[atom.symbol]

        db.execute('''
insert into positions (vasp_id,
                       atom_index,
                       chemical_symbol,
                       tag,
                       x,y,z,
                       fx,fy,fz,
                       potential)
values (:vasp_id,
        :atom_index,
        :chemical_symbol,
        :tag,
        :x,:y,:z,
        :fx,:fy,:fz,
        :potential)''',atom_data)

if __name__ == '__main__':
    connection=apsw.Connection(DB)
    cursor=connection.cursor()

    ## import StringIO as io # use io in Python 3
    ## output=io.StringIO()

    ## shell = apsw.Shell(stdout=output, db=connection)
    ## shell.process_command('.tables')
    ## print output.getvalue()

    from jasp import *
    with jasp('tests/O_test') as calc:
        #shell.process_command('.tables')
        #print output.getvalue()

        insert_database_entry(calc)






    '''
    v = Vasp()


    for key in v.int_params.keys():
        print '     {0} INTEGER,'.format(key)
    for key in v.float_params.keys():
        print '     {0} FLOAT,'.format(key)
    for key in v.string_params.keys():
        print '     {0} TEXT,'.format(key)
    for key in v.bool_params.keys():
        print '     {0} BOOLEAN,'.format(key)

        # all these will be specially treated as strings that later would be evaled
    for key in v.exp_params.keys():
        print '     {0} TEXT,'.format(key)
    for key in v.list_params.keys():
        print '     {0} TEXT,'.format(key)
    for key in v.dict_params.keys():
        print '     {0} TEXT,'.format(key)
    for key in v.special_params.keys():
        print '     {0} TEXT,'.format(key)
    for key in v.input_params.keys():
        print '     {0} TEXT,'.format(key)
'''
