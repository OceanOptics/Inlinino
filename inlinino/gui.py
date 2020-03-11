# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-05-14 16:55:47
# @Last Modified by:   nils
# @Last Modified time: 2017-01-16 15:35:52

import os
import sys
from time import sleep, gmtime, strftime, time
from functools import partial
import numpy as np
from pyqtgraph.Qt import QtGui, QtCore, QtWidgets
import pyqtgraph as pg
from inlinino import RingBuffer
from serial import SerialException
from serial.tools.list_ports import comports as list_serial_comports


class GUI(QtGui.QMainWindow):

    # FONT_FAMILY = 'Helvetica Neue Light'
    FONT_FAMILY = 'Helvetica'

    # Interface
    m_app_icon = 'ressources/inlinino.ico'

    def __init__(self, _app):
        super(GUI, self).__init__()
        self.m_app = _app

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
                self.m_app.m_cfg.m_app['theme'] = "outside"
            if 'ui_disp_pos_shift' not in self.m_app.m_cfg.m_app.keys():
                if self.m_app.m_cfg.m_v > 0:
                    print('app_cfg:ui_disp_pos_shift is missing')
                self.m_app.m_cfg.m_app['ui_disp_pos_shift'] = 3
            else:
                pos_shift = self.m_app.m_cfg.m_app['ui_disp_pos_shift']

        # Init data buffer for each instrument
        self._buffer_timestamp = {}
        self._buffer_data = {}
        for instr_key, instr_val in self.m_app.m_instruments.items():
            self._buffer_timestamp[instr_key] = RingBuffer(self.m_app.m_cfg.m_app['gui_buffer_length'])
            self._buffer_data[instr_key] = [RingBuffer(self.m_app.m_cfg.m_app['gui_buffer_length']) for i in
                                            range(len(instr_val.variable_displayed))]
                                            # TODO Initialize with variable type if available

        # Set window position/size
        self.resize(800, 600)
        self.center()

        # Set icon
        self.setWindowTitle('Inlinino')
        self.setWindowIcon(QtGui.QIcon(self.m_app_icon))

        # Set Theme colors
        if (self.m_app.m_cfg.m_app['theme'] == "light" or
                self.m_app.m_cfg.m_app['theme'] == "outside"):
            self.BACKGROUND_COLOR = '#F8F8F2'
            self.FOREGROUND_COLOR = '#26292C'
        else:
            self.BACKGROUND_COLOR = '#26292C'
            self.FOREGROUND_COLOR = '#F8F8F2'

        # Set action of Menu Bar
        actInstrConnect = QtGui.QAction(QtGui.QIcon('none'), '&Connect', self)
        actInstrConnect.setShortcut('Ctrl+S')
        actInstrConnect.setStatusTip('Connect an instrument to the application')
        actInstrConnect.triggered.connect(self.ActInstrConnect)
        actInstrClose = QtGui.QAction(QtGui.QIcon('none'), '&Disconnect', self)
        actInstrClose.setShortcut('Ctrl+D')
        actInstrClose.setStatusTip('Disconnect an instrument from the application')
        actInstrClose.triggered.connect(self.ActInstrClose)
        actInstrList = QtGui.QAction(QtGui.QIcon('none'), '&List', self)
        actInstrList.setShortcut('Ctrl+I')
        actInstrList.setStatusTip('List all instruments available')
        actInstrList.triggered.connect(self.ActInstrList)

        self.m_actInstrLog = QtGui.QAction(QtGui.QIcon('none'), '&Start/Stop', self)
        self.m_actInstrLog.setShortcut('Ctrl+L')
        self.m_actInstrLog.setStatusTip('Start/Stop logging data')
        self.m_actInstrLog.triggered.connect(self.ActInstrLog)
        actLogPrefix = QtGui.QAction(QtGui.QIcon('none'), '&Filename prefix', self)
        actLogPrefix.setShortcut('Ctrl+F')
        actLogPrefix.setStatusTip('Update logged filename prefix')
        actLogPrefix.triggered.connect(self.ActLogPrefix)
        actLogPath = QtGui.QAction(QtGui.QIcon('none'), '&Path to files', self)
        actLogPath.setShortcut('Ctrl+P')
        actLogPath.setStatusTip('Update path to logged files')
        actLogPath.triggered.connect(self.ActLogPath)

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
        menuLog.addAction(self.m_actInstrLog)
        menuLog.addAction(actLogPrefix)
        menuLog.addAction(actLogPath)
        menuHelp.addAction(actHelpHelp)
        menuHelp.addAction(actHelpSupport)
        menuHelp.addAction(actHelpCredits)

        # Set docked sidebar (sd)
        # Display data
        sd_data = QtGui.QGridLayout()
        wdgt, self.m_time_display, self.m_date_display = \
            self.QVarDisplay('Time (Zulu)',
                    'HH:MM:SS',
                    'yyyy/mm/dd')
        sd_data.addWidget(wdgt)
        self.m_var_display = {}
        i = 0
        for instr_key, instr_val in self.m_app.m_instruments.items():
            self.m_var_display[instr_key] = []
            for var_key in instr_val.variable_displayed:
                wdgt, foo, _ = self.QVarDisplay(instr_val.variable_names[var_key], 'NaN',
                                                instr_val.variable_units[var_key])
                self.m_var_display[instr_key].append(foo)
                sd_data.addWidget(wdgt, (i + pos_shift) // 3, (i + pos_shift) % 3)
                i += 1

        # Instrument Status
        sd_instr_status = QtGui.QVBoxLayout()
        self.m_instr_status = {}
        self.m_instr_pckt_rcvd = {}
        self.m_instr_pckt_mssd = {}
        self.m_instr_pckt_lggd = {}
        self.m_instr_connect_btn = {}
        self.m_instr_close_btn = {}
        self.m_instr_log_btn = {}
        for instr_key in self.m_app.m_cfg.m_instruments.keys():
            instr_val = self.m_app.m_instruments[instr_key]
            wdgt, self.m_instr_status[instr_key], \
                  self.m_instr_pckt_rcvd[instr_key], \
                  self.m_instr_pckt_mssd[instr_key], \
                  self.m_instr_pckt_lggd[instr_key], \
                  self.m_instr_connect_btn[instr_key], \
                  self.m_instr_close_btn[instr_key], \
                  self.m_instr_log_btn[instr_key] = self.QInstrDisplay(
                               instr_key, instr_val.alive, instr_val.log_status(),
                               instr_val.packet_received, instr_val.packet_corrupted, instr_val.packet_logged)
            self.m_instr_connect_btn[instr_key].clicked.connect(
                                   partial(self.ActInstrConnect, instrument_key=instr_key))
            self.m_instr_close_btn[instr_key].clicked.connect(
                                   partial(self.ActInstrClose, instrument_key=instr_key))
            self.m_instr_close_btn[instr_key].hide()
            self.m_instr_log_btn[instr_key].clicked.connect(
                                   partial(self.ActInstrLog, instrument_key=instr_key))
            self.m_instr_log_btn[instr_key].hide()
            sd_instr_status.addWidget(wdgt)
        # Log status/Action
        # sd_log_fname_lbl = QtGui.QLabel('Data logged in:')
        # sd_log_fname_lbl.setWordWrap(True);
        # self.m_sd_log_fname_val = QtGui.QLabel('...')
        # self.m_sd_log_fname_val.setWordWrap(True);
        # self.m_sd_start_btn = QtGui.QPushButton('Start')
        # # self.m_sd_start_btn.setIcon(self.m_sd_start_btn.style().standardIcon(QtWidgets.QStyle.SP_MediaPlay))
        # self.m_sd_stop_btn = QtGui.QPushButton('Stop')
        # # self.m_sd_stop_btn.setIcon(self.m_sd_stop_btn.style().standardIcon(QtWidgets.QStyle.SP_MediaStop))
        # self.m_sd_start_btn.clicked.connect(self.ActLogStart)
        # self.m_sd_stop_btn.clicked.connect(self.ActLogStop)
        # sd_log = QtGui.QVBoxLayout()
        # sd_log.addWidget(sd_log_fname_lbl)
        # sd_log.addWidget(self.m_sd_log_fname_val)
        # sd_log_action = QtGui.QHBoxLayout()
        # sd_log_action.addWidget(self.m_sd_start_btn)
        # sd_log_action.addWidget(self.m_sd_stop_btn)
        # sd_log.addLayout(sd_log_action)
        # self.SetLogFileVal()
        # self.SetEnableLogButtons()
        # Graph actions
        self.m_graph_freeze_cb = QtGui.QCheckBox("Freeze figure", self)
        self.m_graph_freeze_cb.setStatusTip("Freeze only figure, " +
                                            "log keep running in background")
        # Debug buttons
        if __debug__:
            dbg_info_lbl = QtGui.QLabel('DEBUG MODE')
            dbg_layout = QtGui.QVBoxLayout()
            dbg_layout.addWidget(dbg_info_lbl)
        # Custom status bar at the bottom of the widget
        self.m_statusBar = QtGui.QLabel('Inlinino is ready.')
        self.m_statusBar.setWordWrap(True)
        # Set sidebar widgets in dock
        self.dockWidgetContent = QtGui.QWidget()
        self.sidebar = QtGui.QVBoxLayout(self.dockWidgetContent)
        self.sidebar.addLayout(sd_data)
        self.sidebar.addWidget(self.HLine())
        self.sidebar.addLayout(sd_instr_status)
        self.sidebar.addWidget(self.HLine())
        self.sidebar.addWidget(self.m_graph_freeze_cb)
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
        palette.setColor(palette.Window, QtGui.QColor(self.BACKGROUND_COLOR)) # Background
        palette.setColor(palette.WindowText, QtGui.QColor(self.FOREGROUND_COLOR)) # Foreground
        pg.setConfigOption('background', QtGui.QColor(self.BACKGROUND_COLOR))
        pg.setConfigOption('foreground', QtGui.QColor(self.FOREGROUND_COLOR))
        self.setPalette(palette)

        # Button style is os dependend (can force with some CSS)
        self.setFont(QtGui.QFont(self.FONT_FAMILY))

        # Set figure with pyqtgraph
        axis = DateAxis(orientation='bottom')
        if __debug__:
            self.m_pw = pg.PlotWidget(axisItems={'bottom': axis})
        else:
            self.m_pw = pg.PlotWidget(axisItems={'bottom': axis},
                                      enableMenu=False)
        self.m_plot = self.m_pw.plotItem
        self.m_curves = []
        n = sum([len(instr_val.variable_displayed) for instr_val in self.m_app.m_instruments.values()])
        i = 0
        for instr_key, instr_val in self.m_app.m_instruments.items():
            for var_index in range(len(instr_val.variable_displayed)):
                # Init Curve Item
                c = pg.PlotCurveItem(pen=(i, n))  # TODO: Option to force color from configuration file
                # Change Color of Value Displayed
                self.m_var_display[instr_key][var_index].setStyleSheet(
                    'color: ' + c.opts['pen'].color().name())
                # Add item to plot
                self.m_plot.addItem(c)
                # Keep track of item
                # might want to use self.m_plot.listDataItems() instead
                self.m_curves.append(c)
                # Increment to change color
                i += 1
        # self.m_plot.setLabel('bottom', 'Time' , units='s')
        self.m_plot.setLabel('left', 'Signal')  # Update units depending on instrument  #, units='Counts'
        # self.m_plot.setYRange(0, 5)
        # self.m_plot.setXRange(0, 100)
        self.m_plot.setLimits(minYRange=0, maxYRange=4500)  # In version 0.9.9
        self.m_plot.setMouseEnabled(x=False, y=True)
        self.m_plot.showGrid(x=False, y=True)
        self.m_plot.enableAutoRange(x=True, y=True)
        self.m_plot.getAxis('left').enableAutoSIPrefix(False)

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
        self.m_refresh_worker = Worker()
        self.m_refresh_worker.moveToThread(self.m_refresh_thread)
        self.m_refresh_worker.refresh.connect(self.RefreshAll)
        self.m_refresh_worker.finished.connect(self.m_refresh_thread.quit)
        self.m_refresh_thread.started.connect(self.m_refresh_worker.RefreshPing)
        self.m_refresh_worker.m_active = True
        self.m_refresh_thread.start()

    def InstrumentUpdate(self, instrument_key, data=None, timestamp=None):
        # Update Sidebar variables
        if data:
            # Keep only variables to display in main GUI
            data = [data[i] for i in self.m_app.m_instruments[instrument_key].variable_displayed]
            for var_index, var_val in enumerate(data):
                if isinstance(var_val, int):
                    if var_val < 100000:
                        self.m_var_display[instrument_key][var_index].setText(str(var_val))
                    else:
                        self.m_var_display[instrument_key][var_index].setText('%.2E' % var_val)
                elif isinstance(var_val, float):
                    if var_val < 10000:
                        self.m_var_display[instrument_key][var_index].setText('%.2f' % var_val)
                    else:
                        self.m_var_display[instrument_key][var_index].setText('%.2E' % var_val)
                elif var_val is None:
                    self.m_var_display[instrument_key][var_index].setText('NaN')
                elif isinstance(var_val, str):
                    self.m_var_display[instrument_key][var_index].setText(var_val[:6])
        # self.dockWidgetContent.update()
        # Update Sidebar packet counts
        self.m_instr_pckt_rcvd[instrument_key].setText(str(self.m_app.m_instruments[instrument_key].packet_received))
        self.m_instr_pckt_mssd[instrument_key].setText(str(self.m_app.m_instruments[instrument_key].packet_corrupted))
        self.m_instr_pckt_lggd[instrument_key].setText(str(self.m_app.m_instruments[instrument_key].packet_logged))
        self.dockWidgetContent.update()
        # Update Plot
        if data and timestamp:
            self._buffer_timestamp[instrument_key].extend(timestamp)
            for i, v in enumerate(data):
                self._buffer_data[instrument_key][i].extend(v)
            self.SetPlot()
            # TODO Check if multiple instruments can only update the variables of one instrument at a time
            # TODO Add safety to prevent refresh rate greater than 30 Hz

    # Set plot (pyQtGraph)
    def SetPlot(self):
        # Skip Plot Update if Freeze Figure activated
        if self.m_graph_freeze_cb.isChecked():
            return
        # Update position with time
        i = 0
        for instr_key, instr_val in self.m_app.m_instruments.items():
            timestamp = self._buffer_timestamp[instr_key].get(self.m_app.m_cfg.m_app['gui_buffer_length'])
            for var_index in range(len(instr_val.variable_displayed)):
                data = self._buffer_data[instr_key][var_index].get(self.m_app.m_cfg.m_app['gui_buffer_length'])
                sel = ~np.isnan(data)
                self.m_curves[i].setData(timestamp[sel], data[sel], connect="finite")
                i += 1
        self.m_plot.enableAutoRange(x=True)  # Needed as soon as mouth is used

    def ActInstrConnect(self, instrument_key=None):
        # Get instrument to connect
        if instrument_key == None or instrument_key == False:
            list_instr = list(self.m_app.m_instruments.keys())
            instrument_key, ok = QtGui.QInputDialog.getItem(self, 'Connect instrument',
                                                       'Select instrument',
                                                       list_instr)
            if not ok:
                self.m_statusBar.setText('Cancel instrument connection')
                return
        else:
            instrument_key = instrument_key

        if self.m_app.m_instruments[instrument_key].require_port:
            ports_list = list_serial_comports()
            ports_list_name = [str(p.device) + ' - ' + str(p.product) for p in ports_list]
            # Instrument need a port address to connect
            selected_port, ok = QtGui.QInputDialog.getItem(self, 'Connect Instrument',
                                                  'Connecting ' + instrument_key + '\nSelect port', ports_list_name)
            port = ports_list[ports_list_name.index(selected_port)].device
            if ok:
                try:
                    self.m_app.m_instruments[instrument_key].open(port)
                    self.m_statusBar.setText(instrument_key + ' is connected to ' + port)
                except SerialException as e:
                    QtGui.QMessageBox.warning(self, "Connect " + instrument_key,
                                              'ERROR: Failed connecting ' + instrument_key + ' to ' + port + '\n' + str(e),
                                              QtGui.QMessageBox.Ok)
                    # self.m_statusBar.setText('ERROR: Failed connecting ' + instr_key + ' to ' + port + '\n' + str(e))
        else:
            # Instrument do not need anything to connect
            try:
                self.m_app.m_instruments[instrument_key].open()
                self.m_statusBar.setText(instrument_key + ' is connected')
            except ValueError as e:
                QtGui.QMessageBox.warning(self, "Connect " + instrument_key,
                                          'ERROR: Failed connecting ' + instrument_key + '\n' + str(e),
                                          QtGui.QMessageBox.Ok)
                # self.m_statusBar.setText('ERROR: Failed connecting ' + instr_key + '\n' + str(e))
        # Set instrument status
        self.SetInstrumentsStatus()

    def ActInstrClose(self, instrument_key=None):
        # Get instrument to disconnect
        if instrument_key is None or instrument_key == False:
            instrument_key, ok = QtGui.QInputDialog.getItem(self, 'Disconnect instrument',
                                               'Select instrument', self.m_app.m_instruments.keys())
            if not ok:
                self.m_statusBar.setText('Cancel instrument disconnection')
                return
        else:
            instrument_key = instrument_key

        # Disconnect instrument
        if self.m_app.m_instruments[instrument_key].alive:
            self.m_app.m_instruments[instrument_key].close()
            self.m_statusBar.setText('Closed connection with ' + instrument_key)
        else:
            QtGui.QMessageBox.warning(self, "Disconnect " + instrument_key,
                                      'ERROR: Failed disconnecting ' + instrument_key + ': instrument not connected.',
                                      QtGui.QMessageBox.Ok)

        # Update display
        self.SetInstrumentsStatus()

    def ActInstrLog(self, instrument_key=None):
        # Start/Stop logging specific instrument
        if instrument_key is None or instrument_key == False:
            instrument_key, ok = QtGui.QInputDialog.getItem(self, 'Start/Stop logging instrument',
                                                       'Select instrument', self.m_app.m_instruments.keys())
            if not ok:
                self.m_statusBar.setText('Cancel Start/Stop logging instrument')
                return
        else:
            instrument_key = instrument_key

        # Check current status of instrument and switch to the opposite
        if self.m_app.m_instruments[instrument_key].alive:
            if self.m_app.m_instruments[instrument_key].log_status():
                self.m_app.m_instruments[instrument_key].log_stop()
                self.m_statusBar.setText('Stopped logging ' + instrument_key)
            else:
                self.m_app.m_instruments[instrument_key].log_start()
                self.m_statusBar.setText('Started logging ' + instrument_key)
        else:
            QtGui.QMessageBox.warning(self, "Log " + instrument_key,
                                      'ERROR: Failed start/stop logging ' + instrument_key +
                                      ': instrument not connected.',
                                      QtGui.QMessageBox.Ok)
        self.SetInstrumentsStatus()

    # Set instruments display
    def SetClock(self):
        zulu = gmtime(time())
        self.m_time_display.setText(strftime('%H:%M:%S', zulu))
        self.m_date_display.setText(strftime('%Y/%m/%d', zulu))
        self.dockWidgetContent.update()


    def SetInstrumentsStatus(self, instrument_key=None):
        if instrument_key is None:
            instrument_keys = self.m_app.m_instruments.keys()
        else:
            instrument_keys = [instrument_key]
        for instr_key in instrument_keys:
            instr_value = self.m_app.m_instruments[instr_key]
            if instr_value.alive:
                self.m_instr_connect_btn[instr_key].hide()
                self.m_instr_close_btn[instr_key].show()
                self.m_instr_log_btn[instr_key].show()
                if instr_value.log_status():
                    self.m_instr_status[instr_key].setText('logging')
                    self.m_instr_status[instr_key].setStyleSheet('color: #9ce22e')  # Green: #12ab29 (darker) #29ce42 (lighter) #9ce22e (pyQtGraph)
                    # self.m_instr_log_btn[instr_key].setEnabled(False)
                    self.m_instr_log_btn[instr_key].setToolTip('Stop logging data from ' + instr_key)
                else:
                    self.m_instr_status[instr_key].setText('active')
                    self.m_instr_status[instr_key].setStyleSheet('color: #ff9e17')  # Orange: #ffc12f (lighter)
                    # self.m_instr_log_btn[instr_key].setEnabled(True)
                    self.m_instr_log_btn[instr_key].setToolTip('Start logging data from ' + instr_key)
            else:
                self.m_instr_connect_btn[instr_key].show()
                self.m_instr_close_btn[instr_key].hide()
                self.m_instr_log_btn[instr_key].hide()
                self.m_instr_status[instr_key].setText('off')
                self.m_instr_status[instr_key].setStyleSheet('color: #f92670')  # Red: #e0463e (darker) #5cd9ef (lighter)  #f92670 (pyQtGraph)
        self.dockWidgetContent.update()

    # Action Log
    def ActInstrList(self, line):
        foo = ''
        for instr_val in self.m_app.m_instruments.values():
            foo += '    ' + str(instr_val) + '\n'
        reply = QtGui.QMessageBox.information(self, 'Instrument list',
                                              'List of instruments:\n' + foo)

    def ActLogPrefix(self):
        prefix, ok = QtGui.QInputDialog.getText(self, 'Set filename prefix',
                                                'New header:')
        if ok:
            for instr in self.m_app.m_instruments.values():
                instr.log_set_filename_prefix(prefix)
            self.m_statusBar.setText('Set filename prefix to ' + prefix)
        else:
            self.m_statusBar.setText('Cancel filename prefix update')

    def ActLogPath(self):
        path = QtGui.QFileDialog.getExistingDirectory(self, 'Select directory',
                    self.m_app.m_instruments[list(self.m_app.m_instruments.keys())[0]].log_get_path())

        if path == '':
            self.m_statusBar.setText('Cancel change log path')
        else:
            for instr in self.m_app.m_instruments.values():
                instr.log_set_path(path)
            self.m_statusBar.setText('Set log path to ' + path)

    # TODO Specific to each instrument now
    # def SetLogFileVal(self):
    #     if (self.m_app.m_log_data.m_file_name is not None and
    #             self.m_app.m_log_data.m_active_log):
    #         foo = os.path.join(self.m_app.m_log_data.m_file_path,
    #                            self.m_app.m_log_data.m_file_name)
    #     else:
    #         foo = os.path.join(self.m_app.m_log_data.m_file_path,
    #                            self.m_app.m_log_data.m_file_header) \
    #             + '_yyyymmdd_HHMMSS.csv'
    #     self.m_sd_log_fname_val.setText('...' + foo[-30:])
    #     self.m_sd_log_fname_val.repaint()

    # Action Help
    def ActHelpHelp(self):
        msg = QtGui.QMessageBox()
        msg.setIcon(QtGui.QMessageBox.Question)
        msg.setText("Inlinino Help")
        msg.setInformativeText('Inlinino is a simple data logger.\n' +
                               'To start logging data:\n' +
                               '   1. connect an instrument (Instrument>' +
                               'Connect)\n' +
                               '   2. start the logger (Log>Start)\n' +
                               'To stop logging data:\n' +
                               '   + stop the logger (Log>Stop)\n' +
                               '   + exit application (will stop logging to)' +
                               '\nMore details at: github.com/OceanOptics/' +
                               'Inlinino')
        msg.setWindowTitle('Help')
        msg.exec_()

    def ActHelpSupport(self):
        msg = QtGui.QMessageBox()
        msg.setIcon(QtGui.QMessageBox.Question)
        msg.setText('Inlinino Support')
        msg.setInformativeText('Send questions, bug reports, fixes, ' +
                               'enhancements, t-shirts, ' +
                               'money, lobsters & beers to Nils\n' +
                               '<nils.haentjens+inlinino@maine.edu>')
        msg.setWindowTitle('Support')
        msg.exec_()

    def ActHelpCredits(self):
        msg = QtGui.QMessageBox()
        msg.setIcon(QtGui.QMessageBox.Information)
        msg.setText('Inlinino Credits')
        msg.setInformativeText('Developped by Nils Haëntjens (University of ' +
                               'Maine)\nGNU GENERAL PUBLIC LICENSE\nVersion ' +
                               '3, 29 June 2007')
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
        name.setFont(QtGui.QFont(self.FONT_FAMILY, 10))
        name.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignBottom)
        value = QtGui.QLabel(str(_value))
        value.setFont(QtGui.QFont(self.FONT_FAMILY, 12))
        value.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        unit = QtGui.QLabel(_unit)
        unit.setFont(QtGui.QFont(self.FONT_FAMILY, 10))
        unit.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignTop)

        widget = QtGui.QWidget()
        group = QtGui.QVBoxLayout(widget)
        group.setSpacing(0)
        group.setContentsMargins(0, 0, 0, 0)
        group.addWidget(name)
        group.addWidget(value)
        group.addWidget(unit)

        return widget, value, unit

    def QInstrDisplay(self, _name, _alive, _logging, _pckt_received, _pckt_missed, _pckt_logged):
        name = QtGui.QLabel(_name)
        # name.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        status_lbl1 = QtGui.QLabel(' [')
        status_lbl2 = QtGui.QLabel('] : ')
        if _alive:
            if _logging:
                status_val = QtGui.QLabel('logging')
                status_val.setStyleSheet('color: #9ce22e')  # Green: #12ab29 (darker) #29ce42 (lighter) #9ce22e (pyQtGraph)
            else:
                status_val = QtGui.QLabel('active')
                status_val.setStyleSheet('color: #ff9e17')  # Orange: #ffc12f (lighter)
        else:
            status_val = QtGui.QLabel('off')
            status_val.setStyleSheet('color: #f92670')  # Red: #e0463e (darker) #5cd9ef (lighter)  #f92670 (pyQtGraph)
        connect_btn = QtGui.QPushButton()
        connect_btn.setIcon(connect_btn.style().standardIcon(QtWidgets.QStyle.SP_MediaPlay))
        connect_btn.setToolTip('Connect ' + _name)
        close_btn = QtGui.QPushButton()
        close_btn.setIcon(close_btn.style().standardIcon(QtWidgets.QStyle.SP_MediaStop))
        close_btn.setToolTip('Disconnect ' + _name)
        log_btn = QtGui.QPushButton()
        log_btn.setIcon(log_btn.style().standardIcon(QtWidgets.QStyle.SP_DriveFDIcon))
        log_btn.setToolTip('Start logging data from' + _name)
        log_btn.setCheckable(True)
        pckt_received_lbl = QtGui.QLabel('  pckt received: ')
        pckt_received_val = QtGui.QLabel(str(_pckt_received))
        pckt_missed_lbl = QtGui.QLabel('  pckt corrupted: ')
        pckt_missed_val = QtGui.QLabel(str(_pckt_missed))
        pckt_logged_lbl = QtGui.QLabel('  pckt logged: ')
        pckt_logged_val = QtGui.QLabel(str(_pckt_logged))

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
        header.addWidget(log_btn)
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
        pckt_logged = QtGui.QHBoxLayout()
        pckt_logged.addWidget(pckt_logged_lbl)
        pckt_logged.addWidget(pckt_logged_val)
        group.addLayout(pckt_logged)

        return widget, status_val, pckt_received_val, pckt_missed_val, pckt_logged_val,\
               connect_btn, close_btn, log_btn

    def RefreshAll(self):
        self.SetClock()
        self.SetInstrumentsStatus()


# Thread and Workers to refresh data
# From Matthew Levine on http://stackoverflow.com/questions/6783194
class Worker(QtCore.QObject):
    refresh = QtCore.pyqtSignal()
    finished = QtCore.pyqtSignal()

    def __init__(self, _parent=None):
        QtCore.QObject.__init__(self, _parent)
        self.m_active = True
        self.m_timeout = 0.5

    def __del__(self):
        self.m_active = False
        if __debug__:
            print('Closing Qtworker')

    @QtCore.pyqtSlot()
    def RefreshPing(self):
        start_time = time()
        while self.m_active:
            try:
                sleep(self.m_timeout) # TODO Replace by python scheduler
                # sleep(self.m_timeout - (time() - start_time) % self.m_timeout)
                self.refresh.emit()
                start_time = time()
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


class DateAxis(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        pg.AxisItem.__init__(self, *args, **kwargs)

    def tickStrings(self, values, scale, spacing):
        strns = []
        if values:
            rng = max(values) - min(values)
            # if rng < 120:
            #    return pg.AxisItem.tickStrings(self, values, scale, spacing)
            if rng < 3600 * 24:
                string = '%H:%M:%S'
                label1 = '%b %d - '
                label2 = '%d, %Y'
            elif rng >= 3600 * 24 and rng < 3600 * 24 * 30:
                string = '%d'
                label1 = '%b - '
                label2 = '%b,  %Y'
            elif rng >= 3600 * 24 * 30 and rng < 3600 * 24 * 30 * 24:
                string = '%b'
                label1 = '%Y -'
                label2 = ' %Y'
            elif rng >= 3600 * 24 * 30 * 24:
                string = '%Y'
                label1 = ''
                label2 = ''
            for x in values:
                try:
                    strns.append(strftime(string, gmtime(x)))
                except ValueError:  # Windows can't handle dates before 1970
                    strns.append('')
            # try:
            #     label = strftime(label1, gmtime(min(values))) + \
            #             strftime(label2, gmtime(max(values)))
            # except ValueError:
            #     label = ''
            # self.setLabel(text=label)
            return strns
        else:
            return []

if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    main_ui = GUI(None)
    sys.exit(app.exec_())
