"""Runs ON THE PI. Owns the two buzzers and the button, nothing else.

The laptop does all the vision and sends one-line commands over TCP.
Keeping the Pi dumb is deliberate: when something breaks at 3am you only
have to ask "is the laptop sending it" or "is the Pi beeping", never both.

    python3 buzzbox.py

Commands in (newline delimited, port 9999):
    LOCK                two quick high beeps, "I found it"
    CROSS               one short low beep, "your hand is on it now"
    RATE <0.0-1.0>      pulse continuously, 1.0 = closest, 0 = stop
    BEEP <hz> <ms>      raw tone
    STOP                silence
    PING                replies PONG

Lines out:
    BTN                 sent the moment the button is pressed
    PONG / ERR <msg>
"""
import socket
import threading
import time

PORT = 9999

# Grove Base HAT digital port -> BCM pin. The number printed on the socket IS
# the BCM pin, which is why these look the way they do.
BUZZER_PIN = 5     # buzzer 1 into Grove port D5
BUTTON_PIN = 18    # button into Grove port D18

try:
    from gpiozero import TonalBuzzer, Button
    from gpiozero.tones import Tone
    HAVE_GPIO = True
except Exception as e:                      # running on a laptop for testing
    print("gpiozero unavailable (%s), SIMULATION mode" % e)
    HAVE_GPIO = False


class Box:
    def __init__(self):
        self.lock = threading.Lock()
        self.rate = 0.0
        self.running = True
        self.buzzer = TonalBuzzer(BUZZER_PIN) if HAVE_GPIO else None
        self.button = Button(BUTTON_PIN, pull_up=True, bounce_time=0.05) if HAVE_GPIO else None
        threading.Thread(target=self._pulse_loop, daemon=True).start()

    def tone(self, hz, ms):
        with self.lock:
            if self.buzzer:
                self.buzzer.play(Tone(frequency=hz))
                time.sleep(ms / 1000.0)
                self.buzzer.stop()
            else:
                print(f"  [sim] tone {hz}Hz {ms}ms", flush=True)
                time.sleep(ms / 1000.0)

    def lock_found(self):
        self.tone(1800, 70)
        time.sleep(0.06)
        self.tone(1800, 70)

    def cross(self):
        self.tone(700, 90)

    def _pulse_loop(self):
        """RATE becomes a pulse train: faster and higher as you close in.
        That is the one signal a blindfolded person reads without training."""
        while self.running:
            r = self.rate
            if r <= 0.01:
                time.sleep(0.02)
                continue
            gap = 0.5 - 0.44 * min(r, 1.0)      # 0.5s far -> 0.06s near
            hz = int(600 + 1200 * min(r, 1.0))
            self.tone(hz, 45)
            time.sleep(max(gap, 0.0))


def send(conn, s):
    try:
        conn.sendall((s + "\n").encode())
    except Exception:
        pass


def handle(conn, box):
    if box.button is not None:
        box.button.when_pressed = lambda: send(conn, "BTN")

    buf = b""
    while True:
        try:
            chunk = conn.recv(4096)
        except Exception:
            break
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            parts = line.decode(errors="replace").strip().split()
            if not parts:
                continue
            cmd = parts[0].upper()
            try:
                if cmd == "LOCK":
                    box.rate = 0.0
                    box.lock_found()
                elif cmd == "CROSS":
                    box.cross()
                elif cmd == "RATE":
                    box.rate = float(parts[1])
                elif cmd == "BEEP":
                    box.tone(int(parts[1]), int(parts[2]))
                elif cmd == "STOP":
                    box.rate = 0.0
                elif cmd == "PING":
                    send(conn, "PONG")
                else:
                    send(conn, f"ERR unknown {cmd}")
            except Exception as e:
                send(conn, f"ERR {e}")
    if box.button is not None:
        box.button.when_pressed = None
    box.rate = 0.0
    conn.close()


def main():
    box = Box()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", PORT))
    s.listen(1)
    print(f"buzzbox listening on :{PORT}  (gpio={'real' if HAVE_GPIO else 'sim'})",
          flush=True)
    while True:
        conn, addr = s.accept()
        print("connected", addr, flush=True)
        handle(conn, box)
        print("disconnected", addr, flush=True)


if __name__ == "__main__":
    main()
