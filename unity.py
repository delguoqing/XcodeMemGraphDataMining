# -*- coding: utf-8 -*-
import sys
import subprocess
import os
import re

HEAP = "heap"
MALLOC_HISTORY = "malloc_history"

START_MARK = "Call graph:"
END_MARK = "Total number in stack -- this line is here to get the correct format for importing with the Sampler instrument in Instruments.app"

# 这个工具打印的size，最多只会有3个有效数字
# 所以KB=1000
KB = 1024
MB = KB * KB
GB = KB * KB * KB

def toSizeFloat(number):
    a = number // 1000
    b = number % 1000
    ret = str(a)
    rem = 3 - len(ret)
    if rem <= 0:
        return ret
    strB = str(b)
    strB = strB.zfill(3)
    ret += "." + strB[:rem]
    return ret

# 这两个函数的写法是为了保证提取信息和转换回去的结果能完全一致
# 这样才能够用sample数据来做测试
# 可能有更简单的写法，太久不写python忘了
def sizeToStr(size):
    if size < KB * 1000:
        return "%d bytes" % (size // 1000)
    elif size < MB * 1000:
        return "%sK" % toSizeFloat(size // KB)
    elif size < GB * 1000:
        return "%sM" % toSizeFloat(size // MB)
    else:
        return "%sG" % toSizeFloat(size // GB)

def strToSize(sizeStr):
    digitEnd = len(sizeStr)
    dotPosition = -1
    for i in range(len(sizeStr)):
        if sizeStr[i] == ".":
            dotPosition = i
        elif not sizeStr[i].isdigit():
            digitEnd = i
            break
    
    if dotPosition == -1:
        v = int(sizeStr[:digitEnd]) * 1000
    else:
        a = int(sizeStr[:dotPosition])
        b = int(sizeStr[dotPosition + 1: digitEnd])
        v = a * 1000 + b * (10 ** (4 - digitEnd + dotPosition))

    unit = sizeStr[digitEnd:]
    if unit == "G":
        mul = GB
    elif unit == "M":
        mul = MB
    elif unit == "K":
        mul = KB
    else:
        mul = 1

    return v * mul

class Node(object):
    """
    name can be "???", in that case, a load address will be used instead.
    """
    def __init__(self):
        self.count = 0
        self.size = 0
        self.name = ""
        self.moduleName = ""
        self.address = 0
        self.offset = 0
        self.loadAddress = 0
        self.children = []

    def getReadableSize(self):
        return sizeToStr(self.size)

    def __str__(self):
        ret = str(self.count)
        if self.size != 0:
            ret += " (%s)" % self.getReadableSize()
        ret += " %s  (in %s)" % (self.name, self.moduleName)
        if self.name == "???":
            ret += "  load address 0x%x" % self.loadAddress
            ret += " + 0x%x  [0x%x]" % (self.offset, self.address)
        else:
            ret += " + %d  [0x%x]" % (self.offset, self.address)
        return ret

def findStartOfLine(lineStr):
    for i in range(len(lineStr)):
        if lineStr[i] not in " +!:|":
            return i, i
    raise RuntimeError("invalid line!")

def findCount(lineStr, start):
    end = len(lineStr)
    for j in range(start, len(lineStr)):
        if not lineStr[j].isdigit():
            end = j
            break
    if end == start:
        raise RuntimeError("invalid line! can't parse count")
    return int(lineStr[start:end]), end

def findSize(lineStr, start):
    oldStart = start
    start = lineStr.find('(', start)
    if start == -1:
        raise RuntimeError("invalid line! can't parse size!")
    if not lineStr[start + 1].isdigit():    # 我们可能没有size，不知道为啥。。。
        return 0, oldStart
    end = lineStr.find(')', start)
    if end == -1 or end == start + 1:
        raise RuntimeError("invalid line! can't parse size!")
    return strToSize(lineStr[start + 1: end]), end + 1

def findName(lineStr, start):
    end = lineStr.find("(in ", start)
    if end == -1:
        raise RuntimeError("invalid line! can't parse name!")
    return lineStr[start:end].strip(), end

def findModuleName(lineStr, start):
    start = lineStr.find("(in ", start) + 4
    end = lineStr.find(")", start + 1)
    return lineStr[start: end], end + 1

def findLoadAddress(lineStr, start):
    mark = "load address "
    start = lineStr.find(mark, start) + len(mark)
    end = lineStr.find("+", start)
    return int(lineStr[start: end].strip(), 16), end

def findOffset(lineStr, start):
    start = lineStr.find("+", start) + 1
    end = lineStr.find("[", start)
    token = lineStr[start: end].strip()
    if token.startswith("0x"):
        return int(token, 16), end
    else:
        return int(token), end

def findAddress(lineStr, start):
    start = lineStr.find("[", start) + 1
    end = lineStr.find("]", start + 1)
    return int(lineStr[start: end], 16), end + 1

def buildNode(parent, lines):
    lineStr = lines.pop()
    # print (lineStr)
    nd = Node()
    indent, offset = findStartOfLine(lineStr)
    nd.count, offset = findCount(lineStr, offset)
    nd.size, offset = findSize(lineStr, offset)
    nd.name, offset = findName(lineStr, offset)
    nd.moduleName, offset = findModuleName(lineStr, offset)
    if nd.name == "???":
        nd.loadAddress, offset = findLoadAddress(lineStr, offset)
    nd.offset, offset = findOffset(lineStr, offset)
    nd.address, offset = findAddress(lineStr, offset)
    if str(nd) != lineStr[indent:]:
        print(str(nd))
        print(lineStr[indent:])
        assert False

    while len(lines) != 0:
        l = lines[-1]
        ind, _ = findStartOfLine(l)
        if ind > indent:
            child = buildNode(parent, lines)
            nd.children.append(child)
        else:
            break
    return nd

# Root node is a bit special, it's like count (size) << TOTAL >>
def buildRootNode(lineStr):
    nd = Node()
    indent, offset = findStartOfLine(lineStr)
    nd.count, offset = findCount(lineStr, offset)
    nd.size, offset = findSize(lineStr, offset)
    nd.name = "<< TOTAL >>"
    return nd

def buildTree(treeStr):
    start = treeStr.find(START_MARK)
    if start == -1:
        return False
    start += len(START_MARK) + len(os.linesep)
    end = treeStr.find(END_MARK)
    if end == -1:
        return False
    lines = treeStr[start:end].strip().split(os.linesep)
    lines.reverse()

    root = buildRootNode(lines.pop())
    while len(lines) != 0:
        child = buildNode(root, lines)
        root.children.append(child)
    return True

if __name__ == "__main__":
    filePath = sys.argv[1]
    treeStr = subprocess.check_output([MALLOC_HISTORY, filePath, "-q", "-callTree"]).decode("ascii")
    succ = buildTree(treeStr)
    if not succ:
        print ("build tree failed! possibly not a valid output from malloc_history")
    else:
        print ("build tree successfully!")
