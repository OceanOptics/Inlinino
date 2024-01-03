import os

from pyqtgraph.Qt import QtCore, QtGui, uic

from inlinino.shared.worker import Worker
from inlinino.instruments.hypernav import HyperNav
from inlinino.widgets import GenericWidget, GenericDialog, classproperty
from inlinino.widgets.hypernav.calibrate_dialog import HyperNavCalibrateDialog
try:
    from hypernav.calibrate.reports import spec_board_report, write_report_to_pdf, calibration_history_report
    from hypernav.calibrate import register_wavelengths
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
        self.run_button.clicked.connect(self.analyze)

    def setup(self):
        pass

    @QtCore.pyqtSlot()
    def analyze(self):
        # Check button is enabled
        if not self.run_button.isEnabled():
            return
        # Check file to analyze is closed
        if self.instrument.log_active:
            self.instrument.signal.warning.emit('Stop logging to analyze data.')
            return
        if HyperNavIO is None:
            self.instrument.signal.warning.emit('Package `HyperNav` required.')
            return
        # Start appropriate analysis
        self.run_button.setEnabled(False)
        if self.rb_eval_spec_board.isChecked():
            dialog = HyperNavCharacterizeDMDialog(self, self.instrument)
        elif self.rb_wl_reg.isChecked():
            dialog = HyperNavWavelengthRegistrationDialog(self, self.instrument)
        elif self.rb_calibration.isChecked():
            dialog = HyperNavCalibrateDialog(self, self.instrument)
        elif self.rb_compare_cals.isChecked():
            dialog = HyperNavCalibrationHistoryDialog(self, self.instrument)
        else:
            self.instrument.signal.warning.emit('Invalid analysis.')
            return
        dialog.exec()
        self.run_button.setEnabled(True)


class HyperNavCharacterizeDMDialog(GenericDialog, Worker):
    @classproperty
    def __snake_name__(cls) -> str:
        return 'hypernav_characterize_dm_dialog'

    def __init__(self, parent, instrument: HyperNav, join_target=None):
        self.instrument = instrument
        # Initialize GenericDialog(parent) and Worker(fun, signal)
        super().__init__(parent=parent, fun=HyperNavCharacterizeDMDialog.run, signal=instrument.signal.warning)
        self.browse_datafile_button.clicked.connect(self.browse_datafile)

    @QtCore.pyqtSlot()
    def browse_datafile(self):
        file_name, _ = QtGui.QFileDialog.getOpenFileName(self,
                                                         caption='Choose HyperNav data file',
                                                         filter='Device File (*.raw *.txt)')
        self.le_datafile.setText(file_name)

    @QtCore.pyqtSlot()
    def start(self):
        if not self.check_fields_passed():
            return
        self.disable_run_button()
        super().start(
            os.path.basename(self.le_datafile.text()),
            self.instrument.prt_sbs_sn, self.instrument.sbd_sbs_sn,
            self.instrument.log_path, self.le_datafile.text(), self.queue
        )

    @staticmethod
    def run(prt_sn, sbd_sn, out_path, filename, queue):
        data, meta = HyperNavIO.read_inlinino(filename)
        # Find HyperNav frame serial numbers
        analyzed_sn = set([int(k[6:]) for k in meta['valid_frames'].keys() if
                           True in [k.startswith(hdr) for hdr in ('SATYLZ', 'SATYDZ', 'SATXLZ', 'SATXDZ')]])
        warning_sn, reports_generated = [], []
        for sn in analyzed_sn:
            if sn not in (prt_sn, sbd_sn):
                warning_sn.append(sn)
            ref = os.path.splitext(os.path.basename(filename))[0]
            report = spec_board_report(data, ref, sn)
            target_filename = os.path.join(out_path, f"{ref}_SBSSN{sn:04}.pdf")
            write_report_to_pdf(target_filename, report)
            report.show(config=GRAPH_CFG)
            reports_generated.append(target_filename)
        if warning_sn:
            queue.put(('warning', f"Unexpected head serial number(s) {', '.join([f'{sn:04d}' for sn in warning_sn])}. "
                                  f"Expected heads {prt_sn:04d} and {sbd_sn:04d}. "
                                  f"Nonetheless, report(s) were generated:\n" + '\n'.join(reports_generated)))
        else:
            return reports_generated


class HyperNavWavelengthRegistrationDialog(GenericDialog, Worker):
    @classproperty
    def __snake_name__(cls) -> str:
        return 'hypernav_wl_reg_dialog'

    def __init__(self, parent, instrument: HyperNav):
        self.instrument = instrument
        # Initialize GenericDialog(parent) and Worker(fun, signal)
        super().__init__(parent=parent, fun=register_wavelengths, signal=instrument.signal.warning)
        self.browse_datafile_button.clicked.connect(self.browse_datafile)
        self.browse_wavelength_button.clicked.connect(self.browse_wavelength_file)

        self.cb_head_side.currentTextChanged.connect(self.set_head)
        self.set_head(self.cb_head_side.currentText())

        self.le_hypernav_sn.setText(self.instrument.serial_number)

    @QtCore.pyqtSlot()
    def browse_datafile(self):
        file_name, _ = QtGui.QFileDialog.getOpenFileName(self,
                                                         caption='Choose HyperNav data file',
                                                         filter='Device File (*.raw *.txt)')
        self.le_raw_filename.setText(file_name)

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
        if not self.check_fields_passed():
            return
        self.disable_run_button()
        # Start worker
        super().start(
            os.path.basename(self.le_raw_filename.text()),
            self.instrument.log_path,
            self.le_raw_filename.text(),
            self.le_wavelength_path.text(),
            int(self.le_hypernav_sn.text()),
            self.cb_head_side.currentText(),
            int(self.le_head_sn.text()),
            int(self.le_spec_sn.text()),
            self.sb_wl_shift.value(),
            'show+pdf',
        )

    def join(self):
        super().join()
        self.enable_run_button()


class HyperNavCalibrationHistoryDialog(GenericDialog, Worker):
    @classproperty
    def __snake_name__(cls) -> str:
        return 'hypernav_cal_history_dialog'

    def __init__(self, parent, instrument: HyperNav):
        self.instrument = instrument
        # Initialize QDialog(parent) and Worker(fun, signal)
        super().__init__(parent=parent, fun=HyperNavCalibrationHistoryDialog.run, signal=instrument.signal.warning)

        self.browse_history_button.clicked.connect(self.browse_history_path)

    @QtCore.pyqtSlot()
    def browse_history_path(self):
        path = QtGui.QFileDialog.getExistingDirectory(self, caption='Choose history directory')
        self.le_history_path.setText(path)

    def start(self):
        if not self.check_fields_passed():
            return
        self.disable_run_button()
        # Start worker
        super().start(
            f'folder {os.path.basename(self.le_history_path.text())}',
            self.le_history_path.text(), int(self.le_head_sn.text())
        )

    @staticmethod
    def run(path, head_sn):
        report = calibration_history_report(path, head_sn)
        report.show(config=GRAPH_CFG)
        # target_filename = os.path.join(path, f"{ref}_SBSSN{sn:04}.pdf")
        # write_report_to_pdf(target_filename, report)

        # reports_generated.append(target_filename)
        # return report_generated

    def join(self):
        super().join()
        self.enable_run_button()
