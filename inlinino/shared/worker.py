import logging
import warnings
from threading import Thread
from multiprocessing import Process, Queue


logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, fun, signal, **kwargs):
        self.fun = fun
        self.signal = signal
        self.process = None
        self.queue = Queue()
        self.ref = None

    def start(self, ref, *args):
        self.ref = ref
        # Start worker
        self.process = Process(name='HyperNavWorker', target=Worker._run,
                               args=args, kwargs=dict(fun=self.fun, queue=self.queue))
        self.process.start()
        # Start join thread
        Thread(target=self.join, daemon=True).start()

    @staticmethod
    def _run(*args, fun, queue):
        try:
            with warnings.catch_warnings(record=True) as ws:
                res = fun(*args)
                if len(ws) > 0:
                    for w in ws:
                        logger.warning(w.message)
                    msg = "Warning(s):\n" + "\n".join([f"  - {w.message}" for w in ws])
                    if res is not None:
                        msg += f"\n\nFile(s) generated:\n" + '\n'.join(res)
                    queue.put(('warning', msg))
                elif res is not None:
                    queue.put(('success', f"File(s) generated:\n" + '\n'.join(res)))
        except Exception as e:
            if queue is not None:
                queue.put(('error', str(e)))

    def join(self):
        if self.process is None:
            return
        self.process.join()
        while not self.queue.empty():
            level, message = self.queue.get_nowait()
            if level == 'success':
                self.signal[str, str, str].emit("Success!", message, 'info')
            else:
                intro = f"while analyzing '{self.ref}'" if self.ref else ''
                self.signal[str, str, str].emit(f"{level.capitalize()} {intro}", message, level)
