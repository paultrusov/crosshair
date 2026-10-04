"""Crosshair with no laptop. Everything runs on the Raspberry Pi 5.

    python onboard.py                   button to talk, motor on D5
    python onboard.py --out buzzer      the Grove buzzer instead of a motor
    python onboard.py --say "kiwi"      no microphone; the button searches for kiwi
    python onboard.py --show            draw the boxes on an HDMI monitor

The button (Grove D18):
    short press     start listening; short press again when you are done
    long press      reset

The flow, one signal per step:
  1. Say what you want.                           whisper, on the Pi
  2. Found and in frame: three vibrations.        box RED
  3. Move your arm up or down. Three vibrations
     again when your hand is level with it.       box YELLOW
  4. Sweep sideways. One buzz the instant your
     hand crosses it, every time it does.         box GREEN
  Not found: one long buzz. Lost the lock: two long ones.

What changed from main.py to fit a Pi: OWL-ViT base/32 instead of OWLv2
(detect_lite.py), 640x480 instead of 720p, re-detect every 3 s instead of
1.2 s, whisper base.en instead of small.en. The crossing logic is the same,
and it still fires early by the measured loop time, which is longer here.
"""
import os

os.environ.setdefault("OMP_NUM_THREADS", "3")

import argparse
import collections
import queue
import time

import cv2
import numpy as np

from sweep import WristTracker, pick_camera, open_camera
from track import Lock
from redetect import Anchor
from haptics import Haptics, PushButton

RE_ARM_S = 0.45          # ignore a second crossing this soon after one
MIN_SPEED = 0.03         # frac of frame per second, below this it is not a sweep
SETTLE_S = 0.9           # after a signal, before the next step may fire
BAND_FRAMES = 2          # frames level with the object before "aligned"

RED = (0, 0, 255)
YELLOW = (0, 255, 255)
GREEN = (0, 255, 0)

IDLE, LISTENING, FOUND, LEVEL, ON = range(5)
COLOUR = {FOUND: RED, LEVEL: YELLOW, ON: GREEN}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", choices=["motor", "buzzer"], default="motor",
                    help="what is plugged into D5")
    ap.add_argument("--cam", type=int, default=None)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--model", default="base.en", help="whisper model")
    ap.add_argument("--detector", default=None,
                    help="HF model id, default google/owlvit-base-patch32")
    ap.add_argument("--tracker", choices=["csrt", "kcf"], default="csrt")
    ap.add_argument("--redetect", type=float, default=3.0,
                    help="seconds between background re-detections, 0 = off")
    ap.add_argument("--mic", type=int, default=None)
    ap.add_argument("--say", default=None,
                    help="skip the microphone; the button searches for this")
    ap.add_argument("--show", action="store_true",
                    help="open a window (needs a monitor on the Pi)")
    ap.add_argument("--mute", action="store_true")
    ap.add_argument("--secs", type=float, default=0.0, help="auto-quit after N s")
    args = ap.parse_args()

    out = Haptics(args.out, mute=args.mute)
    events = queue.Queue()
    PushButton(events)

    listener = None
    if args.say is None:
        try:
            from listen import Listener
            listener = Listener(args.model,
                                args.mic if args.mic is not None else "auto")
            if listener.device_index is None:
                print("no microphone; plug one in or use --say", flush=True)
        except Exception as e:
            print(f"speech unavailable ({e}); use --say", flush=True)
            listener = None
    from listen import to_noun

    from detect_lite import Detector, MODEL
    detector = Detector(args.detector or MODEL)

    cam = args.cam if args.cam is not None else pick_camera()
    if cam is None:
        print("No camera delivers frames. Is the webcam plugged into the Pi?")
        return
    cap = open_camera(cam, args.width, args.height)
    make = cv2.TrackerKCF_create if args.tracker == "kcf" else None

    track = WristTracker()
    stage = IDLE
    lock = None
    anchor = None
    phrase = ""
    prev = None              # (t, x, y)
    last_cross = 0.0
    last_signal = 0.0
    in_band = 0
    crossings = 0
    times = collections.deque(maxlen=30)

    def reset():
        nonlocal stage, lock, anchor, prev, crossings, in_band
        if anchor is not None:
            anchor.close()
        stage, lock, anchor, prev, crossings, in_band = IDLE, None, None, None, 0, 0

    def search(frame, said):
        nonlocal stage, lock, anchor, phrase, last_signal, prev
        reset()
        phrase = to_noun(said or "")
        if not phrase:
            print("did not catch that", flush=True)
            out.miss()
            return
        print(f"looking for {phrase!r} ...", flush=True)
        t0 = time.perf_counter()
        r = detector.find(frame, phrase)
        print(f"  detect took {time.perf_counter()-t0:.2f}s", flush=True)
        if r is None:
            print(f"cannot see a {phrase}", flush=True)
            out.miss()
            return
        lock = Lock(frame, r[3], phrase, r[2], make=make)
        if args.redetect > 0:
            anchor = Anchor(detector, phrase, period=args.redetect)
        stage = FOUND
        last_signal = time.perf_counter()
        print(f"{phrase} locked (score {r[2]:.2f}) - line up vertically",
              flush=True)
        out.lock()

    def press(frame, kind):
        nonlocal stage
        if kind == "long":
            print("reset", flush=True)
            out.clear()
            if stage == LISTENING and listener is not None:
                listener.stop()
            reset()
            out.pulses(2, 60)
            return
        if listener is None or listener.device_index is None:
            if args.say:
                search(frame, args.say)
            else:
                out.miss()
            return
        if stage != LISTENING:
            reset()
            out.clear()
            out.tick()
            stage = LISTENING
            print("listening", flush=True)
            listener.start()
        else:
            out.tick()
            said = listener.stop()
            print(f"heard: {said!r}", flush=True)
            stage = IDLE
            search(frame, said)

    if args.show:
        cv2.namedWindow("crosshair", cv2.WINDOW_NORMAL)
    t_quit = time.perf_counter() + args.secs if args.secs else None
    print("ready - press the button and say what you want", flush=True)
    out.ready()

    while True:
        t0 = time.perf_counter()
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]

        try:
            while True:
                press(frame, events.get_nowait())
        except queue.Empty:
            pass

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        hit = track(rgb)

        if lock is not None:
            if anchor is not None:
                fresh = anchor.take()
                if fresh is not None:
                    # Re-seed on the detector's answer; the only cure for drift.
                    lock = Lock(frame, fresh[0], phrase, fresh[1], make=make)
                anchor.offer(frame)
            if not lock.update(frame):
                print(f"lost the {phrase}", flush=True)
                reset()
                out.lost()

        times.append(time.perf_counter() - t0)
        now = time.perf_counter()

        if hit and lock is not None:
            wx, wy, _vis = hit
            bx, by, bw, bh = lock.bbox
            tx = (bx + bw / 2) / w
            ty = (by + bh / 2) / h
            half = max(0.03, 0.3 * bh / h)      # middle of the object, not its edge
            if prev is not None and now - prev[0] > 1e-4:
                dt = now - prev[0]
                vx = (wx - prev[1]) / dt
                vy = (wy - prev[2]) / dt
                lead = float(np.mean(times))    # fire where the hand WILL be

                if stage == FOUND and now - last_signal > SETTLE_S:
                    in_band = in_band + 1 if abs(wy + vy * lead - ty) < half else 0
                    if in_band >= BAND_FRAMES:
                        stage, last_signal = LEVEL, now
                        print("  level - now sweep", flush=True)
                        out.aligned()

                elif stage in (LEVEL, ON) and now - last_signal > SETTLE_S / 2:
                    a = prev[1] + vx * lead
                    b = wx + vx * lead
                    if ((a - tx) * (b - tx) <= 0 and abs(vx) > MIN_SPEED
                            and now - last_cross > RE_ARM_S):
                        last_cross = now
                        crossings += 1
                        stage = ON
                        out.cross()
                        print(f"  CROSS #{crossings} at x={wx:.3f}", flush=True)
            prev = (now, wx, wy)
        elif not hit:
            prev = None

        if t_quit and now > t_quit:
            break
        if not args.show:
            continue

        if lock is not None:
            c = COLOUR.get(stage, RED)
            x, y, bw, bh = lock.bbox
            cv2.rectangle(frame, (x, y), (x + bw, y + bh), c, 3)
            cv2.line(frame, (x + bw // 2, 0), (x + bw // 2, h), c, 1)
            if stage >= LEVEL:
                cv2.line(frame, (0, y + bh // 2), (w, y + bh // 2), c, 1)
            cv2.putText(frame, phrase, (x, max(18, y - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, c, 2)
        if hit:
            cv2.circle(frame, (int(hit[0] * w), int(hit[1] * h)), 12,
                       (255, 255, 0), 3)
        ms = 1000 * float(np.mean(times)) if times else 0
        label = "LISTENING" if stage == LISTENING else f"{ms:4.0f} ms/frame"
        cv2.putText(frame, label, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 255, 255), 2)
        cv2.imshow("crosshair", frame)
        k = cv2.waitKey(1) & 0xFF
        if k == ord('q'):
            break
        if k == ord(' '):
            events.put("short")
        if k == ord('r'):
            events.put("long")

    reset()
    cap.release()
    if args.show:
        cv2.destroyAllWindows()
    if listener is not None:
        listener.close()


if __name__ == "__main__":
    main()
