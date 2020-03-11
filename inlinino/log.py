import os
from time import gmtime, strftime
from struct import pack

# TODO Solve bug of data not written when app exited without stopping instruments


class Log:

    FILE_EXT = 'csv'
    FILE_MODE = 'w'

    def __init__(self, cfg):
        # Load Config
        if 'filename_prefix' not in cfg.keys():
            cfg['filename_prefix'] = 'Inlinino'
        if 'path' not in cfg.keys():
            cfg['path'] = ''
        if 'length' not in cfg.keys():
            cfg['length'] = 60  # minutes
        if 'variable_names' not in cfg.keys():
            cfg['variable_names'] = []
        if 'variable_units' not in cfg.keys():
            cfg['variable_units'] = []
        if 'variable_precision' not in cfg.keys():
            cfg['variable_precision'] = []

        self._file = None
        self._file_timestamp = None
        # self.file_mode_binary = cfg['mode_binary']
        self.file_length = cfg['length'] * 60 # seconds
        self.filename_prefix = cfg['filename_prefix']
        self.path = cfg['path']

        self.variable_names = cfg['variable_names']
        self.variable_units = cfg['variable_units']
        self.variable_precision = cfg['variable_precision']

        self.terminator = '\r\n'

    def open(self, timestamp):
        # Create directory
        if not os.path.exists(self.path):
            os.makedirs(self.path)
        # Generate unique filename
        filename = os.path.join(self.path, self.filename_prefix + '_' +
                                strftime('%Y%m%d_%H%M%S', gmtime(timestamp)) + '.' + self.FILE_EXT)
        suffix = 0
        while os.path.exists(filename):
            filename = os.path.join(self.path, self.filename_prefix + '_' +
                                    strftime('%Y%m%d_%H%M%S', gmtime(timestamp)) + '_' + str(suffix) + self.FILE_EXT)
            suffix += 1
        # Create File
        # TODO add exception in case can't open file
        # TODO specify number of bytes in buffer depending on instrument
        self._file = open(filename, self.FILE_MODE)
        # Write header (only if has variable names)
        if self.variable_names:
            self._file.write(
                'time, ' + ', '.join(x for x in self.variable_names) + self.terminator)
            self._file.write(
                'HH:MM:SS.fff, ' + ', '.join(x for x in self.variable_units) + self.terminator)
        # Time file open
        self._file_timestamp = timestamp
        # TODO Reset Instrument Number of Packet Received

    def _smart_open(self, timestamp):
        # Open file if necessary
        if self._file is None or self._file.closed or \
                gmtime(self._file_timestamp).tm_mday != gmtime(timestamp).tm_mday or \
                timestamp - self._file_timestamp >= self.file_length:
            # Close previous file if open
            if self._file and not self._file.closed:
                self.close()
            # Create new file
            self.open(timestamp)

    def write(self, data, timestamp):
        """
        Write data to file
        :param data: list of values
        :param timestamp: date and time associated with the data frame
        :return:
        """
        self._smart_open(timestamp)
        if self.variable_precision:
            self._file.write(strftime('%Y/%m/%d %H:%M:%S', gmtime(timestamp)) + ("%.3f" % timestamp)[-4:] +
                             ', ' + ', '.join(p % d for p, d in zip(self.variable_precision, data)) + self.terminator)
        else:
            self._file.write(strftime('%Y/%m/%d %H:%M:%S', gmtime(timestamp)) + ("%.3f" % timestamp)[-4:] +
                             ', ' + ', '.join(str(d) for d in data) + self.terminator)

    def close(self):
        if self._file:
            self._file.close()
        self._file_timestamp = None

    def __del__(self):
        self.close()


class LogBinary(Log):

    FILE_EXT = 'bin'
    FILE_MODE = 'wb'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.variable_names = []
        self.variable_units = []
        self.registration = b'\xff\x00\xff\x00'
        self.terminator = b''

    def write(self, data, timestamp):
        self._smart_open(timestamp)
        self._file.write(self.registration + data + self.terminator + pack('!d', timestamp))
        # TODO Test unpacking (especially for ACS and HyperSAS)


class LogText(Log):

    FILE_EXT = 'raw'
    ENCODING = 'utf-8'
    UNICODE_HANDLING = 'replace'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.variable_names = ['packet']
        self.variable_units = [self.ENCODING]
        self.registration = ''

    def write(self, data, timestamp):
        """
        Write raw ascii data to file
        :param data: typically a binary array of ascii characters
        :param timestamp: date and time associated with the data frame
        :return:
        """
        self._smart_open(timestamp)
        self._file.write(strftime('%Y/%m/%d %H:%M:%S', gmtime(timestamp)) + ("%.3f" % timestamp)[-4:] +
                                  ', ' + self.registration + data.decode(self.ENCODING, self.UNICODE_HANDLING) + self.terminator)