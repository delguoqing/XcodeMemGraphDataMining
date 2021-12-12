# -*- coding: utf-8 -*-
import sys
import subprocess
import os

HEAP = "heap"
MALLOC_HISTORY = "malloc_history"

START_MARK = "Call graph:"
END_MARK = "Total number in stack -- this line is here to get the correct format for importing with the Sampler instrument in Instruments.app"

def buildTree(treeStr):
    start = treeStr.find(START_MARK)
    if start == -1:
        return False
    start += len(START_MARK) + len(os.linesep)
    end = treeStr.find(END_MARK)
    if end == -1:
        return False
    lines = treeStr[start:end].strip().split(os.linesep)
    return True

if __name__ == "__main__":
    filePath = sys.argv[1]
    treeStr = subprocess.check_output([MALLOC_HISTORY, filePath, "-q", "-callTree"]).decode("ascii")
    succ = buildTree(treeStr)
    if not succ:
        print ("build tree failed! possibly not a valid output from malloc_history")
    else:
        print ("build tree successfully!")
