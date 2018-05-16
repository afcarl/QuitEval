#!/usr/bin/env python3
import psutil
import argparse
import requests
import sys
import os
import datetime
import time
import threading
from subprocess import check_output

class QueryLogExecuter:
    logFile = ''
    commits = []

    def __init__(
            self,
            endpoint='http://localhost:8080/r43ples/sparql',
            logFile='execution.log',
            logDir='/var/logs',
            queryLog='',
            mode='bsbm-log',
            store=None,
            count=None):

        self.mode = mode
        self.endpoint = endpoint
        self.queryLog = queryLog
        self.logDir = logDir
        self.logFile = os.path.join(self.logDir, logFile)
        self.mode = mode
        self.store = store
        self.count = count

        try:
            response = requests.post(endpoint, data={'query': 'SELECT * WHERE {?s ?p ?o} LIMIT 1'}, headers={'Accept': 'application/json'})
        except Exception:
            raise Exception('Cannot access {}'.endpoint)

        if response.status_code == 200:
            pass
        else:
            raise Exception('Something wrong with sparql endpoint.')

        try:
            self.initQueryLog()
        except Exception:
            raise Exception('Could not read query log')

    def initQueryLog(self):
        queries = []
        if self.mode.lower() == 'bsbm-log':
            if os.path.isfile(self.queryLog):
                write = False
                query = []
                with open(self.queryLog, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('Query string:'):
                            write = True
                            query = []
                        elif line.startswith('Query result'):
                            write = False
                            queries.append(' '.join(query))
                            if len(queries) == self.count:
                                break
                        elif write is True:
                            query.append(line)
        elif self.mode.lower() == 'dataset_update':
            query = []
            delete_triples = 0
            queryType = 'insert'
            patterns = {'insert': {
                            'quit': 'WITH <urn:bsbm> INSERT DATA {{ {} }}',
                            'r43ples': 'INSERT DATA {GRAPH <urn:bsbm> REVISION "master" INSERT DATA {{ {} }}',
                            'rawbase': 'INSERT DATA {{ {} }} '},
                        'delete': {
                            'quit': 'WITH <urn:bsbm> DELETE DATA {{ {} }}',
                            'r43ples': 'DELETE DATA {GRAPH <urn:bsbm> REVISION "master" {{ {} }}',
                            'rawbase': 'DELETE DATA {{ {} }}'}}
            with open(self.queryLog, 'r') as f:
                # Toggle between INSERT and DELETE
                for i, line in enumerate(f):
                    if len(queries) == self.count:
                        break

                    line = line.strip()
                    if queryType == 'insert':
                        query.append(line)
                        if i != 0 and ((i-delete_triples)) % 40 == 0:
                            queries.append(patterns[queryType][self.store].format(' '.join(query)))
                            queryType = 'delete'
                            query = []
                    elif queryType == 'delete':
                        query.append(line)
                        delete_triples += 1
                        if ((delete_triples)) % 20 == 0:
                            queries.append(patterns[queryType][self.store].format(' '.join(query)))
                            queryType = 'insert'
                            query = []

        if len(queries) < self.count:
            print('Did not get enoug queries. Found {} queries'.format(len(queries)))
            sys.exit()
        else:
            print('Found {} queries'.format(len(queries)))
            self.queries = queries

    def runQueries(self):
        for query in self.queries:
            with open(self.logFile, 'a') as executionLog:
                start, end = self.postRequest(query)
                data = [str(end - start), str(start), str(end)]
                executionLog.write(' '.join(data) + '\n')

    def postRequest(self, query):
        start = datetime.datetime.now()
        res = requests.post(
            self.endpoint,
            data={'query': query},
            headers={'Accept': 'application/json'})
        end = datetime.datetime.now()
        return start, end

    def get_size(self, start_path='database/dataset'):
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(start_path):
            total_size += os.path.getsize(dirpath)
            # self.logger.debug("size {} of {}".format(os.path.getsize(dirpath), dirpath))
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
                # self.logger.debug("size {} of {}".format(os.path.getsize(fp), fp))
        return total_size / 1024

class MonitorThread(threading.Thread):
    """The Monitor Thread.

    Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition.
    """

    def __init__(self, logFile='memory.log', logDir='.'):
        self.logDir = logDir
        self.logFile = os.path.join(self.logDir, logFile)
        super(MonitorThread, self).__init__()
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

    def setstoreProcessAndDirectory(self, pid, observedDir='.', logDir='var/logs', logFile='memory.log'):
        # self.process = process
        print(pid, observedDir, logDir, logFile)
        self.PID = pid
        self.observedDir = observedDir

    def run(self):
        print("Start monitor on pid: {} in directory: {}".format(self.PID, self.observedDir))
        psProcess = psutil.Process(int(self.PID))
        du = 0
        mem = 0

        while not self.stopped():
            with open(self.logFile, 'a') as memoryLog:
                timestamp = float(round(time.time() * 1000) / 1000)
                try:
                    mem = float(psProcess.memory_info().rss) / 1024
                except Exception as exc:
                    print("Monitor exception: mem", exc)
                try:
                    du = self.get_size(self.observedDir)
                except Exception as exc:
                    print("Monitor exception: du {}".format(str(exc)))
                    try:
                        du = self.get_size(self.observedDir)
                    except Exception as exc:
                        print("Monitor exception failed again: du {}".format(str(exc)))
                        print("using old value for du {}".format(str(du)))
                memoryLog.write("{} {} {}\n".format(timestamp, du, mem))
                time.sleep(1)
        print("Monitor stopped")
    # print("Monitor Run finished and all resources are closed")
    # try:
    #     timestamp = float(round(time.time() * 1000) / 1000)
    #     try:
    #         mem = float(psProcess.memory_info().rss) / 1024
    #     except psutil.NoSuchProcess:
    #         mem = 0
    #         try:
    #             du = self.get_size(self.observedDir)
    #         except Exception as exc:
    #             du = 0
    #             logging.info("{} {} {}\n".format(timestamp, du, mem))
    #         except Exception as exc:
    #             print("Monitor exception when writing the last line: {}".format(str(exc)))


    def get_size(self, start_path='.'):
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(start_path):
            total_size += os.path.getsize(dirpath)
            # self.logger.debug("size {} of {}".format(os.path.getsize(dirpath), dirpath))
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
                # self.logger.debug("size {} of {}".format(os.path.getsize(fp), fp))
        return total_size / 1024


def getPID(name):
    return int(check_output(["pidof", name]))

def parseArgs(args):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-E', '--endpoint',
        type=str,
        default='http://localhost:8080/r43ples/sparql',
        help='Link to the SPARQL-Endpoint')

    parser.add_argument(
        '-L',
        '--logdir',
        type=str,
        default='/var/logs/',
        help='The link where to log the benchmark')

    parser.add_argument(
        '-O',
        '--observeddir',
        default='.',
        help='The directory that should be monitored')

    parser.add_argument(
        '-P',
        '--processid',
        help='The process id of the process to be monitored')

    parser.add_argument(
        '-Q',
        '--querylog',
        type=str,
        default='run.log',
        help='The link where to find a bsbm run log benchmark')

    parser.add_argument(
        '-M',
        '--mode',
        type=str,
        default='bsbm-log',
        help='The mode the log will be parsed. Chose between "bsbm-log" or "dataset_update".')

    parser.add_argument(
        '-S',
        '--store',
        type=str,
        help='Queries will be serialized for "quit", "r43ples" or "rawbase"')

    parser.add_argument(
        '-C',
        '--count',
        type=int,
        default=1000,
        help='The total number of queries that will be executed.')

    return parser.parse_args()


if __name__ == '__main__':
    args = parseArgs(sys.argv[1:])
    now = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M')
    print('Args', args)

    exe = QueryLogExecuter(
        endpoint=args.endpoint,
        logDir=args.logdir,
        logFile=now + '_execution.log',
        mode=args.mode,
        count=args.count,
        store=args.store,
        queryLog=args.querylog)

    if args.processid:
        mon = MonitorThread(logDir=args.logdir, logFile=now + '_memory.log')

        mon.setstoreProcessAndDirectory(
            pid=args.processid,
            observedDir=args.observeddir)
        mon.start()

    print('Starting Benchmark')
    exe.runQueries()
    print('Benchmark finished')

    if args.processid:
        mon.stop()
