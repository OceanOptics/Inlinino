import numpy as np  # Needed to compute advanced products

from inlinino.instruments import Instrument
from time import time, sleep

class DATAQ(Instrument):
    """
    slist for model DI-1100
    0x0000 = Analog channel 0, ±10 V range
    0x0001 = Analog channel 1, ±10 V range
    0x0002 = Analog channel 2, ±10 V range
    0x0003 = Analog channel 3, ±10 V range
    """
    SLIST = [0x0000, 0x0001, 0x0002, 0x0003, 0x0004, 0x0005, 0x0006, 0x0007]
    REQUIRED_CFG_FIELDS = ['channels_enabled',
                           'model', 'serial_number', 'module',
                           'log_path', 'log_raw', 'log_products',
                           'variable_names', 'variable_units', 'variable_precision']

    def __init__(self, uuid, cfg, signal, *args, **kwargs):
        # DATAQ Specific attributes
        self.channels_enabled = [0, 1, 2, 3, 4, 5, 6, 7]
        self.variable_equations = []

        super().__init__(uuid, cfg, signal, *args, **kwargs)

        # Default serial communication parameters
        self.default_serial_baudrate = 115200
        self.default_serial_timeout = 1

    def setup(self, cfg):
        # Set DATAQ specific attributes
        if 'channels_enabled' not in cfg.keys():
            raise ValueError('Missing field channels enabled')
        self.channels_enabled = cfg['channels_enabled']
        # Handle legacy configuration
        for k in [k for k in cfg.keys() if k.startswith('variable_')]:
            if len(cfg[k]) == 1 and cfg[k][0] == '':
                del cfg[k]
        # Overload cfg with DATAQ specific parameters
        cfg['variable_names'] = ['C%d' % (c+1) for c in self.channels_enabled] + \
                                (cfg['variable_names'] if 'variable_names' in cfg.keys() else [])
        cfg['variable_units'] = ['V'] * len(self.channels_enabled) + \
                                (cfg['variable_units'] if 'variable_units' in cfg.keys() else [])
        cfg['variable_precision'] = ['%.3f'] * len(self.channels_enabled) + \
                                    (cfg['variable_precision'] if 'variable_precision' in cfg.keys() else [])
        cfg['variable_equations'] = ['c[%d]' % (c+1) for c in self.channels_enabled] + \
                                    (cfg['variable_equations'] if 'variable_equations' in cfg.keys() else [])
        cfg['terminator'] = b'\r'
        cfg['separator'] = b','
        # Set standard configuration and check cfg input
        super().setup(cfg)
        # Update DATAQ specific attributes after cfg checks
        self.variable_equations = cfg['variable_equations']

    def close(self, *args, **kwargs):
        if self.alive:
            self.send_cmd('stop')
            sleep(self._interface.timeout)
        super().close(*args, **kwargs)

    def send_cmd(self, command):
        if self.alive:
            self.logger.debug('send_cmd: ' + command)
            self._interface.write((command + '\r').encode())
            sleep(0.1)
            if command not in ['start']:  # Exclude log echo for commands that do not return
                cmd_time = time()
                cmd_response = bytearray()
                while self._terminator not in cmd_response and time() - cmd_time < 1.5 * self._interface.timeout:
                    cmd_response.extend(self._interface.read())
                if cmd_response:
                    # .strip('\r\n'+chr(0))
                    self.logger.info(cmd_response.decode(errors='ignore').strip(chr(0)))
        else:
            self.logger.warning('unable to send cmd, instrument not alive ' + command)

    def init_interface(self):
        # Set End of line character(s) for ASCII mode
        # 0 \r | 1 \n | 2 \r\n
        self.send_cmd('eol 0')
        # Stop in case DI-1100 is already scanning
        self.send_cmd("stop")
        # Check firmware version
        # self.send_cmd("info 2")
        # Define binary output mode
        # 0 binary | 1 ASCII
        self.send_cmd("encode 1")
        # Keep the packet size small for responsiveness
        self.send_cmd("ps 0")
        # Configure the instrument's scan list
        for p, c in enumerate(self.channels_enabled):
            self.send_cmd("slist " + str(p) + " " + str(self.SLIST[c]))
        # Set filter for each channel
        # Oversampling mode available: 0 Last point | 1 Average | 2 Maximum | 3 Minimum
        for p, c in enumerate(self.channels_enabled):
            self.send_cmd("filter " + str(p) + " 1")
        # Sample rate type (Hz) = (dividend) ÷ (srate × dec × deca)
        # For DI-1100
        #     dividend = 60000000    fixed
        #     dec = 1                fixed
        #     deca = [1, 40000]      defined through filter command
        #     srate = [1500, 65535]  define through srate command
        # Example: srate = 60000 and deca = 1000 then sample rate = 1 Hz
        # In practice this is off. with 60000 and 10 sample at 0.5 Hz...
        # 6000 and 500 is exactly at 1 Hz with 500 points to average for each sample
        self.send_cmd("srate 6000")
        self.send_cmd("deca 500")
        # Start acquisition
        self.send_cmd("start")

    def parse(self, packet):
        # Get voltage from each channel
        c = [float('nan')] * 9
        for i, v in zip(self.channels_enabled, packet.split(self.separator)):
            c[i+1] = float(v)  # Shift channels by 1 so that index starts at 1 instead of 0
        # Compute Products
        return [eval(eq, {'c': c, 'np': np}) for eq in self.variable_equations]
