"""Push to talk. Hold the button (or a key), say the thing, let go.

Runs faster-whisper locally. No internet, no API key, nothing to go wrong on
conference wifi at the exact moment a judge is watching.
"""
import re
import sys
import threading
import time

import os
import subprocess
import sys
import wave

import numpy as np
import sounddevice as sd

SR = 16000

# Words people put in front of the thing they actually want. Stripped in three
# passes rather than one regex, because "Okay, where is the remote control" has
# a comma after the filler and "my phone" has no verb at all. One pattern that
# handles both ends up matching things it should not.
_FILLER = re.compile(r"^\s*(ok|okay|hey|um|uh|so|yeah|alright)\b[\s,]*", re.I)
_VERB = re.compile(
    r"^\s*(where(\'s| is| are)?|find|look for|locate|i(\'m| am)? looking for|"
    r"get|show me|point( me)?( to| at)?|can you find)\b[\s,]*", re.I)
_DET = re.compile(r"^\s*(the|my|a|an|some|our)\b\s*", re.I)
_TRAIL = re.compile(r"[\s,]*(for me|please|thanks|thank you)?[.!?]*\s*$", re.I)


def to_noun(text):
    t = text.strip()
    for _ in range(3):                 # "ok so uh find..." stacks
        t2 = _FILLER.sub("", t)
        if t2 == t:
            break
        t = t2
    t = _VERB.sub("", t)
    for _ in range(2):                 # "where is the my phone" happens
        t2 = _DET.sub("", t)
        if t2 == t:
            break
        t = t2
    t = _TRAIL.sub("", t)
    return t.strip().lower()


class Listener:
    """Records here, transcribes in a child process. See whisper_worker.py for
    why the model cannot live in this process."""

    def __init__(self, model="small.en", device_index=None):
        self.device_index = device_index
        self._buf = []
        self._stream = None
        here = os.path.dirname(os.path.abspath(__file__))
        print(f"starting whisper worker ({model}) ...", flush=True)
        self.proc = subprocess.Popen(
            [sys.executable, "-u", os.path.join(here, "whisper_worker.py"), model],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1)
        # Intel MKL prints a deprecation banner to STDOUT before anything we
        # write, so the handshake has to scan for READY rather than trust the
        # first line.
        for _ in range(40):
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("whisper worker died during startup")
            if line.strip() == "READY":
                break
        else:
            raise RuntimeError("whisper worker never said READY")
        print("whisper ready", flush=True)

    def start(self):
        self._buf = []

        def cb(indata, frames, t, status):
            self._buf.append(indata.copy())

        self._stream = sd.InputStream(samplerate=SR, channels=1,
                                      dtype="float32", callback=cb,
                                      device=self.device_index)
        self._stream.start()

    def stop(self):
        if not self._stream:
            return ""
        self._stream.stop(); self._stream.close(); self._stream = None
        if not self._buf:
            return ""
        audio = np.concatenate(self._buf).flatten()
        if len(audio) < SR * 0.3:
            return ""
        path = "/tmp/crosshair_say.wav"
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        with wave.open(path, "wb") as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR)
            f.writeframes(pcm.tobytes())
        self.proc.stdin.write(path + "\n")
        self.proc.stdin.flush()
        for _ in range(10):
            line = self.proc.stdout.readline()
            if not line:
                return ""
            t = line.strip()
            if t.startswith("Intel MKL") or t == "READY":
                continue
            return "" if t.startswith("ERR ") else t
        return ""

    def record_for(self, secs):
        import time
        self.start(); time.sleep(secs); return self.stop()

    def close(self):
        try:
            self.proc.stdin.close(); self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()


if __name__ == "__main__":
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
    L = Listener()
    print(f"\nSPEAK NOW, {secs:.0f} seconds. Say something like "
          f"'where's my water bottle'")
    raw = L.record_for(secs)
    print(f"\nheard : {raw!r}")
    print(f"noun  : {to_noun(raw)!r}")
