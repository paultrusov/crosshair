"""Crosshair, end to end.

    python main.py                 laptop beeps, no Pi needed
    python main.py --host crosshair.local     beeps come from the Pi

    SPACE  press, say what you want, press again
    r      reset
    q      quit

The flow, and why it is in this order:
  1. You say what you want.               (whisper, local)
  2. We find it ONCE and remember where.  (owl-vit, local, ~1s)
  3. Two high beeps: found it.
  4. You sweep. One low beep the instant your hand crosses its bearing.
  5. You reach. Pulses speed up as your hand closes in.

The object does not move; only your hand does. So the detector runs once and
the fast loop only tracks a wrist. That is what keeps the beep on time.
"""
import os

# faster-whisper (ctranslate2) and torch each link their own OpenMP runtime.
# Loading both in one process aborts with "OMP: Error #15" unless this is set
# BEFORE either import, which is why it is the first thing in the file.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "4")

import argparse
import collections
import time

import cv2
import numpy as np

from sweep import WristTracker, pick_camera
from box_client import Box
from tones import Tones
from listen import Listener, to_noun

RE_ARM_S = 0.45
MIN_SPEED = 0.03


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=None, help="Pi running buzzbox.py")
    ap.add_argument("--cam", type=int, default=None)
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--mic", default=None, type=int,
                    help="input device index; default is the camera's own mic")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--say", default=None,
                    help="skip the microphone and search for this instead")
    ap.add_argument("--secs", type=float, default=0.0)
    args = ap.parse_args()

    box = Box(args.host, on_button=None) if args.host else Tones()
    listener = Listener(args.model,
                        args.mic if args.mic is not None else "auto")
    from detect import Detector
    detector = Detector()

    cam = args.cam if args.cam is not None else pick_camera()
    cap = cv2.VideoCapture(cam)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    track = WristTracker()
    target = None           # (x, y) of the thing, normalised
    phrase = ""
    prev = None
    last_cross = 0.0
    crossings = 0
    recording = False
    times = collections.deque(maxlen=30)
    status = "press SPACE, say what you want, press SPACE again"

    def search(frame, said):
        nonlocal target, phrase, crossings, status, prev
        phrase = to_noun(said)
        if not phrase:
            status = "did not catch that"
            return
        status = f"looking for {phrase!r} ..."
        print(status, flush=True)
        r = detector.find(frame, phrase)
        if r is None:
            target, status = None, f"cannot see a {phrase}"
            box.beep(300, 220)                   # one low note = not found
        else:
            target = (r[0], r[1])
            crossings, prev = 0, None
            status = f"{phrase} at x={r[0]:.2f} (score {r[2]:.2f}) - sweep now"
            box.lock()
        print(status, flush=True)

    if not args.headless:
        cv2.namedWindow("crosshair")
    t_quit = time.perf_counter() + args.secs if args.secs else None

    if args.say:                                  # scripted run, no microphone
        ok, frame = cap.read()
        for _ in range(10):
            ok, frame = cap.read()
        search(cv2.flip(frame, 1), args.say)

    while True:
        t0 = time.perf_counter()
        ok, frame = cap.read()
        if not ok:
            continue
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        hit = track(rgb)
        times.append(time.perf_counter() - t0)
        now = time.perf_counter()

        if hit and target is not None:
            wx, wy, _vis = hit
            px, py = int(wx * w), int(wy * h)
            cv2.circle(frame, (px, py), 14, (0, 255, 255), 3)

            if prev is not None:
                dt = now - prev[0]
                if dt > 1e-4:
                    vx = (wx - prev[1]) / dt
                    lead = float(np.mean(times))
                    a = prev[1] + vx * lead
                    b = wx + vx * lead
                    if ((a - target[0]) * (b - target[0]) <= 0
                            and abs(vx) > MIN_SPEED
                            and now - last_cross > RE_ARM_S):
                        last_cross = now
                        crossings += 1
                        box.cross()
                        print(f"  CROSS #{crossings} at x={wx:.3f}", flush=True)
            # distance proxy: how near the hand is to the object in frame
            d = np.hypot(wx - target[0], wy - target[1])
            box.rate(float(np.clip(1.0 - d / 0.45, 0.0, 1.0)))
            prev = (now, wx)
        elif target is not None:
            box.rate(0.0)

        if target is not None:
            tx, ty = int(target[0] * w), int(target[1] * h)
            cv2.line(frame, (tx, 0), (tx, h), (0, 0, 255), 2)
            cv2.circle(frame, (tx, ty), 10, (0, 0, 255), 2)

        ms = 1000 * float(np.mean(times)) if times else 0
        cv2.putText(frame, f"{1000/max(ms,1):4.1f} fps  {ms:4.1f} ms  "
                           f"crossings {crossings}", (12, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, "RECORDING" if recording else status, (12, h - 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 0, 255) if recording else (0, 200, 255), 2)

        if t_quit and time.perf_counter() > t_quit:
            break
        if args.headless:
            continue

        cv2.imshow("crosshair", frame)
        k = cv2.waitKey(1) & 0xFF
        if k == ord('q'):
            break
        if k == ord('r'):
            target, prev, crossings = None, None, 0
            box.stop(); status = "press SPACE, say what you want, press again"
        if k == ord(' '):
            # OpenCV windows give no key-up event, so SPACE toggles rather
            # than holds: press to start talking, press again when done.
            if not recording:
                recording = True
                box.stop()
                status = "listening"
                listener.start()
            else:
                recording = False
                said = listener.stop()
                print(f"heard: {said!r}", flush=True)
                search(frame, said)

    cap.release()
    cv2.destroyAllWindows()
    box.stop()


if __name__ == "__main__":
    main()
