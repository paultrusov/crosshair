"""Headless camera + tracker benchmark. No window, no interaction.

Prints the numbers the hour-6 gate asks for: real resolution, real end-to-end
latency, and whether a wrist is actually being found.
"""
import sys, time, collections
import cv2, numpy as np
from sweep import WristTracker

idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0

cap = cv2.VideoCapture(idx)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
if not cap.isOpened():
    print(f"camera index {idx} would not open"); sys.exit(1)

w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"camera {idx}: {w}x{h}  driver fps {cap.get(cv2.CAP_PROP_FPS)}")

tr = WristTracker()
grab, infer, total = [], [], []
hits = 0; n = 0; xs = []
t_end = time.time() + secs
while time.time() < t_end:
    a = time.perf_counter()
    ok, frame = cap.read()
    b = time.perf_counter()
    if not ok: break
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB); rgb.flags.writeable = False
    r = tr(rgb)
    c = time.perf_counter()
    grab.append(b-a); infer.append(c-b); total.append(c-a)
    n += 1
    if r: hits += 1; xs.append(r[0])
cap.release()

def ms(v):
    if not len(v): return "no frames"
    return f"{1000*np.mean(v):6.1f} ms   p95 {1000*np.percentile(v,95):6.1f} ms"
print(f"frames        {n}  over {secs:.0f}s  = {n/secs:5.1f} fps")
print(f"grab          {ms(grab)}")
print(f"pose infer    {ms(infer)}")
print(f"END TO END    {ms(total)}   <-- this is the lead-compensation number")
print(f"wrist found   {hits}/{n}  ({100*hits/max(n,1):.0f}%)")
if xs:
    print(f"wrist x range {min(xs):.2f} .. {max(xs):.2f}  (0=left edge, 1=right edge)")
