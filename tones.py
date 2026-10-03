"""Beeps straight out of the laptop. Same interface as box_client.Box.

Why this exists: the Pi is a nice-to-have, not a dependency. The signal this
project delivers is a sound at the right instant, and a laptop makes a sound
at the right instant with nothing plugged in. Route the laptop's audio to a
cheap earbud or a small speaker on the strap and the wearable is complete.

Swap to the Pi later by changing one line in sweep.py. Nothing else moves.
"""
import threading
import time

import numpy as np
import sounddevice as sd

SR = 44100


def _burst(hz, ms, amp=0.35):
    """One tone with 5ms raised-cosine edges. Without the ramp you get a click
    at each end, which on a cheap speaker is louder than the tone itself."""
    n = int(SR * ms / 1000.0)
    t = np.arange(n) / SR
    w = amp * np.sin(2 * np.pi * hz * t)
    e = max(1, int(SR * 0.005))
    ramp = 0.5 * (1 - np.cos(np.linspace(0, np.pi, e)))
    w[:e] *= ramp
    w[-e:] *= ramp[::-1]
    return w.astype(np.float32)


class Tones:
    def __init__(self, device=None):
        self.device = device
        self._rate = 0.0
        self.running = True
        self._lock = threading.Lock()
        # Pre-render everything. Generating a buffer inside the hot path adds
        # jitter exactly where the whole product is a precisely timed sound.
        self._cross = _burst(700, 90)
        self._lock_beep = _burst(1800, 70)
        self._pulses = {i: _burst(int(600 + 1200 * i / 20.0), 45)
                        for i in range(21)}
        sd.default.samplerate = SR
        sd.default.channels = 1
        if device is not None:
            sd.default.device = device
        threading.Thread(target=self._pulse_loop, daemon=True).start()

    def _play(self, buf, block=False):
        with self._lock:
            sd.play(buf, SR, blocking=block)

    def lock(self):
        self._rate = 0.0
        self._play(self._lock_beep, block=True)
        time.sleep(0.06)
        self._play(self._lock_beep, block=True)

    def cross(self):
        self._play(self._cross)

    def rate(self, r):
        self._rate = max(0.0, min(1.0, float(r)))

    def stop(self):
        self._rate = 0.0

    def beep(self, hz, ms):
        self._play(_burst(hz, ms))

    def ping(self):
        pass

    def _pulse_loop(self):
        while self.running:
            r = self._rate
            if r <= 0.01:
                time.sleep(0.02)
                continue
            self._play(self._pulses[int(round(r * 20))], block=True)
            time.sleep(max(0.5 - 0.44 * r, 0.0))


if __name__ == "__main__":
    print("devices:")
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0:
            print(f"  {i} {d['name']}")
    print("\nlock..."); t = Tones(); t.lock(); time.sleep(0.4)
    print("cross...");  t.cross(); time.sleep(0.5)
    print("rate 0.15 (far)...");  t.rate(0.15); time.sleep(2.0)
    print("rate 0.9 (close)...");  t.rate(0.9);  time.sleep(2.0)
    t.stop(); time.sleep(0.3)
    print("done")
