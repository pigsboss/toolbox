#!/usr/bin/env python2
"""Fetch remote directories through rsync with parallelism and auto-retry.

Syntax:
fetch.py RSYNC_OPTS SRC LIST DEST

RSYNC_OPTS is the options for rsync.
SRC        is the URL of the remote parant path of all required directories.
LIST       is a local text file which contains all required directories.
DEST       is a local path which is the new parent path of required directories.
"""
## rsync error codes:
##
##   0     Success
##   1     Syntax or usage error
##   2     Protocol incompatibility
##   3     Errors selecting input/output files, dirs
##   4     Requested action not supported: an attempt was made to manipulate 64-bit
##         files on a platform that cannot support them; or an option was specified
##         that is supported by the client and not by the server.
##   5     Error starting client-server protocol
##   6     Daemon unable to append to log-file
##  10     Error in socket I/O
##  11     Error in file I/O
##  12     Error in rsync protocol data stream
##  13     Errors with program diagnostics
##  14     Error in IPC code
##  20     Received SIGUSR1 or SIGINT
##  21     Some error returned by waitpid()
##  22     Error allocating core memory buffers
##  23     Partial transfer due to error
##  24     Partial transfer due to vanished source files
##  25     The --max-delete limit stopped deletions
##  30     Timeout in data send/receive
##  35     Timeout waiting for daemon connection
##  

from threading import Thread
from os import path
import os,sys,subprocess,time
import numpy as np
nthreads = 4
retry    = 100
dispatch_on = True
display_on = True

try:
    rsync_opts = sys.argv[1]
    rsync_src  = sys.argv[2]
    with open(sys.argv[3], 'r') as f:
        fetch_list = [line[:-1] for line in f]
    rsync_dest = sys.argv[4]
except:
    print __doc__
    sys.exit()

if not path.isdir(rsync_dest):
    print '{} does not exist.'.format(rsync_dest)
    os.mkdir(rsync_dest)
    print '{} is created.'.format(rsync_dest)

jobs_pool = []
for i in range(len(fetch_list)):
    job = {}
    job['id']        = i
    job['command']   = ['rsync', rsync_opts, path.join(rsync_src, fetch_list[i]), rsync_dest]
    job['status']    = 'pending'
    job['return']    = None
    job['output']    = ''
    job['worker']    = None
    job['retry']     = retry
    jobs_pool.append(job)
njobs = len(jobs_pool)

workers_pool = []
for i in range(nthreads):
    worker = {}
    worker['id']     = i
    worker['output'] = []
    worker['status'] = 'idle'
    workers_pool.append(worker)

def display(interval=500.0):
    global jobs_pool, workers_pool
    job_progress = {}
    worker_progress = {}
    job_status = ['pending', 'syncing', 'broken', 'failed', 'completed']
    worker_status = ['idle', 'working', 'dismissed']
    tic = time.time()
    while display_on:
        ## update progress
        for s in job_status:
            job_progress[s] = 0
        for s in worker_status:
            worker_progress[s] = 0
        for job in jobs_pool:
            job_progress[job['status']] += 1
        for worker in workers_pool:
            worker_progress[worker['status']] += 1
        sys.stdout.write("\r\033[H\033[J")
        sys.stdout.flush()
        sys.stdout.write("{} seconds elapsed.\n".format(int(time.time()-tic)))
        sys.stdout.write("Workers ({} in total): {} idle, {} working, {} dismissed.\n".format(
            nthreads,
            worker_progress['idle'],
            worker_progress['working'],
            worker_progress['dismissed']
        ))
        sys.stdout.write("Jobs ({} in total): {} pending, {} syncing, {} broken, {} failed, {} completed.\n".format(
            njobs,
            job_progress['pending'],
            job_progress['syncing'],
            job_progress['broken'],
            job_progress['failed'],
            job_progress['completed']
        ))
        for worker in workers_pool:
            sys.stdout.write("\nWorker {} latest output:\n".format(worker['id']))
            sys.stdout.write('\n'.join(worker['output'][-5:]))
        sys.stdout.flush()
        time.sleep(interval/1000.0)

def dispatch(interval=100.0):
    """Dispatch pending jobs to idle workers.
interval - time delay in ms.
"""
    global jobs_pool, workers_pool, dispatch_on
    i = 0
    while dispatch_on:
        job = jobs_pool[i % njobs]
        if job['status'] == 'pending' and job['worker'] is None:
            for worker in workers_pool:
                if worker['status'] == 'idle':
                    job['worker'] = worker['id']
        time.sleep(interval/1000.0)
        i += 1

def rsync(worker_id, interval=10.0):
    global jobs_pool, workers_pool
    worker = workers_pool[worker_id]
    i = 0
    while worker['status'] != 'dismissed':
        job = jobs_pool[i % njobs]
        if job['worker'] == worker_id:
#            worker['output'].append('Job %d is dispatched to me.'%job['id'])
            if job['status'] == 'pending':
                worker['output'].append('Job %d is pending.'%job['id'])
                worker['status'] = 'working'
                try:
                    job['status'] = 'syncing'
                    output = subprocess.check_output(job['command'])
                    worker['output'] += output.split('\n')
                    job['status'] = 'completed'
                    job['return'] = 0
                except subprocess.CalledProcessError, e:
                    worker['output'] += e.output.split('\n')
                    job['return'] = e.returncode
                    if job['return'] < 30:
                        worker['output'].append('Job %d encounters fatal error (code: %d).'%(job['id'], job['return']))
                        job['status'] = 'failed'
                    else:
                        if 'Broken pipe' in e.output:
                            worker['output'].append('Job %d is broken. We will retry it later.'%job['id'])
                            job['status'] = 'broken'
                        else:
                            worker['output'].append('Job %d encounters unknown error. We give up.'%job['id'])
                            job['status'] = 'failed'
                worker['status'] = 'idle'
            elif job['status'] == 'syncing':
                worker['output'].append('Conflict! Job %d is syncing.'%job['id'])
#                raise StandardError('Conflict! A job in working has been re-dispatched.')
            elif job['status'] == 'broken':
                worker['output'].append('Job %d is broken.'%job['id'])
                worker['output'].append('Job %d has %d retry left.'%(job['id'],job['retry']))
                worker['status'] = 'working'
                if job['retry'] > 0:
                    job['retry'] -= 1
                    job['status'] = 'pending'
                else:
                    worker['output'].append('Job %d is failed because it does not have retry left.')
                    job['status'] = 'failed'
                worker['status'] = 'idle'
            elif job['status'] == 'failed':
                worker['output'].append('Job %d is failed.'%job['id'])
            elif job['status'] == 'completed':
                worker['output'].append('Job %d is completed.'%job['id'])
            else:
                raise StandardError('Status %s is undefined.'%job['status'])
        time.sleep(interval/1000.0)
        i += 1

displayer = Thread(target=display)
displayer.start()
dispatcher = Thread(target=dispatch)
dispatcher.start()
workers = []
for i in range(nthreads):
    worker = Thread(target=rsync, args=(i,))
    worker.start()
    workers.append(worker)
finished = np.zeros(njobs)
i = 0
while np.sum(finished) < njobs:
    job = jobs_pool[i % njobs]
    if job['status'] in ['failed', 'completed']:
        finished[i % njobs] = 1
    time.sleep(0.1)
    i += 1
display_on = False
displayer.join()
dispatch_on = False
dispatcher.join()
for i in range(nthreads):
    workers_pool[i]['status'] = 'dismissed'
    workers[i].join()
