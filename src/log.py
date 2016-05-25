# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-14 16:54:14
# @Last Modified by:   nils
# @Last Modified time: 2016-05-24 22:34:28

import os
from threading import Thread
from time import sleep, time, gmtime, strftime
from collections import deque


class LogData():

    # Thread
    m_thread = None
    m_active = False

    # Buffer (stored element in RollingBuffer)
    m_buffer = {}
    # Interval between buffer updates (seconds)
    m_buffer_update_interval = None
    m_buffer_size = None  # Size of buffer should be > m_max_bin_size
    # Bin to write (keep tracks of element to write)
    m_bin_size = 0          # Number of element in buffer to write in log file
    m_max_bin_size = None   # Maximum size of bin, should < m_buffer_size

    # File infos
    m_file = None
    m_file_length = None    # Maximum length of file (seconds)
    m_file_header = None
    m_file_path = None
    m_file_start = None

    # Instruments
    m_instruments = None
    m_instnames = {}  # m_instnames.keys() -> list of all the variables
    # m_instnames.values() -> instrument of the variable
    m_varnames = []   # ordered list of the variables of all the instruments

    def __init__(self, _cfg, _instruments):
        # Load cfg
        if 'frequency' in _cfg.keys():
            self.m_interval_buffer = 1 / _cfg['frequency']
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
        for instname, inst in self.m_instruments.items():
            for varname in inst.m_cache.keys():
                self.m_instnames[varname] = instname
                self.m_varnames.append(varname)
        # Initialize buffer
        self.m_buffer['timestamp'] = RingBuffer(self.m_buffer_size)
        for name in self.m_instnames.keys():
            self.m_buffer[name] = RingBuffer(self.m_buffer_size)

    def Start(self):
        # Start thread
        self.m_thread = Thread(target=self.RunUpdate, args=())
        self.m_thread.daemon = True
        self.m_active = True
        self.m_bin_size = 0
        self.m_thread.start()

    def Stop(self, disp=True):
        # Stop thread
        if self.m_thread is not None:
            self.m_active = False
            if self.m_thread.isAlive():
                self.m_thread.join(self.m_interval_buffer * 1.1)
            elif disp:
                print('Log thread already stopped.')
        elif disp:
            print('Log thread not initialized.')
        if self.m_file is not None:
            if not self.m_file.closed:
                # Update buffer a last time
                self.UpdateBuffer()
                # Write buffer in current file
                self.WriteBuffer()
                # Close file
                self.m_file.close()
            elif disp:
                print('Log file already closed.')
        elif disp:
            print('Log file not initialized.')

    def RunUpdate(self):
        # Running thread
        while(self.m_active):
            sleep(self.m_interval_buffer)
            # try:
            self.Update()
            # except:
            #     print('Unexpected error while updating or writting data')

    def Update(self):
        # Update buffer
        self.UpdateBuffer()
        # Write buffer if necessary
        if self.m_file is None:
            # Create new file (first itertion, nothing to log)
            self.CreateFile()
        elif self.m_file.closed:
            # Create new file (previous file was closed)
            self.CreateFile()
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
        elif self.m_bin_size == self.m_max_bin_size:
            # Update current file
            self.WriteBuffer()

    def UpdateBuffer(self):
        # Time stamp
        self.m_buffer['timestamp'].extend([time()])
        # Read data from active instruments
        for varname, instname in self.m_instnames.items():
            if self.m_instruments[instname].m_active:
                self.m_buffer[varname].extend(
                    [self.m_instruments[instname].ReadVar(varname)])
            else:
                self.m_buffer[varname].extend([None])
        # Increase bin size to write in log file
        self.m_bin_size += 1

    def WriteBuffer(self):
        # Write in log file
        n = self.m_bin_size
        for i in range(0, n):
            self.m_file.write(
                strftime('%H:%M:%S', gmtime(self.m_buffer['timestamp'].get(n)[i])) +
                ', ' + ', '.join(str(self.m_buffer[x].get(n)[i]) for x in self.m_varnames) + '\r')
        self.m_bin_size = 0

    def CreateFile(self):
        # Create new log file
        self.m_file_start = self.m_buffer['timestamp'].data[-1]
        filename = self.m_file_header + '_' + \
            strftime('%Y%m%d_%H%M%S', gmtime(self.m_file_start)) + '.csv'
        self.m_file = open(os.path.join(self.m_file_path, filename), 'w')
        # Write column header line
        self.m_file.write(
            'time, ' + ', '.join(x for x in self.m_varnames) + '\r')

    # def __del__(self):
    #     # Stop if necessary
    #     print('LogData.__del__')


class RingBuffer():
    # Ring buffer based on deque for every kind of data
    def __init__(self, length):
        # initialize buffer with None values
        self.data = deque([None] * length, length)

    def extend(self, x):
        # Add x at the end of the buffer
        self.data.extend(x)

    def get(self, n=1):
        # return the most recent n element(s) in buffer
        return list(self.data)[-1 * n:]

    def getleft(self, n=1):
        # return the oldest n element(s) in buffer
        return list(self.data)[0:n]


# class RingBufferNP():
#     # Ring buffer based on numpy.roll for np.array
#     # Same concept as FIFO except that the size of the numpy array does not
#     # vary
#     def __init__(self, length):
#         # initialize buffer with NaN values
#         # length correspond to the size of the buffer
#         self.data = np.empty(length, dtype='f')
#         self.data[:] = np.NAN

#     def extend(self, x):
#         # Add np.array at the end of the buffer
#         step = x.size
#         self.data = np.roll(self.data, -step)
#         self.data[-step:] = x

#     def get(self, n=1):
#         # return the most recent n element(s) in buffer
#         return self.data[-1 * n:]

#     def getleft(self, n=1):
#         # return the oldest n element(s) in buffer
#         return self.data[0:n]
