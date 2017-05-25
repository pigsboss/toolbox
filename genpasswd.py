#!/usr/bin/python2.7
import numpy as np
import sys

def is_valid(passwd):
    has_digit = False
    has_lower = False
    has_upper = False
    for i in range(ord('0'),ord('9')+1):
        if chr(i) in passwd:
            has_digit = True
            break
    for i in range(ord('a'),ord('z')+1):
        if chr(i) in passwd:
            has_lower = True
            break
    for i in range(ord('A'),ord('Z')+1):
        if chr(i) in passwd:
            has_upper = True
            break
    return has_digit & has_lower & has_upper

def randstr(length):
    cdata = np.uint8(np.random.rand(length)*(10.0+26.0*2))
    str = ''
    for i in range(length):
        if cdata[i]<10:
            str+=chr(ord('0')+cdata[i])
        elif cdata[i]<36:
            str+=chr(ord('a')+cdata[i]-10)
        else:
            str+=chr(ord('A')+cdata[i]-36)
    return str

def gen_valid_passwd(length,maxloops=1000):
    t=0
    while t<maxloops:
        str = randstr(length)
        if is_valid(str) is True:
            break
        t+=1
    return str

if __name__ == '__main__':
    length = eval(sys.argv[1])
    passwd = gen_valid_passwd(length)
    print passwd
