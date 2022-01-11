# -*- coding: utf-8 -*-
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
        return "%s bytes" % toSizeFloat(size)
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