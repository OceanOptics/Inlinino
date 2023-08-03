import os
from glob import glob

from pyqtgraph.Qt import QtCore, QtGui, QtWidgets, uic

from inlinino import PATH_TO_RESOURCES
from inlinino.shared.worker import Worker
from inlinino.instruments.hypernav import HyperNav
from inlinino.widgets import GenericWidget, classproperty
from inlinino.widgets.hypernav.calibrate_dialog import HyperNavCalibrateDialogWidget
try:
    from hypernav.calibrate import spec_board_report, register_wavelengths
    from hypernav.io import HyperNav as HyperNavIO
    from hypernav.viz import GRAPH_CFG
except ImportError:
    spec_board_report, register_wavelengths = None, None
    HyperNavIO = None
    GRAPH_CFG = None


class HyperNavAnalyzeWidget(GenericWidget):
    @classproperty
    def __snake_name__(cls) -> str:
        return 'hypernav_analyze_widget'

    def __init__(self, instrument: HyperNav):
        super().__init__(instrument)
        self.characterize = CharacterizeDM(instrument, self.enable_button)
        self.run_button.clicked.connect(self.analyze)
        self.instrument.signal.status_update.connect(self.update_filename_combobox)

    def setup(self):
        self.update_filename_combobox()

    @QtCore.pyqtSlot()
    def update_filename_combobox(self):
        self.filename_combobox.clear()
        file_list = [os.path.basename(f) for f in sorted(glob(os.path.join(
            self.instrument._log_raw.path, f'*.{self.instrument._log_raw.FILE_EXT}')))]
        self.filename_combobox.addItems(file_list)
        self.filename_combobox.setCurrentIndex(len(file_list)-1)

    @QtCore.pyqtSlot()
    def analyze(self):
        # Check button is enabled
        if not self.run_button.isEnabled():
            return
        # Check file to analyze is closed
        filename = self.filename_combobox.currentText()
        if self.instrument.log_active and filename == self.instrument.log_filename:
            self.instrument.signal.warning.emit('Stop logging to analyze data.')
            return
        # Start appropriate analysis
        self.disable_button()
        if self.rb_eval_spec_board.isChecked():
            self.disable_button('Processing ...')
            self.characterize.start(filename)
            # Enable button is set when threads join
        elif self.rb_wl_reg.isChecked():
            dialog = HyperNavWavelengthRegistrationDialogWidget(self, self.instrument, filename)
            dialog.exec()
            self.enable_button()
        elif self.rb_calibration.isChecked():
            dialog = HyperNavCalibrateDialogWidget(self, self.instrument, filename)
            dialog.exec()
            self.enable_button()

    def disable_button(self, text='Run'):
        self.run_button.setText(text)
        self.run_button.setEnabled(False)

    def enable_button(self):
        self.run_button.setText('Run')
        self.run_button.setEnabled(True)


class CharacterizeDM(Worker):
    def __init__(self, instrument: HyperNav, join_target=None):
        self.instrument = instrument
        self.join_target = join_target
        super().__init__(CharacterizeDM.run, instrument.signal.warning)

    @QtCore.pyqtSlot()
    def start(self, filename):
        if HyperNavIO is None:
            self.instrument.signal.warning.emit('Package `HyperNav` required.')
        super().start(
            filename,
            self.instrument.prt_sbs_sn, self.instrument.sbd_sbs_sn,
            self.instrument.log_path, filename, self.queue
        )

    @staticmethod
    def run(prt_sn, sbd_sn, path, filename, queue):
        data, meta = HyperNavIO.read_inlinino(os.path.join(path, filename))
        # Find HyperNav frame serial numbers
        analyzed_sn = set([int(k[6:]) for k in meta['valid_frames'].keys() if
                           True in [k.startswith(hdr) for hdr in ('SATYLZ', 'SATYDZ', 'SATXLZ', 'SATXDZ')]])
        warning_sn, reports_generated = [], []
        for sn in analyzed_sn:
            if sn not in (prt_sn, sbd_sn):
                warning_sn.append(sn)
            ref = os.path.splitext(filename)[0]
            report = spec_board_report(data, ref, sn)
            dpi = 96
            target_filename = os.path.join(path, f"{ref}_SBSSN{sn:04}.pdf")
            report.write_image(target_filename, width=dpi * 11, height=dpi * 8.5)
            report.show(config=GRAPH_CFG)
            reports_generated.append(target_filename)
        if warning_sn:
            queue.put(('warning', f"Unexpected head serial number(s) {', '.join([f'{sn:04d}' for sn in warning_sn])}. "
                                  f"Expected heads {prt_sn:04d} and {sbd_sn:04d}. "
                                  f"Nonetheless, report(s) were generated:\n" + '\n'.join(reports_generated)))
        else:
            return reports_generated

    def join(self):
        super().join()
        if self.join_target is not None:
            self.join_target()


class HyperNavWavelengthRegistrationDialogWidget(QtWidgets.QDialog, Worker):
    def __init__(self, parent, instrument: HyperNav, raw_filename: str):
        self.instrument = instrument
        ## Initialize QDialog(parent) and Worker(fun, signal)
        super().__init__(parent=parent, fun=register_wavelengths, signal=instrument.signal.warning)
        if parent.isActiveWindow():
            self.setWindowModality(QtCore.Qt.WindowModal)
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, "widget_hypernav_wl_reg_dialog.ui"), self)

        self.le_raw_filename.setText(raw_filename)

        self.run_button = self.button_box.addButton("Run", QtGui.QDialogButtonBox.ActionRole)
        self.run_button.clicked.connect(self.start)
        self.button_box.button(QtGui.QDialogButtonBox.Close).clicked.connect(self.accept)

        self.browse_wavelength_button.clicked.connect(self.browse_wavelength_file)

        self.cb_head_side.currentTextChanged.connect(self.set_head)
        self.set_head(self.cb_head_side.currentText())

        self.le_hypernav_sn.setText(self.instrument.serial_number)

    @QtCore.pyqtSlot()
    def browse_wavelength_file(self):
        file_name, _ = QtGui.QFileDialog.getOpenFileName(self,
                                                         caption='Choose wavelength registration file',
                                                         filter='Device File (*.cgs)')
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

    def start(self):
        for f in [f for f in self.__dict__.keys() if f.startswith('le_')]:
            if not getattr(self, f).text():
                self.instrument.signal.warning.emit('All fields must be field.')
                return
        # Disable button
        self.run_button.setText('Processing ...')
        self.run_button.setEnabled(False)
        # Start worker
        super().start(
            os.path.basename(self.le_raw_filename.text()),
            self.instrument.log_path,
            os.path.join(self.instrument.log_path, self.le_raw_filename.text()),
            self.le_wavelength_path.text(),
            int(self.le_hypernav_sn.text()),
            self.cb_head_side.currentText(),
            int(self.le_head_sn.text()),
            int(self.le_spec_sn.text()),
        )

    def join(self):
        super().join()
        self.run_button.setEnabled(True)
        self.run_button.setText('Run')
