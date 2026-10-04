"""One cancellable, debounced numerical worker per command window."""
from dataclasses import dataclass
import threading
import time

try:
    from .curve_engine import analyze, Cancelled
except ImportError:
    from curve_engine import analyze, Cancelled


@dataclass(frozen=True)
class PreviewResult:
    generation: int
    settings: object
    table: object = None
    count: object = None
    error: str = ''


class PreviewController:
    def __init__(self, deliver, calculate=analyze, debounce=0.3):
        self.deliver = deliver
        self.calculate = calculate
        self.debounce = debounce
        self.generation = 0
        self._closed = False
        self._pending = None
        self._condition = threading.Condition()
        self._cached = None
        self._thread = threading.Thread(target=self._work, daemon=True, name='FusionArcPreview')
        self._thread.start()

    def request(self, settings):
        with self._condition:
            self.generation += 1
            self._pending = (self.generation, settings, time.monotonic()+self.debounce)
            self._condition.notify_all()
            return self.generation

    def invalidate(self):
        with self._condition:
            self.generation += 1
            self._pending = None
            self._condition.notify_all()
            return self.generation

    def current(self, generation):
        with self._condition:
            return not self._closed and generation == self.generation

    def close(self):
        with self._condition:
            self._closed = True
            self.generation += 1
            self._pending = None
            self._cached = None
            self._condition.notify_all()

    def _work(self):
        while True:
            with self._condition:
                while not self._closed and self._pending is None:
                    self._condition.wait()
                if self._closed:
                    return
                generation, cfg, due = self._pending
                remaining = due-time.monotonic()
                if remaining > 0:
                    self._condition.wait(remaining)
                    continue
                self._pending = None
            try:
                cfg.validate()
                table = self._cached
                if table is None or table.cfg.length_key() != cfg.length_key():
                    table = self.calculate(cfg, cancel=lambda: not self.current(generation))
                count = table.count_for(cfg.spacing_mm)
                # The calculation is finished; the table must not retain the
                # old generation's cancellation closure when spacing changes.
                table.cancel = lambda: False
                result = PreviewResult(generation, cfg, table, count)
            except Cancelled:
                continue
            except Exception as exc:
                result = PreviewResult(generation, cfg, error=str(exc))
            with self._condition:
                if self._closed or generation != self.generation:
                    continue
                if result.table is not None:
                    self._cached = result.table
            # The UI recipient checks generation again when the queued event
            # actually reaches the main thread.
            try:
                self.deliver(result)
            except Exception:
                # Fusion may be shutting down while a custom event is posted.
                self.close()
