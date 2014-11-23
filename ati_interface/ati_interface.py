__author__ = "Mats Larsen"
__copyright__ = "Mats Larsen 2014"
__credits__ = ["Mats Larsen, Morten Lind"]
__license__ = "GPL"
__maintainer__ = "Mats Larsen"
__email__ = "matsla@{ntnu.no}"
__status__ = "Development"
#--------------------------------------------------------------------
#File: ati_interface.py
#Module Description
"""
This module handle the interaction between the ft-sensor class and the
ft-sensor. Here it can be data from the real sensor or from the
simulation sensor. The sensor has several modes it can be running
in. The ATI class has to be run as a thread, and the result can
received in  synchronously and asynchronously way.
"""
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
#--------------------------------------------------------------------
#CONSTANTS
#--------------------------------------------------------------------
#General
LOG_LEVEL = 2 # Information level
ALWAYS_LOG_LEVEL = 1 # print always
FILE = 'ati_interface'
FILEREC = 'ati_rec'
NAME = 'ATI_INTERFACE'
RECEIVE_FORMAT = '3I6i'
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
STARTUP_STREAMING = 'STOP' # Which mode it will be start up with

#Modes for the ati box
modes = {STOP_STREAMING : '_stop_streaming_mode',
         REALTIME_STREAMING : '_realtime_streaming_mode',
         REALTIME_BUFFERED_STREAMING : '_realtime_streaming_buffered_mode',
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

class ATI_INTERFACE(threading.Thread):
    """Class for interacting withthe ati-box."""
    class Error(Exception):
        """Exception class."""
        def __init__(self, message):
            self.message = message
            Exception.__init__(self, self.message)
        def __repr__(self):
            return self.message

    def __init__(self, host='127.0.0.1', # host to connect toSrealtime
                 port=49152, # port to the sensor
                 name='1', # name of the ATI instance
                 timestamps=False, # taking timestamps ati class
                 timestamps_reciver=False, # taking timestamps receiver class
                 headerstamps=False, # taking header information
                 socket_timeout=1.5, # timeout for the socket
                 timeout=0.1, # to wait for get data
                 buffersize=40, # buffer size for buffer mode
                 log_level=3): # information level
        # Assignment
        self._host = host  # ATI net box IP address on the network
        self._port = port # port of the ATI box
        self._streaming = STARTUP_STREAMING # streaming mode
        self._current_streaming = self._streaming # for state-machine
        self._log_level = log_level
        self._name = 'ATI#' + name
        self._timestamps = timestamps
        self._timestamps_reciver = timestamps_reciver
        self._headerstamps = headerstamps
        self._socket_timeout = socket_timeout
        self._timeout = timeout
        self._buffersize = buffersize # the buffer size of received data

        global sockATI
        sockATI = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sockATI.settimeout(self._socket_timeout)
        #sockATI.setblocking(False)
        #Threading
        threading.Thread.__init__(self) # initialize th
        self.daemon = True
        #Condition
        self._getdata_condition = threading.Condition() # Notify when sampled are handled
        #Event
        self._thread_alive = threading.Event() # status for the thread
        self._thread_teminated = threading.Event() # status for the thread terminated
        self._operational_mode = STOP_STREAMING
        self._old_opernational_mode = None
        self._wait_stop_mode = threading.Event() # which process mode
        self._wait_buffered_mode = threading.Event() # which process mode
        self._wait_realtime_mode = threading.Event() # which process mode

        #Reset
        self._wait_stop_mode.clear()
        self._wait_buffered_mode.clear()
        self._wait_realtime_mode.clear()

        self._samples = 0
        self._data = None # Header force and torque data
        self._timelist = None # file for timestamps
        self._thread_alive.clear()
        self._thread_teminated.clear()
        self.set_streaming(streaming='STOP') #ensure to stop the sensor

        self.start() # start main loop
        log('ATI created:' + 'name = ' + self._name, ALWAYS_LOG_LEVEL)

    def get_name(self):
        return self._name
    name = property(get_name,'Name Property')
    def get_streaming(self):
        """ Property returning the streaming setting"""
        return self._current_streaming
    streaming = property(get_streaming, "Streaming Property")

    def set_streaming(self, streaming = 'STOP',samples=1):
        """ Property setting the streaming to one of the 5 modes of the
        ft-sensor.
        Inputs:
        streaming:string -> defines one of the five modes.
        samples:int -> defines how many samples to receive"""
        log('Set streaming is set to ' + streaming, self._log_level)
        self._samples = samples
        if streaming == 'STOP':# stop the ati transmission
            self._streaming = STOP_STREAMING
            self._send_request(streaming=self._streaming) # send a request to sensor to stop
        elif streaming == 'REALTIME':# mode of realtime
            self._streaming = REALTIME_STREAMING
        elif streaming == 'REALTIME_BUFFERED':# mode of realtime with buffer
            self._streaming = REALTIME_BUFFERED_STREAMING
        elif streaming == 'MULTI_UNIT': # mode of multi unit
            self._streaming = MULTI_UNIT_STREAMING
        elif streaming == 'INFINITE': # mode of inifinite streaming
            self._streaming = REALTIME_STREAMING
            self._samples = 0
        else:
            self._streaming = None
            raise self.Error('ATI: ' + 'Streaming setup for ATI is ' +' not known on arguments :'
                                +  '"{}"'.format(str(streaming)))

    def  _send_request(self,header=COMMAND_HEADER,
                       streaming=REALTIME_STREAMING,
                       samples=1):
        """Send a request to the ATI. Setting of the property will be
        send here.
        Inputs:
        header:hex -> define the header command to the ft-sensor.
        streaming:str -> streaming mode.
        samples:int-> number of samples"""
        log('Request is send with  mode : ' + str(streaming) + ' and samples : ' + str(samples),self._log_level)
        request = struct.pack("!HHi", COMMAND_HEADER,streaming,samples)
        sockATI.sendto(request,(self._host,self._port))

    def _stop_streaming(self):
        """Will send stop_streaming to the ati-box."""
        #log('Stop streaming', self._log_level)
        request = struct.pack("!HHi", COMMAND_HEADER,STOP_STREAMING,self._samples)
        sockATI.sendto(request,(self._host,self._port))

    def get_format(self):
        """ Return the format for the struct format.
        Inputs:
        size:int-> how long the buffer will be."""
        #log('Performing get format',self._log_level)
        if self._current_streaming == REALTIME_STREAMING:
            size = 1
        else:
            size = self._buffersize
        structformat = '!'
        for i in range(0,size):
            structformat += RECEIVE_FORMAT
        return structformat

    def _calibration(self,received):
        """Will calibrate the data, by separate the header and the data
        and applied the factor to the data. Plus minus the bias from
        the data. When data is handled it is notified to waiting threads.
        Inputs:list-> data from the ft-sensor"""
        log('Performing calibration', self._log_level)

        if self._current_streaming == REALTIME_STREAMING:
            size = 1
        else:
            size = self._buffersize
        #initialize arrayes
        unp = struct.unpack(self.get_format(),received) # unpack the message
        #print(unp)
        self._getdata_condition.acquire()
        self._info_data = np.array([[unp[0],unp[1],unp[2]]])
        self._force_data = np.array([[unp[3]/FORCE_CALIBRATION,unp[4]/FORCE_CALIBRATION,unp[5]/FORCE_CALIBRATION]],dtype=np.float)
        self._torque_data = np.array([[unp[6]/TORQUE_CALIBRATION,unp[7]/TORQUE_CALIBRATION,unp[8]/TORQUE_CALIBRATION]],dtype=np.float)
        for i in range(1, size):# loop the size of buffersize with calibration
            self._info_data = np.append(self._info_data,[[unp[0+i*9],unp[1+i*9],unp[2+i*9]]],axis=0)
            self._force_data = np.append(self._force_data,[[unp[3+i*9]/FORCE_CALIBRATION,unp[4+i*9]/FORCE_CALIBRATION,unp[5+i*9]/FORCE_CALIBRATION]],axis=0)
            self._torque_data = np.append(self._torque_data,[[unp[6+i*9]/TORQUE_CALIBRATION,unp[7+i*9]/TORQUE_CALIBRATION,unp[8+i*9]/TORQUE_CALIBRATION]],axis=0)
        #Notify to others tasks that new sample are ready
        self._getdata_condition.notifyAll()
        self._getdata_condition.release()

    def get_data_ATI(self, sync=True,timeout=None,data_type=None):
        """Used to get data from the run method. Return the
        force and torque. Combined with
        thread.condition it will return force and torque synchronously
        and without will be asynchronously
        Input:
        - sync: True=to be in sync, wait for next new sample.
        False=get data async.
        - timeout: break wait operation with a timeout."""
        #log('Performing get data from ATI', self._log_level)
        if sync == True: # synchronously operation
            if self._wait_for_idle(timeout=timeout): # wait until data is recvied or timeout
                if data_type == None:
                    return self._info_data, self._force_data, self._torque_data
                elif data_type == 'force':
                    return self._force_data
                elif data_type == 'force_torque':
                    return self._force_data, self._torque_data
                else:
                    raise self.Error('Data_type is not found !!!! : ' + '"{}"'.format(data_type))
            else:
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

    def _wait_for_idle(self, timeout=None):
        """Call by get_data_ATI, to observe when this thread has
        sampled. Wait until a notified or a timeout occurs.
        - timeout: when a timeout occur,floating point,[s]."""
        #log('Performing wait for idle', self._log_level)
        self._getdata_condition.acquire() # Acquire the underlying lock
        status = self._getdata_condition.wait(timeout)
        self._getdata_condition.release() # Release the underlying lock
        if status:
            return True
        else:
            return False

    def wait_for_mode(self,mode,timeout=1):
        """Wait for a specific mode."""
        if mode == 'STOP':
            e = self._wait_stop_mode.wait(timeout)
        elif mode == 'REALTIME_BUFFERED':
            e = self._wait_buffered_mode.wait(timeout)
        if e == True:
            log(mode + ' is in process :'  + '"{}"'.format(mode), self._log_level)
        else:
            raise self.Error(mode + ' is not swicted in the given time :: ' + '"{}"'.format(timeout))


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
        log('STOP STREAMING MODE', self._log_level)
        if self._current_streaming == STOP_STREAMING: #Stop streaming, will continue to send stop request until it response appears.
            if self._data != None: # If it still receiving data, send stop request again
                self._send_request(streaming=self._streaming,samples=self._samples)
            elif self._data == None: #  Receiving None data
                self._operational_mode = self._current_streaming
                #print(self._operational_mode)

    def _realtime_streaming_mode(self):
        """Realtime mode, contain both certain number of samples and infinite samples, depending of samples."""
        log('Performing realtime_mode', self._log_level)
        if self._current_streaming == REALTIME_STREAMING and self._samples == INFINITE_STREAMING: #For inifinty streaming
             if self._data == None: # none data, because of timeout
                 self._send_request(streaming=self._streaming,samples=self._samples)
             elif self._data != None: # data received
                 self._operational_mode = self._current_streaming
                 self._calibration(received=self._data)

        elif self._current_streaming == REALTIME_STREAMING: #For realtime streaming with nr. of samples
            #log('realtime', self._log_level)
            if self._data == None and self._samples_temp == self._samples:
                self._send_request(streaming=self._streaming,samples=self._samples)
                log('send realtime ' + str(self._samples_temp),self._log_level)
            elif self._data != None and self._samples_temp > 0:
                self._samples_temp -= 1
                self._calibration(received=self._data)

    def _realtime_streaming_buffered_mode(self):
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

    def _set_operational_mode(self):
        """Update the events for when a specific mode is in process."""
        if self._old_opernational_mode != self._operational_mode:
            if self._operational_mode == STOP_STREAMING:
                self._wait_stop_mode.set()
            else:
                self._wait_stop_mode.clear()

            if self._operational_mode == REALTIME_BUFFERED_STREAMING:
                self._wait_buffered_mode.set()
            else:
                self._wait_buffered_mode.clear()
            if self._operational_mode == REALTIME_STREAMING:
                self._wait_realtime_mode.set()
            else:
                self._wait_realtime_mode.clear()
            self._old_opernational_mode = self._operational_mode

    def run(self):
        """Initlize a receiver class to sampling data specified to a
        frequency. In set_streaming the mode is selected. It works as
        state machine to change between these modes."""
        log('ATI Thread ' + self._name + ' is RUNNING', ALWAYS_LOG_LEVEL)
        self._stop_streaming() # stop streaming
        self._thread_alive.set() # set thread to be alive
        #Initilize the receiver class
        self._recATI = ReceiverATI(timestamps=self._timestamps_reciver, headerstamps=self._headerstamps)
        self._recATI.wait_startup(1) # wait until recATI is started.
        #Reset
        self._current_streaming = STOP_STREAMING
        self._streaming = STOP_STREAMING
        state_change = False
        samples = 0

        while self._thread_alive.isSet() == True:
            """Will only run if thread is set to alive, if it's false
            the run method will end, and this means the thread will
            be terminated.
            If none data receiving, it will run at frequency specificed
            by the timeout."""
            log('ATI is running',self._log_level)
            self._data = self._recATI.get_data_ATI(sync= True,timeout=self._timeout) # get data from receiver

            if self._data == None and self._current_streaming != STOP_STREAMING:
                log('TimeOut happens', self._log_level)
                pass
            else:
                log('Data recieved from receiver class',self._log_level)
                pass
            #print(data)

            if self._timestamps and data != None: # If write timestamps to file is true
                self._measure_samplingfrequency()

            # STATE MECHANISEM
            if self._current_streaming != self._streaming:
                #Change state mechanisem, can first be sure that the state is changed, of data will not be revecing.
                self._stop_streaming()
                if self._data == None:
                    self._current_streaming = self._streaming
                    self._samples_temp = self._samples
                    log('Streaming mode is changed to ' + modes[self._current_streaming], ALWAYS_LOG_LEVEL)
            try:
                method = getattr(self,modes[self._current_streaming])
            except AttributeError:
                raise self.Error(task + ' not found !!!! : ' + '"{}"'.format(self._name))
            else:
                method() # call task from the queue
            self._set_operational_mode()




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
        if self._thread_alive.wait(timeout):
            return True
        else:
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


class ReceiverATI(threading.Thread):
    """Class to receive data from the ati box"""
    class Error(Exception):
        """Exception class."""
        def __init__(self, message):
            self.message = message
            Exception.__init__(self, self.message)
        def __repr__(self):
            return self.message

    def __init__(self,timestamps=False, # take timestamps
                 headerstamps=False, # take header stamps
                 name='atireciever', # name
                 log_level=3):
        #Assignment
        self._timestamps = timestamps # to take timestamps or not
        self._headerstamps = headerstamps
        self._name = NAME + '#' + name
        self._log_level = log_level
        #Threading
        threading.Thread.__init__(self) # initialize thw thread
        self.daemon = True
        #Event
        self._rec_event = threading.Event() # event for received data
        self._thread_alive = threading.Event() # status for the thread
        self._thread_terminated = threading.Event() # when thread is terminated.
        #Reset
        self._received = None
        self._timelist = None
        self._headerlist = None
        self._rec_event.clear()
        self._thread_alive.clear()
        self._thread_terminated.clear()
        self.start()
        self.log(self._name + ' is created, ' + name, ALWAYS_LOG_LEVEL)

    def log(self,msg, log_level=LOG_LEVEL):
        """Print a message, and track, where the log is invoked
        Input:
        -msg: message to be printed, ''
        -log_level: informationlevel, i"""
        global LOG_LEVEL
        if log_level <= LOG_LEVEL:
            print(str(log_level) + ' : ' + FILEREC + ' ::' +
                traceback.extract_stack()[-2][2] + ' : ' + msg)

    def get_data_ATI(self, sync=True, timeout=0.5):
        """Property will return recevied from the sensor.
        Input:
        - sync. If true it will wait until the event will be set, it
        means that new sensor data is received. If false, it is
        async and will just return the current value.
        - timeout, indicate how long it should wait for event.
        0 = forever.
        Output:
        - revieced, sensor data, None for timeout."""
        if self._rec_event.isSet(): # if event is  set from the run
            self._rec_event.clear() # clear the flag
            return self._received   # return sensor data
        elif sync == True: # if sync is enabled
            if self._rec_event.wait(timeout): # wait for event or timeout
                self._rec_event.clear() # clear flag
                return self._received
            else:
                return None # None for timeout happen
        else: # async
            return self._received
    getdata = property(get_data_ATI, "Data Property")

    def _closeSocket(self):
        """Close the socket connection."""
        sockATI.close()

    def run(self):
        """Thread will get the new input from the sensor, and set the
        event to true. Continueouly update received
        """
        self.log('ATI Receiver ' + self._name + ' is RUNNING', ALWAYS_LOG_LEVEL)
        self._thread_alive.set() # set the thread to be alive

        while self._thread_alive.isSet() == True:
            """Will only run if thread is set to alive, if it's false
            the run method will end, and this means the thread will
            be terminated."""
            try:
                self._received = sockATI.recv(2048) # get reciced
                self._rec_event.set() # flag for recived data
                """
                if self._timestamps: # If write timestamps to file is true
                    self._measure_samplingfrequency()
                if self._headerstamps:
                    self._measure_header_information()
                """
                #log('recived data',self._log_level)
                #print(self._received)
            except socket.timeout: # socket timeout
                pass

        log('ATI_Reciver ' + self._name + ' is stopped', ALWAYS_LOG_LEVEL)
        if self._timelist:
            self._timelist.close() # close the timestamps file
            log('Close timestamps receiver', self._log_level)
        if self._headerlist:
            self._headerlist.close()
            log('Close timestamps receiver', self._log_level)
        self._closeSocket()
        self._thread_terminated.set()
        log('Close Socket Connection')

    def _measure_header_information(self):
        """Measure the header information, to see if any packages are
        lost, or coming in different order."""
        if self._headerlist == None:
            self._headerlist = open('Headerstamps at reciever','w')
        unp = struct.unpack('!3I6i3I6i',self._received) # unpack the message
        header = unp[0] # separate the header
        self._headerlist.write(str(header) + '\n')

    def _measure_samplingfrequency(self):
        """Measure the timestamps, write to a file."""
        if self._timelist == None:
            self._timelist = open('Timestamps at receiver', 'w')
            self._old = float((time.time() * 1))
        else:
            new = float((time.time()*1))
            self._timelist.write(str((new - self._old)) + '\n' )
            self._old = new
        # print('time reciver = ' + str(( new - old)) + ' ms')

    def stop(self):
        """Stop the thread."""
        log('Trying to stop ATIReciver' + self._name, ALWAYS_LOG_LEVEL)
        self._thread_alive.clear()

    def wait_startup(self,timeout=None):
        """Wait to this thread is started up, expect
        if a timeout is given.
        Inputs:
        timeout:float-> timeout given in secs."""
        if self._thread_alive.wait(timeout):
            return True
        else:
            return False

    def wait_terminated(self,timeout=None):
        """Wait to this thread is terminated, expect
        if a timeout is given.
        Inputs:
        timeout:float-> timeout given in secs."""
        self.stop()
        if self._thread_terminated.wait(timeout):
            return True
        else:
            return False

def get_format(size=2):
    """ Return the format for the struct format.
    Inputs:
    size:int-> how long the buffer will be."""
    structformat = '!'
    for i in range(0,size):
        structformat += RECEIVE_FORMAT
    return structformat
