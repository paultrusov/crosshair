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


def _opens(idx):
    """A device that lists is not a device that opens. The Brio's microphone
    enumerates fine and then fails with PortAudio -9986, most likely because
    OpenCV already holds that USB device for video."""
    try:
        sr = int(sd.query_devices(idx)["default_samplerate"])
        st = sd.InputStream(samplerate=sr, channels=1, dtype="float32",
                            device=idx)
        st.start(); st.stop(); st.close()
        return True
    except Exception:
        return False


def pick_mic(prefer="Brio"):
    """Prefer the camera's own mic, so the pod on the chest both sees and
    hears. Fall back to whatever works, because a demo that cannot hear is
    worse than a demo tethered to the laptop."""
    devs = sd.query_devices()
    cands = [i for i, d in enumerate(devs)
             if d["max_input_channels"] > 0 and prefer.lower() in d["name"].lower()]
    cands += [i for i, d in enumerate(devs) if d["max_input_channels"] > 0
              and i not in cands]
    for i in cands:
        if _opens(i):
            print(f"mic: {devs[i]['name']} (device {i})")
            return i
    print("mic: no input device would open")
    return None


class Listener:
    """Records here, transcribes in a child process. See whisper_worker.py for
    why the model cannot live in this process."""

    def __init__(self, model="small.en", device_index="auto"):
        self.device_index = pick_mic() if device_index == "auto" else device_index
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

        # Record at whatever the device actually runs at and resample here.
        # Asking a 48 kHz USB mic for 16 kHz fails on macOS with an opaque
        # PortAudio -9986, because CoreAudio will not resample for us.
        info = sd.query_devices(self.device_index if self.device_index is not None
                                else sd.default.device[0])
        self._native_sr = int(info["default_samplerate"])
        self._stream = sd.InputStream(samplerate=self._native_sr, channels=1,
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
        native = getattr(self, "_native_sr", SR)
        if native != SR:                       # linear resample to whisper's 16k
            n_out = int(len(audio) * SR / native)
            audio = np.interp(np.linspace(0, len(audio) - 1, n_out),
                              np.arange(len(audio)), audio).astype(np.float32)
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
