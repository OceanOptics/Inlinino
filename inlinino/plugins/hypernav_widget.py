import os.path
from time import time, sleep

import numpy as np
from pyqtgraph.Qt import QtCore, QtGui

from inlinino.instruments.hypernav import HyperNav
from inlinino.instruments.satlantic import SatPacket
from inlinino.plugins import GenericPlugin
from inlinino.plugins.hypernav_sensor_calibration import compute_dark_stats, compute_light_stats, grade_dark_frames, grade_light_frames

UPASS = u'\u2705'
UFAIL = u'\u274C'


class HyperNavCalPlugin(GenericPlugin):
    BUFFER_LENGTH = 120
    HN_PARAMETERS = [
        'SENSTYPE','SENSVERS','SERIALNO','PWRSVISR','USBSWTCH','SPCSBDSN','SPCPRTSN','FRMSBDSN','FRMPRTSN',
        'ACCMNTNG','ACCVERTX','ACCVERTY','ACCVERTZ','MAG_MINX','MAG_MAXX','MAG_MINY','MAG_MAXY','MAG_MINZ','MAG_MAXZ',
        'GPS_LATI','GPS_LONG','MAGDECLI','DIGIQZSN','DIGIQZU0','DIGIQZY1','DIGIQZY2','DIGIQZY3',
        'DIGIQZC1','DIGIQZC2','DIGIQZC3','DIGIQZD1','DIGIQZD2','DIGIQZT1','DIGIQZT2','DIGIQZT3','DIGIQZT4','DIGIQZT5',
        'DQTEMPDV','DQPRESDV','SIMDEPTH','SIMASCNT','PUPPIVAL','PUPPSTRT','PMIDIVAL','PMIDSTRT','PLOWIVAL','PLOWSTRT',
        'STUPSTUS','MSGLEVEL','MSGFSIZE','DATFSIZE','OUTFRSUB','LOGFRAMS','ACQCOUNT','CNTCOUNT','DATAMODE'
    ]

    def __init__(self, instrument: HyperNav):
        # Plugin variables (init before super() due to setup)
        self.lu = {}
        self.characterized_head_sn = None
        self.time_last_tx = 0
        super().__init__(instrument)
        # Connect signals (must be after super() as required ui to be loaded)
        self.instrument.signal.warning.connect(self.warning_message_box)
        self.instrument.signal.cfg_update.connect(self.update_set_cfg_value)
        self.instrument.signal.cfg_update.connect(self.update_set_head_value)
        # Control
        self.instrument.signal.toggle_command_mode.connect(self.toggle_control)
        self.ctrl_get_cfg.clicked.connect(self.get_cfg)
        self.ctrl_set_cfg.clicked.connect(self.set_cfg)
        self.ctrl_set_parameter.currentTextChanged.connect(self.update_set_cfg_value)
        self.ctrl_set_head.currentTextChanged.connect(self.set_head)
        self.ctrl_start.clicked.connect(self.start)
        self.ctrl_stop.clicked.connect(self.stop)
        self.ctrl_cal.clicked.connect(self.cal)
        # Characterize
        self.crt_characterized_head.currentTextChanged.connect(self.set_head_to_characterize)
        self.instrument.signal.new_frame.connect(self.characterize)
        # Serial Monitor
        self.instrument.interface_signal.read.connect(self.update_serial_console)
        self.instrument.interface_signal.write.connect(self.update_serial_console)
        self.serial_monitor_command.returnPressed.connect(self.send_command)
        self.serial_monitor_send.clicked.connect(self.send_command)
        self.serial_monitor_console.setMaximumBlockCount(80)  # Maximum number of lines in console

    def show(self):
        self.group_box_instrument_control.show()
        super().show()

    def hide(self):
        self.group_box_instrument_control.hide()
        super().hide()

    def setup(self):
        self.clear()
        # Control
        for param in self.HN_PARAMETERS:
            self.ctrl_set_parameter.addItem(param)
        self.toggle_control(False)  # TODO Should be toggled when instrument is open or closed
        # Characterize
        self.set_head_to_characterize(self.crt_characterized_head.currentText())

    def clear(self):
        # Characterize
        self.lu = {}
        self.clear_characterize()
        # Serial Monitor
        self.serial_monitor_console.clear()

    @QtCore.pyqtSlot(str)
    def warning_message_box(self, message):
        QtGui.QMessageBox.warning(self, "Inlinino: HyperNavCal", message, QtGui.QMessageBox.Ok)

    """
    Control
    """
    @QtCore.pyqtSlot(bool)
    def toggle_control(self, enable):
        self.ctrl_get_cfg.setEnabled(enable)
        self.ctrl_set_cfg.setEnabled(enable)
        self.ctrl_set_parameter.setEnabled(enable)
        self.ctrl_set_value.setEnabled(enable)
        self.ctrl_set_head.setEnabled(enable)
        self.ctrl_start.setEnabled(enable)
        self.ctrl_int_time.setEnabled(enable)
        self.ctrl_light_dark_ratio.setEnabled(enable)
        self.ctrl_cal.setEnabled(enable)
        self.instrument.command_mode = enable

    def tx(self, cmd: str, check_timing=True):
        """
        Append terminator, encode, and send command
        :param cmd:
        :return:
        """
        if not self.instrument.alive:
            self.warning_message_box('Instrument must be connected before sending commands.')
            return False
        if check_timing and time() - self.time_last_tx < 0.5:
            self.warning_message_box('Wait at least one second between command transmission.')
            return False
        self.instrument.interface_write(f'{cmd}\r\n'.encode('utf8', errors='replace'))
        self.time_last_tx = time()
        return True

    def get_cfg(self):
        self.tx('get cfg')

    def set_cfg(self):
        parameter = self.ctrl_set_parameter.currentText()
        value = self.ctrl_set_value.text()
        self.tx(f'set {parameter} {value}')

    @QtCore.pyqtSlot(str)
    def update_set_cfg_value(self, parameter):
        if parameter == '*':
            parameter = self.ctrl_set_parameter.currentText()
        elif parameter != self.ctrl_set_parameter.currentText():
            return
        if parameter in self.instrument.local_cfg_keys():
            self.ctrl_set_value.setText(f'{self.instrument.get_local_cfg(parameter)}')
        else:
            self.ctrl_set_value.setText('')

    @QtCore.pyqtSlot(str)
    def update_set_head_value(self, parameter):
        if parameter not in ['*', 'FRMPRTSN', 'FRMSBDSN']:
            return
        update = ''
        keys = self.instrument.local_cfg_keys()
        if 'FRMPRTSN' in keys and self.instrument.get_local_cfg('FRMPRTSN') == 0:
            if self.ctrl_set_head.currentText() != 'SBD':
                update = 'SBD'
        elif 'FRMSBDSN' in keys and self.instrument.get_local_cfg('FRMSBDSN') == 0:
            if self.ctrl_set_head.currentText() != 'PRT':
                update = 'PRT'
        else:
            if self.ctrl_set_head.currentText() != 'BOTH':
                update = 'BOTH'
        if update:
            self.ctrl_set_head.blockSignals(True)  # Prevent triggering set_head
            self.ctrl_set_head.setCurrentText(update)
            self.ctrl_set_head.blockSignals(False)

    def set_head(self, head):
        if head == 'BOTH':
            if not self.tx(f'set FRMPRTSN {self.instrument.prt_sbs_sn}', check_timing=False):
                return
            sleep(0.1)
            if not self.tx(f'set FRMSBDSN {self.instrument.sbd_sbs_sn}', check_timing=False):
                return
        elif head == 'PRT':
            if not self.tx(f'set FRMPRTSN {self.instrument.prt_sbs_sn}', check_timing=False):
                return
            sleep(0.1)
            if not self.tx(f'set FRMSBDSN 0', check_timing=False):
                return
        elif head == 'SBD':
            if not self.tx(f'set FRMPRTSN 0', check_timing=False):
                return
            sleep(0.1)
            if not self.tx(f'set FRMSBDSN {self.instrument.sbd_sbs_sn}', check_timing=False):
                return
        sleep(0.1)
        self.warning_message_box('Power cycle HyperNav to complete change in spectrometer sampling.')

    def start(self):
        self.tx('start')

    def stop(self):
        self.tx('stop')

    def cal(self):
        self.tx(f'cal {self.ctrl_int_time.currentText()},{self.ctrl_light_dark_ratio.value()}')

    """
    Characterize
    """
    def set_head_to_characterize(self, head):
        self.characterized_head_sn = self.instrument.get_head_sbs_sn(head)
        if self.instrument.px_reg_path[head]:
            self.crt_pix_reg.setText(os.path.basename(self.instrument.px_reg_path[head]))
        else:
            self.crt_pix_reg.setText('pixel number')
        self.clear_characterize()  # Empty UI

    @QtCore.pyqtSlot(object)
    def characterize(self, data: SatPacket):
        # Update buffer
        if data.frame_header not in self.lu.keys():
            self.lu[data.frame_header] = np.empty((self.BUFFER_LENGTH, 2048), dtype=np.float32)
            self.lu[data.frame_header][:] = np.NaN
        self.lu[data.frame_header] = np.roll(self.lu[data.frame_header], -1, axis=0)
        idx_start, idx_end = self.instrument._parser_core_idx_limits[data.frame_header]
        self.lu[data.frame_header][-1, :] = data.frame[idx_start:idx_end]
        # Get side to analyze
        if int(data.frame_header[-4:]) != self.characterized_head_sn:
            # Only analyze relevant side
            return
        # Update integration time
        idx_inttime = 4
        self.crt_int_time.setText(f'{data.frame[idx_inttime]}')
        # Get number of observations
        n_obs = np.sum(np.any(~np.isnan(self.lu[data.frame_header]), axis=1))
        # Update Dark
        if data.frame_header[4] == 'D':
            stats = compute_dark_stats(self.lu[data.frame_header])
            test = grade_dark_frames(stats)
            self.dark_tests.setTitle(f'Dark Tests (n={n_obs})')
            self.dt_spec_shape_value.setText(f'{stats.spectral_shape:.1f}')
            self.dt_spec_shape_test.setText(UPASS if test.spectral_shape else UFAIL)
            self.dt_mean_value.setText(f'{stats.mean_value:.1f}')
            self.dt_mean_test.setText(UPASS if test.mean_value else UFAIL)
            self.dt_noise_level_value.setText(f'{stats.noise_level:.1f}')
            self.dt_noise_level_test.setText(UPASS if test.noise_level else UFAIL)
        # Update Light
        if data.frame_header[4] == 'L':
            stats = compute_light_stats(self.lu[data.frame_header])
            test = grade_light_frames(stats)
            self.light_tests.setTitle(f'Light Tests (n={n_obs})')
            self.lt_px_reg_offset.setText(f'{stats.pixel_registration:.2f}')
            self.lt_px_reg_test.setText(UPASS if test.pixel_registration else UFAIL)
            self.lt_peak_value.setText(f'{stats.peak_value:.0f}')
            self.lt_peak_test.setText(UPASS if test.peak_value else UFAIL)

    def clear_characterize(self):
        self.dt_spec_shape_value.setText('')
        self.dt_spec_shape_test.setText('')
        self.dt_mean_value.setText('')
        self.dt_mean_test.setText('')
        self.dt_noise_level_value.setText('')
        self.dt_noise_level_test.setText('')
        self.lt_px_reg_offset.setText('')
        self.lt_px_reg_test.setText('')
        self.lt_peak_value.setText('')
        self.lt_peak_test.setText('')
        self.dark_tests.setTitle(f'Dark Tests')
        self.light_tests.setTitle(f'Light Tests')


    """
    Serial Monitor
    """
    @QtCore.pyqtSlot(bytes)
    def update_serial_console(self, data: bytes):
        data.replace(b'\r', b'')  # Use only \n otherwise create extra line
        self.serial_monitor_console.moveCursor(QtGui.QTextCursor.End)
        self.serial_monitor_console.insertPlainText(data.decode('utf8', errors='replace'))
        self.serial_monitor_console.moveCursor(QtGui.QTextCursor.StartOfLine)

    def send_command(self):
        cmd = self.serial_monitor_command.text()
        if not cmd:
            self.warning_message_box('Command is empty.')
        else:
            self.tx(cmd)
            self.serial_monitor_command.setText('')
