# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-14 16:55:33
# @Last Modified by:   nils
# @Last Modified time: 2016-07-05 16:28:37

import os
import importlib
import sys
import numpy as np
from inlinino.cfg import Cfg
from inlinino.instruments import Instrument


class Inlinino():
    '''
    Main class for the application
    '''

    # Set variables
    m_cfg = None
    m_instruments = {}  # TODO Replace by list
    m_log_data = None
    m_com = None

    def __init__(self, _cfg_filename):
        # Load configuration
        # TODO update to configparser
        # TODO pop-up to ask configuration file to load
        self.m_cfg = Cfg()
        self.m_cfg.Load(_cfg_filename)
        if not self.m_cfg.Check():
            if self.m_cfg.m_v > 0:
                print('Configuration check failed, exit')
            exit()

        # Initialize instruments
        if any(self.m_cfg.m_instruments):
            for name, cfg in self.m_cfg.m_instruments.items():
                if 'module' in cfg.keys():
                    # Initialize instruments through generic serial parser
                    module = importlib.import_module('inlinino.instruments.' + cfg['module'].lower())
                    self.m_instruments[name] = getattr(module, cfg['module'])(name, cfg)
                else:
                    # Initialize instruments through generic serial parser
                    self.m_instruments[name] = Instrument(name, cfg)
        else:
            if self.m_cfg.m_v > 0:
                print('No Instrument, exit')
            exit()

        # Load interface
        if 'interface' not in self.m_cfg.m_app.keys():
            if self.m_cfg.m_v > 0:
                print('Need to specify user interface, exit')
            exit()
        if self.m_cfg.m_app['interface'] == 'gui':
            # Load Graphical User Interface
            module = importlib.import_module('gui')
            GUI = getattr(module, 'GUI')
            # Load Qt
            module = importlib.import_module('pyqtgraph.Qt')
            QtGui = getattr(module, 'QtGui')
            # init Qt
            gui_app = QtGui.QApplication(sys.argv)
            # init GUI
            self.m_gui = GUI(self)
            for k in self.m_instruments.keys():
                self.m_instruments[k].ui = self.m_gui
            # start GUI
            foo = gui_app.exec_()
            gui_app.deleteLater()  # Needed for QThread
            sys.exit(foo)
        elif self.m_cfg.m_app['interface'] == 'cli':
            print('UNTESTED !!!')
            # Initialize plots (with matplotlib)
            # module = importlib.import_module('plot')
            # Plot = getattr(module, 'Plot')
            # self.m_plot = Plot(self.m_log_data)
            # Load Command Line Interface
            module = importlib.import_module('cli')
            CLI = getattr(module, 'CLI')
            try:
                CLI(self).cmdloop()
            except KeyboardInterrupt:
                print('Keyboard Interrupt received.\n' +
                      'Trying to close connection with instrument(s),' +
                      ' to save data and close log file properly.')
                self.Close()
        else:
            if self.m_cfg.m_v > 0:
                print('Unknown user interface type, exit')
            exit()

        # Connect all instruments
        # for name, inst in self.m_instruments.items():
        #     if self.m_cfg.m_v > 0:
        #         print('Connecting ' + name)
        #     inst.Connect()

    def Close(self):
        # Close connection with instruments still active
        if self.m_instruments is not None:
            for name, inst in self.m_instruments.items():
                if inst.alive:
                    if self.m_cfg.m_v > 1:
                        print('Closing connection with ' + name)
                    inst.Close()
        # Close openned log file
        if self.m_log_data is not None:
            if self.m_log_data.m_active_log:
                print('Stop logging data.')
                self.m_log_data.Stop()
            if self.m_log_data.m_active_buffer:
                print('Stop buffer thread.')
                self.m_log_data.StopThread()

    def __str__(self):
        foo = str(self.m_cfg) + '\n[Instruments]\n'
        for inst in self.m_instruments.values():
            foo += '\t' + str(inst) + '\n'
        return foo

    def __del__(self):
        # Close safely application
        # Object with thread running won't call the __del__ method
        #   Need to close thread manually before
        self.Close()


class RingBuffer():
    # Ring buffer based on numpy.roll for np.array
    # Same concept as FIFO except that the size of the numpy array does not vary
    def __init__(self, _length, _dtype=None):
        # initialize buffer with NaN values
        # length correspond to the size of the buffer
        if _dtype is None:
            self.data = np.empty(_length)  # np.dtype = float64
            self.data[:] = np.NAN
        else:
            # type needs to be compatible with np.NaN
            self.data = np.empty(_length, dtype=_dtype)
            self.data[:] = None

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

    def __str__(self):
        return str(self.data)


# Test Inlinino App
if __name__ == '__main__':
    if len(sys.argv) == 2:
        inlinino = Inlinino(sys.argv[1])
    else:
        inlinino = Inlinino(os.path.join('cfg', 'test_cfg.json'))
    print(inlinino)
