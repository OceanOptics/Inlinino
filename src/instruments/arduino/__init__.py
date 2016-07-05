# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-04-08 16:22:19
# @Last Modified by:   nils
# @Last Modified time: 2016-07-05 13:05:55


from time import sleep
from serial import Serial
from threading import Thread
from instruments import Instrument


class Arduino(Instrument):
    '''
    Interface to Arduino Data logger
    '''

    m_pin_list = ['SIN_A0', 'SIN_A1', 'SIN_A2', 'SIN_A3', 'SIN_A4', 'SIN_A5',
                  'DIF_A01', 'DIF_A23']

    def __init__(self, _name, _cfg):
        Instrument.__init__(self, _name)

        # No Responsive Counter
        self.m_maxNoResponse = 10

        # Do specific configuration
        self.m_connect_need_port = True
        self.m_pins = []
        self.m_pin2var = {}

        # Initialize serial communication
        self.m_serial = Serial()
        self.m_serial.baudrate = 9600
        self.m_serial.bytesize = 8
        self.m_serial.parity = 'N'  # None
        self.m_serial.stopbits = 1

        # Load cfg
        if 'frequency' in _cfg.keys():
            self.m_frequency = _cfg['frequency']
            self.m_serial.timeout = 1 / _cfg['frequency']  # seconds
            self.m_serial.write_timeout = self.m_serial.timeout
        else:
            print(_name + ' missing frequency')
            exit()
        if 'variables' in _cfg.keys():
            if any(_cfg['variables']):
                for var, val in _cfg['variables'].items():
                    self.m_cache[var] = None
                    self.m_cacheIsNew[var] = False
                    if 'pin' in val.keys():
                        if val['pin'] in self.m_pin_list:
                            self.m_pin2var[val['pin']] = var
                        else:
                            print(_name + ':' + var + ' Unknown pin ' +
                                  val['pin'])
                            exit()
                    else:
                        print(_name + ':' + var + ' missing pin')
                        exit()
                    if 'units' in val.keys():
                        self.m_units[var] = val['units']
                    else:
                        print(_name + ':' + var + ' missing units')
                        exit()
                    self.m_varnames.append(var)
            else:
                print(_name + ' variables are empty')
                exit()
        else:
            print(_name + ' missing variables')
            exit()

        # Build ordered list of pin
        for p in self.m_pin_list:
            if p in self.m_pin2var.keys():
                self.m_pins.append(p)
        self.m_n_pins = len(self.m_pins)

    def Connect(self, _port=None):
        if _port is None:
            print(self.m_name + ' need a port to establish connection.')
            return None

        try:
            if self.m_serial.isOpen():
                self.m_serial.close()
            self.m_serial.port = _port
            self.m_serial.open()
        except:
            print('%s did not respond' % (self.m_name))
            return None

        # Send configuration to Arduino
        if self.m_serial.isOpen():
            header_buffer = []
            # Skip first data
            header_buffer.append(self.m_serial.readline())
            sleep(self.m_serial.timeout)    # Wait for instrument to start
            # Skip header
            header_buffer.append(self.m_serial.readline())
            while header_buffer[-1] is not b'' and len(header_buffer) < 6:
                header_buffer.append(self.m_serial.readline())
                # Set configuration of controller
            if not self.SetConfiguration(header_buffer[-2]):
                # Fail to set configuration
                print(self.m_name + ' fail to send configuration')
                if __debug__:
                    print('Last communication with Arduino:')
                    for l in header_buffer:
                        print('\t' + str(l))
                    print('\t' + str(self.m_serial.readline()))
                    print('\t' + str(self.m_serial.readline()))
                    print('Possible cause:')
                    print('\tunexpected software on Arduino Controller')
                    print('\tlocal configuration not matching controller')
                self.m_serial.close()
                return None

            # Create thread to update cache
            self.m_thread = Thread(target=self.RunUpdateCache, args=())
            self.m_thread.daemon = True
            self.m_active = True
            self.m_thread.start()
            return True
        else:
            return None

    def Close(self):
        # Stop thread updating cache
        if self.m_thread is not None:
            self.m_active = False
            if self.m_thread.isAlive():
                self.m_thread.join(self.m_serial.timeout * 1.1)
            else:
                print(self.m_name + ' thread already close.')
        # Close serial connection
        if self.m_serial.isOpen():
            self.m_serial.close()
        else:
            print(self.m_name + ' serial communication already close.')
        # Empty cache
        self.EmptyCache()

    def RunUpdateCache(self):
        while(self.m_active):
            try:
                self.UpdateCache()
            except Exception as e:
                print(self.m_name +
                      ': Unexpected error while updating cache.\n' +
                      'Suggestions:\n' +
                      '\t-Arduino board might be unplug.')
                sleep(self.m_serial.timeout)
                try:
                    self.EmptyCache()
                    self.CommunicationError()
                except:
                    print(self.m_name +
                          ': Unexpected error while emptying cache')
                print(e)

    def UpdateCache(self):
        # readline wait for \EOT or timeout and
        data = self.m_serial.readline()
        if data:
            # data is a byte array
            data = data[0:-2].split(b'\t')
            if len(data) == self.m_n_pins:
                for i in range(0, self.m_n_pins):
                    self.m_cache[self.m_pin2var[self.m_pins[i]]] = int(data[i])
                    self.m_cacheIsNew[self.m_pin2var[self.m_pins[i]]] = True
                self.m_n += 1
            else:
                # Incomplete data transmission
                self.CommunicationError('Incomplete data transmission.\n' +
                                        'This might happen on few first ' +
                                        'bytes received.\nIf it keeps going ' +
                                        'try disconnecting and reconnecting ' +
                                        'the Arduino board.\nAnother cause ' +
                                        'is that the number of pin set is ' +
                                        'incorrect.')
        else:
            # No data
            self.CommunicationError('No data after updating cache.\n' +
                                    'Suggestions:\n' +
                                    '\t- Wiring issue.\n' +
                                    '\t- Sensor power is off.\n')

    def CommunicationError(self, _msg=''):
        # Set cache to None
        for key in self.m_cache.keys():
            self.m_cache[key] = None

        # Error message if necessary
        self.m_nNoResponse += 1
        if (self.m_nNoResponse >= self.m_maxNoResponse and
                self.m_nNoResponse % 60 == self.m_maxNoResponse):
            print('%s did not respond %d times\n%s' % (self.m_name,
                                                       self.m_nNoResponse,
                                                       _msg))
