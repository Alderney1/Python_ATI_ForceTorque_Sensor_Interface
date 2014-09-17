__author__ = "Mats Larsen"
__copyright__ = "SINTEF, NTNU 2012"
__credits__ = ["Morten Lind"]
__license__ = "GPL"
__maintainer__ = "Mats Larsen"
__email__ = "matsla@{ntnu.no}"
__status__ = "Development"
#--------------------------------------------------------------------
#File: test_ati.py
#
#Module Description
"""
This module test ati.py, to see if it can be connected to the ATI
"""
#--------------------------------------------------------------------
#IMPORT
#--------------------------------------------------------------------
from ati_interface import ATI_INTERFACE
import numpy as np
import threading

import time
#--------------------------------------------------------------------
#CONSTANTS
#--------------------------------------------------------------------
LOG_LEVEL = 2 # Information level
ATI_PORT = 49152
#--------------------------------------------------------------------
#METHODS
#--------------------------------------------------------------------
class testReciver(threading.Thread):
    def __init__(self):
        """
        Threadomg
        """
        threading.Thread.__init__(self) # initialize th
        self.daemon = True
    def run(self):
        while True:

            data = ati.get_data_ATI(sync=True)
            print('----------------print data')
            print(data)

global ati
ati = ATI_INTERFACE(host='127.0.0.1',
                    port=ATI_PORT,
          name='ATI#test',
          timestamps=False,
          timestamps_reciver=False,
          headerstamps=False,
          socket_timeout=0.5,
          timeout=0.1,
          buffersize=5,
          log_level=2)

ati.wait_startup(1)
rec = testReciver()
rec.start()


#ati.set_streaming('STOP',0)
time.sleep(0.1)
while ati.alive == False:
    pass
ati.set_streaming('STOP',2)
ati.wait_for_mode(mode='STOP',timeout=0.5)
#a = ati.get_data_ATI(sync=True, timeout=None)
#print(a)

ati.set_streaming('REALTIME_BUFFERED',1)
ati.wait_for_mode(mode='REALTIME_BUFFERED',timeout=0.8)
#a = ati.get_data_ATI(sync=True, timeout=None)
#print(a)
time.sleep(0.1)
ati.set_streaming('STOP',0)
ati.wait_for_mode(mode='STOP',timeout=0.8)
#print(a)
"""

time.sleep(0.1)


time.sleep(0.1)
#ati.set_streaming('STOP',0)
time.sleep(0.1)
#ati.set_streaming('REALTIME',15)
time.sleep(0.1)

#ati.set_streaming('INFINITE',0)
time.sleep(0.1)

ati.set_streaming('REALTIME_BUFFERED',2)
#a = ati.get_data_ATI(sync=True, timeout=None)
#print(a)
time.sleep(0.5)

ati.set_streaming('INFINITE',0)
for x in range(0, 100):
    ati.get_data_ATI(sync=True, timeout=None)
    new = float((time.time() * 1000))
   # print('time = ' + str(( new - old)))
    old = new
ati.set_streaming('STOP',0)
"""
"""
meanlist = np.array(timelist[10:])
print('-------------------')
print(meanlist)
print('Mean = ' + str(np.mean(meanlist)) )
print('Std = ' + str(np.std(meanlist)) )
"""
"""
ati.set_streaming('REALTIME_STREAMING')
header, force, torque = ati.get_ft()
print('recieve data')
print(header)
print(force)
print(torque)
"""

ati.stop()
time.sleep(3)
print('END')
