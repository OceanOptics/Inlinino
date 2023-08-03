import os.path

from pyqtgraph.Qt import QtCore, QtGui, QtWidgets, uic

from inlinino import PATH_TO_RESOURCES, package_dir
from inlinino.shared.worker import Worker
from inlinino.instruments.hypernav import HyperNav



try:
    from hypernav.io import HyperNav as HyperNavIO
    from hypernav.calibrate import calibrate_legacy, calibrate
except ModuleNotFoundError:
    HyperNavIO = None


class HyperNavCalibrateDialogWidget(QtWidgets.QDialog, Worker):
    def __init__(self, parent, instrument: HyperNav, log_file_name: str):
        self.instrument = instrument
        super().__init__(parent=parent, fun=calibrate, signal=instrument.signal.warning)
        if parent.isActiveWindow():
            self.setWindowModality(QtCore.Qt.WindowModal)
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, "widget_hypernav_calibrate_dialog.ui"), self)

        self.le_log_file.setText(log_file_name)

        self.run_button = self.button_box.addButton("Run", QtGui.QDialogButtonBox.ActionRole)
        self.run_button.clicked.connect(self.start)
        self.button_box.button(QtGui.QDialogButtonBox.Close).clicked.connect(self.accept)

        self.browse_lamp_button.clicked.connect(self.browse_lamp_file)
        self.browse_plaque_button.clicked.connect(self.browse_plaque_file)
        self.browse_wavelength_button.clicked.connect(self.browse_wavelength_file)

        self.cb_head_side.currentTextChanged.connect(self.set_head)
        self.set_head(self.cb_head_side.currentText())

        self.le_hypernav_sn.setText(self.instrument.serial_number)

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

    @QtCore.pyqtSlot(str)
    def set_head(self, head):
        self.le_head_sn.setText(str(self.instrument.get_head_sbs_sn(head)))

    @QtCore.pyqtSlot()
    def start(self):
        for f in [f for f in self.__dict__.keys() if f.startswith('le_')]:
            if not getattr(self, f).text():
                self.instrument.signal.warning.emit('All fields must be field.')
                return
        # Disable button
        self.run_button.setText('Processing ...')
        self.run_button.setEnabled(False)

        if self.cb_software.currentText() == 'legacy':
            # Execute legacy function
            try:
                # Calls external executable so no need for Thread
                calibrate_legacy(
                    self.instrument.log_path,
                    os.path.join(self.instrument.log_path, self.le_log_file.text()),
                    self.le_lamp_path.text(),
                    self.le_plaque_path.text(),
                    self.le_wavelength_path.text(),
                    int(self.le_hypernav_sn.text()),
                    self.cb_head_side.currentText(),
                    self.le_head_sn.text(),
                    int(self.le_spec_sn.text()),
                    self.lamp_to_plaque_distance.value(),
                    self.lamp_calibration_distance.value(),
                    log_filename=os.path.join(package_dir, 'log', 'calibrate.log')
                )
            except SystemError as e:
                self.instrument.signal.warning[str, str, str].emit(f"Error running 'legacy' calibration.",
                                                                   str(e), 'error')
            except Exception as e:
                self.instrument.signal.warning[str, str, str].emit(f"Error while analyzing '{self.le_log_file.text()}'."
                                                                   , str(e), 'error')
            # Reset buttons
            self.run_button.setEnabled(True)
            self.run_button.setText('Run')
        elif self.cb_software.currentText() == 'python':
            # Execute Python Code
            super().start(
                self.le_log_file.text(),
                self.instrument.log_path,
                os.path.join(self.instrument.log_path, self.le_log_file.text()),
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
            )
        else:
            self.instrument.signal.warning.emit(f'Calibration software `{self.cb_software}` not available.')
            # Reset buttons
            self.run_button.setEnabled(True)
            self.run_button.setText('Run')

    def join(self):
        super().join()
        self.run_button.setEnabled(True)
        self.run_button.setText('Run')
