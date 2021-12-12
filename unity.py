# -*- coding: utf-8 -*-
import sys
import subprocess

HEAP = "heap"
MALLOC_HISTORY = "malloc_history"

if __name__ == "__main__":
    filePath = sys.argv[1]
    treeStr = subprocess.check_output([MALLOC_HISTORY, filePath, "-callTree"]).decode("ascii")

    print (treeStr)