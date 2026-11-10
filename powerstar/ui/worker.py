"""Run a callable off the GUI thread and hand its result back on the GUI thread."""

from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal

_running: set["_Job"] = set()  # keeps each thread object alive until it finishes


class _Job(QThread):
    result = pyqtSignal(object)

    def __init__(self, fn: Callable) -> None:
        super().__init__()
        self.fn = fn

    def run(self) -> None:
        try:
            self.result.emit(self.fn())
        except BaseException as e:  # reported to `done`, never raised in the thread
            self.result.emit(e)


def run_async(fn: Callable, done: Callable) -> None:
    """Call fn() in a thread, then done(result_or_exception) on the calling (GUI) thread."""
    job = _Job(fn)
    job.result.connect(done)
    job.finished.connect(lambda: _running.discard(job))
    _running.add(job)
    job.start()
