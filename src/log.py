# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-14 16:54:14
# @Last Modified by:   nils
# @Last Modified time: 2016-06-21 13:58:13

import os
from threading import Thread
from time import sleep, time, gmtime, strftime
from collections import deque
from time import sleep, time
import numpy as np


class LogData():

    # Thread
    m_thread = None
    m_active_buffer = False
    m_active_log = False

    # Buffer (stored element in RollingBuffer)
    m_buffer = {}
    # Interval between buffer updates (seconds)
    m_buffer_interval = None
    m_buffer_size = None  # Size of buffer should be > m_max_bin_size
    # Bin to write (keep tracks of element to write)
    m_bin_size = 0          # Number of element in buffer to write in log file
    m_max_bin_size = None   # Maximum size of bin, should < m_buffer_size

    # File infos
    m_file = None
    m_file_length = None    # Maximum length of file (seconds)
    m_file_header = None
    m_file_name = None
    m_file_path = None
    m_file_start = None

    # Instruments
    m_instruments = None
    m_instnames = {}  # m_instnames.keys() -> list of all the variables
    # m_instnames.values() -> instrument of the variable
    m_varnames = []   # ordered list of the variables of all the instruments
    m_varunits = []

    def __init__(self, _cfg, _instruments, _instruments_cfg=None):
        # Load cfg
        if 'frequency' in _cfg.keys():
            # Takes about 0.01 s for the program to run
            self.m_buffer_interval = 1 / _cfg['frequency'] - 0.01
        else:
            print('Missing frequency in section log')
            exit()
        if 'interval_write' in _cfg.keys():
            self.m_max_bin_size = _cfg['interval_write'] * _cfg['frequency']
            self.m_buffer_size = self.m_max_bin_size + 1
        else:
            print('Missing interval_write in section log')
            exit()
        if 'length' in _cfg.keys():
            self.m_file_length = _cfg['length'] * 60
        else:
            print('Missing length in section log')
            exit()
        if 'header' in _cfg.keys():
            self.m_file_header = _cfg['header']
        else:
            print('Missing header in section log')
            exit()
        if 'path' in _cfg.keys():
            self.m_file_path = _cfg['path']
        else:
            print('Missing path in section log')
            exit()
        # Keep instruments
        self.m_instruments = _instruments
        # Create directory where to log data
        if not os.path.exists(self.m_file_path):
            os.makedirs(self.m_file_path)
        # Create list of variables to log
        if _instruments_cfg is None:
            for instname, inst in self.m_instruments.items():
                for varname in inst.m_cache.keys():
                    self.m_instnames[varname] = instname
                    self.m_varnames.append(varname)
                    self.m_varunits.append(inst.m_units[varname])
        else:
            for instr_key in _instruments_cfg.keys():
                for varname in self.m_instruments[instr_key].m_varnames:
                    self.m_instnames[varname] = instr_key
                    self.m_varnames.append(varname)
                    self.m_varunits.append(
                        self.m_instruments[instr_key].m_units[varname])

        # Initialize buffer
        self.m_buffer['timestamp'] = RingBuffer(self.m_buffer_size)
        for name in self.m_instnames.keys():
            self.m_buffer[name] = RingBuffer(self.m_buffer_size)

    def CountActiveInstruments(self):
        active_instr = 0
        for instr in self.m_instruments.values():
            if instr.m_active:
                active_instr += 1
        return active_instr

    def Start(self):
        # Start logging data
        self.m_active_log = True
        if not self.m_active_buffer:
            # Start thread updating buffer
            self.StartThread()

    def Stop(self, _disp=True):
        # Stop logging data
        self.m_active_log = False
        if self.m_file is not None:
            if not self.m_file.closed:
                # Update buffer a last time
                self.UpdateBuffer()
                # Write buffer in current file
                self.WriteBuffer()
                # Close file
                self.m_file.close()
            elif _disp:
                print('Log file already closed.')
        elif _disp:
            print('Log file not initialized.')

    def StartThread(self):
        # Start thread
        self.m_thread = Thread(target=self.RunUpdate, args=())
        self.m_thread.daemon = True
        self.m_active_buffer = True
        self.m_bin_size = 0
        self.m_thread.start()

    def StopThread(self, _disp=True):
        # Stop thread
        if self.m_thread is not None:
            self.m_active_buffer = False
            if self.m_thread.isAlive():
                self.m_thread.join(self.m_buffer_interval * 1.1)
            elif _disp:
                print('Log thread already stopped.')
        elif _disp:
            print('Log thread not initialized.')

    def RunUpdate(self):
        # Running thread
        start_time = time()
        while(self.m_active_buffer):
            try:
                sleep(self.m_buffer_interval - (time() - start_time) %
                      self.m_buffer_interval)
                self.Update()
            except Exception as e:
                print('Unexpected error while updating or writting data')
                print(e)

    def Update(self):
        # Update buffer
        self.UpdateBuffer()
        if self.m_active_log:
            # Log data from buffer
            if self.m_file is None:
                # Create new file (first itertion, nothing to log)
                self.CreateFile()
                # Reset Instrument Number of Packet Received
                self.ResetInstrumentCount()
            elif self.m_file.closed:
                # Create new file (previous file was closed)
                self.CreateFile()
                # Reset Instrument Number of Packet Received
                self.ResetInstrumentCount()
            elif (gmtime(self.m_file_start).tm_mday !=
                  gmtime(self.m_buffer['timestamp'].data[-1]).tm_mday or
                  self.m_buffer['timestamp'].data[-1] - self.m_file_start >=
                  self.m_file_length):
                # Current file expired (new day or exceed file_length)
                # Write buffer in current file
                self.WriteBuffer()
                # Close current file
                self.m_file.close()
                # Create new file
                self.CreateFile()
                # Reset Instrument Number of Packet Received
                self.ResetInstrumentCount()
            elif self.m_bin_size == self.m_max_bin_size:
                # Update current file
                self.WriteBuffer()

    def UpdateBuffer(self):
        # Time stamp
        self.m_buffer['timestamp'].extend(time())
        # Read data from active instruments
        for varname, instname in self.m_instnames.items():
            if self.m_instruments[instname].m_active:
                self.m_buffer[varname].extend(
                    self.m_instruments[instname].ReadVar(varname))
            else:
                self.m_buffer[varname].extend(None)
        # Increase bin size to write in log file
        self.m_bin_size += 1

    def WriteBuffer(self):
        # Write in log file
        n = self.m_bin_size
        for i in range(0, n):
            self.m_file.write(
                strftime('%H:%M:%S', gmtime(self.m_buffer['timestamp'].get(n)[i])) +
                # Display milliseconds
                ("%.3f" % self.m_buffer['timestamp'].get(n)[i])[-4:] +
                ', ' + ', '.join(str(self.m_buffer[x].get(n)[i]) for x in self.m_varnames) + '\r')
        self.m_bin_size = 0

    def CreateFile(self):
        # Create new log file
        self.m_file_start = self.m_buffer['timestamp'].data[-1]
        self.m_file_name = self.m_file_header + '_' + \
            strftime('%Y%m%d_%H%M%S', gmtime(self.m_file_start)) + '.csv'
        self.m_file = open(os.path.join(
            self.m_file_path, self.m_file_name), 'w')
        # Write variable names
        self.m_file.write(
            'time, ' + ', '.join(x for x in self.m_varnames) + '\r')
        # Write variable units
        self.m_file.write(
            'HH:MM:SS.fff, ' + ', '.join(x for x in self.m_varunits) + '\r')

    def ResetInstrumentCount(self):
        # reset m_n and m_nNoResponse of all instruments
        for instr in self.m_instruments.values():
            instr.m_n = 0
            instr.m_nNoResponse = 0
        # if __debug__:
        #     print('LogData:ResetInstrumentCount')

    def __str__(self):
        return 'buffer_interval: ' + str(self.m_buffer_interval) + '\n'

    # def __del__(self):
    #     # Stop if necessary
    #     print('LogData.__del__')


# class RingBuffer():
#     # Ring buffer based on deque for every kind of data
#     def __init__(self, _length):
#         # initialize buffer with None values
#         self.data = deque([None] * length, length)

#     def extend(self, _x):
#         # Add x at the end of the buffer
#         self.data.extend(_x)

#     def get(self, _n=1):
#         # return the most recent n element(s) in buffer
#         return list(self.data)[-1 * _n:]

#     def getleft(self, _n=1):
#         # return the oldest n element(s) in buffer
#         return list(self.data)[0:_n]


class RingBuffer():
    # Ring buffer based on numpy.roll for np.array
    # Same concept as FIFO except that the size of the numpy array does not
    # vary
    def __init__(self, _length):
        # initialize buffer with NaN values
        # length correspond to the size of the buffer
        self.data = np.empty(_length)  # , dtype='f')
        self.data[:] = np.NAN

    def extend(self, _x):
        # Add np.array at the end of the buffer
        x = np.array(_x, copy=False)  # dtype=None
        step = x.size
        self.data = np.roll(self.data, -step)
        self.data[-step:] = x

    def get(self, _n=1):
        # return the most recent n element(s) in buffer
        return self.data[-1 * _n:]

    def getleft(self, _n=1):
        # return the oldest n element(s) in buffer
        return self.data[0:_n]
