import os.path
import queue
from threading import Thread
from multiprocessing import Process, Queue

from pyqtgraph.Qt import QtCore, QtGui, QtWidgets, uic
from functools import reduce, partial

# TODO move read_manufacturer_pixel_registration to io as static function
from inlinino.instruments.hypernav import HyperNav, read_manufacturer_pixel_registration
from inlinino.widgets.shared.file_label import FileLabel
from inlinino import PATH_TO_RESOURCES

try:
    from hypernav.calibrate import calibration_report
    from hypernav.io import HyperNav as HyperNavIO
except IndexError:
    HyperNavIO = None

class HyperNavCalibrateDialogWidget(QtWidgets.QDialog):
    def __init__(self, parent, instrument: HyperNav, log_file_name: str):
        self.worker = None
        self.queue = Queue()
        self.log_file_name = log_file_name
        self.instrument = instrument
        super().__init__(parent)
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, "widget_hypernav_calibrate_dialog.ui"), self)

        self.log_file_label.setText(log_file_name)

        self.run_button = self.button_box.addButton("Run", QtGui.QDialogButtonBox.AcceptRole)
        self.cancel_button = self.button_box.addButton("Cancel", QtGui.QDialogButtonBox.RejectRole)
        self.run_button.clicked.connect(self.start_clicked)
        self.cancel_button.clicked.connect(self.cancel_clicked)
        self.run_button.setEnabled(False)

        self.lamp_label = FileLabel(self.lamp_file_label)
        self.plaque_label = FileLabel(self.plaque_file_label)
        self.wavelength_label = FileLabel(self.wavelength_file_label)

        self.setup_browse_files([
            (self.browse_lamp_button, self.lamp_label),
            (self.browse_plaque_button, self.plaque_label),
            (self.browse_wavelength_button, self.wavelength_label),
        ])


    def cancel_clicked(self):
        self.close()

    def setup(self):
        pass

    def setup_browse_files(self, button_label_tuples):
        @QtCore.pyqtSlot()
        def browse_and_check(file_label):
            file_name, _ = QtGui.QFileDialog.getOpenFileName(self)
            file_label.set_file(file_name)
            # Check to see if all files have been populated before enabling report button
            all_labels = [x[1] for x in button_label_tuples]
            form_complete = reduce(lambda acc, cur: acc and cur.get_file() != None, all_labels, True)
            self.run_button.setEnabled(form_complete)

        for button, label in button_label_tuples:
            button.clicked.connect(partial(browse_and_check, label))

    @QtCore.pyqtSlot()
    def start_clicked(self):
        if not self.run_button.isEnabled():
            return

        # Disable button
        self.run_button.setText('Processing ...')
        self.run_button.setEnabled(False)

        # Start worker
        self.worker = Process(name='HyperNavWorker', target=HyperNavCalibrateDialogWidget.run, args=(
            self.instrument.serial_number,
            self.instrument.prt_sbs_sn,
            self.instrument.sbd_sbs_sn,
            self.instrument.log_path,
            self.log_file_name,
            self.queue,
            self.lamp_label.get_file(),
            self.plaque_label.get_file(),
            self.wavelength_label.get_file(),
            float(self.lamp_calibration_distance_input.toPlainText()),
            float(self.lamp_to_plaque_distance_input.toPlainText())
        ))
        self.worker.start()
        # Start join thread
        Thread(target=self._join, daemon=True).start()

    @staticmethod
    def run(
        hn_sn,
        prt_sn,
        sbd_sn,
        path,
        filename,
        queue,
        lamp_file_path,
        plaque_file_path,
        wavelength_file_path,
        fel_lamp_calibration_distance_meters,
        fel_lamp_to_plaque_distance_meters
    ):
        hn = HyperNavIO(sn=hn_sn, prt_head_sn=prt_sn, stb_head_sn=sbd_sn)
        data, meta = hn.read_inlinino(os.path.join(path, filename))
        # Find HyperNav frame serial numbers
        analyzed_sn = set([int(k[6:]) for k in meta['valid_frames'].keys() if
                            True in [k.startswith(hdr) for hdr in ('SATYLZ', 'SATYDZ', 'SATXLZ', 'SATXDZ')]])

        wl_data = read_manufacturer_pixel_registration(wavelength_file_path)

        warning_sn = []
        for sn in analyzed_sn:
            if sn not in (prt_sn, sbd_sn):
                warning_sn.append(sn)
            calibration_report(
                sn,
                data,
                lamp_file_path,
                plaque_file_path,
                wl_data,
                fel_lamp_calibration_distance_meters,
                fel_lamp_to_plaque_distance_meters
            )
        if warning_sn:
            queue.put((filename, 'warning', ', '.join([f'{sn:04d}' for sn in warning_sn])))
        else:
            queue.put((filename, 'ok'))

    def _join(self):
        if self.worker is None:
            return
        self.worker.join()
        # Check if job finished properly
        try:
            result = self.queue.get_nowait()
        except queue.Empty:
            result = ('error', 'No results from worker.')
        if result[1] == 'warning':
            self.instrument.signal.warning.emit(f'Unexpected head serial number(s) {result[2]} in "{result[0]}".')
        elif result[1] == 'error':
            self.instrument.signal.warning.emit(f'The error "{result[2]}" occurred while analyzing "{result[0]}".\n'
                                                f'Unable to generate report.')
        # Reset buttons
        self.run_button.setEnabled(True)
