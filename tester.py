#!/usr/bin/env python3

import time, subprocess


print ("this is a tester")
print ("This program should now restart")



COMMAND=['/home/pi/xbee-code/tester.py']


rc = subprocess.call(COMMAND)
    