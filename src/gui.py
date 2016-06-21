# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-14 16:55:47
# @Last Modified by:   nils
# @Last Modified time: 2016-06-21 13:59:22

import os
import sys
from time import sleep, gmtime, strftime, time
from functools import partial
from numpy import isnan as np_isnan
from pyqtgraph.Qt import QtGui, QtCore
import pyqtgraph as pg


class GUI(QtGui.QMainWindow):

    # Interface
    m_app_icon = 'ressources/inlinino.ico'

    def __init__(self, _app):
        super(GUI, self).__init__()
        self.m_app = _app
        self.initUI()

    def initUI(self):
        # Splash screen
        splashScreen = QtGui.QSplashScreen(QtGui.QPixmap(self.m_app_icon))
        splashScreen.show()

        # Check input
        if self.m_app is None:
            print('Need Inlinino app as argument')
            exit(-1)
        else:
            if 'theme' not in self.m_app.m_cfg.m_app.keys():
                if self.m_app.m_cfg.m_v > 0:
                    print('app_cfg:theme is missing')
                return False
            if 'ui_update_frequency' not in self.m_app.m_cfg.m_app.keys():
                if self.m_app.m_cfg.m_v > 0:
                    print('app_cfg:ui_update_frequency is missing')
                return False

        # Set window position/size
        self.resize(800, 600)
        self.center()

        # Set icon
        self.setWindowTitle('Inlinino')
        self.setWindowIcon(QtGui.QIcon(self.m_app_icon))

        # Set action of Menu Bar
        actInstrConnect = QtGui.QAction(QtGui.QIcon('none'), '&Connect', self)
        actInstrConnect.setShortcut('Ctrl+S')
        actInstrConnect.setStatusTip(
            'Connect an instrument to the application')
        actInstrConnect.triggered.connect(self.ActInstrConnect)
        actInstrClose = QtGui.QAction(QtGui.QIcon('none'), '&Disconnect', self)
        actInstrClose.setShortcut('Ctrl+D')
        actInstrClose.setStatusTip(
            'Disconnect an instrument from the application')
        actInstrClose.triggered.connect(self.ActInstrClose)
        actInstrList = QtGui.QAction(QtGui.QIcon('none'), '&List', self)
        actInstrList.setShortcut('Ctrl+L')
        actInstrList.setStatusTip('List all instruments available')
        actInstrList.triggered.connect(self.ActInstrList)

        self.m_actLogStart = QtGui.QAction(QtGui.QIcon('none'), '&Start', self)
        self.m_actLogStart.setShortcut('Ctrl+W')
        self.m_actLogStart.setStatusTip('Start logging data')
        self.m_actLogStart.triggered.connect(self.ActLogStart)
        self.m_actLogStop = QtGui.QAction(QtGui.QIcon('none'), '&Stop', self)
        self.m_actLogStop.setShortcut('Ctrl+E')
        self.m_actLogStop.setStatusTip('Stop logging data')
        self.m_actLogStop.triggered.connect(self.ActLogStop)
        actLogHeader = QtGui.QAction(QtGui.QIcon('none'), '&File header', self)
        actLogHeader.setShortcut('Ctrl+F')
        actLogHeader.setStatusTip('Change header of log file name')
        actLogHeader.triggered.connect(self.ActLogHeader)

        actHelpHelp = QtGui.QAction(QtGui.QIcon('none'), '&Help', self)
        actHelpHelp.setStatusTip('Help')
        actHelpHelp.triggered.connect(self.ActHelpHelp)
        actHelpSupport = QtGui.QAction(QtGui.QIcon('none'), '&Support', self)
        actHelpSupport.setStatusTip('Support')
        actHelpSupport.triggered.connect(self.ActHelpSupport)
        actHelpCredits = QtGui.QAction(QtGui.QIcon('none'), '&Credits', self)
        actHelpCredits.setStatusTip('Credits')
        actHelpCredits.triggered.connect(self.ActHelpCredits)

        # Set menu bar
        menuBar = self.menuBar()
        # Add menu to menu bar
        menuInstr = menuBar.addMenu('&Instrument')
        menuLog = menuBar.addMenu('&Log')
        menuHelp = menuBar.addMenu('&Help')
        # Add actions to menu
        menuInstr.addAction(actInstrConnect)
        menuInstr.addAction(actInstrClose)
        menuInstr.addAction(actInstrList)
        menuLog.addAction(self.m_actLogStart)
        menuLog.addAction(self.m_actLogStop)
        menuLog.addAction(actLogHeader)
        menuHelp.addAction(actHelpHelp)
        menuHelp.addAction(actHelpSupport)
        menuHelp.addAction(actHelpCredits)

        # Set docked sidebar (sd)
        # Display data
        sd_data = QtGui.QGridLayout()
        wdgt, self.m_time_display, self.m_date_display = \
            self.QVarDisplay('Time (Zulu)',
                    self.m_app.m_log_data.m_buffer['timestamp'].get()[0],
                    'yyyy/mm/dd')
        sd_data.addWidget(wdgt)
        self.m_var_display = {}
        for i in range(len(self.m_app.m_log_data.m_varnames)):
            varname = self.m_app.m_log_data.m_varnames[i]
            wdgt, self.m_var_display[varname], foo = self.QVarDisplay(varname,
                self.m_app.m_log_data.m_buffer[varname].get(),
                self.m_app.m_log_data.m_varunits[i])
            sd_data.addWidget(wdgt, (i + 1) // 3 , (i + 1) % 3)
        # Instrument Status
        sd_instr_status = QtGui.QVBoxLayout()
        self.m_instr_status = {}
        self.m_instr_pckt_rcvd = {}
        self.m_instr_pckt_mssd = {}
        self.m_instr_connect_btn = {}
        self.m_instr_close_btn = {}
        for instr_key in self.m_app.m_cfg.m_instruments.keys():
            instr_val = self.m_app.m_instruments[instr_key]
            wdgt, self.m_instr_status[instr_key], \
                  self.m_instr_pckt_rcvd[instr_key], \
                  self.m_instr_pckt_mssd[instr_key], \
                  self.m_instr_connect_btn[instr_key], \
                  self.m_instr_close_btn[instr_key] = self.QInstrDisplay(
                               instr_key, instr_val.m_active,
                               instr_val.m_n, instr_val.m_nNoResponse)
            QtCore.QObject.connect(self.m_instr_connect_btn[instr_key],
                                   QtCore.SIGNAL('clicked()'),
                                   partial(self.ActInstrConnect, line=False, _instr_key=instr_key))
            QtCore.QObject.connect(self.m_instr_close_btn[instr_key],
                                   QtCore.SIGNAL('clicked()'),
                                   partial(self.ActInstrClose, line=False, _instr_key=instr_key))
            self.m_instr_close_btn[instr_key].hide()
            sd_instr_status.addWidget(wdgt)
        # Log status/Action
        sd_log_fname_lbl = QtGui.QLabel('Data logged in:')
        sd_log_fname_lbl.setWordWrap(True);
        self.m_sd_log_fname_val = QtGui.QLabel('...')
        self.m_sd_log_fname_val.setWordWrap(True);
        self.m_sd_start_btn = QtGui.QPushButton('Start')
        self.m_sd_stop_btn = QtGui.QPushButton('Stop')
        QtCore.QObject.connect(self.m_sd_start_btn, QtCore.SIGNAL('clicked()'), self.ActLogStart)
        QtCore.QObject.connect(self.m_sd_stop_btn, QtCore.SIGNAL('clicked()'), self.ActLogStop)
        sd_log = QtGui.QVBoxLayout()
        sd_log.addWidget(sd_log_fname_lbl)
        sd_log.addWidget(self.m_sd_log_fname_val)
        sd_log_action = QtGui.QHBoxLayout()
        sd_log_action.addWidget(self.m_sd_start_btn)
        sd_log_action.addWidget(self.m_sd_stop_btn)
        sd_log.addLayout(sd_log_action)
        self.SetLogFileVal()
        self.SetEnableLogButtons()
        # Debug buttons
        if __debug__:
            dbg_info_lbl = QtGui.QLabel('DEBUG MODE')
            dbg_refresh_btn = QtGui.QPushButton('Refresh')
            QtCore.QObject.connect(dbg_refresh_btn, QtCore.SIGNAL('clicked()'), self.RefreshAll)
            dbg_layout = QtGui.QVBoxLayout()
            dbg_layout.addWidget(dbg_info_lbl)
            dbg_layout.addWidget(dbg_refresh_btn)
        # Custom status bar at the bottom of the widget
        self.m_statusBar = QtGui.QLabel('Inlinino is ready.')
        self.m_statusBar.setWordWrap(True);
        # Set sidebar widgets in dock
        self.dockWidgetContent = QtGui.QWidget()
        self.sidebar = QtGui.QVBoxLayout(self.dockWidgetContent)
        self.sidebar.addLayout(sd_data)
        self.sidebar.addWidget(self.HLine())
        self.sidebar.addLayout(sd_instr_status)
        self.sidebar.addWidget(self.HLine())
        self.sidebar.addLayout(sd_log)
        if __debug__:
            self.sidebar.addWidget(self.HLine())
            self.sidebar.addLayout(dbg_layout)
        self.sidebar.addStretch(1)
        self.sidebar.addWidget(self.m_statusBar)
        # Setup the dock widget
        self.dockWidget = QtGui.QDockWidget(self)
        self.dockWidget.setObjectName('Sidebar')
        self.dockWidget.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea |
                                        QtCore.Qt.RightDockWidgetArea)
        self.dockWidget.setWidget(self.dockWidgetContent)
        self.dockWidget.setFeatures(QtGui.QDockWidget.DockWidgetMovable |
                                    QtGui.QDockWidget.DockWidgetFloatable)
        # self.dockWidget.setFeatures(QtGui.QDockWidget.NoDockWidgetFeatures)
        self.dockWidget.setTitleBarWidget(QtGui.QWidget(None))
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.dockWidget)

        # Set Colors
        palette = QtGui.QPalette()
        if (self.m_app.m_cfg.m_app['theme'] == "light" or
            self.m_app.m_cfg.m_app['theme'] == "outside"):
            palette.setColor(palette.Window, QtGui.QColor('#F8F8F2')) # Background
            palette.setColor(palette.WindowText, QtGui.QColor('#26292C')) # Foreground
            pg.setConfigOption('background', QtGui.QColor('#F8F8F2'))
            pg.setConfigOption('foreground', QtGui.QColor('#26292C'))
        else:
            palette.setColor(palette.Window, QtGui.QColor('#26292C'))
            palette.setColor(palette.WindowText, QtGui.QColor('#F8F8F2'))
            pg.setConfigOption('background', QtGui.QColor('#26292C'))
            pg.setConfigOption('foreground', QtGui.QColor('#F8F8F2'))
        self.setPalette(palette)

        # Button style is os dependend (can force with some CSS)
        self.setFont(QtGui.QFont("Helvetica Neue Light"))

        # Set figure with pyqtgraph
        self.m_pw = pg.PlotWidget()
        self.m_plot = self.m_pw.plotItem
        self.m_curves = []
        n = len(self.m_app.m_log_data.m_varnames)
        for i in range(n):
            c = pg.PlotCurveItem(pen=(i,n))
            self.m_plot.addItem(c)
            self.m_curves.append(c)
        self.m_plot.setLabel('bottom', 'Time', units='s')
        self.m_plot.setLabel('left', 'Signal', units='Volts')
        self.m_plot.setYRange(0, 5)
        self.m_plot.setXRange(0, 100)
        self.m_plot.setLimits(minYRange=0, maxYRange=4500) # In version 0.9.9
        self.m_plot.setMouseEnabled(x=False,y=True)

        # Set layout in main window
        widget = QtGui.QWidget()
        layout = QtGui.QVBoxLayout(widget)
        layout.addWidget(self.m_pw)
        self.setCentralWidget(widget)

        # Close splash screen before starting main app
        if not __debug__:
            sleep(0.5)
        splashScreen.finish(self)

        # Show main window and make it active
        self.show()
        self.raise_()

        # Save state of current window
        self.saveState()
        # self.restorState()

        # Connect background thread refreshing info on UI
        self.m_refresh_thread = Thread()
        self.m_refresh_worker = Worker(1/self.m_app.m_cfg.m_app['ui_update_frequency'])
        self.m_refresh_worker.moveToThread(self.m_refresh_thread)
        self.m_refresh_worker.refresh.connect(self.RefreshAll)
        self.m_refresh_worker.finished.connect(self.m_refresh_thread.quit)
        self.m_refresh_thread.started.connect(self.m_refresh_worker.RefreshPing)
        # self.m_refresh_thread.start()

    # Set plot (pyQtGraph)
    def SetPlot(self):
        for i in range(len(self.m_app.m_log_data.m_varnames)):
            varname = self.m_app.m_log_data.m_varnames[i]
            # data = np.random.normal(size=100)
            data = self.m_app.m_log_data.m_buffer[varname].get(100)
            self.m_curves[i].setData(data)

    # Instrument Actions
    def ActInstrConnect(self, line, _instr_key=None):
        # Get instrument to connect
        if _instr_key == None:
            list_instr = list(self.m_app.m_instruments.keys())
            instr_key, ok = QtGui.QInputDialog.getItem(self, 'Connect instrument',
                                                        'Select instrument',
                                                        ['All'] + list_instr)
        else:
            instr_key = _instr_key
            ok = True

        # Connect instrument
        if ok:
            if instr_key == 'All':
                # Connect all inactive instruments
                allConnectionSuccess = True
                allConnectionFailed = False
                updateComPort = True
                for instr_key in list_instr:
                    if not self.m_app.m_instruments[instr_key].m_active:
                        if (self.m_app.m_instruments[instr_key].m_connect_need_port
                            and updateComPort):
                            # Update list of com port if needed for first instrumnt
                            self.m_app.m_com.ListPorts()
                            updateComPort = False
                        foo = self.InstrConnect(instr_key)
                        if foo == False:
                            allConnectionSuccess = False
                        else:
                            allConnectionFailed = False
                if allConnectionSuccess:
                    self.m_statusBar.setText('All instrument are ' +
                                                 'connected')
                elif allConnectionFailed:
                    self.m_statusBar.setText('ERROR: All instrument ' +
                                                 'connection failed')
                else:
                    self.m_statusBar.setText('WARNING: Some connection ' +
                                                 'succeded, some failed')
            else:
                # Connect specified instrument
                if self.m_app.m_instruments[instr_key].m_connect_need_port:
                    # Update list of Com port if needed
                    self.m_app.m_com.ListPorts()
                self.InstrConnect(instr_key)
        # Update Thread to Refresh UI
        self.UpdateThread()

    def InstrConnect(self, _instr_key):
        if self.m_app.m_instruments[_instr_key].m_connect_need_port:
            # Instrument need a port address to connect
            port, ok = QtGui.QInputDialog.getItem(self, 'Connect Instrument',
                                              'Connecting ' + _instr_key + '\nSelect port', self.m_app.m_com.m_port_list)
            if ok:
                if self.m_app.m_instruments[_instr_key].Connect(port):
                    self.m_statusBar.setText(_instr_key + ' is connected to ' + port)
                else:
                    self.m_statusBar.setText('ERROR: Fail connecting ' + _instr_key + ' to ' + port)
        else:
            # Instrument do not need anything to connect
            if self.m_app.m_instruments[_instr_key].Connect():
                self.m_statusBar.setText(_instr_key + ' is connected')
            else:
                self.m_statusBar.setText('ERROR: Fail connecting ' + _instr_key)
        # Set instrument status
        self.SetInstrumentsStatus()

    def ActInstrClose(self, line, _instr_key = None):
        # Get instrument to disconnect
        if _instr_key is None:
            list_instr = list(self.m_app.m_instruments.keys())
            instr_key, ok = QtGui.QInputDialog.getItem(self, 'Disconnect instrument',
                                               'Select instrument', ['All'] + list_instr)
        else:
            instr_key = _instr_key
            ok = True

        # Disconnect instrument
        if ok:
            if instr_key == 'All':
                for instr_key in list_instr:
                    self.m_app.m_instruments[instr_key].Close()
                self.m_statusBar.setText('All instrument connection closed')
            else:
                self.m_app.m_instruments[instr_key].Close()
                self.m_statusBar.setText('Closed connection with ' + instr_key)
        else:
            self.m_statusBar.setText('Cancel instrument disconnection')

        # Update display
        self.SetInstrumentsStatus()
        # Update Thread to Refresh UI
        self.UpdateThread()

    # Set instruments display
    def SetInstrumentsVar(self):
        # Update time and date
        t = self.m_app.m_log_data.m_buffer['timestamp'].get()[0]
        if not np_isnan(t):
            zulu = gmtime(t)
            self.m_time_display.setText(strftime('%H:%M:%S', zulu))
            self.m_time_display.repaint()
            self.m_date_display.setText(strftime('%Y/%m/%d', zulu))
            self.m_date_display.repaint()
        # Update variables
        for varname in self.m_app.m_log_data.m_varnames:
            self.m_var_display[varname].setText('%.4f' %
                self.m_app.m_log_data.m_buffer[varname].get()[0])
            self.m_var_display[varname].repaint()

    def SetInstrumentsStatus(self):
        for instr_key, instr_value in self.m_app.m_instruments.items():
            if instr_value.m_active:
                # Change status
                self.m_instr_status[instr_key].setText('active')
                self.m_instr_status[instr_key].setStyleSheet('color: #9ce22e')
                # Change button
                self.m_instr_connect_btn[instr_key].hide()
                self.m_instr_close_btn[instr_key].show()
            else:
                # Change status
                self.m_instr_status[instr_key].setText('inactive')
                self.m_instr_status[instr_key].setStyleSheet('color: #f92670')
                # Change button
                self.m_instr_connect_btn[instr_key].show()
                self.m_instr_close_btn[instr_key].hide()
            self.m_instr_status[instr_key].repaint()

    def SetInstrumentsPackets(self):
        for instr_key, instr_value in self.m_app.m_instruments.items():
            self.m_instr_pckt_rcvd[instr_key].setText(str(instr_value.m_n))
            self.m_instr_pckt_mssd[instr_key].setText(str(instr_value.m_nNoResponse))
            self.m_instr_pckt_rcvd[instr_key].repaint()
            self.m_instr_pckt_mssd[instr_key].repaint()

    # Action Log
    def ActInstrList(self, line):
        foo = ''
        for instr_val in self.m_app.m_instruments.values():
            foo += '  ' + str(instr_val) + '\n'
        reply = QtGui.QMessageBox.information(self, 'Instrument list',
                                              'List of instruments:\n' + foo)

    def ActLogStart(self):
        if not self.m_app.m_log_data.m_active_log:
            if self.m_app.m_log_data.CountActiveInstruments() < 1:
                reply = QtGui.QMessageBox.warning(self, 'Start logging data',
                    "No instruments are connected, do you still want to start logging data ?", QtGui.QMessageBox.Yes |
                    QtGui.QMessageBox.No, QtGui.QMessageBox.No)

                if reply == QtGui.QMessageBox.Yes:
                    self.m_app.m_log_data.Start()
                    self.m_statusBar.setText('Start logging data')
                else:
                    self.m_statusBar.setText('Cancel Start logging data')
            else:
                self.m_app.m_log_data.Start()
                self.m_statusBar.setText('Start logging data')
        else:
            QtGui.QMessageBox.information(self, 'Start logging data',
                                              'Already logging data')
        self.SetEnableLogButtons()
        self.SetLogFileVal()

    def ActLogStop(self):
        if self.m_app.m_log_data.m_active_log:
            self.m_app.m_log_data.Stop()
            self.m_statusBar.setText('Stop logging data')
        else:
            QtGui.QMessageBox.information(self, 'Stop logging data',
                                              'Already stopped logging data')
        self.SetEnableLogButtons()
        self.SetLogFileVal()

    def ActLogHeader(self):
        header, ok = QtGui.QInputDialog.getText(self, 'Set log file name header',
                                                'New header:')
        if ok:
            self.m_app.m_log_data.m_file_header = header
            self.m_statusBar.setText('Set log file header to ' + header)
        self.SetLogFileVal()

    # Set log display
    def SetEnableLogButtons(self):
        if self.m_app.m_log_data.m_active_log:
            self.m_sd_start_btn.setEnabled(False)
            self.m_sd_stop_btn.setEnabled(True)
            self.m_actLogStart.setEnabled(False)
            self.m_actLogStop.setEnabled(True)
        else:
            self.m_sd_start_btn.setEnabled(True)
            self.m_sd_stop_btn.setEnabled(False)
            self.m_actLogStart.setEnabled(True)
            self.m_actLogStop.setEnabled(False)

    def SetLogFileVal(self):
        # sleep(0.01), in order to read after it was updated
        if self.m_app.m_log_data.m_file_name is not None and self.m_app.m_log_data.m_active_log:
            foo = os.path.join(self.m_app.m_log_data.m_file_path, self.m_app.m_log_data.m_file_name)
        else:
            foo = os.path.join(self.m_app.m_log_data.m_file_path, self.m_app.m_log_data.m_file_header) + '_yyyymmdd_HHMMSS.csv'
        self.m_sd_log_fname_val.setText('...' + foo[-30:])
        self.m_sd_log_fname_val.repaint()

    # Refresh user interface with data from other thread
    def RefreshAll(self):
        # if __debug__:
        #     print('GUI:RefreshAll')
        self.SetInstrumentsVar()
        self.SetInstrumentsPackets()
        self.SetInstrumentsStatus()
        self.SetLogFileVal()
        self.SetPlot()

    # Action Help
    def ActHelpHelp(self):
        msg = QtGui.QMessageBox()
        msg.setIcon(QtGui.QMessageBox.Question)
        msg.setText("Inlinino Help")
        msg.setInformativeText('Inlinino is a simple data logger.\n' +
                               'To start logging data:\n' +
                               '   1. connect an instrument (Instrument>Connect)\n' +
                               '   2. start the logger (Log>Start)\n' +
                               'To stop logging data:\n' +
                               '   + stop the logger (Log>Stop)\n' +
                               '   + exit application (will stop logging to)\n' +
                               'More details at: github.com/OceanOptics/Inlinino/wiki')
        msg.setWindowTitle('Help')
        msg.exec_()

    def ActHelpSupport(self):
        msg = QtGui.QMessageBox()
        msg.setIcon(QtGui.QMessageBox.Question)
        msg.setText('Inlinino Support')
        msg.setInformativeText('Send questions, bug reports, fixes, enhancements, t-shirts, ' +
                               'money, lobsters & beers to Nils\n' +
                               '<nils.haentjens+inlinino@maine.edu>')
        msg.setWindowTitle('Support')
        msg.exec_()

    def ActHelpCredits(self):
        msg = QtGui.QMessageBox()
        msg.setIcon(QtGui.QMessageBox.Information)
        msg.setText('Inlinino Credits')
        msg.setInformativeText('Developped by Nils Haëntjens (University of Maine)\nUsing pySerial, pyQt, and pyQtGraph\n')
        msg.setWindowTitle('Credits')
        msg.exec_()

    # UI specific actions
    def closeEvent(self, event):
        if not __debug__:
            reply = QtGui.QMessageBox.question(self, 'Closing application',
                "Are you sure to quit?", QtGui.QMessageBox.Yes |
                QtGui.QMessageBox.No, QtGui.QMessageBox.No)

            if reply == QtGui.QMessageBox.Yes:
                event.accept()
            else:
                event.ignore()

    def center(self):
        qr = self.frameGeometry()
        cp = QtGui.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    # UI custom widgets
    def HLine(self):
        foo = QtGui.QFrame()
        foo.setFrameShape(QtGui.QFrame.HLine)
        foo.setFrameShadow(QtGui.QFrame.Sunken)
        return foo

    def QVarDisplay(self, _name, _value, _unit='No Units'):
        name = QtGui.QLabel(_name)
        name.setFont(QtGui.QFont("Helvetica Neue Light", 10))
        name.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignBottom)
        value = QtGui.QLabel(str(_value))
        value.setFont(QtGui.QFont("Helvetica Neue Light", 12))
        value.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        unit = QtGui.QLabel(_unit)
        unit.setFont(QtGui.QFont("Helvetica Neue Light", 10))
        unit.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignTop)

        widget = QtGui.QWidget()
        group = QtGui.QVBoxLayout(widget)
        group.setSpacing(0)
        group.setContentsMargins(0, 0, 0, 0)
        group.addWidget(name)
        group.addWidget(value)
        group.addWidget(unit)

        return widget, value, unit

    def QInstrDisplay(self, _name, _status, _pckt_received, _pckt_missed):
        name = QtGui.QLabel(_name)
        # name.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        status_lbl1 = QtGui.QLabel(' [')
        status_lbl2 = QtGui.QLabel('] : ')
        if _status:
            status_val = QtGui.QLabel('active')
            status_val.setStyleSheet('color: #9ce22e')
        else:
            status_val = QtGui.QLabel('inactive')
            status_val.setStyleSheet('color: #f92670') # 5cd9ef
        connect_btn = QtGui.QPushButton('>')
        connect_btn.setToolTip('Connect ' + _name)
        close_btn = QtGui.QPushButton('o')
        close_btn.setToolTip('Disconnect ' + _name)
        pckt_received_lbl = QtGui.QLabel('  pckt received: ')
        pckt_received_val = QtGui.QLabel(str(_pckt_received))
        pckt_missed_lbl = QtGui.QLabel('  pckt missed: ')
        pckt_missed_val = QtGui.QLabel(str(_pckt_missed))

        widget = QtGui.QWidget()
        group = QtGui.QVBoxLayout(widget)
        group.setSpacing(0)
        group.setContentsMargins(0, 0, 0, 0)
        header = QtGui.QHBoxLayout()
        header.addWidget(name)
        header.addWidget(status_lbl1)
        header.addWidget(status_val)
        header.addWidget(status_lbl2)
        header.addWidget(connect_btn)
        header.addWidget(close_btn)
        header.addStretch(1)
        group.addLayout(header)
        pckt_received = QtGui.QHBoxLayout()
        pckt_received.addWidget(pckt_received_lbl)
        pckt_received.addWidget(pckt_received_val)
        group.addLayout(pckt_received)
        pckt_missed = QtGui.QHBoxLayout()
        pckt_missed.addWidget(pckt_missed_lbl)
        pckt_missed.addWidget(pckt_missed_val)
        group.addLayout(pckt_missed)

        return widget, status_val, pckt_received_val, pckt_missed_val, \
            connect_btn, close_btn

    def UpdateThread(self):
        # if __debug__:
        #     print('GUI:UpdateThread')
        # If any instrument is active start log buffer
        for instr_value in self.m_app.m_instruments.values():
            if instr_value.m_active:
                if not self.m_app.m_log_data.m_active_buffer:
                    self.m_app.m_log_data.StartThread()
                if not self.m_refresh_thread.isRunning():
                    self.m_refresh_worker.m_active = True
                    self.m_refresh_thread.start()
                return
        # If all instrument are off stop log buffer
        if self.m_app.m_log_data.m_active_buffer:
            self.m_app.m_log_data.StopThread()
        if self.m_refresh_thread.isRunning():
            self.m_refresh_worker.m_active = False


# Thread and Workers to refresh data
# From Matthew Levine on http://stackoverflow.com/questions/6783194
class Worker(QtCore.QObject):
    refresh = QtCore.pyqtSignal()
    finished = QtCore.pyqtSignal()

    def __init__(self, _timeout, _parent=None):
        QtCore.QObject.__init__(self, _parent)
        self.m_timeout = _timeout
        self.m_active = True

    def __del__(self):
        self.m_active = False
        if __debug__:
            print('Closing Qtworker')

    @QtCore.pyqtSlot()
    def RefreshPing(self):
        start_time = time()
        while self.m_active:
            try:
                sleep(self.m_timeout - (time() - start_time) % self.m_timeout)
                self.refresh.emit()
            except Exception as e:
                print('Unexpected error while updating GUI')
                print(e)
        self.finished.emit()


class Thread(QtCore.QThread):
    def __init__(self, _parent=None):
        QtCore.QThread.__init__(self, _parent)

    def start(self):
        QtCore.QThread.start(self)

    def run(self):
        QtCore.QThread.run(self)


if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    main_ui = GUI(None)
    sys.exit(app.exec_())
