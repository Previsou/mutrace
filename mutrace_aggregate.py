#!/usr/bin/python

# parse output of mutrace, and aggregate data for multiple instances of mutexes

import re, sys

#  Mutex #   Locked  Changed    Cont. tot.Time[ms] cont.Time[ms] avg.Time[ms]  Flags
#     1390     3730     2754     1406        1.472        0.000        0.004 M-.--.
#     1971     8261     7344     1150       20.597        0.002        0.065 Mx.--.
# ....
#
#  Cond #    Waits  Signals    Cont. tot.Time[ms] cont.Time[ms] avg.Time[ms] Flags
#      33      101        1       99        0.476         0.000        0.000     -.
#       8      100        0       99        0.000         0.000        0.000     -.


# Type information
mutexInfo = {   'type': 'mutex',
                'headers_int': ['Locked', 'Changed', 'Cont'],
                'headers_dbl': ['tot', 'cont', 'avg'],
                'item_regex': re.compile("^Mutex #(\d+)", re.IGNORECASE)
            }
mutexInfo['table_regex'] = re.compile("^" \
        + "\s+(?P<%s>\d+)" % 'mutex' \
        + "".join([ "\s+(?P<%s>\d+)" % s for s in mutexInfo['headers_int']]) \
        + "".join([ "\s+(?P<%s>\d+\.\d+)" % s for s in mutexInfo['headers_dbl']]),
        re.IGNORECASE)

###############################################################################

condvarInfo = { 'type': 'condvar',
                'headers_int': ['Waits', 'Signals', 'Cont'],
                'headers_dbl': ['tot', 'cont', 'avg'],
                'item_regex': re.compile("^Condvar #(\d+)")
              }
condvarInfo['table_regex'] = re.compile("^" \
        + "\s+(?P<%s>\d+)" % 'condvar' \
        + "".join([ "\s+(?P<%s>\d+)" % s for s in condvarInfo['headers_int']]) \
        + "".join([ "\s+(?P<%s>\d+\.\d+)" % s for s in condvarInfo['headers_dbl']]))

###############################################################################

sig_line = re.compile("^\t")#.*\[0x[0-9a-f]+\]")

###############################################################################


class MutraceInfo(object):
    def __init__(self, typeInfo):
        self.backtraces = {}
        self.indices = {}
        self.nums = {}
        self.stats = {}
        self.aggregated = []
        self.typeInfo = typeInfo

    def aggregate(self, sortKey="Cont"):
        """Aggregate the traces and sort"""

        self.indices = dict(zip(self.backtraces, range(len(self.backtraces))))
        zeroes = [ 0 for _ in self.typeInfo['headers_int'] ]
        zeroes += [ 0.0 for _ in self.typeInfo['headers_dbl'] ]

        for sig in self.backtraces:
            s = zeroes
            for item in self.nums[sig]:
                if item in self.stats:
                    s = map(sum, zip(s, self.stats[item]))
            d = dict(zip(self.typeInfo['headers_int'] + self.typeInfo['headers_dbl'], s))

            d['Cont_p'] = 0.0
            if d.get('Locked',0) != 0:
                d['avg'] = d['cont'] / d['Locked']
                d['Cont_p'] = 100 * float(d['Cont']) / d['Locked']
            elif d.get("Waits",0) != 0:
                d['avg'] = d['cont'] / d['Waits']
                d['Cont_p'] = 100 * float(d['Cont']) / d['Waits']
            d['index'] = self.indices[sig]
            d['sig'] = sig
            self.aggregated += [d]

        self.aggregated.sort(key=lambda d: d[sortKey], reverse=True)

    def display(self, firstN=20):

        if firstN == None:
            firstN = len(self.aggregated)

        for stat in self.aggregated[:firstN]:
            sig = stat['sig']
            if sig == '':
	            continue

            l = self.nums[sig]
            if len(l) == 0:
                continue
            l.sort()
            l = map(str, l)

            print("#%s %d: (count: %d)" % (self.typeInfo['type'], self.indices[sig], len(l)))
            print(sig)

        print("------ Aggregated results -----")
        print(" ".join([' % 7s' % x for x in [self.typeInfo['type']] + self.typeInfo['headers_int'] ] \
                           + [' % 7s' % 'Cont_p'] \
                           + [' % 11s[ms]' % x for x in self.typeInfo['headers_dbl'] ]))

        for d in self.aggregated[:firstN]:
            if d.get('Locked',0) != 0 or d.get('Waits',0) != 0:
                print " ".join([' % 7d' % d[x] for x in ['index'] \
                         + self.typeInfo['headers_int'] ] \
                         + [' % 3.2f' % d['Cont_p']] \
                         + [' % 15.3f' % d[x] for x in self.typeInfo['headers_dbl'] ])
        print("\n\n")

###############################################################################
###############################################################################

def addBacktrace(sig, n, bt, mutrace):

    if sig != '':
        if sig not in mutrace.backtraces:
            mutrace.backtraces[sig] = bt
            mutrace.nums[sig]  = [n]
        else:
            mutrace.nums[sig] += [n]

def parseItem(line, (n,sig,bt,lastMatch), mutrace):

    typeInfo = mutrace.typeInfo
    varType = typeInfo['type']

    if varType == lastMatch: #shared regex for the tables, distinction based on state
        m = typeInfo['table_regex'].match(line)
        if m:
            addBacktrace(sig, n, bt, mutrace)
            d = m.groupdict()
            item = int(d[typeInfo['type']])
            mutrace.stats[item] = \
                [ int(d[s]) for s in typeInfo['headers_int'] ] \
                + [ float(d[s]) for s in typeInfo['headers_dbl'] ]
            return (0,'',[],typeInfo['type'])

    m = typeInfo['item_regex'].match(line)
    if m:
        addBacktrace(sig, n, bt, mutrace)
        n = int(m.group(1))
        return (n,'',[],typeInfo['type'])

    # Failed to match item
    return (n,sig,bt,'')


def parse(fileHandler, mutraceInfos):
    """Parse a file to gather mutex and/or condvar information"""

    parseMutex = "mutex" in mutraceInfos.keys()
    parseCondvar = "condvar" in mutraceInfos.keys()
    n, sig, bt = 0, '', []
    lastMatch = ""

    for line in fileHandler:
        # if looking for mutexes
        if parseMutex:
            (n, sig, bt, matched) = parseItem(line, (n,sig,bt, lastMatch), mutraceInfos['mutex'])
            if matched != '':
                lastMatch = matched
                continue

        if parseCondvar:
            (n, sig, bt, matched) = parseItem(line, (n,sig,bt, lastMatch), mutraceInfos['condvar'])
            if matched != '':
                lastMatch = matched
                continue

        m = sig_line.match(line)
        if m:
            sig += line
            bt += [line]

###############################################################################
###############################################################################

if __name__ == "__main__":


    mutraceInfos = {"mutex": MutraceInfo(mutexInfo),
                    "condvar": MutraceInfo(condvarInfo)}
    for filename in sys.argv:
        with open(filename, 'r') as fileHandler:
            parse(fileHandler, mutraceInfos)
    for info in mutraceInfos.values():
        info.aggregate("Cont_p")
        info.display(None)
