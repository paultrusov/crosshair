"""The core interaction, with the target set by hand.

This is the hour-6 deliverable. It proves the loop works before any object
detection exists, which is deliberate: if the crossing does not feel right
with a target you placed yourself, it will never feel right with one the
detector placed.

    python sweep.py --host 192.168.2.2        # Pi address, omit to run silent

Keys
    click   put the target where you clicked
    space   put the target at the wrist's current position
    r       reset
    q       quit
"""
import argparse
import collections
import time

import cv2
import numpy as np
import mediapipe as mp

from box_client import Box

RE_ARM_S = 0.45          # ignore a second crossing this soon after one
MIN_SPEED = 0.03         # frac of width per second, below this it is not a sweep


class WristTracker:
    """MediaPipe Pose, right and left wrist, whichever is more confident.

    Pose rather than Hands on purpose: at arm's length, with motion blur, and
    with the hand often turned away from a chest camera, Hands drops out and
    Pose does not.
    """

    def __init__(self):
        self.pose = mp.solutions.pose.Pose(
            model_complexity=0,              # fastest, we only need a wrist
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            smooth_landmarks=True,
        )

    def __call__(self, rgb):
        res = self.pose.process(rgb)
        if not res.pose_landmarks:
            return None
        lm = res.pose_landmarks.landmark
        L = mp.solutions.pose.PoseLandmark
        best, best_v = None, 0.0
        for side in (L.RIGHT_WRIST, L.LEFT_WRIST):
            p = lm[side]
            if p.visibility > best_v:
                best, best_v = p, p.visibility
        if best is None or best_v < 0.4:
            return None
        return float(best.x), float(best.y), float(best_v)


def pick_camera(max_idx=5):
    """Return the camera index that delivers a real picture.

    Two traps on this Mac, both of which look like a broken build:
      - index 0 opens and then hands back no frames at all (Continuity camera)
      - another index reads fine but every frame is black (lens covered)
    So opening is not evidence, and neither is reading. Score on image
    variance and take the liveliest.
    """
    best, best_score = None, 0.0
    for i in range(max_idx):
        cap = cv2.VideoCapture(i)
        score = 0.0
        if cap.isOpened():
            got = None
            for _ in range(12):            # let auto-exposure settle first,
                ok, f = cap.read()         # a cold first frame scores near zero
                if ok:
                    got = f
            if got is not None:
                score = float(np.std(got))
        cap.release()
        if score > best_score:
            best, best_score = i, score
    if best is not None:
        print(f"camera {best} (variance {best_score:.1f})")
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=None, help="Pi address running buzzbox.py")
    ap.add_argument("--cam", type=int, default=None,
                    help="camera index, default = auto-pick one that reads")
    ap.add_argument("--lead", type=float, default=0.0,
                    help="seconds of pipeline latency to fire early by")
    args = ap.parse_args()

    box = Box(args.host) if args.host else None

    cam = args.cam if args.cam is not None else pick_camera()
    if cam is None:
        print("No camera delivers frames. Check the cable and the macOS "
              "camera permission for your terminal.")
        return
    cap = cv2.VideoCapture(cam)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)        # latency, not smoothness
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    track = WristTracker()

    target = None            # normalised x of the thing we are pointing at
    last_cross = 0.0
    prev = None              # (t, x)
    frame_times = collections.deque(maxlen=30)
    crossings = 0

    def on_mouse(event, mx, my, flags, _):
        nonlocal target, crossings
        if event == cv2.EVENT_LBUTTONDOWN:
            target = mx / float(w)
            crossings = 0
            if box:
                box.lock()

    cv2.namedWindow("crosshair")
    cv2.setMouseCallback("crosshair", on_mouse)

    while True:
        t_cap = time.perf_counter()
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)             # mirror, so left is left
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        hit = track(rgb)
        t_done = time.perf_counter()
        frame_times.append(t_done - t_cap)

        now = time.perf_counter()
        wx = None
        if hit:
            wx, wy, vis = hit
            px, py = int(wx * w), int(wy * h)
            cv2.circle(frame, (px, py), 14, (0, 255, 255), 3)
            cv2.circle(frame, (px, py), 2, (0, 255, 255), -1)

            if target is not None and prev is not None:
                dt = now - prev[0]
                if dt > 1e-4:
                    vx = (wx - prev[1]) / dt                 # frac width / s
                    # Fire where the hand WILL be when the sound actually lands.
                    lead = args.lead + float(np.mean(frame_times))
                    pred_now = wx + vx * lead
                    pred_prev = prev[1] + vx * lead
                    crossed = (pred_prev - target) * (pred_now - target) <= 0
                    if (crossed and abs(vx) > MIN_SPEED
                            and now - last_cross > RE_ARM_S):
                        last_cross = now
                        crossings += 1
                        if box:
                            box.cross()
                        cv2.circle(frame, (int(target * w), py), 40,
                                   (0, 0, 255), 4)
            prev = (now, wx)

        if target is not None:
            tx = int(target * w)
            cv2.line(frame, (tx, 0), (tx, h), (0, 0, 255), 2)
            cv2.putText(frame, "TARGET", (tx + 8, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        ms = 1000.0 * float(np.mean(frame_times)) if frame_times else 0.0
        fps = 1000.0 / ms if ms else 0.0
        hud = f"{fps:4.1f} fps   pipeline {ms:5.1f} ms   crossings {crossings}"
        cv2.putText(frame, hud, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (255, 255, 255), 2)
        if not hit:
            cv2.putText(frame, "NO WRIST", (12, 64), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (0, 0, 255), 2)
        if target is None:
            cv2.putText(frame, "click to place a target", (12, h - 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

        cv2.imshow("crosshair", frame)
        k = cv2.waitKey(1) & 0xFF
        if k == ord('q'):
            break
        if k == ord('r'):
            target, prev, crossings = None, None, 0
            if box:
                box.stop()
        if k == ord(' ') and wx is not None:
            target, crossings = wx, 0
            if box:
                box.lock()

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
