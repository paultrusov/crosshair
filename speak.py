"""Speech for the things a beep cannot say. xAI's /v1/tts, with a free fallback.

The product here is a 700 Hz burst landing at the exact millisecond a hand
crosses the target, and nothing in this file is allowed to get in the way of
that. But a beep cannot say "water bottle", it cannot say "I can't see a ketchup
bottle from here", and it cannot say "lost it, ask again". Those need words, and
words do not have to be on time to the millisecond. So the two channels split by
what each is good at: beeps own timing, speech owns context.

Three decisions worth keeping:

Speech never goes through sounddevice. `sd.play()` drives one global stream, and
starting a second playback stops the first, so a spoken sentence routed that way
would cut off the crossing beep, the one sound in this project that may never be
interrupted. `afplay` and `say` are separate processes with their own CoreAudio
clients, so the system mixer blends them and neither can pre-empt the other.

Speech never runs on the video loop. It is a worker thread holding one pending
utterance, the same shape redetect.Anchor uses for detection. Newest wins and
older pending text is dropped, because an announcement about an object the
tracker has already lost is worse than silence.

No key is a supported configuration, not a degraded one. With no XAI_API_KEY the
module speaks through macOS `say`, which is offline, free, and cannot expire at
8am on the morning of a demo. The same fallback catches a timeout or an HTTP
error mid-run, so the device keeps talking even when the network stops.
"""
import base64
import hashlib
import json
import os
import subprocess
import threading
import time

API_URL = "https://api.x.ai/v1/tts"
LANGUAGE = "en"
TIMEOUT_S = 8.0

_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(_HERE, ".voice")


def load_key(env_path=None):
    """XAI_API_KEY from the environment, else from a gitignored .env.

    The .env branch exists because a hackathon laptop gets its terminal
    restarted a dozen times and an `export` does not survive that. Returns
    None rather than raising: having no key is a supported configuration.
    """
    key = os.environ.get("XAI_API_KEY", "").strip()
    if key:
        return key
    path = os.path.join(_HERE, ".env") if env_path is None else env_path
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, val = line.partition("=")
                if name.strip() == "XAI_API_KEY":
                    return val.strip().strip("'\"") or None
    except OSError:
        return None
    return None


def bearing_words(cx):
    """Left or right, in the words a person actually uses. cx is normalised and
    0.5 is straight ahead.

    The bands are wide on purpose. This is a bearing off a chest camera, so a
    spoken degree figure would imply a precision the geometry does not have.
    """
    dx = cx - 0.5
    a = abs(dx)
    if a < 0.06:
        return "straight ahead"
    side = "left" if dx < 0 else "right"
    if a < 0.18:
        return f"slightly {side}"
    if a < 0.33:
        return f"to your {side}"
    return f"far {side}"


def reach_words(cy):
    """A coarse distance band from how high the object sits in frame.

    Same observation that killed the vertical sweep: from a sternum camera,
    height in frame is mostly a function of distance, because the things people
    reach for are sitting on surfaces. Good enough for three hedged bands and
    useless for a number, so it is never spoken as one. The README's standing
    rule is that this device delivers a bearing and not a 3D point, and the
    word "about" is what keeps the sentence honest about that.
    """
    if cy > 0.72:
        return "within reach"
    if cy > 0.52:
        return "about an arm's length"
    return "a few steps away"


def cache_path(text, voice_id):
    """Where this exact utterance in this exact voice lives on disk.

    The key covers the voice as well as the text. Keying on text alone would
    quietly serve last night's voice forever after XAI_VOICE_ID changed.
    """
    h = hashlib.sha256(f"{voice_id}|{LANGUAGE}|{text}".encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{h[:20]}.mp3")


class Voice:
    """Spoken context, with the method names of tones.Tones so it can stand
    where Tones stands. It is meant to run *alongside* Tones, not instead of
    it: see cross() and rate() for why.
    """

    def __init__(self, voice_id=None, mute=False, verbose=True, env_path=None):
        self.voice_id = voice_id or os.environ.get("XAI_VOICE_ID", "eve")
        self.mute = mute
        self.key = load_key(env_path)
        self.backend = "grok" if self.key else "say"
        self.running = True
        self._lock = threading.Lock()
        self._pending = None            # one utterance waiting, newest wins
        self._proc = None               # the player currently making noise
        self._spoken = 0                # for the self-test, which needs to
        self._fell_back = False         # see that the worker ran
        os.makedirs(CACHE_DIR, exist_ok=True)
        if verbose:
            # Says which backend is live and never says the key. Knowing which
            # of the two is talking is the first question at 8am.
            print(f"voice: xai grok tts, voice_id={self.voice_id}"
                  if self.key else
                  "voice: macos say (no XAI_API_KEY, offline fallback)",
                  flush=True)
        threading.Thread(target=self._loop, daemon=True).start()

    def say(self, text):
        """Queue one utterance. Returns immediately. The video loop calls this."""
        if not text:
            return
        with self._lock:
            self._pending = text

    def lock(self, phrase=None, cx=None, cy=None):
        """What it found and roughly where. Callable with no arguments, so code
        written against tones.Tones.lock() still does something sensible."""
        if not phrase:
            self.say("Found it.")
            return
        bits = [phrase.strip().capitalize()]
        if cx is not None:
            bits.append(bearing_words(cx))
        if cy is not None:
            bits.append(reach_words(cy))
        self.say(", ".join(bits) + ".")

    def miss(self, phrase):
        self.say(f"I can't see a {phrase} from here.")

    def lost(self):
        self.say("Lost it, ask again.")

    def cross(self):
        """Nothing, deliberately. The crossing signal is a 700 Hz burst out of
        tones.py and it has to land within a few milliseconds of the hand
        passing the bearing. A round trip to a speech API is two orders of
        magnitude too slow, and even cached speech has an attack far too soft
        to time a reach against. This method exists only so Voice can be
        swapped in where Tones is expected."""

    def rate(self, r):
        """Nothing, for the same reason. Proximity is a pulse train whose rate
        IS the information, and speech cannot carry a continuous variable."""

    def beep(self, hz, ms):
        """Nothing. A caller reaching for beep() wants the not-found note, and
        the spoken version of that is miss()."""

    def ping(self):
        pass

    def stop(self):
        """Shut up now: drop what is queued and cut off what is playing.

        Barging in is the point. main.py calls this when the user presses SPACE
        to talk, and a device that keeps describing the last object while
        somebody is speaking into its microphone is worse than one that says
        nothing.

        The worker thread stays alive. main.py also calls stop() on reset and
        on a lost lock, mid-run, so tearing the thread down here would leave
        the device mute for the rest of the session. close() is the one that
        ends it.
        """
        with self._lock:
            self._pending = None
            p, self._proc = self._proc, None
        if p is not None:
            p.terminate()

    def close(self):
        self.stop()
        self.running = False

    def _loop(self):
        while self.running:
            with self._lock:
                text, self._pending = self._pending, None
            if text is None:
                time.sleep(0.02)
                continue
            try:
                self._utter(text)
            except Exception as e:
                # One sentence failing is not a reason for the device to stop
                # talking, but a silent swallow is how you spend a demo
                # wondering why it went quiet. So it is caught and named.
                print(f"voice: could not speak ({e})", flush=True)
            self._spoken += 1

    def _utter(self, text):
        print(f"voice: {text}", flush=True)
        if self.mute:
            return
        if self.backend == "grok":
            path = self._audio(text)
            if path:
                self._play(["afplay", path])
                return
            if not self._fell_back:
                self._fell_back = True
                print("voice: xai tts unavailable, using macos say", flush=True)
        self._play(["say", text])

    def _play(self, argv):
        """Run a player and keep a handle on it, so stop() can cut it off.

        Popen rather than subprocess.run because run() gives nothing to
        interrupt, and the whole value of stop() is interrupting this.
        """
        p = subprocess.Popen(argv)
        with self._lock:
            self._proc = p
        p.wait()                    # waited outside the lock, or stop() blocks
        with self._lock:
            if self._proc is p:
                self._proc = None

    def _audio(self, text):
        """Cached path to spoken audio, or None if the API would not give any.

        The cache is what makes this usable live. "Lost it, ask again" gets
        said on nearly every run, and the second time it costs a file read
        instead of a network round trip.
        """
        path = cache_path(text, self.voice_id)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        audio = self._fetch(text)
        if not audio:
            return None
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(audio)
        # Rename rather than write in place, so a request killed halfway
        # cannot leave a truncated file that the cache then trusts forever.
        os.replace(tmp, path)
        return path

    def _fetch(self, text):
        """POST /v1/tts. Audio bytes, or None on any failure.

        requests is imported here and not at module scope so the no-key path
        has nothing to import and nothing to fail at.

        The response is read two ways on purpose. The documented endpoint
        returns raw audio in the body, but the REST reference also describes a
        JSON envelope carrying base64 `audio`, which is the shape that comes
        back with with_timestamps set. Sniffing Content-Type covers both
        without betting on which one a given deployment sends.

        optimize_streaming_latency is left off: the guide documents it as an
        integer and the reference as a string enum, and a 400 on an optional
        tuning field would push every utterance to the fallback. The cache is
        the real latency fix anyway.
        """
        import requests

        r = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {self.key}",
                     "Content-Type": "application/json"},
            json={"text": text,
                  "voice_id": self.voice_id,
                  "language": LANGUAGE,
                  # Named rather than defaulted, so a change to the endpoint's
                  # default codec cannot hand afplay something it will not play.
                  "output_format": {"codec": "mp3"}},
            timeout=TIMEOUT_S,
        )
        if r.status_code != 200:
            # The body carries the reason and cannot carry the key, so printing
            # it is safe and it is the only way to debug this at 8am.
            print(f"voice: /v1/tts said {r.status_code}: {r.text[:200]}",
                  flush=True)
            return None
        if "json" in r.headers.get("Content-Type", "").lower():
            return base64.b64decode(json.loads(r.text)["audio"])
        return r.content


def _selftest():
    """Proves the no-key path, which is the one that has to work at 8:30am."""
    missing = os.path.join(_HERE, ".env.does-not-exist")
    saved = os.environ.pop("XAI_API_KEY", None)
    fails = []

    def ok(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        if not cond:
            fails.append(name)

    try:
        print("no-key fallback")
        ok("load_key returns None with no env var and no .env",
           load_key(missing) is None)

        tmp = os.path.join(CACHE_DIR, "selftest.env")
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(tmp, "w") as f:
            f.write("# comment\nXAI_API_KEY='xai-from-dotenv'\n")
        ok("load_key reads a quoted value out of .env",
           load_key(tmp) == "xai-from-dotenv")
        os.environ["XAI_API_KEY"] = "xai-env-wins"
        ok("the env var beats the .env file", load_key(tmp) == "xai-env-wins")
        del os.environ["XAI_API_KEY"]
        os.remove(tmp)

        v = Voice(verbose=False, mute=True, env_path=missing)
        ok("backend is macos say when there is no key", v.backend == "say")
        ok("no key is held", v.key is None)

        print("\nthe beeps are untouched")
        t0 = time.perf_counter()
        for _ in range(500):
            v.cross()
            v.rate(0.7)
        dt = time.perf_counter() - t0
        ok(f"cross() and rate() are no-ops, 1000 calls in {dt*1000:.2f}ms",
           dt < 0.05)

        print("\nthe video loop never waits")
        t0 = time.perf_counter()
        v.lock("water bottle", 0.41, 0.6)
        dt = time.perf_counter() - t0
        ok(f"lock() returned in {dt*1000:.3f}ms", dt < 0.02)
        for _ in range(100):
            if v._spoken:
                break
            time.sleep(0.02)
        ok("the worker thread picked it up", v._spoken >= 1)

        print("\nnothing was requested over the network")
        ok("no audio was cached, so /v1/tts was never called",
           not os.path.exists(cache_path("Water bottle, slightly left, "
                                         "about an arm's length.", v.voice_id)))

        print("\nwhat it actually says")
        for args, want in [
            (("water bottle", 0.41, 0.60),
             "Water bottle, slightly left, about an arm's length."),
            (("mug", 0.50, 0.80), "Mug, straight ahead, within reach."),
            (("chair", 0.95, 0.30), "Chair, far right, a few steps away."),
        ]:
            v.stop()
            v.lock(*args)
            got = v._pending
            ok(f"{got!r}", got == want)

        v.stop()
        v.miss("ketchup bottle")
        ok(f"{v._pending!r}",
           v._pending == "I can't see a ketchup bottle from here.")
        v.stop()
        v.lost()
        ok(f"{v._pending!r}", v._pending == "Lost it, ask again.")

        print("\ncache keys")
        a = cache_path("Lost it, ask again.", "eve")
        ok("the same text in the same voice is the same file",
           a == cache_path("Lost it, ask again.", "eve"))
        ok("a different voice is a different file",
           a != cache_path("Lost it, ask again.", "ara"))
        ok("a different text is a different file",
           a != cache_path("Lost it, ask again!", "eve"))
        v.close()

        print("\nstop() cuts off a sentence already playing")
        v2 = Voice(verbose=False, env_path=missing)
        v2.say("This is a long sentence, and it should be cut off well before "
               "it has had any chance of finishing on its own.")
        for _ in range(150):
            if v2._proc is not None:
                break
            time.sleep(0.02)
        ok("a player process started", v2._proc is not None)
        t0 = time.perf_counter()
        v2.stop()
        for _ in range(150):
            if v2._spoken:
                break
            time.sleep(0.02)
        dt = time.perf_counter() - t0
        ok(f"it ended {dt*1000:.0f}ms later, not the ~7s it needed to finish",
           v2._spoken >= 1 and dt < 1.5)
        v2.close()
    finally:
        if saved is not None:
            os.environ["XAI_API_KEY"] = saved
        elif "XAI_API_KEY" in os.environ:
            del os.environ["XAI_API_KEY"]

    print(f"\n{'all passed' if not fails else str(len(fails)) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    import sys

    if "--test" in sys.argv:
        sys.exit(_selftest())

    v = Voice()
    print(f"backend: {v.backend}\n")
    v.lock("water bottle", 0.41, 0.60)
    time.sleep(3.5)
    v.miss("ketchup bottle")
    time.sleep(3.0)
    v.lost()
    time.sleep(2.5)
    v.close()
