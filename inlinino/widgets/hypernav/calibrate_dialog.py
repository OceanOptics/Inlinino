import os.path
from threading import Thread
from multiprocessing import Process, Queue

from pyqtgraph.Qt import QtCore, QtGui, QtWidgets, uic
from functools import reduce, partial
from hypernav.calibrate import CalibrationResult, CalibrationError, CalibrationPlotter, CalibrationFileWriter
from hypernav.viz import set_plotly_template

from inlinino.instruments.hypernav import HyperNav
from inlinino.widgets.shared.file_label import FileLabel
from inlinino import PATH_TO_RESOURCES

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))

class HyperNavCalibrateDialogWidget(QtWidgets.QDialog):
    def __init__(self, parent, instrument: HyperNav, log_file_name: str):
        self.worker = None
        self.queue = Queue()
        self.log_file_name = log_file_name
        self.instrument = instrument
        super().__init__(parent)
        uic.loadUi(os.path.join(PATH_TO_RESOURCES, "widget_hypernav_calibrate_dialog.ui"), self)

        self.log_file_label.setText(log_file_name)

        self.run_button = self.button_box.addButton("Run", QtGui.QDialogButtonBox.ActionRole)
        self.cancel_button = self.button_box.addButton("Close", QtGui.QDialogButtonBox.RejectRole)
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
            self.queue,
            CalibrationResult(
                self.instrument.prt_sbs_sn, # OR sbd_sbs_sn
                'port', # OR starboard
                self.instrument.get_local_cfg('SPCPRTSN'), # OR SPCSBDSN
                'chan',
                os.path.join(self.instrument.log_path, self.log_file_name),
                self.lamp_label.get_file(),
                self.plaque_label.get_file(),
                self.wavelength_label.get_file(),
                float(self.lamp_calibration_distance_input.toPlainText()),
                float(self.lamp_to_plaque_distance_input.toPlainText())
            )
        ))
        self.worker.start()
        # Start join thread
        Thread(target=self._join, daemon=True).start()

    @staticmethod
    def run(queue: Queue, result: CalibrationResult):
        try:
            set_plotly_template()
            plotter = CalibrationPlotter(result)
            fig = plotter.plot()
            fig.show()

            writer = CalibrationFileWriter(result, os.path.join(CURRENT_DIR, '../../../data'))
            writer.write_cal_files()
        except CalibrationError as err:
            queue.put(('error', err.message))
        except Exception as err:
            queue.put(('error', f"Unexpected {err=}, {type(err)=}"))

    def _join(self):
        if self.worker is None:
            return
        self.worker.join()
        while not self.queue.empty():
            level, message = self.queue.get_nowait()
            if level == 'warning':
                self.instrument.signal.warning.emit(f'Warning while analyzing "{self.log_file_name}"\n\n{message}')
            elif level == 'error':
                self.instrument.signal.warning.emit(f'The error "{message}" occurred while analyzing "{self.log_file_name}".\n\nUnable to generate report.')

        # Reset buttons
        self.run_button.setEnabled(True)
        self.run_button.setText('Run')
