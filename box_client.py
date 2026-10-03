"""Laptop side of the link to the Pi. Import this, do not run it.

Never raises at a call site. If the Pi is unplugged the methods go quiet
instead of taking the demo down in front of a judge.
"""
import socket
import threading


class Box:
    def __init__(self, host, port=9999, on_button=None, verbose=True):
        self.host, self.port = host, port
        self.on_button = on_button
        self.verbose = verbose
        self.sock = None
        self.connect()

    def connect(self):
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=3)
            self.sock.settimeout(None)
            threading.Thread(target=self._reader, daemon=True).start()
            print(f"box connected {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"box NOT connected ({e}) - running silent")
            self.sock = None
            return False

    def _reader(self):
        buf = b""
        while self.sock:
            try:
                chunk = self.sock.recv(4096)
            except Exception:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                msg = line.decode(errors="replace").strip()
                if msg == "BTN" and self.on_button:
                    self.on_button()
                elif msg.startswith("ERR") and self.verbose:
                    print("box:", msg)
        self.sock = None

    def _send(self, s):
        if not self.sock:
            return
        try:
            self.sock.sendall((s + "\n").encode())
        except Exception:
            self.sock = None

    def lock(self):          self._send("LOCK")
    def cross(self):         self._send("CROSS")
    def rate(self, r):       self._send(f"RATE {r:.3f}")
    def stop(self):          self._send("STOP")
    def beep(self, hz, ms):  self._send(f"BEEP {hz} {ms}")
    def ping(self):          self._send("PING")
