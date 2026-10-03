"""Headless field-of-view gate. No window needed.

Wear/hold the camera where it will sit, sweep an arm left to right, and this
says whether the lens can actually follow the hand across the sweep.
"""
import sys, time
import cv2, numpy as np
from sweep import WristTracker, pick_camera

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0
cam = int(sys.argv[2]) if len(sys.argv) > 2 else pick_camera()

cap = cv2.VideoCapture(cam)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
for _ in range(10): cap.read()

delay = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
if delay:
    t0 = time.time()
    while time.time() - t0 < delay:      # countdown so the human can get ready
        cap.read()

tr = WristTracker()
xs, ys, seen = [], [], []
t_end = time.time() + secs
while time.time() < t_end:
    ok, f = cap.read()
    if not ok: continue
    f = cv2.flip(f, 1)
    rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB); rgb.flags.writeable = False
    r = tr(rgb)
    seen.append(bool(r))
    if r:
        xs.append(r[0]); ys.append(r[1])
cap.release()

n = len(seen); hit = sum(seen)
print(f"frames            {n}")
print(f"wrist visible     {hit}/{n} = {100*hit/max(n,1):.0f}%")
if xs:
    span = max(xs) - min(xs)
    print(f"wrist x travelled {min(xs):.2f} .. {max(xs):.2f}   span {span:.2f} of frame width")
    print(f"wrist y range     {min(ys):.2f} .. {max(ys):.2f}")
    # longest unbroken run with no wrist = how long the hand was outside the lens
    worst = run = 0
    for s in seen:
        run = 0 if s else run + 1
        worst = max(worst, run)
    print(f"longest dropout   {worst} frames (~{worst/30:.2f} s)")
    print()
    if span >= 0.55 and hit/max(n,1) > 0.85 and worst < 8:
        print("PASS. The lens follows the hand across the sweep.")
    elif span < 0.35:
        print("INCONCLUSIVE. The hand barely moved across frame. Sweep wider,")
        print("or the camera is too far from the body.")
    else:
        print("FAIL. The hand leaves the lens mid-sweep.")
        print("Move the mount up toward the collarbone and angle it down harder.")
else:
    print("No wrist seen at all. Is the camera pointing at you?")
