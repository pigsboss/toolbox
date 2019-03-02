#!/bin/bash
route -n get default|grep 'gateway: '|sed 's/.*gateway:\ \(.*\)/\1/'
