#!/usr/bin/env python3
#coding=utf-8
"""Simple Unified Grouping Version Control.

Syntax:
  sugvc up[date]|st[atus] path

Copyright:
  pigsboss@github
"""
import sys
import os
from os import path
import subprocess
cwd = os.getcwd()
action = sys.argv[1]
grpath = path.normpath(path.abspath(path.realpath(sys.argv[2])))
assert path.isdir(grpath), '{} is not accessible.'.format(grpath)
for sub in os.listdir(grpath):
    subpath = path.normpath(path.abspath(path.realpath(path.join(grpath, sub))))
    print(subpath)
    if path.isdir(path.join(subpath, '.svn')):
        if action.startswith('up'):
            print(r'Update SVN local working copy: {}'.format(subpath))
            subprocess.run(['svn', 'up', subpath], check=True)
        elif action.startswith('st'):
            print(r'Check SVN local working copy: {}'.format(subpath))
            subprocess.run(['svn', 'st', subpath], check=True)
    elif path.isdir(path.join(subpath, '.git')):
        if action.startswith('up'):
            print(r'Update Git local branch: {}'.format(subpath))
            os.chdir(subpath)
            subprocess.run(['git', 'pull'], check=True)
        elif action.startswith('st'):
            print(r'Check Git local branch: {}'.format(subpath))
            os.chdir(subpath)
            subprocess.run(['git', 'status', '-s'], check=True)
os.chdir(cwd)
