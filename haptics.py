"""The Pi's own output and input, for the standalone build. No laptop, no TCP.

buzzbox.py takes orders over the network. This is the same hardware driven
from inside onboard.py, so the vision loop talks to the pin directly.

One output pin, two kinds of part, same code:
    --out motor    a Grove vibration motor module (it has its own driver, so
                   a GPIO pin can switch it; a bare FA-130 cannot, see README)
    --out buzzer   the Grove buzzer, square wave at a pitch

Every signal is a count of pulses, because the writeup's interaction is
"three vibrations" and a buzzer can say three just as well as a motor can.
"""
import queue
import threading
import time

OUT_PIN = 5        # Grove D5
BUTTON_PIN = 18    # Grove D18
LONG_PRESS_S = 1.2

try:
    from gpiozero import PWMOutputDevice, Button
    HAVE_GPIO = True
except Exception as e:                      # on a laptop for testing
    print("gpiozero unavailable (%s), SIMULATION mode" % e)
    HAVE_GPIO = False


class Haptics:
    """Pulses on a worker thread, so three vibrations never stall the camera
    loop for the ~600 ms they take."""

    def __init__(self, kind="motor", pin=OUT_PIN, mute=False):
        self.kind = kind
        self.mute = mute
        self.dev = None
        if HAVE_GPIO and not mute:
            # PWMOutputDevice rather than TonalBuzzer: TonalBuzzer refuses
            # anything outside one octave of A4, which rules out every tone
            # buzzbox.py asks it for.
            self.dev = PWMOutputDevice(pin, frequency=100, initial_value=0)
        self._q = queue.Queue()
        threading.Thread(target=self._loop, daemon=True).start()

    # The vocabulary. Short pulses are "yes, next step"; one long one is "no".
    def ready(self):     self.pulses(1, 80)
    def tick(self):      self.pulses(1, 40, hz=1500)
    def lock(self):      self.pulses(3, 110, hz=1800)
    def aligned(self):   self.pulses(3, 110, hz=1200)
    def cross(self):     self.pulses(1, 160, hz=700)
    def miss(self):      self.pulses(1, 600, hz=300)
    def lost(self):      self.pulses(2, 300, hz=300, gap_ms=150)

    def pulses(self, n, on_ms, hz=1000, gap_ms=110):
        self._q.put((n, on_ms, hz, gap_ms))

    def clear(self):
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    def _loop(self):
        while True:
            n, on_ms, hz, gap_ms = self._q.get()
            for i in range(n):
                self._on(hz)
                time.sleep(on_ms / 1000.0)
                self._off()
                if i < n - 1:
                    time.sleep(gap_ms / 1000.0)
            time.sleep(0.08)        # so back to back signals stay countable

    def _on(self, hz):
        if self.dev is None:
            if not self.mute:
                print(f"  [haptic] on {hz}Hz", flush=True)
            return
        if self.kind == "buzzer":
            self.dev.frequency = hz
            self.dev.value = 0.5
        else:
            self.dev.value = 1.0

    def _off(self):
        if self.dev is not None:
            self.dev.value = 0


class PushButton:
    """Short press and long press, delivered as events to a queue so the main
    loop handles them with the frame it actually has in hand."""

    def __init__(self, events, pin=BUTTON_PIN):
        self.events = events
        self._down = None
        self.btn = None
        if HAVE_GPIO:
            self.btn = Button(pin, pull_up=True, bounce_time=0.05)
            self.btn.when_pressed = self._pressed
            self.btn.when_released = self._released

    def _pressed(self):
        self._down = time.perf_counter()

    def _released(self):
        if self._down is None:
            return
        held = time.perf_counter() - self._down
        self._down = None
        self.events.put("long" if held >= LONG_PRESS_S else "short")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", choices=["motor", "buzzer"], default="motor")
    args = ap.parse_args()
    h = Haptics(args.out)
    for name in ("ready", "lock", "aligned", "cross", "miss", "lost"):
        print(name, flush=True)
        getattr(h, name)()
        time.sleep(1.6)
    q = queue.Queue()
    PushButton(q)
    print("press the button (short, then long). Ctrl-C to quit.")
    while True:
        print("button:", q.get(), flush=True)
