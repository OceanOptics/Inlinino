import os.path

from pyqtgraph.Qt import QtCore, QtGui, QtWidgets, uic

from inlinino import PATH_TO_RESOURCES
from inlinino.shared.worker import Worker
from inlinino.instruments.hypernav import HyperNav
from inlinino.widgets import GenericDialog, classproperty

try:
    from hypernav.io import HyperNav as HyperNavIO
    from hypernav.calibrate import calibrate_legacy, calibrate
except ModuleNotFoundError:
    HyperNavIO = None


class HyperNavCalibrateDialog(GenericDialog, Worker):
    @classproperty
    def __snake_name__(cls) -> str:
        return 'hypernav_calibrate_dialog'

    def __init__(self, parent, instrument: HyperNav):
        self.instrument = instrument
        super().__init__(parent=parent, fun=calibrate, signal=instrument.signal.warning)

        self.browse_datafile_button.clicked.connect(self.browse_datafile)
        self.browse_lamp_button.clicked.connect(self.browse_lamp_file)
        self.browse_plaque_button.clicked.connect(self.browse_plaque_file)
        self.browse_wavelength_button.clicked.connect(self.browse_wavelength_file)
        self.browse_history_cal_button.clicked.connect(self.browse_history_cal_dir)

        self.cb_head_side.currentTextChanged.connect(self.set_head)
        self.set_head(self.cb_head_side.currentText())

        self.le_hypernav_sn.setText(self.instrument.serial_number)

    @QtCore.pyqtSlot()
    def browse_datafile(self):
        file_name, _ = QtGui.QFileDialog.getOpenFileName(self,
                                                         caption='Choose HyperNav data file',
                                                         filter='Device File (*.raw *.txt)')
        self.le_log_file.setText(file_name)

    @QtCore.pyqtSlot()
    def browse_lamp_file(self):
        file_name, _ = QtGui.QFileDialog.getOpenFileName(self,
            caption='Choose FEL lamp file', filter='Device File (*.dat *.FIT)')
        self.le_lamp_path.setText(file_name)

    @QtCore.pyqtSlot()
    def browse_plaque_file(self):
        file_name, _ = QtGui.QFileDialog.getOpenFileName(self,
            caption='Choose reflectance plaque file', filter='Device File (*.dat *.FIT)')
        self.le_plaque_path.setText(file_name)

    @QtCore.pyqtSlot()
    def browse_wavelength_file(self):
        file_name, _ = QtGui.QFileDialog.getOpenFileName(self,
            caption='Choose wavelength registration file', filter='Device File (*.cgs *.txt)')
        self.le_wavelength_path.setText(file_name)
        try:
            name = os.path.splitext(os.path.basename(file_name))[0].strip()
            try:
                spec_sn = int(name)  # ex: 117886.cgs
            except:
                spec_sn = int(name.split('_')[2][2:])  # ex: HNAV-55_stbrd_R-117886_20210408T185635Zfake_Wavelengths.cgs
            self.le_spec_sn.setText(str(spec_sn))
        except:
            pass

    @QtCore.pyqtSlot()
    def browse_history_cal_dir(self):
        self.le_history_cal_path.setText(QtGui.QFileDialog.getExistingDirectory(
            caption='Choose historical calibration directory'))

    @QtCore.pyqtSlot(str)
    def set_head(self, head):
        self.le_head_sn.setText(str(self.instrument.get_head_sbs_sn(head)))

    @QtCore.pyqtSlot()
    def start(self):
        if not self.check_fields_passed(ignore=['le_history_cal_path']):
            return
        self.disable_run_button()

        if self.cb_software.currentText() == 'legacy':
            # Execute legacy function
            try:
                # Calls external executable so no need for Thread
                calibrate_legacy(
                    self.instrument.log_path,
                    self.le_log_file.text(),
                    self.le_lamp_path.text(),
                    self.le_plaque_path.text(),
                    self.le_wavelength_path.text(),
                    int(self.le_hypernav_sn.text()),
                    self.cb_head_side.currentText(),
                    int(self.le_head_sn.text()),
                    int(self.le_spec_sn.text()),
                    self.lamp_to_plaque_distance.value(),
                    self.lamp_calibration_distance.value(),
                    'show+pdf',
                    self.le_history_cal_path.text()
                )
            except SystemError as e:
                self.instrument.signal.warning[str, str, str].emit(f"Error running 'legacy' calibration.",
                                                                   str(e), 'error')
            except Exception as e:
                self.instrument.signal.warning[str, str, str].emit(f"Error while analyzing '{os.path.basename(self.le_log_file.text())}'."
                                                                   , str(e), 'error')
            self.enable_run_button()
        elif self.cb_software.currentText() == 'python':
            # Execute Python Code
            super().start(
                os.path.basename(self.le_log_file.text()),
                self.instrument.log_path,
                self.le_log_file.text(),
                self.le_lamp_path.text(),
                self.le_plaque_path.text(),
                self.le_wavelength_path.text(),
                int(self.le_hypernav_sn.text()),
                self.cb_head_side.currentText(),
                int(self.le_head_sn.text()),
                int(self.le_spec_sn.text()),
                self.le_operator.text(),
                self.lamp_to_plaque_distance.value(),
                self.lamp_calibration_distance.value(),
                'show+pdf',
                self.le_history_cal_path.text()
            )
        else:
            self.instrument.signal.warning.emit(f'Calibration software `{self.cb_software}` not available.')
            self.enable_run_button()

    def join(self):
        super().join()
        self.enable_run_button()
