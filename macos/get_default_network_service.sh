#!/bin/bash
networksetup -listnetworkserviceorder|grep "Device: $(get_default_interface.sh)"|sed -e 's/.*Hardware\ Port:\ \(.*\),.*/\1/'
