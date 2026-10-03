"""Keep the lock honest while the camera walks.

CSRT follows an object fine when the camera is still and loses it completely
when a head-mounted camera walks and turns. Once it drifts, nothing pulls it
back, so the box ends up floating over a window and the demo falls apart on
film about five seconds in.

The detector is the only thing that actually knows where the object is, but it
costs ~900 ms and the video loop runs at 30 fps. So it runs on a worker thread:
the loop hands it the newest frame, carries on tracking, and picks up the
answer whenever it is ready. The video never stalls and the box never wanders
for more than about a second.
"""
import threading
import time


class Anchor:
    """Re-runs detection in the background and hands back fresh boxes."""

    def __init__(self, detector, phrase, period=1.2):
        self.detector = detector
        self.phrase = phrase
        self.period = period
        self._lock = threading.Lock()
        self._pending = None        # frame waiting to be looked at
        self._result = None         # (box_norm, score) not yet collected
        self._busy = False
        self._last = 0.0
        self._stop = False
        threading.Thread(target=self._loop, daemon=True).start()

    def offer(self, frame):
        """Give the worker the newest frame, if it is time and it is free."""
        now = time.perf_counter()
        if self._busy or now - self._last < self.period:
            return
        with self._lock:
            self._pending = frame.copy()

    def take(self):
        """Collect a finished detection, or None. Never blocks."""
        with self._lock:
            r, self._result = self._result, None
        return r

    def close(self):
        self._stop = True

    def _loop(self):
        while not self._stop:
            with self._lock:
                frame, self._pending = self._pending, None
            if frame is None:
                time.sleep(0.02)
                continue
            self._busy = True
            try:
                r = self.detector.find(frame, self.phrase)
            except Exception:
                r = None
            self._last = time.perf_counter()
            self._busy = False
            if r is not None:
                with self._lock:
                    self._result = (r[3], r[2])
