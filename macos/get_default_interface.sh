#!/bin/bash
route -n get default|grep 'interface: '|sed -e 's/.*interface:\ \(.*\)/\1/'
