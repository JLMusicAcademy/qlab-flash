"""Run blocking work (OSC round-trips) off the Qt UI thread."""

from __future__ import annotations

from typing import Callable, Set

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

# QThreadPool auto-deletes a finished QRunnable. If we let it delete our task
# (which owns the signals object) before the queued done/error signal is
# delivered to the UI thread, the result is silently lost. So we disable
# auto-delete and keep a strong reference here until the slot has fired.
_LIVE_TASKS: "Set[_Task]" = set()


class _Signals(QObject):
    done = Signal(object)
    error = Signal(str)
    progress = Signal(str)
    finished = Signal()


class _Task(QRunnable):
    def __init__(self, fn: Callable):
        super().__init__()
        self.setAutoDelete(False)
        self.fn = fn
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.fn(self.signals.progress.emit)
        except Exception as exc:  # surfaced to the UI, never crashes the app
            self.signals.error.emit(str(exc))
        else:
            self.signals.done.emit(result)
        finally:
            self.signals.finished.emit()


def run_async(fn: Callable, on_done=None, on_error=None, on_progress=None) -> None:
    """Run ``fn(progress_emit)`` in a thread pool, dispatching results to Qt.

    ``fn`` receives a ``progress`` callable it can use to report status text.
    """
    task = _Task(fn)
    _LIVE_TASKS.add(task)
    if on_done:
        task.signals.done.connect(on_done)
    if on_error:
        task.signals.error.connect(on_error)
    if on_progress:
        task.signals.progress.connect(on_progress)
    # Release our reference only after all queued slots have run on the UI thread.
    task.signals.finished.connect(lambda: _LIVE_TASKS.discard(task))
    QThreadPool.globalInstance().start(task)
