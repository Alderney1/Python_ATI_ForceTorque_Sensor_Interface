#--------------------------------------------------------------------
#Administration Details
#--------------------------------------------------------------------
__author__ = "Mats Larsen"
__copyright__ = "Mats Larsen 2014"
__credits__ = ["Mats Larsen, Morten Lind"]
__license__ = "GPLv3"
__maintainer__ = "Mats Larsen"
__email__ = "larsen.mats.87@gmail.com"
__status__ = "Development"
__description__ = "This module handle the interaction between the ft-sensor class and the ft-sensor. Here it can be data from the real sensor or from the simulation sensor. The sensor has several modes it can be running in. The ATI class has to be run as a thread, and the result can received in  synchronously and asynchronously way."
__file__ = "ati_controller.py"
#__class__ ="ATIController"
__dependencies__ = [""]

#--------------------------------------------------------------------
#IMPORT
#--------------------------------------------------------------------
import traceback
import threading
import struct
import socket
import sys
import time
import numpy as np
sys.path.append('C:\mats\git_mats\DeviceSocketInterface/code')
from device_interface import DeviceSocketInterface as DSI
sys.path.remove('C:\mats\git_mats\DeviceSocketInterface/code')

#--------------------------------------------------------------------
#CONSTANTS
#--------------------------------------------------------------------
#General
LOG_LEVEL = 2 # Information level
ALWAYS_LOG_LEVEL = 1 # print always
RECEIVE_FORMAT = '3I6i' # Format from the ATI sensor
COMMAND_HEADER = 0x1234 # Uint16_command_header
#Calibration
FORCE_CALIBRATION = 1000000.0
TORQUE_CALIBRATION = 1000000.0
#Uint16 command:
STOP_STREAMING = 0X0000 # Stop mode
REALTIME_STREAMING = 0x0002 # Fast (up to 7000 Hz)
REALTIME_BUFFERED_STREAMING = 0x0003 # Buffer mode
MULTI_UNIT_STREAMING = 0X0004 # Multi mode
INFINITE_STREAMING = 0x0000 #Infinite mode for realtime
STARTUP_STREAMING = 'STOP' # Mode it will start up with

#Modes for the ati box
modes = {STOP_STREAMING : 'stop_streaming_mode',
         REALTIME_STREAMING : 'realtime_streaming_mode',
         REALTIME_BUFFERED_STREAMING : 'realtime_streaming_buffered_mode',
         }
#--------------------------------------------------------------------
#METHODS
#-------------------------------------------------------------------
def log(msg, log_level=LOG_LEVEL):
    """Print a message, and track, where the log is invoked
    Input:
    -msg: message to be printed, ''
    -log_level: informationlevel"""
    global LOG_LEVEL
    if log_level <= LOG_LEVEL:
        print(str(log_level) + ' : ' + FILE + ' ::' +
              traceback.extract_stack()[-2][2] + ' : ' + msg)

class ATIController(threading.Thread):
    """Class for interacting withthe ati-box."""
    class Error(Exception):
        """Exception class."""
        def __init__(self, message):
            self.message = message
            Exception.__init__(self, self.message)
        def __repr__(self):
            return self.message

    def __init__(self, host=None, port=None, **kwargs): 
        """
        """
        # Arg Assignment
        self.__host = host  # ATI net box IP address on the network
        self.__port = port # port of the ATI box
        self.__name =  'ATI#' + kwargs.get('name','Invalid')
        self.__timeout = kwargs.get('timeout',0.1)
        self.__buffersize = kwargs.get('buffersize',1)
        self.__log_level = kwargs.get('log_level',2)
        
        #private assignment
        self.__streaming = STARTUP_STREAMING # streaming mode
        self.__current_streaming = self.__streaming # for state-machine
        
        self.__io = DSI(host=self.__host,port=self.__port,timeout=kwargs.get('socket_timeout',1.5),name=kwargs.get('name','Invalid'),timestamps=kwargs.get('timestamps',False),log_level=self.__log_level)
        
        self.__io.wait_startup(timeout=2)
        
        #Threading
        threading.Thread.__init__(self) # initialize th
        self.daemon = True
        #Condition
        self.__getdata_condition = threading.Condition() # Notify when sampled are handled
        #Event
        self.__thread_init = threading.Event() # status for the thread
        self.__thread_terminated = threading.Event() # status for the thread terminated
        self.__operational_mode = STOP_STREAMING
        self.__prev_opernational_mode = None
        self.__wait_stop_mode = threading.Event() # which process mode
        self.__wait_buffered_mode = threading.Event() # which process mode
        self.__wait_realtime_mode = threading.Event() # which process mode

        #Reset
        self.__wait_stop_mode.clear()
        self.__wait_buffered_mode.clear()
        self.__wait_realtime_mode.clear()

        self.__samples = 0
        self._info_data = None # Header force and torque data
        self._force_data = None
        self._torque_data = None
        self.__timelist = None # file for timestamps
        self.__thread_init.clear()
        self.__thread_terminated.clear()
        self.set_streaming(streaming='STOP') #ensure to stop the sensor

        #interface
      
        self.start() # start main loop
        log('ATI created:' + 'name = ' + self.__name, ALWAYS_LOG_LEVEL)

    def get_name(self):
        return self.__name
    name = property(get_name,'Name Property')
    def get_streaming(self):
        """ Property returning the streaming setting"""
        return self.__current_streaming
    streaming = property(get_streaming, "Streaming Property")

    def set_streaming(self, streaming = 'STOP',samples=1):
        """ Property setting the streaming to one of the 5 modes of the
        ft-sensor.
        Inputs:
        streaming:string -> defines one of the five modes.
        samples:int -> defines how many samples to receive"""
        log('Set streaming is set to ' + streaming, self.__log_level)
        self._samples = samples
        if streaming == 'STOP':# stop the ati transmission
            self.__streaming = STOP_STREAMING
            self.__send_request(streaming=self.__streaming) # send a request to sensor to stop
        elif streaming == 'REALTIME':# mode of realtime
            self.__streaming = REALTIME_STREAMING
            self.__samples = samples
        elif streaming == 'REALTIME_BUFFERED':# mode of realtime with buffer
            self.__streaming = REALTIME_BUFFERED_STREAMING
        elif streaming == 'MULTI_UNIT': # mode of multi unit
            self.__streaming = MULTI_UNIT_STREAMING
        elif streaming == 'INFINITE': # mode of inifinite streaming
            self.__streaming = REALTIME_STREAMING
            self.__samples = 0
        else:
            self.__streaming = None
            raise self.Error('ATI: ' + 'Streaming setup for ATI is ' +' not known on arguments :'
                                +  '"{}"'.format(str(streaming)))
    def check_connection(self,**kwargs):
        """
        To veritfy the connection and statistical results.
        """
        samples = kwargs.get('samples',100)
        timeout = kwargs.get('timeout',2)
        self.set_streaming(streaming='STOP')
        self.wait_for_mode(mode='STOP',timeout=timeout)
        

    def  __send_request(self,header=COMMAND_HEADER,streaming=REALTIME_STREAMING,
                       samples=1):
        """Send a request to the ATI. Setting of the property will be
        send here.
        Inputs:
        header:hex -> define the header command to the ft-sensor.
        streaming:str -> streaming mode.
        samples:int-> number of samples"""
        log('Request is send with  mode : ' + str(streaming) + ' and samples : ' + str(samples),self.__log_level)
        request = struct.pack("!HHi", COMMAND_HEADER,streaming,samples)
        self.__io.send_data(request)

    def __stop_streaming(self):
        """Will send stop_streaming to the ati-box."""
        log('Stop streaming', self.__log_level)
        request = struct.pack("!HHi", COMMAND_HEADER,STOP_STREAMING,self._samples)
        self.__io.send_data(request)    
        
    def get_format(self):
        """ Return the format for the struct format.
        Inputs:
        size:int-> how long the buffer will be."""
        #log('Performing get format',self._log_level)
        if self.__current_streaming == REALTIME_STREAMING:
            size = 1
        else:
            size = self._buffersize
        structformat = '!'
        for i in range(0,size):
            structformat += RECEIVE_FORMAT
        return structformat

    def __calibration(self,received):
        """Will calibrate the data, by separate the header and the data
        and applied the factor to the data. Plus minus the bias from
        the data. When data is handled it is notified to waiting threads.
        Inputs:list-> data from the ft-sensor"""
        log('Performing calibration', self.__log_level)

        if self.__current_streaming == REALTIME_STREAMING:
            size = 1
        else:
            size = self.__buffersize
        #initialize arrayes
        unp = struct.unpack(self.get_format(),received) # unpack the message
        #print(unp)
        self.__getdata_condition.acquire()
        self._info_data = np.array([[unp[0],unp[1],unp[2]]])
        self._force_data = np.array([[unp[3]/FORCE_CALIBRATION,unp[4]/FORCE_CALIBRATION,unp[5]/FORCE_CALIBRATION]],dtype=np.float)
        self._torque_data = np.array([[unp[6]/TORQUE_CALIBRATION,unp[7]/TORQUE_CALIBRATION,unp[8]/TORQUE_CALIBRATION]],dtype=np.float)
        for i in range(1, size):# loop the size of buffersize with calibration
            self._info_data = np.append(self._info_data,[[unp[0+i*9],unp[1+i*9],unp[2+i*9]]],axis=0)
            self._force_data = np.append(self._force_data,[[unp[3+i*9]/FORCE_CALIBRATION,unp[4+i*9]/FORCE_CALIBRATION,unp[5+i*9]/FORCE_CALIBRATION]],axis=0)
            self.__torque_data = np.append(self._torque_data,[[unp[6+i*9]/TORQUE_CALIBRATION,unp[7+i*9]/TORQUE_CALIBRATION,unp[8+i*9]/TORQUE_CALIBRATION]],axis=0)
        #Notify to others tasks that new sample are ready
        self.__getdata_condition.notifyAll()
        self.__getdata_condition.release()
        #print('INFO')
        #print(self._info_data)
        #print(self._force_data)
        #print(self._torque_data)
        
    def get_data_ATI(self, sync=True,timeout=None,data_type=None):
        """Used to get data from the run method. Return the
        force and torque. Combined with
        thread.condition it will return force and torque synchronously
        and without will be asynchronously
        Input:
        - sync: True=to be in sync, wait for next new sample.
        False=get data async.
        - timeout: break wait operation with a timeout."""
        log('Performing get data from ATI', self.__log_level)
        if sync == True: # synchronously operation
            print('in syc')
            if self.__wait_for_idle(timeout=timeout): # wait until data is recvied or timeout
                if data_type == None:
                    print('Getting data ATI-------')
                    return self._info_data, self._force_data, self._torque_data
                elif data_type == 'force':
                    return self._force_data
                elif data_type == 'force_torque':
                    return self._force_data, self._torque_data
                else:
                    raise self.Error('Data_type is not found !!!! : ' + '"{}"'.format(data_type))
            else:
                print('NOT Getting data ATI-------')
                if data_type == None:
                    return None, None, None
                elif data_type == 'force':
                    return None
                elif data_type == 'force_torque':
                    return None, None
                else:
                    raise self.Error('Data_type is not found !!!! : ' + '"{}"'.format(data_type))
         
        elif sync == False:
            if data_type == None:
                return self._info_data, self._force_data, self._torque_data
            elif data_type == 'force':
                return self._force_data
            elif data_type == 'force_torque':
                return self._force_data, self._torque_data
            else:
                raise self.Error('Data_type is not found !!!! : ' + '"{}"'.format(data_type))

        else:
            raise self.Error('ATI: ' + 'Sync setup for ATI is not ' +'correct or not known'
                             + '"{}"'.format(str(sync)))
    getdata  = property(get_data_ATI,"getdata property")

    def __wait_for_idle(self, timeout=None):
        """Call by get_data_ATI, to observe when this thread has
        sampled. Wait until a notified or a timeout occurs.
        - timeout: when a timeout occur,floating point,[s]."""
        log('Performing wait for idle', self.__log_level)
        self.__getdata_condition.acquire() # Acquire the underlying lock
        status = self.__getdata_condition.wait(timeout)
        self.__getdata_condition.release() # Release the underlying lock
        print(status)
        if status == None:
            return True
        else:
            return False

    def wait_for_mode(self,mode,timeout=1):
        """Wait for a specific mode."""
        if mode == 'STOP':
            self.__wait_stop_mode.wait(timeout)
            if self.__wait_stop_mode.isSet():
                log(mode + ' is in process :'  + '"{}"' + (mode), self.__log_level)
                print('--------------------------sandt er sat ')
            else:
                raise self.Error(mode + ' is not swicted in the given time :: ' + '"{}"'+ str(timeout))

                print('------------- IKKE SANDT MODE')
        elif mode == 'REALTIME':
            e = self.__wait_realtime_mode.wait(timeout)
            if self.__wait_realtime_mode.isSet():
                print('--------------------------sandt er sat ')
            else:
                print('------------- IKKE SANDT MODE')
        elif mode == 'REALTIME_BUFFERED':
            e = self._wait_buffered_mode.wait(timeout)
       

    def _measure_samplingfrequency(self):
        """Measure the timestamps, write to a file."""
        if self._timelist == None:
            self._timelist = open('Timestamps_ati', 'w')
            self._old = float((time.time() * 1000))
        else:
            new = float((time.time() * 1000))
            self._timelist.write(str((new - self._old)) + '\n' )
            self._old = new

    def _stop_streaming_mode(self):
        """STOP_STREAMING """
        log('STOP STREAMING MODE', self.__log_level)
        if self.__current_streaming == STOP_STREAMING: #Stop streaming, will continue to send stop request until it response appears.
            if self.__data != None: # If it still receiving data, send stop request again
                self.__send_request(streaming=self._streaming,samples=self._samples)
            elif self.__data == None: #  Receiving None data
                self.__operational_mode = self.__current_streaming
                #print(self._operational_mode)

    def _realtime_streaming_mode(self):
        """Realtime mode, contain both certain number of samples and infinite samples, depending of samples."""
        log('Performing realtime_mode', self.__log_level)
        if self.__current_streaming == REALTIME_STREAMING and self.__samples == INFINITE_STREAMING: #For inifinty streaming
             if self.__data == None: # none data, because of timeout
                 self.__send_request(streaming=self.__streaming,samples=self.__samples)
             elif self.__data != None: # data received
                 self.__operational_mode = self.__current_streaming
                 self.__calibration(received=self.__data)

        elif self.__current_streaming == REALTIME_STREAMING: #For realtime streaming with nr. of samples
            log('Performing realtime with limited samples', self.__log_level)
            if self.__data == None and self.__samples_temp == self.__samples:
                self.__send_request(streaming=self.__streaming,samples=self.__samples)
                log('send realtime ' + str(self.__samples_temp),self.__log_level)
            elif self.__data != None and self.__samples_temp > 0:
                self.__samples_temp -= 1
                self.__calibration(received=self.__data)

    def __realtime_streaming_buffered_mode(self):
        """Realtime buffered streaming, with a certain number of samples or infinite sampling."""
        log('REALTIME_BUFFERED_STREAMING MODE', self._log_level)
        if self._current_streaming == REALTIME_BUFFERED_STREAMING and self._samples == INFINITE_STREAMING: #For RealTime and infinite
            if self._data == None: # none data, because of timeout
                self._send_request(streaming=self._streaming,samples=self._samples)
            elif self._data != None: # data received
                self._operational_mode = self._current_streaming
                self._calibration(received=self._data)

        elif self._current_streaming == REALTIME_BUFFERED_STREAMING: #For buffered streaming with nr. of samples.
            #log('REALTIME_BUFFERED_STREAMING MODE', self._log_level)
            if self._data == None and self._samples_temp == self._samples:
                self._send_request(streaming=self._streaming,samples=self._samples)
                log('Sending REALTIME Buffered ' + str(self._samples), self._log_level)
            elif self._data != None and self._samples_temp > 0:
                log('Receiving REALTIME Buffered ' + str(self._samples), self._log_level)
                self._samples_temp -=  1
                self._operational_mode = self._current_streaming
                self._calibration(received=self._data)

    def __set_operational_mode(self):
        """Update the events for when a specific mode is in process."""
        log('Performing operatial mode', self.__log_level)
        if self.__prev_opernational_mode != self.__operational_mode:
            if self.__operational_mode == STOP_STREAMING:
                print('set operaitonal mode---------')
                self.__wait_stop_mode.set()
            else:
                self.__wait_stop_mode.clear()

            if self.__operational_mode == REALTIME_BUFFERED_STREAMING:
                self.__wait_buffered_mode.set()
            else:
                self.__wait_buffered_mode.clear()
            if self.__operational_mode == REALTIME_STREAMING:
                self.__wait_realtime_mode.set()
            else:
                self.__wait_realtime_mode.clear()
            self.__prev_opernational_mode = self.__operational_mode

    def run(self):
        """Initlize a receiver class to sampling data specified to a
        frequency. In set_streaming the mode is selected. It works as
        state machine to change between these modes."""
        log('ATI Thread ' + self.__name + ' is RUNNING', ALWAYS_LOG_LEVEL)
        self.__stop_streaming() # stop streaming
        self.__thread_init.set() # set thread to be alive
        #Reset
        self.__current_streaming = STOP_STREAMING
        self.__streaming = STOP_STREAMING
        state_change = False
        samples = 0
        log('ATI is running',self.__log_level)

        while self.__thread_init.isSet() == True:
            """Will only run if thread is set to alive, if it's false
            the run method will end, and this means the thread will
            be terminated.
            If none data receiving, it will run at frequency specificed
            by the timeout."""
            self.__data = self.__io.get_data(sync= True,timeout=self.__timeout) # get data from receiver
            if self.__data == None and self.__current_streaming != STOP_STREAMING:
                log('TimeOut happens', self.__log_level)
                pass
            else:
                #log('Data recieved from receiver class',self.__log_level)
                pass
            

            # STATE MECHANISEM
            if self.__current_streaming != self.__streaming:
                #Change state mechanisem, can first be sure that the state is changed, of data will not be revecing.
                self.__stop_streaming()
                if self.__data == None:
                    self.__current_streaming = self.__streaming
                    self.__samples_temp = self.__samples
                    log('Streaming mode is changed to ' + modes[self.__current_streaming], ALWAYS_LOG_LEVEL)
            try:
                method = getattr(self,'_' + modes[self.__current_streaming])
            except AttributeError:
                raise self.Error( modes[self.__current_streaming] +  ' not found !!!! : ' + '"{}"' + (self.__name))
            else:
                method() # call task from the queue
            self.__set_operational_mode()




        #Stopping thread process
        log('ATI thread ' + self._name + ' is stopped', ALWAYS_LOG_LEVEL)

        if self._recATI.wait_terminated(2) == False:
             raise Exception('ATIReciver: '+ 'could not be stopped in the given timeout.')

        if self._timelist:
            self._timelist.close() # close the timestamps file

    def get_alive(self):
        """Property return if the thread is alive or not.
        Output: true = alive, false = stopped."""
        if self._thread_alive.isSet():
            return True
        else:
            return False
    alive = property(get_alive,'Alive Property')

    def stop(self):
        """Stop the thread, and also stop the reciver class and
        close the socket."""
        log('Trying to stop ATI', ALWAYS_LOG_LEVEL)
        if self._thread_alive.isSet(): # if the thread is alive
            self._thread_alive.clear() # set flag to false

        else:
            raise Exception('ATI: '
                                + 'Is already stopped')
    def wait_startup(self,timeout=None):
        """Wait to this thread is started up, expect
        if a timeout is given.
        Inputs:
        timeout:float-> timeout given in secs."""
         
        log('Waiting to startup ' + self.__name)
        self.__thread_init.wait(timeout)
        if self.__thread_init.isSet():
            log(self.__name + ' is started up')
            return True
        else:
            self.Error(self.__name + ' was not able to started up')
            return False

    def wait_teminated(self,timeout=None):
        """Wait to this thread is terminated, expect
        if a timeout is given.
        Inputs:
        timeout:float-> timeout given in secs."""
        self.stop()
        if self._thread_teminated.wait(timeout):
            return True
        else:
            return False

    streaming = property(get_streaming,set_streaming,"streaming property")

def get_format(size=2):
    """ Return the format for the struct format.
    Inputs:
    size:int-> how long the buffer will be."""
    structformat = '!'
    for i in range(0,size):
        structformat += RECEIVE_FORMAT
    return structformat
