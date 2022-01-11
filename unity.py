# -*- coding: utf-8 -*-
import sys
import subprocess
import os
import utils

HEAP = "heap"
MALLOC_HISTORY = "malloc_history"

START_MARK_CALL_TREE = "Call graph:"
END_MARK_CALL_TREE = "Total number in stack -- this line is here to get the correct format for importing with the Sampler instrument in Instruments.app"

START_MARK_ALL_BY_SIZE = "----"
END_MARK_ALL_BY_SIZE = "Binary Images"

ENABLE_VALIDATION = False   # debug模式，验证数据提取是不是有bug

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
        return utils.sizeToStr(self.size)

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

    def getSum(self):
        if len(self.children) == 0:
            return self.size
        sz = 0
        for child in self.children:
            sz += child.getSum()
        # if sz != self.size:
        #     print ("Size dismatch! %d != %d" % (sz, self.size))
        #     print (str(self))
        return sz

    # 根据叶子节点，自动重算非叶子节点的值
    def recalc(self):
        if len(self.children) == 0:
            return
        self.size = 0
        self.count = 0
        for child in self.children:
            child.recalc()
            self.size += child.size
            self.count += child.count

    def prettyPrint(self, depth=0):
        print (('  ' * depth) + str(self))
        for child in self.children:
            child.prettyPrint(depth + 1)

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
    if not lineStr[start + 1].isdigit():    # size可能不存在，因为malloc_history命令
                                            # 对于vm region来说，显示的是
                                            # dirty+swapped-purgableVolatile，而
                                            # 这个值可能为0
        return 0, oldStart
    end = lineStr.find(')', start)
    if end == -1 or end == start + 1:
        raise RuntimeError("invalid line! can't parse size!")
    return utils.strToSize(lineStr[start + 1: end]), end + 1

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
    if ENABLE_VALIDATION and str(nd) != lineStr[indent:]:
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
    start = treeStr.find(START_MARK_CALL_TREE)
    if start == -1:
        return None
    start += len(START_MARK_CALL_TREE) + len(os.linesep)
    end = treeStr.find(END_MARK_CALL_TREE)
    if end == -1:
        return None
    lines = treeStr[start:end].strip().split(os.linesep)
    lines.reverse()

    root = buildRootNode(lines.pop())
    while len(lines) != 0:
        child = buildNode(root, lines)
        root.children.append(child)
    return root

# 根据-allBySize的输出构建树形结构
# START_MARK为'----'
# END_MARK没有作用，一直在字符串结尾
def buildTree2(treeStr):
    start = treeStr.find(START_MARK_ALL_BY_SIZE)
    if start == -1:
        return None
    start += len(START_MARK_ALL_BY_SIZE) + len(os.linesep)
    end = treeStr.find(END_MARK_ALL_BY_SIZE, start)
    lines = treeStr[start:end].strip().split(os.linesep)

    # create a root node manually
    root = Node()
    root.name = "<< TOTAL >>"

    BEFORE_SIZE = ("1 call for", " calls for ")
    AFTER_SIZE = " bytes:"
    totalBytes = 0
    for line in lines:
        if len(line) == 0:
            continue
        if line[0] == '1' and line[1] == ' ':
            before_size = BEFORE_SIZE[0]
        else:
            before_size = BEFORE_SIZE[1]
        idx0 = line.find(before_size) + len(before_size)
        idx1 = line.find(AFTER_SIZE, idx0)
        size = int(line[idx0:idx1])
        totalBytes += size
    print ("totalBytes = %d" % totalBytes)

def filterNode(node, pattern):
    if pattern in node.name:
        return node.size
    sz = 0
    for child in node.children:
        sz += filterNode(child, pattern)
    return sz

# 用于测试实际累加的size与解析出来的值有何不同
# 这个函数会打印出查找到的第一个尺寸不匹配的节点及其子节点
def printFirstSizeDismatch(nd):
    nd_ = findFirstSizeDismatch(nd)
    if nd_ is None:
        print ("Nothing is different")
    else:
        nd_.prettyPrint(depth=0)

# 稍微有些低效，但是是外围函数，没事
def findFirstSizeDismatch(nd):
    readSize = nd.size
    calcSize = nd.getSum()
    if utils.sizeToStr(readSize) == utils.sizeToStr(calcSize):
        return None
    for child in nd.children:
        ret = findFirstSizeDismatch(child)
        if ret is not None:
            return ret
    return nd

def printFirstZeroSize(nd):
    nd_ = findFirstZeroSize(nd)
    if nd_ is None:
        print ("No zero-sized node!")
    else:
        nd_.prettyPrint(depth=0)

def findFirstZeroSize(nd):
    readSize = nd.size
    if readSize == 0:
        return nd
    for child in nd.children:
        ret = findFirstZeroSize(child)
        if ret is not None:
            return ret
    return None
    
def buildTreeByCallTree():
    filePath = sys.argv[1]
    print (filePath)
    treeStr = subprocess.check_output([MALLOC_HISTORY, filePath, "-q", "-callTree"]).decode("ascii")
    rootNode = buildTree(treeStr)
    if rootNode is None:
        print ("build tree failed! possibly not a valid output from malloc_history")
    else:
        print ("build tree successfully!")
        if len(sys.argv) > 2:
            pattern = sys.argv[2]
            print ("size for %s = %s" % (pattern, utils.sizeToStr(filterNode(rootNode, pattern))))
        
        # printFirstSizeDismatch(rootNode)
        # printFirstZeroSize(rootNode)

        # sm = rootNode.getSum()
        # print ("calculated sum = %d vs %d, diff=%d" % (sm, rootNode.size, sm - rootNode.size))
    return rootNode

def buildTreeByAllBySize():
    filePath = sys.argv[1]
    treeStr = subprocess.check_output([MALLOC_HISTORY, filePath, "-allBySize"]).decode("ascii")
    buildTree2(treeStr)

def reportMonoVM(rootNode):
    print (utils.sizeToStr(filterNode(rootNode, "GC_unmap") + filterNode(rootNode, "GC_unix_mmap_get_mem")))

def reportWWiseVM(rootNode):
    print (utils.sizeToStr(filterNode(rootNode, "AKPLATFORM::") + filterNode(rootNode, "ausdk::")))

def reportLuaVM(rootNode):
    print (utils.sizeToStr(filterNode(rootNode, "mmap_probe")))

def reportUnityVM(rootNode):
    print (utils.sizeToStr(filterNode(rootNode, "MemoryManager::VirtualAllocator::ReserveMemoryBlock")))

if __name__ == "__main__":
    # buildTreeByAllBySize()
    rootNode = buildTreeByCallTree()
        
