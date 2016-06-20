# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-14 16:55:33
# @Last Modified by:   nils
# @Last Modified time: 2016-06-20 16:06:53

import os
import importlib
import sys

from cfg import Cfg
from instruments import Communication
from log import LogData


class Inlinino():
    '''
    Main class for the application
    '''

    # Set variables
    m_cfg = None
    m_instruments = {}
    m_log_data = None
    m_com = None
    m_plot = None

    def __init__(self, _cfg_filename):
        # Load configuration
        self.m_cfg = Cfg()
        self.m_cfg.Load(_cfg_filename)
        if not self.m_cfg.Check():
            if self.m_cfg.m_v > 0:
                print('Configuration check failed, exit')
            exit()

        # Initialize instruments
        if any(self.m_cfg.m_instruments):
            for name, cfg in self.m_cfg.m_instruments.items():
                if 'module' in cfg.keys() and 'name' in cfg.keys():
                    module = importlib.import_module('instruments.' +
                                                     cfg['module'].lower() +
                                                     '.' + cfg['name'].lower())
                    class_ = getattr(module, cfg['name'])
                    self.m_instruments[name] = class_(name, cfg)
                else:
                    if self.m_cfg.m_v > 0:
                        print('Need to specify module and name of' +
                              ' instrument ' + name)
                    exit()
        else:
            if self.m_cfg.m_v > 0:
                print('No Instrument, exit')
            exit()

        # Initiliaze com ports
        self.m_com = Communication()

        # Initialize data logger
        self.m_log_data = LogData(
            self.m_cfg.m_log, self.m_instruments, self.m_cfg.m_instruments)

        # Self-t   est
        # self.m_log_data.Start()
        # self.m_log_data.Stop()

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
            # start GUI
            foo = gui_app.exec_()
            gui_app.deleteLater()  # Needed for QThread
            sys.exit(foo)
        elif self.m_cfg.m_app['interface'] == 'cli':
            # Initialize plots (with matplotlibs)
            module = importlib.import_module('plot')
            Plot = getattr(module, 'Plot')
            self.m_plot = Plot(self.m_log_data)
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
                if inst.m_active:
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

    def ListInstruments(self):
        print('WARNING: function deprecated\n' +
              'Prefer: list(self.m_app.m_instruments.keys())')
        ls = []
        for key, value in self.m_instruments.items():
            ls.append(value.m_name)
        return ls

    def __str__(self):
        foo = str(self.m_cfg) + '\n[Instruments]\n'
        for inst, inst in self.m_instruments.items():
            foo += '\t' + str(inst) + '\n'
        return foo

    def __del__(self):
        # Close safely application
        # Object with thread running won't call the __del__ method
        #   Need to close thread manually before
        self.Close()


# Test Inlinino App
if __name__ == '__main__':
    if len(sys.argv) == 2:
        inlinino = Inlinino(sys.argv[1])
    elif __debug__:
        inlinino = Inlinino(os.path.join('cfg', 'test_cfg.json'))
    else:
        inlinino = Inlinino(os.path.join('cfg', 'simulino_cfg.json'))
    print(inlinino)
