from jasp import *
import uuid
import textwrap

# http://cms.mpi.univie.ac.at/vasp/vasp/Files_used_VASP.html
vaspfiles = ['INCAR', 'STOPCAR', 'stout', 'POTCAR',
             'OUTCAR', 'vasprun.xml',
             'KPOINTS', 'IBZKPT', 'POSCAR', 'CONTCAR',
             'EXHCAR', 'CHGCAR', 'CHG', 'WAVECAR',
             'TMPCAR', 'EIGENVAL', 'DOSCAR', 'PROCAR',
             'OSZICAR', 'PCDAT', 'XDATCAR', 'LOCPOT',
             'ELFCAR', 'PROOUT', 'ase-sort.dat', 'METADATA']


def clone(self, newdir, extra_files=None):
    '''copy a vasp directory to a new directory. Does not overwrite
    existing files. newdir is relative to the the directory the
    calculator was created from, not the current working directory,
    unless an absolute path is used.

    what to do about METADATA, the uuid will be wrong!
    '''
    if extra_files is None:
        extra_files = []

    if os.path.isabs(newdir):
        newdirpath = newdir
    else:
        newdirpath = os.path.join(self.cwd, newdir)

    import shutil
    if not os.path.isdir(newdirpath):
        os.makedirs(newdirpath)
    for vf in vaspfiles+extra_files:

        if (not os.path.exists(os.path.join(newdirpath, vf))
            and os.path.exists(vf)):
            shutil.copy(vf, newdirpath)

    # if we are an neb calculation we need to copy the image
    # directories
    if hasattr(self, 'neb'):
        import glob
        for imagedir in glob.glob('0[0-9]'):
            dst = os.path.join(newdirpath, imagedir)
            if not os.path.exists(dst):
                shutil.copytree(imagedir, dst)

    # update metadata. remember we are in the vaspdir
    d = {}
    d['uuid'] = str(uuid.uuid1())
    d['cloned on'] = time.ctime(time.time())

    os.chdir(self.cwd)

    from jasp import jasp
    with jasp(newdir) as calc:
        if hasattr(calc, 'metadata'):
            calc.metadata.update(d)
            calc.write_metadata()

    os.chdir(self.vaspdir)

Vasp.clone = clone


def archive(self, archive='vasp', extra_files=[], append=False):
    '''
    Create an archive file (.tar.gz) of the vasp files in the current
    directory.  This is a way to save intermediate results.
    '''

    import tarfile

    if not archive.endswith('.tar.gz'):
        archive = archive + '.tar.gz'

    if not append and os.path.exists(archive):
        # we do not overwrite existing archives except to append
        return None
    elif append and os.path.exists(archive):
        mode = 'a:gz'
    else:
        mode = 'w:gz'

    f = tarfile.open(archive, mode)
    for vf in vaspfiles + extra_files:
        if os.path.exists(vf):
            f.add(vf)

    # if we are an neb calculation we need to copy the image
    # directories
    if hasattr(self, 'neb'):
        import glob
        for imagedir in glob.glob('0[0-9]'):
            f.add(imagedir)
    f.close()

Vasp.archive = archive


def get_pseudopotentials(self):
    from os.path import join, isfile, islink
    ''' this is almost the exact code from the original initialize
    function, but all it does is get the pseudpotentials paths, and
    the git-hash for each one
    '''
    atoms = self.get_atoms()
    p = self.input_params

    self.all_symbols = atoms.get_chemical_symbols()
    self.natoms = len(atoms)
    # jrk 10/21/2013 I commented this line out as it was causing an
    # error in serialize by incorrectly resetting spinpol. I do not see
    # why this should be set here. It is not used in the function.
    # self.spinpol = atoms.get_initial_magnetic_moments().any()
    atomtypes = atoms.get_chemical_symbols()

    # Determine the number of atoms of each atomic species
    # sorted after atomic species
    special_setups = []
    symbols = {}
    if self.input_params['setups']:
        for m in self.input_params['setups']:
            try:
                special_setups.append(int(m))
            except:
                continue

    for m, atom in enumerate(atoms):
        symbol = atom.symbol
        if m in special_setups:
            pass
        else:
            if symbol not in symbols:
                symbols[symbol] = 1
            else:
                symbols[symbol] += 1

    # Build the sorting list
    self.sort = []
    self.sort.extend(special_setups)

    for symbol in symbols:
        for m, atom in enumerate(atoms):
            if m in special_setups:
                pass
            else:
                if atom.symbol == symbol:
                    self.sort.append(m)
    self.resort = range(len(self.sort))
    for n in range(len(self.resort)):
        self.resort[self.sort[n]] = n
    self.atoms_sorted = atoms[self.sort]

    # Check if the necessary POTCAR files exists and
    # create a list of their paths.
    self.symbol_count = []
    for m in special_setups:
        self.symbol_count.append([atomtypes[m], 1])
    for m in symbols:
        self.symbol_count.append([m, symbols[m]])

    sys.stdout.flush()
    xc = '/'

    if p['xc'] == 'PW91':
        xc = '_gga/'
    elif p['xc'] == 'PBE':
        xc = '_pbe/'
    if 'VASP_PP_PATH' in os.environ:
        pppaths = os.environ['VASP_PP_PATH'].split(':')
    else:
        pppaths = []
    self.ppp_list = []
    # Setting the pseudopotentials, first special setups and
    # then according to symbols
    for m in special_setups:
        name = 'potpaw'+xc.upper() + p['setups'][str(m)] + '/POTCAR'
        found = False
        for path in pppaths:
            filename = join(path, name)
            if isfile(filename) or islink(filename):
                found = True
                self.ppp_list.append(filename)
                break
            elif isfile(filename + '.Z') or islink(filename + '.Z'):
                found = True
                self.ppp_list.append(filename+'.Z')
                break
        if not found:
            log.debug('Looked for %s' % name)
            print 'Looked for %s' % name
            raise RuntimeError('No pseudopotential for %s:%s!' % (symbol,
                                                                  name))
    for symbol in symbols:
        try:
            name = 'potpaw' + xc.upper() + symbol + p['setups'][symbol]
        except (TypeError, KeyError):
            name = 'potpaw' + xc.upper() + symbol
        name += '/POTCAR'
        found = False
        for path in pppaths:
            filename = join(path, name)

            if isfile(filename) or islink(filename):
                found = True
                self.ppp_list.append(filename)
                break
            elif isfile(filename + '.Z') or islink(filename + '.Z'):
                found = True
                self.ppp_list.append(filename+'.Z')
                break
        if not found:
            print '''Looking for %s
                The pseudopotentials are expected to be in:
                LDA:  $VASP_PP_PATH/potpaw/
                PBE:  $VASP_PP_PATH/potpaw_PBE/
                PW91: $VASP_PP_PATH/potpaw_GGA/''' % name
            log.debug('Looked for %s' % name)
            print 'Looked for %s' % name
            raise RuntimeError('No pseudopotential for %s:%s!' % (symbol,
                                                                  name))
            raise RuntimeError('No pseudopotential for %s!' % symbol)

        # get sha1 hashes similar to the way git does it
        # http://stackoverflow.com/questions/552659/assigning-git-sha1s-without-git
        # git hash-object foo.txt  will generate a command-line hash
        hashes = []
        for ppp in self.ppp_list:
            f = open(ppp, 'r')
            data = f.read()
            f.close()

            s = sha1()
            s.update("blob %u\0" % len(data))
            s.update(data)
            hashes.append(s.hexdigest())

    stripped_paths = [ppp.split(os.environ['VASP_PP_PATH'])[1]
                      for ppp in self.ppp_list]
    return zip(symbols, stripped_paths, hashes)

Vasp.get_pseudopotentials = get_pseudopotentials

'''pre_run and post_run hooks

the idea here is that you can register some functions that will run
before and after running a Vasp calculation. These functions will have
the following signature: function(self). you might use them like this

def set_nbands(self):
   do something if nbands is not set

calc.register_pre_run_hook(set_nbands)

def enter_calc_in_database(self):
   do something

calc.register_post_run_hook(enter_calc_in_database)

maybe plugins
(http://www.luckydonkey.com/2008/01/02/python-style-plugins-made-easy/)
are a better way?

The calculator will store a list of hooks.

'''


def register_pre_run_hook(function):
    if not hasattr(Vasp, 'pre_run_hooks'):
        Vasp.pre_run_hooks = []
    Vasp.pre_run_hooks.append(function)


def register_post_run_hook(function):
    if not hasattr(Vasp, 'post_run_hooks'):
        Vasp.post_run_hooks = []
    Vasp.post_run_hooks.append(function)

Vasp.register_pre_run_hook = staticmethod(register_pre_run_hook)
Vasp.register_post_run_hook = staticmethod(register_post_run_hook)


def job_in_queue(self):
    ''' return True or False if the directory has a job in the queue'''
    if not os.path.exists('jobid'):
        return False
    else:
        # get the jobid
        jobid = open('jobid').readline().strip()
        if JASPRC['scheduler']=='PBS':
            # see if jobid is in queue
            jobids_in_queue = commands.getoutput('qselect').split('\n')
            if jobid in jobids_in_queue:
                # get details on specific jobid
                status, output = commands.getstatusoutput('qstat %s' % jobid)
                if status == 0:
                    lines = output.split('\n')
                    fields = lines[2].split()
                    job_status = fields[4]
                    if job_status == 'C':
                        return False
                    else:
                        return True
            else:
                return False

        if JASPRC['scheduler']=='SGE':
            # SGE qselect does not print a list of jobids, so we have to improvise
            jobids_in_queue = commands.getoutput("qstat | awk '{ print $1; }'").split('\n')[2:]
            if jobid in jobids_in_queue:
                # SGE apparently does not have jobstate == 'C', lets still get status and output for now
                status, output = commands.getstatusoutput('qstat | grep {0}'.format(jobid))

                if status == 0:
                    fields = output.split()
                    job_status = fields[4]                    
                    return True
            else:
                return False
Vasp.job_in_queue = job_in_queue


def calculation_required(self, atoms, quantities):
    '''Monkey-patch original function because (4,4,4) != [4,4,4] which
    makes the test on input_params fail'''

    if self.positions is None:
        log.debug('self.positions is None')
        return True
    elif self.atoms != atoms:
        log.debug('atoms have changed')
        log.debug('self.atoms = ', self.atoms)
        log.debug('atoms = ', self.atoms)
        return True
    elif self.float_params != self.old_float_params:
        log.debug('float_params have changed')
        return True
    elif self.exp_params != self.old_exp_params:
        log.debug('exp_params have changed')
        return True
    elif self.string_params != self.old_string_params:
        log.debug('string_params have changed.')
        log.debug('current: {0}'.format(self.string_params))
        log.debug('old    : {0}'.format(self.old_string_params))
        return True
    elif self.int_params != self.old_int_params:
        log.debug('int_params have changed')
        log.debug('current: {0}'.format(self.int_params))
        log.debug('old    : {0}'.format(self.old_int_params))
        return True
    elif self.bool_params != self.old_bool_params:
        log.debug('bool_params have changed')
        return True
    elif self.dict_params != self.old_dict_params:
        log.debug('current: {0}'.format(str(self.dict_params)))
        log.debug('old: {0}'.format(str(self.old_dict_params)))
        log.debug('dict_params have changed')
        return True

    for key in self.list_params:
        if (self.list_params[key] is None
            and self.old_list_params[key] is None):
            # no check required
            continue
        elif (self.list_params[key] is None
              or self.old_list_params[key] is None):
            # handle this because one may be a list and the other is
            # not, either way they are not the same. We cannot just
            # cast each element as a list, like we do in the next case
            # because list(None) raises an exception.
            log.debug('odd list_param case:')
            log.debug('current: {0} \n'.format(self.list_params[key]))
            log.debug('old: {0} \n'.format(self.old_list_params[key]))
            return True
        # here we explicitly make both lists so we can compare them
        if list(self.list_params[key]) != list(self.old_list_params[key]):
            log.debug('list_params have changed')
            log.debug('current: {0}'.format(self.list_params[key]))
            log.debug('old:     {0}'.format(self.old_list_params[key]))
            return True

    for key in self.input_params:
        if key == 'kpts':
            if (list(self.input_params[key])
                != list(self.old_input_params[key])):
                log.debug('1. {}'.format(list(self.input_params[key])))
                log.debug('2. {}'.format(list(self.old_input_params[key])))
                log.debug('KPTS have changed.')

                return True
            else:
                continue
        elif key == 'setups':
            log.warn('We do not know how to compare setups yet! '
                     'silently continuing.')
            continue
        elif key == 'txt':
            log.warn('We do not know how to compare txt yet!'
                     'silently continuing.')
            continue
        else:
            if self.input_params[key] != self.old_input_params[key]:
                print '{0} FAILED'.format(key)
                print self.input_params[key]
                print self.old_input_params[key]
                return True

    if 'magmom' in quantities:
        return not hasattr(self, 'magnetic_moment')

    if self.converged is None:
        self.converged = self.read_convergence()

    if not self.converged:
        if not JASPRC['restart_unconverged']:
            raise VaspNotConverged("This calculation did not converge."
                                   " Set JASPRC['restart_unconverged'] ="
                                   " True to restart")
        return True

    return False
Vasp.calculation_required = calculation_required

original_calculate = Vasp.calculate


def calculate(self, atoms=None):
    '''
    monkeypatched function to avoid calling calculate unless we really
    want to run a job. If a job is queued or running, we should exit
    here to avoid reinitializing the input files.

    I also made it possible to not give an atoms here, since there
    should be one on the calculator.
    '''
    if hasattr(self, 'vasp_queued'):
        raise VaspQueued('Queued', os.getcwd())

    if hasattr(self, 'vasp_running'):
        raise VaspRunning('Running', os.getcwd())

    if atoms is None:
        atoms = self.get_atoms()

    # this may not catch magmoms
    if not self.calculation_required(atoms, []):
        return

    if 'mode' in JASPRC:
        if JASPRC['mode'] is None:
            log.debug(self)
            log.debug('self.converged" %s', self.converged)
            raise Exception('''JASPRC['mode'] is None. '''
                            '''we should not be running!''')

    # finally run the original function
    original_calculate(self, atoms)

Vasp.calculate = calculate


def run(self):
    '''monkey patch to submit job through the queue.

    If this is called, then the calculator thinks a job should be run.
    If we are in the queue, we should run it, otherwise, a job should
    be submitted.

    '''
    if hasattr(self, 'pre_run_hooks'):
        for hook in self.pre_run_hooks:
            hook(self)

    # if we are in the queue and jasp is called or if we want to use
    # mode='run' , we should just run the job. First, we consider how.
    if 'PBS_O_WORKDIR' in os.environ or JASPRC['mode'] == 'run':
        log.info('In the queue. determining how to run')
        if 'PBS_NODEFILE' in os.environ:
            # we are in the queue. determine if we should run serial
            # or parallel
            NPROCS = len(open(os.environ['PBS_NODEFILE']).readlines())
            log.debug('Found {0} PROCS'.format(NPROCS))
            if NPROCS == 1:
                # no question. running in serial.
                vaspcmd = JASPRC['vasp.executable.serial']
                log.debug('NPROCS = 1. running in serial')
                exitcode = os.system(vaspcmd)
                return exitcode
            else:
                # vanilla MPI run. multiprocessing does not work on more
                # than one node, and you must specify in JASPRC to use it
                if (JASPRC['queue.nodes'] > 1
                    or (JASPRC['queue.nodes'] == 1
                        and JASPRC['queue.ppn'] > 1
                        and (JASPRC['multiprocessing.cores_per_process']
                             == 'None'))):
                    log.debug('queue.nodes = {0}'.format(JASPRC['queue.nodes']))
                    log.debug('queue.ppn = {0}'.format(JASPRC['queue.ppn']))
                    log.debug('multiprocessing.cores_per_process'
                              '= {0}'.format(JASPRC['multiprocessing.cores_per_process']))
                    log.debug('running vanilla MPI job')

                    print 'MPI NPROCS = ', NPROCS
                    vaspcmd = JASPRC['vasp.executable.parallel']
                    parcmd = 'mpirun -np %i %s' % (NPROCS, vaspcmd)
                    exitcode = os.system(parcmd)
                    return exitcode
                else:
                    # we need to run an MPI job on cores_per_process
                    if JASPRC['multiprocessing.cores_per_process'] == 1:
                        log.debug('running single core multiprocessing job')
                        vaspcmd = JASPRC['vasp.executable.serial']
                        exitcode = os.system(vaspcmd)
                    elif JASPRC['multiprocessing.cores_per_process'] > 1:
                        log.debug('running mpi multiprocessing job')
                        NPROCS = JASPRC['multiprocessing.cores_per_process']

                        vaspcmd = JASPRC['vasp.executable.parallel']
                        parcmd = 'mpirun -np %i %s' % (NPROCS, vaspcmd)
                        exitcode = os.system(parcmd)
                        return exitcode
        else:
            # probably running at cmd line, in serial.
            vaspcmd = JASPRC['vasp.executable.serial']
            exitcode = os.system(vaspcmd)
            return exitcode
        # end

    # if you get here, a job is getting submitted
    script = '#!/bin/{0}\n'.format(JASPRC['queue.shell'])
    script += 'module load {0}\n'.format(JASPRC['module'])
    script +='''cd {self.cwd}  # this is the current working directory
cd {self.vaspdir}  # this is the vasp directory
runjasp.py   # this is the vasp command
#end'''.format(**locals())


    if JASPRC['scheduler'] == 'PBS':
        jobname = self.vaspdir
        log.debug('{0} will be the jobname.'.format(jobname))
        log.debug('-l nodes={0}:ppn={1}'.format(JASPRC['queue.nodes'],
                                                JASPRC['queue.ppn']))

        cmdlist = ['{0}'.format(JASPRC['queue.command'])]
        cmdlist += [option for option in JASPRC['queue.options'].split()]
        cmdlist += ['-N', '{0}'.format(jobname),
                    '-l walltime={0}'.format(JASPRC['queue.walltime']),
                    '-l nodes={0}:ppn={1}'.format(JASPRC['queue.nodes'],
                                                  JASPRC['queue.ppn']),
                    '-l mem={0}'.format(JASPRC['queue.mem'])]

    elif JASPRC['scheduler'] == 'SGE':
        jobname = (self.vaspdir).replace('/','|') # SGE does not allow '/' in job names
        log.debug('{0} will be the jobname.'.format(jobname))        
        f = open('qscript','w')
        f.write(script)
        f.close()
        log.debug('-pe {0} {1}'.format(JASPRC['queue.pe'],
                                       JASPRC['queue.nprocs']))
        log.debug('-q {0}'.format(JASPRC['queue.q']))

        cmdlist = ['{0}'.format(JASPRC['queue.command'])]
        cmdlist += [option for option in JASPRC['queue.options'].split()]
        cmdlist += ['-N', '{0}'.format(jobname),
                    '-q {0}'.format(JASPRC['queue.q']),
                    '-pe {0} {1}'.format(JASPRC['queue.pe'], JASPRC['queue.nprocs'])
                    #'-l mem_free={0}'.format(JASPRC['queue.mem'])
                     ]
        cmdlist += ['qscript']

    log.debug('{0}'.format(' '.join(cmdlist)))
    p = Popen(cmdlist,
              stdin=PIPE, stdout=PIPE, stderr=PIPE)

    log.debug(script)

    out, err = p.communicate(script)

    if out == '' or err != '':
        raise Exception('something went wrong in qsub:\n\n{0}'.format(err))

    if JASPRC['scheduler'] == 'SGE':    
        jobid = out.split()[2]
    else:
        jobid =  out
    f = open('jobid', 'w')
    f.write(jobid)
    f.close()
    raise VaspSubmitted(out)

Vasp.run = run


def prepare_input_files(self):
    # Initialize calculations
    atoms = self.get_atoms()
    self.initialize(atoms)
    # Write input
    from ase.io.vasp import write_vasp
    write_vasp('POSCAR',
               self.atoms_sorted,
               symbol_count=self.symbol_count)
    self.write_incar(atoms)
    self.write_potcar()
    self.write_kpoints()
    self.write_sort_file()
    self.create_metadata()
Vasp.prepare_input_files = prepare_input_files


def pretty_print(self):
    '''
    __str__ function to print the calculator with a nice summary, e.g. jaspsum
    '''
    # special case for neb calculations
    if self.int_params['images'] is not None:
        # we have an neb.
        s = []
        s.append(': -----------------------------')
        s.append('  VASP NEB calculation from %s' % os.getcwd())
        try:
            images, energies = self.get_neb()
            for i, e in enumerate(energies):
                s += ['image {0}: {1: 1.3f}'.format(i, e)]
        except (VaspQueued):
            s += ['Job is in queue']
        return '\n'.join(s)

    s = []
    s.append(': -----------------------------')
    s.append('  VASP calculation from %s' % os.getcwd())
    if hasattr(self, 'converged'):
        s.append('  converged: %s' % self.converged)

    try:
        atoms = self.get_atoms()

        uc = atoms.get_cell()

        try:
            self.converged = self.read_convergence()
        except IOError:
            # eg no outcar
            self.converged = False

        if not self.converged:
            try:
                print self.read_relaxed()
            except IOError:
                print False
        if self.converged:
            energy = atoms.get_potential_energy()
            forces = atoms.get_forces()
        else:
            energy = np.nan
            forces = [np.array([np.nan, np.nan, np.nan]) for atom in atoms]

        if self.converged:
            if hasattr(self, 'stress'):
                stress = self.stress
            else:
                stress = None
        else:
            stress = None

        # get a,b,c,alpha,beta, gamma
        A = uc[0, :]
        B = uc[1, :]
        C = uc[2, :]

        a = np.linalg.norm(A)
        b = np.linalg.norm(B)
        c = np.linalg.norm(C)

        alpha = np.arccos(np.dot(B/np.linalg.norm(B),
                                 C/np.linalg.norm(C))) * 180/np.pi

        beta = np.arccos(np.dot(A/np.linalg.norm(A),
                                C/np.linalg.norm(C))) * 180/np.pi

        gamma = np.arccos(np.dot(B/np.linalg.norm(B),
                                 C/np.linalg.norm(C))) * 180/np.pi

        volume = np.abs(np.linalg.det(uc))

        s.append('  Energy = %f eV' % energy)
        s.append('\n  Unit cell vectors (angstroms)')
        s.append('        x       y     z      length')
        s.append('  a0 [% 3.3f % 3.3f % 3.3f] %3.3f' % (uc[0][0],
                                                        uc[0][1],
                                                        uc[0][2],
                                                        a))
        s.append('  a1 [% 3.3f % 3.3f % 3.3f] %3.3f' % (uc[1][0],
                                                        uc[1][1],
                                                        uc[1][2],
                                                        b))
        s.append('  a2 [% 3.3f % 3.3f % 3.3f] %3.3f' % (uc[2][0],
                                                        uc[2][1],
                                                        uc[2][2],
                                                        c))
        s.append('  a,b,c,alpha,beta,gamma (deg):'
                 '%1.3f %1.3f %1.3f %1.1f %1.1f %1.1f' % (a,
                                                          b,
                                                          c,
                                                          alpha,
                                                          beta,
                                                          gamma))
        s.append('  Unit cell volume = {0:1.3f} Ang^3'.format(volume))

        if stress is not None:
            s.append('  Stress (GPa):xx,   yy,    zz,    yz,    xz,    xy')
            s.append('            % 1.3f % 1.3f % 1.3f'
                     '% 1.3f % 1.3f % 1.3f' % tuple(stress))
        else:
            s += ['  Stress was not computed']

        constraints = None
        if hasattr(atoms, 'constraints'):
            from ase.constraints import FixAtoms, FixScaled
            constraints = [[None, None, None] for atom in atoms]
            for constraint in atoms.constraints:
                if isinstance(constraint, FixAtoms):
                    for i, constrained in enumerate(constraint.index):
                        if constrained:
                            constraints[i] = [True, True, True]
                if isinstance(constraint, FixScaled):
                    constraints[constraint.a] = constraint.mask.tolist()

        if constraints is None:
            s.append(' Atom#  sym       position [x,y,z]'
                     'tag  rmsForce')
        else:
            s.append(' Atom#  sym       position [x,y,z]'
                     'tag  rmsForce constraints')

        for i, atom in enumerate(atoms):
            rms_f = np.sum(forces[i]**2)**0.5
            ts = ('  {0:^4d} {1:^4s} [{2:<9.3f}'
                  '{3:^9.3f}{4:9.3f}]'
                  '{5:^6d}{6:1.2f}'.format(i,
                                           atom.symbol,
                                           atom.x,
                                           atom.y,
                                           atom.z,
                                           atom.tag,
                                           rms_f))
            # VASP has the opposite convention of constrained
            # Think: F = frozen
            if constraints is not None:
                ts += '      {0} {1} {2}'.format('F' if constraints[i][0]
                                                 is True else 'T',
                                                 'F' if constraints[i][1]
                                                 is True else 'T',
                                                 'F' if constraints[i][2]
                                                 is True else 'T')

            s.append(ts)

        s.append('--------------------------------------------------')
        if self.get_spin_polarized() and self.converged:
            s.append('Spin polarized: '
                     'Magnetic moment = %1.2f'
                     % self.get_magnetic_moment(atoms))

    except AttributeError:
        # no atoms
        pass

    if os.path.exists('INCAR'):
        # print all parameters that are set
        self.read_incar()
        ppp_list = self.get_pseudopotentials()
    else:
        ppp_list = [(None, None, None)]
    s += ['\nINCAR Parameters:']
    s += ['-----------------']
    for d in [self.int_params,
              self.float_params,
              self.exp_params,
              self.bool_params,
              self.list_params,
              self.dict_params,
              self.string_params,
              self.special_params,
              self.input_params]:

        for key in d:
            if key is 'magmom':
                np.set_printoptions(precision=3)
                value = textwrap.fill(str(d[key]),
                                      width=56,
                                      subsequent_indent=' '*17)
                s.append('  %12s: %s' % (key, value))
            elif d[key] is not None:
                value = textwrap.fill(str(d[key]),
                                      width=56,
                                      subsequent_indent=' '*17)
                s.append('  %12s: %s' % (key, value))

    s += ['\nPseudopotentials used:']
    s += ['----------------------']

    for sym, ppp, hash in ppp_list:
        s += ['{0}: {1} (git-hash: {2})'.format(sym, ppp, hash)]

    #  if ibrion in [5,6,7,8] print frequencies
    if self.int_params['ibrion'] in [5, 6, 7, 8]:
        freq, modes = self.get_vibrational_modes()
        s += ['\nVibrational frequencies']
        s += ['mode   frequency']
        s += ['------------------']
        for i, f in enumerate(freq):

            if isinstance(f, float):
                s += ['{0:4d}{1: 10.3f} eV'.format(i, f)]
            elif isinstance(f, complex):
                s += ['{0:4d}{1: 10.3f} eV'.format(i, -f.real)]
    return '\n'.join(s)

Vasp.__str__ = pretty_print

#########################################################################
def vasp_changed_bands(calc):
    '''Check here if VASP changed nbands.'''
    log.debug('Checking if vasp changed nbands')

    if not os.path.exists('OUTCAR'):
        return

    with open('OUTCAR') as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if 'The number of bands has been changed from the values supplied' in line:

                s = lines[i + 5]  # this is where the new bands are found
                nbands_cur = calc.nbands
                nbands_ori, nbands_new = [int(x) for x in
                                          re.search(r"I found NBANDS\s+ =\s+([0-9]*).*=\s+([0-9]*)", s).groups()]
                log.debug('Calculator nbands = {0}.\n'
                          'VASP found {1} nbands.\n'
                          'Changed to {2} nbands.'.format(nbands_cur,
                                                          nbands_ori,
                                                          nbands_new))

                calc.set(nbands=nbands_new)
                calc.write_incar(calc.get_atoms())

                log.debug('calc.kwargs: {0}'.format(calc.kwargs))
                if calc.kwargs.get('nbands', None) != nbands_new:
                    raise VaspWarning('The number of bands was changed by VASP. '
                                      'This happens sometimes when you run in '
                                      'parallel. It causes problems with jasp. '
                                      'I have already updated your INCAR. '
                                      'You need to change the number of bands '
                                      'in your script to match what VASP used '
                                      'to proceed.\n\n '
                                      + '\n'.join(lines[i - 9: i + 8]))


def checkerr_vasp(self):
    ''' Checks vasp output in OUTCAR for errors. adapted from atat code'''
    error_strings = ['forrtl: severe',  # seg-fault
                     'highest band is occupied at some k-points!',
                     'rrrr',  # I think this is from Warning spelled
                              # out in ascii art
                     'cnorm',
                     'failed',
                     'non-integer']

    # Check if VASP changed the bands
    vasp_changed_bands(self)

    errors = []
    if os.path.exists('OUTCAR'):
        f = open('OUTCAR')
        for i, line in enumerate(f):
            i += 1
            for es in error_strings:
                if es in line:
                    errors.append((i, line))
        f.close()

        converged = self.read_convergence()
        if not converged:
            errors.append(('Converged', converged))

        # Then if ibrion > 0, check whether ionic relaxation condition been
        # fulfilled, but we do not check ibrion >3 because those are vibrational
        # type calculations.
        if self.int_params['ibrion'] in [1, 2, 3]:
            if not self.read_relaxed():
                errors.append(('Ions/cell Converged', converged))

        if len(errors) != 0:
            f = open('error', 'w')
            for i, line in errors:
                f.write('{0}: {1}\n'.format(i, line))
            f.close()
        else:
            # no errors found, lets delete any error file that had existed.
            if os.path.exists('error'):
                os.unlink('error')
        if os.path.exists('error'):
            with open('error') as f:
                print 'Errors found:\n', f.read()
    else:
        if not hasattr(self, 'neb'):
            raise Exception('no OUTCAR` found')

Vasp.register_post_run_hook(checkerr_vasp)


def strip(self, extrafiles=()):
    '''removes large uncritical output files from directory'''
    files_to_remove = ['CHG', 'CHGCAR', 'WAVECAR'] + extrafiles

    for f in files_to_remove:
        if os.path.exists(f):
            os.unlink(f)

Vasp.strip = strip


def set_nbands(self, N=None, f=1.5):
    ''' convenience function to set NBANDS to N or automatically
    compute nbands

    for non-spin-polarized calculations
    nbands = int(nelectrons/2 + nions*f)

    this formula is suggested at
    http://cms.mpi.univie.ac.at/vasp/vasp/NBANDS_tag.html

    for transition metals f may be as high as 2.
    '''
    if N is not None:
        self.set(nbands=int(N))
        return
    atoms = self.get_atoms()
    nelectrons = self.get_valence_electrons()
    nbands = int(np.ceil(nelectrons/2.) + len(atoms)*f)
    self.set(nbands=nbands)

Vasp.set_nbands = set_nbands


def get_valence_electrons(self):
    '''Return all the valence electrons for the atoms.

    Calculated from the POTCAR file.
    '''
    if not os.path.exists('POTCAR'):
        self.initialize(self.get_atoms())
        self.write_potcar()
    default_electrons = self.get_default_number_of_electrons()

    d = {}
    for s, n in default_electrons:
        d[s] = n
    atoms = self.get_atoms()

    nelectrons = 0
    for atom in atoms:
        nelectrons += d[atom.symbol]
    return nelectrons

Vasp.get_valence_electrons = get_valence_electrons


def get_elapsed_time(self):
    '''Return elapsed calculation time in seconds from the OUTCAR file.'''
    import re
    regexp = re.compile('Elapsed time \(sec\):\s*(?P<time>[0-9]*\.[0-9]*)')

    with open('OUTCAR') as f:
        lines = f.readlines()

    m = re.search(regexp, lines[-8])

    time = m.groupdict().get('time', None)
    if time is not None:
        return float(time)
    else:
        return None
Vasp.get_elapsed_time = get_elapsed_time

old_read_ldau = Vasp.read_ldau


def read_ldau(self):
    '''Upon restarting the calculation, Vasp.read_incar() read
    list_keys ldauu, ldauj, and ldaul as list params, even though we
    are only allowed to define them through a dict key. If the
    calculation is complete, this is never a problem because we
    initially call read_incar(), and, seeing the ldauu, ldauj, and
    ldaul keys in the INCAR, VASP believes we initially defined them
    as lists. However, when we call restart a calculation and call
    read_ldau, this reads the ldauu, ldaul, and ldauj keys from the
    OUTCAR and sets the dictionary. We now have two instances where
    the ldauu, ldauj, and ldaul tags are stored (in the dict and list
    params)!

    This is particularly troublesome for continuation
    calculations. What happens is that Vasp writes the ldauu, ldaul,
    and ldauj tags twice, because it is stored in both the list_params
    and dict_params. The easiest way to get rid of this is when we
    read the ldauu, ldauj, and ldaul tags from the OUTCAR upon
    restart, we should erase the list params. This is what this
    function does.

    'Note: the problem persists with continuation calculations with
    nbands and magmoms.
    '''
    ldau, ldauprint, ldautype, ldau_luj = old_read_ldau(self)

    self.set(ldauu=None)
    self.set(ldaul=None)
    self.set(ldauj=None)
    return ldau, ldauprint, ldautype, ldau_luj

Vasp.read_ldau = read_ldau


def get_nearest_neighbor_table(self):
    """read the nearest neighbor table from OUTCAR

    returns a list of atom indices and the connecting neighbors. The
    list is not sorted according to self.sorted or self.resorted.
    """
    with open('OUTCAR') as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        if 'nearest neighbor table' in line:
            break

    # i contains index of line
    i += 1  # first line of the table

    # sometimes there is carriover to the next line.
    line_counter = 0

    NN = []

    while True:
        line = lines[i]
        if ('LATTYP' in line
            or line.strip() == ''):
            break
        line = lines[i].strip()
        if '        ' in lines[i+1]:
            # this was a continuation line
            line += lines[i+1]
            i += 2
        else:
            i += 1

        fields = line.split()

        atom_index = int(fields[0])
        nearest_neigbors = fields[4:]
        nn_indices = [int(nearest_neigbors[x])
                      for x in range(0, len(nearest_neigbors), 2)]
        nn_distances = [float(nearest_neigbors[x])
                        for x in range(1, len(nearest_neigbors), 2)]
        NN.append((atom_index, nn_indices))
    return NN

Vasp.get_nearest_neighbor_table = get_nearest_neighbor_table


# this fixes a bug in ase.calculators.vasp, which does not return a
# copy of the forces
def get_forces(self, atoms):
    self.update(atoms)
    return np.copy(self.forces)

Vasp.get_forces = get_forces


def get_energy_components(self, outputType=0):
    '''Returns all of the components of the energies.

    outputType = 0, returns each individual component

    outputType = 1, returns a major portion of the electrostatic
    energy and the total

    outputType = 2, returns a major portion of the electrostatic
    energy and the other components

    vasp forum may provide help:
    http://cms.mpi.univie.ac.at/vasp-forum/forum_viewtopic.php?4.273

    Contributed by Jason Marshall, 2014.
    '''
    # self.calculate()

    with open('OUTCAR') as f:
        lines = f.readlines()

    lineNumbers = []
    for i, line in enumerate(lines):
        # note: this is tricky, the exact string to search for is not
        # the last energy line in OUTCAR, there are space differences
        # ...  USER BEWARE: Be careful with this function ... may be
        # buggy depending on inputs
        if line.startswith('  free energy    TOTEN  ='):
            lineNumbers.append(i)

    lastLine = lineNumbers[-1]
    data = lines[lastLine - 10:lastLine]
    energies = []

    alphaZ = float(data[0].split()[-1])
    ewald = float(data[1].split()[-1])
    halfHartree = float(data[2].split()[-1])
    exchange = float(data[3].split()[-1])
    xExchange = float(data[4].split()[-1])
    PAWDoubleCounting1 = float(data[5].split()[-2])
    PAWDoubleCounting2 = float(data[5].split()[-1])
    entropy = float(data[6].split()[-1])
    eigenvalues = float(data[7].split()[-1])
    atomicEnergy = float(data[8].split()[-1])

    if outputType == 1:
        energies = [['electro', alphaZ + ewald + halfHartree],
                    ['else', exchange + xExchange + PAWDoubleCounting1
                     + PAWDoubleCounting2 + entropy + eigenvalues
                     + atomicEnergy],
                    ['total', alphaZ + ewald + halfHartree + exchange
                     + xExchange
                     + PAWDoubleCounting1 + PAWDoubleCounting2 + entropy
                     + eigenvalues + atomicEnergy]]
    elif outputType == 2:
        energies = [['electro', alphaZ + ewald + halfHartree],
                    ['exchange', exchange],
                    ['xExchange', xExchange],
                    ['PAW', PAWDoubleCounting1 + PAWDoubleCounting2],
                    ['entropy', entropy],
                    ['eigenvalues', eigenvalues],
                    ['atomicEnergy', atomicEnergy],
                    ['total', alphaZ + ewald + halfHartree + exchange
                     + xExchange
                     + PAWDoubleCounting1 + PAWDoubleCounting2 + entropy
                     + eigenvalues + atomicEnergy]]
    else:
        energies = [['alphaZ', alphaZ],
                    ['ewald', ewald],
                    ['halfHartree', halfHartree],
                    ['exchange', exchange],
                    ['xExchange', xExchange],
                    ['PAW', PAWDoubleCounting1 + PAWDoubleCounting2],
                    ['entropy', entropy],
                    ['eigenvalues', eigenvalues],
                    ['atomicEnergy', atomicEnergy]]

    return energies

Vasp.get_energy_components = get_energy_components


def get_beefens(self, n=-1):
    '''Get the BEEFens 2000 ensemble energies from the OUTCAR.

    This only works with Vasp 5.3.5 compiled with libbeef.

    I am pretty sure this array is the deviations from the total
    energy. There are usually 2000 of these, but it is not clear this will
    always be the case. I assume the 2000 entries are always in the same
    order, so you can calculate ensemble energy differences for reactions,
    as long as the number of samples in the ensemble is the same.

    There is usually more than one BEEFens section. By default we return
    the last one. Choose another one with the the :par: n.

    see http://suncat.slac.stanford.edu/facility/software/functional/
    '''
    beefens = []
    with open('OUTCAR') as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if 'BEEFens' in line:
                nsamples = int(re.search('(\d+)', line).groups()[0])
                beefens.append([float(x) for x in lines[i + 1: i + nsamples]])
    return np.array(beefens[n])

Vasp.get_beefens = get_beefens

def get_orbital_occupations(self):
    '''Read occuations from OUTCAR.
    Returns a numpy array of
    [[s, p, d tot]] for each atom.

    You probably need to have used LORBIT=11 for this function to
    work.
    '''

    # this finds the last entry of occupations. Sometimes, this is printed multiple times in the OUTCAR.
    with open('OUTCAR', 'r') as f:
        lines = f.readlines()
        start = None
        for i,line in enumerate(lines):
            if line.startswith(" total charge "):
                start = i

    if not i:
        raise Exception('Occupations not found')

    atoms = self.get_atoms()
    occupations = []
    for j in range(len(atoms)):
        line = lines[start + 4 + j]
        fields = line.split()
        s, p, d, tot = [float(x) for x in fields[1:]]
        occupations.append(np.array((s, p, d, tot)))
    return np.array(occupations)

Vasp.get_orbital_occupations = get_orbital_occupations

def get_number_of_ionic_steps(self):
    "Returns number of ionic steps from the OUTCAR."
    nsteps = None
    for line in open('OUTCAR'):
        # find the last iteration number
        if line.find('- Iteration') != -1:
            nsteps = int(line.split('(')[0].split()[-1].strip())
    return nsteps

Vasp.get_number_of_ionic_steps = get_number_of_ionic_steps


def get_required_memory(self):
    ''' Returns the recommended memory needed for a VASP calculation

    Code retrieves memory estimate based on the following priority:
    1) METADATA
    2) existing OUTCAR
    3) run diagnostic calculation

    The final method determines the memory requirements from
    KPOINT calculations run locally before submission to the queue
    '''
    import json

    def get_memory():
        ''' Retrieves the recommended memory from the OUTCAR
        '''

        if os.path.exists('OUTCAR'):
            with open('OUTCAR') as f:
                lines = f.readlines()
        else:
            return None

        for line in lines:

            # There can be multiple instances of this,
            # but they all seem to be identical
            if 'memory' in line:

                # Read the memory usage
                required_mem = float(line.split()[-2]) / 1e6
                return required_mem

    # Attempt to get the recommended memory from METADATA
    # JASP automatically generates a METADATA file when
    # run, so there should be no instances where it does not exist
    with open('METADATA', 'r') as f:
        data = json.load(f)

    try:
        memory = data['recommended.memory']
    except(KeyError):
        # Check if an OUTCAR exists from a previous run
        if os.path.exists('OUTCAR'):
            memory = get_memory()

            # Write the recommended memory to the METADATA file
            with open('METADATA', 'r+') as f:

                data = json.load(f)
                data['recommended.memory'] = memory
                f.seek(0)
                json.dump(data, f)

        # If no OUTCAR exists, we run a 'dummy' calculation
        else:
            original_ialgo = self.int_params.get('ialgo')
            self.int_params['ialgo'] = -1

            # Generate the base files needed for VASP calculation
            atoms = self.get_atoms()
            self.initialize(atoms)

            from ase.io.vasp import write_vasp
            write_vasp('POSCAR',
                       self.atoms_sorted,
                       symbol_count=self.symbol_count)
            self.write_incar(atoms)
            self.write_potcar()
            self.write_kpoints()
            self.write_sort_file()

            # Need to pass a function to Timer for delayed execution
            def kill():
                process.kill()

            # We only need the memory estimate, so we can greatly
            # accelerate the process by terminating after we have it
            process = Popen(JASPRC['vasp.executable.serial'],
                            stdout=PIPE)

            from threading import Timer
            timer = Timer(20.0, kill)
            timer.start()
            while True:
                if timer.is_alive():
                    memory = get_memory()
                    if memory:
                        timer.cancel()
                        process.terminate()
                        break
                    else:
                        time.sleep(0.1)
                else:
                    raise RuntimeError('Memory estimate timed out')

            # return to original settings
            self.int_params['ialgo'] = original_ialgo
            self.write_incar(atoms)

            # Write the recommended memory to the METADATA file
            with open('METADATA', 'r+') as f:

                data = json.load(f)
                data['recommended.memory'] = memory
                f.seek(0)
                json.dump(data, f)

            # Remove all non-initialization files
            files = ['CHG', 'CHGCAR', 'CONTCAR', 'DOSCAR',
                     'EIGENVAL', 'IBZKPT', 'OSZICAR', 'PCDAT',
                     'vasprun.xml', 'OUTCAR', 'WAVECAR', 'XDATCAR']

            for f in files:
                os.unlink(f)

    # Each node will require the memory read from the OUTCAR
    nodes = JASPRC['queue.nodes']
    ppn = JASPRC['queue.ppn']

    # Return an integer
    import math
    total_memory = int(math.ceil(nodes * ppn * memory))

    JASPRC['queue.mem'] = '{0}GB'.format(total_memory)

    # return the memory as read from the OUTCAR
    return memory

Vasp.get_required_memory = get_required_memory


def chgsum(self):
    '''
    Uses the chgsum.pl utility to sum over the AECCAR0 and AECCAR2 files
    '''
    cmdlist = ['chgsum.pl', 'AECCAR0', 'AECCAR2']
    p = Popen(cmdlist, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    out, err = p.communicate()
    if out == '' or err != '':
        raise Exception('Cannot perform chgsum:\n\n{0}'.format(err))

Vasp.chgsum = chgsum


def bader(self, cmd=None, ref=False, verbose=False, overwrite=False):

    '''
    Performs bader analysis for a calculation

    Follows defaults unless full shell command is specified

    Does not overwrite existing files if overwrite=False
    If ref = True, tries to reference the charge density to
    the sum of AECCAR0 and AECCAR2

    Requires the bader.pl (and chgsum.pl) script to be in the system PATH
    '''

    if 'ACF.dat' in os.listdir('./') and not overwrite:
        self._get_calculated_charges()
        return

    if cmd is None:
        if ref:
            self.chgsum()
            cmdlist = ['bader',
                       'CHGCAR',
                       '-ref',
                       'CHGCAR_sum']
        else:
            cmdlist = ['bader',
                       'CHGCAR']
    elif type(cmd) is str:
        cmdlist = cmd.split()
    elif type(cmd) is list:
        cmdlist = cmd

    p = Popen(cmdlist, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    out, err = p.communicate()
    if out == '' or err != '':
        raise Exception('Cannot perform Bader:\n\n{0}'.format(err))
    elif verbose:
        print('Bader completed for {0}'.format(self.vaspdir))

    # Now store calculated charges
    self._get_calculated_charges()

Vasp.bader = bader


def _get_calculated_charges(self,
                            atoms=None,
                            fileobj='ACF.dat',
                            displacement=1e-4):

    """Calculate the charges from the fileobj.
    This is a modified version of the attach_charges function in
    ase.io.bader to work better with VASP.
    Does not require the atom positions to be in Bohr and references
    the charge to the ZVAL in the POTCAR
    """

    if isinstance(fileobj, str):
        try:
            fileobj = open(fileobj)
            f_open = True
        except(IOError):
            return None

    if atoms is None:
        atoms = self.get_atoms()

    # Get the sorting and resorting lists
    sort = self.sort
    resort = self.resort

    # First get a dictionary of ZVALS from the pseudopotentials
    LOP = self.get_pseudopotentials()
    ppp = os.environ['VASP_PP_PATH']

    zval = {}
    for sym, ppath, hash in LOP:
        fullpath = ppp + ppath
        z = get_ZVAL(fullpath)
        zval[sym] = z

    # Get sorted symbols and positions according to POSCAR and ACF.dat
    symbols = np.array(atoms.get_chemical_symbols())[sort]
    positions = atoms.get_positions()[sort]

    charges = []
    sep = '---------------'
    i = 0  # Counter for the lines
    k = 0  # Counter of sep
    assume6columns = False
    for line in fileobj:
        if line[0] == '\n':  # check if there is an empty line in the
            i -= 1           # head of ACF.dat file
        if i == 0:
            headings = line
            if 'BADER' in headings.split():
                j = headings.split().index('BADER')
            elif 'CHARGE' in headings.split():
                j = headings.split().index('CHARGE')
            else:
                print('Can\'t find keyword "BADER" or "CHARGE".' \
                      + ' Assuming the ACF.dat file has 6 columns.')
                j = 4
                assume6columns = True
        if sep in line:  # Stop at last seperator line
            if k == 1:
                break
            k += 1
        if not i > 1:
            pass
        else:
            words = line.split()
            if assume6columns is True:
                if len(words) != 6:
                    raise IOError('Number of columns in ACF file incorrect!\n'
                                  'Check that Bader program version >= 0.25')

            sym = symbols[int(words[0]) - 1]
            charges.append(zval[sym] - float(words[j]))

            if displacement is not None:
                # check if the atom positions match
                xyz = np.array([float(w) for w in words[1:4]])
                assert np.linalg.norm(positions[int(words[0]) - 1] - xyz) < displacement
        i += 1

    if f_open:
        fileobj.close()

    # Now attach the resorted charges to the atom
    charges = np.array(charges)[resort]
    self._calculated_charges = charges

Vasp._get_calculated_charges = _get_calculated_charges


def get_charges(self, atoms=None):
    '''
    Returns a list of cached charges from a previous
    call to bader(). Useful for storing the charges to
    a database outside the context manager.
    '''

    if atoms is None:
        atoms = self.get_atoms()

    if hasattr(self, '_calculated_charges'):
        return self._calculated_charges
    else:
        return None

Vasp.get_charges = get_charges


def get_property(self, name, atoms=None, allow_calculation=True):
    """A function meant to mimic the get_property() function
    already implemented for non-VASP calculators in ASE.
    This function is required for proper usage of the ASE database
    the way it is currently written.
    """

    if atoms is None:
        atoms = self.get_atoms()

    if name == 'energy':
        return atoms.get_potential_energy()

    elif name == 'forces':
        return atoms.get_forces()

    elif name == 'stress':
        return atoms.get_stress()

    elif name == 'dipole':
        return atoms.get_dipole_moment()

    elif name == 'magmom' and hasattr(self, 'magnetic_moment'):
        return atoms.get_magnetic_moment()

    elif name == 'magmoms':
        return atoms.get_magnetic_moments()

    elif name == 'charges':
        return atoms.get_charges()

    elif name == 'free_energy':
        return atoms.get_potential_energy(force_consistent=True)
    else:
        raise NotImplementedError

Vasp.get_property = get_property

# implemented_properties = ['energy', 'forces', 'stress', 'dipole',
#                           'charges', 'magmom', 'magmoms']

# Vasp.implemented_properties = implemented_properties


# def get_property(self, name, atoms=None, allow_calculation=False):
#     if name not in self.implemented_properties:
#         raise NotImplementedError

#     if atoms is None:
#         atoms = self.atoms
#         system_changes = []
#     else:
#         system_changes = self.check_state(atoms)
#         if system_changes:
#             # self.reset()
#             # Vasp does not have a reset. Silently continue here...
#             pass

#     if name not in self.results:
#         return None
#         # if not allow_calculation:
#         #    return None
#         # We don't want to calculate things here...
#         # try:
#         #    self.calculate(atoms, [name], system_changes)
#         # except Exception:
#         #    self.reset()
#         #    raise

#     if name == 'magmom' and 'magmom' not in self.results:
#         return 0.0

#     if name == 'magmoms' and 'magmoms' not in self.results:
#         return np.zeros(len(atoms))

#     result = self.results[name]
#     if isinstance(result, np.ndarray):
#         result = result.copy()
#     return result

# Vasp.get_property = get_property


# def attach_results(self):
#     '''
#     Attaches values of the main properties to
#     self.results
#     '''

#     atoms = self.get_atoms()
#     results = {}
#     results['energy'] = atoms.get_potential_energy()
#     results['forces'] = atoms.get_forces()
#     self.results = results

# Vasp.attach_results = attach_results
