# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import utils
import functools
from multiprocessing import Pool 

class Region(object):

    PURGABLE_MODE_VOLATILE = "V"
    PURGABLE_MODE_NON_VOLATILE = "N"
    PURGABLE_MODE_EMPTY = "E"

    def __init__(self):
        self.type = ""
        self.start = 0
        self.end = 0
        self.virtualSize = 0
        self.residentSize = 0
        self.dirtySize = 0
        self.swappedSize = 0
        self.purgableMode = Region.PURGABLE_MODE_NON_VOLATILE
        self.detail = ""
    
    def accountForFootPrint(self):
        if self.purgableMode == Region.PURGABLE_MODE_VOLATILE:
            return False
        return self.dirtySize > 0 or self.swappedSize > 0

class RegionParser(object):
    def __init__(self, title):
        self.addrSepIndex = title.find("START - END") + 6
        self.sizeStart = title.find("[ VSIZE") + 1
        self.sizeEnd = title.find("SWAP]") + 4
        self.purgableModeIndex = title.find("PURGE")
        self.detailIndex = title.find("REGION DETAIL")

    def parse(self, s):
        # print ("parsing: %s" % s)
        sj = self.addrSepIndex
        si = sj - 1
        while s[si].isalnum():
            si -= 1
        si += 1

        region = Region()
        region.type = s[:si].rstrip()
        region.start = int(s[si:sj], 16)

        ei = sj + 1
        ej = ei + 1
        while s[ej].isalnum():
            ej += 1
        region.end = int(s[ei:ej], 16)

        sizeTokens = s[self.sizeStart:self.sizeEnd].split()
        region.virtualSize = utils.strToSize(sizeTokens[0])
        region.residentSize = utils.strToSize(sizeTokens[1])
        region.dirtySize = utils.strToSize(sizeTokens[2])
        region.swappedSize = utils.strToSize(sizeTokens[3])
        
        tok = s[self.purgableModeIndex:self.purgableModeIndex+7]
        if tok == "       ":
            region.purgableMode = ""
        else:
            region.purgableMode = tok[-1]
        region.detail = s[self.detailIndex:].rstrip()
        return region

def getRegions(memgraph):
    s = subprocess.check_output(["vmmap", "-submaps", "-noCoalesce", "-interleaved", memgraph])
    BEGIN = "==== regions for"
    END = "==== Legend"
    ibeg = s.find(BEGIN) + len(BEGIN)
    ibeg = s.find(os.linesep, ibeg) + len(os.linesep)
    iend = s.find(END, ibeg)

    lines = s[ibeg:iend].split(os.linesep)
    regions = []
    parser = RegionParser(lines[0])
    for i in range(1, len(lines) - 2):
        region = parser.parse(lines[i])
        if region.dirtySize + region.swappedSize > 0 and region.purgableMode != Region.PURGABLE_MODE_VOLATILE:
            regions.append(region)
    return regions

def getMallocs(memgraph):
    s = subprocess.check_output(["heap", "--addresses=all", memgraph])
    BEGIN = "Active blocks in all zones that match pattern '.*':"
    ibeg = s.find(BEGIN) + len(BEGIN)
    ibeg = s.find(os.linesep, ibeg) + len(os.linesep)
    
    lines = s[ibeg:].split(os.linesep)
    addrs = []
    sizes = []
    for i in range(0, len(lines) - 2):
        line = lines[i]
        # print (line)
        addrs.append(int(line.split(":")[0], 16))
        sizeBeg = line.rfind("(") + 1
        sizeEnd = line.rfind(" ")
        sizes.append(int(line[sizeBeg: sizeEnd]))
    return addrs, sizes

def excludeMallocRegions(regions, mallocAddrs):
    i = 0
    j = 0
    imax = len(regions)
    jmax = len(mallocAddrs)
    outRegions = []
    while i < imax and j < jmax:
        addr = mallocAddrs[j]
        region = regions[i]
        if addr < region.start:
            j += 1
            continue
        i += 1
        if addr >= region.end:
            outRegions.append(region)
    return outRegions

def hasStack(memgraph, addr):
    s = subprocess.check_output(["malloc_history", memgraph, "-allBySize", "-q", hex(addr)])
    return s.find("1 call for") != -1
    
def report(memgraph):
    regions = getRegions(memgraph)
    mallocAddrs, mallocSizes = getMallocs(memgraph)
    vmRegions = excludeMallocRegions(regions, mallocAddrs)

    untrackedSize = 0
    i = 0
    mallocN = len(mallocAddrs)
    pool = Pool()
    for bHasStack in pool.imap(functools.partial(hasStack, memgraph), mallocAddrs):
        sz = mallocSizes[i]
        if not bHasStack:
            untrackedSize += sz
        i += 1

    print ("")
    print ("untracked malloc size: %s" % utils.sizeToStr(untrackedSize * 1000))

    for region in vmRegions:
        if not hasStack(memgraph, region.start):
            print ("untracked vm region at 0x%x, size=%d bytes" % (region.start, region.dirtySize + region.swappedSize))
            untrackedSize += region.dirtySize + region.swappedSize

    print ("untracked size: %s" % utils.sizeToStr(untrackedSize * 1000))

if __name__ == "__main__":
    report(sys.argv[1])



