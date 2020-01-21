#!/usr/bin/env python3
#coding=utf-8
"""whatsnew.py compares signatures of two directories A and B in order to find files contained in A but not in B.

Syntax:
  whatsnew.py A.sig B.sig
  A.sig and B.sig are signatures of directories A and B, generated as:
  find A -type f -exec CHECKSUM {} \; > A.sig
  where CHECKSUM can be md5sum, sha224sum or other compatible programs.

Copyright: pigsboss@github
"""
import sys
from os import path

def compare_dict(a,b):
    """compare dict a and b, and list keys contained in a but not in b as well as values of those keys in a.
"""
    c = {}
    for k in a:
        if k not in b:
            c[k] = a[k]
    return c
def make_dict(input_file):
    """make dict of input signature file.
"""
    d = {}
    with open(path.normpath(path.abspath(path.realpath(input_file))),'r') as fp:
        for l in fp.read().splitlines():
            k,v = l.split(maxsplit=1)
            d[k] = v
    return d
if __name__ == '__main__':
    a_sig = sys.argv[1]
    b_sig = sys.argv[2]
    a_dict = make_dict(a_sig)
    b_dict = make_dict(b_sig)
    c_dict = compare_dict(a_dict, b_dict)
    if len(c_dict) > 0:
        print("New files:")
        for v in c_dict.values():
            print("  {}".format(v))
