"""Record a session of arm movement for offline analysis.

Saves the video plus every joint position per frame, so the question "when is
the arm pointing at the thing" can be answered against real data instead of
guessed at. Captures both arms and the full shoulder-elbow-wrist-index chain,
because the current rule (wrist x crosses the target x) is only one candidate.
Others worth testing: the elbow-to-wrist ray, the shoulder-to-wrist ray, and
the index fingertip.

    python record.py 30 sweep1       # 30 seconds, writes sessions/sweep1.*
"""
import json
import os
import sys
import time

import cv2
import mediapipe as mp

from sweep import pick_camera, open_camera

L = mp.solutions.pose.PoseLandmark
POINTS = {
    "l_shoulder": L.LEFT_SHOULDER, "r_shoulder": L.RIGHT_SHOULDER,
    "l_elbow": L.LEFT_ELBOW,       "r_elbow": L.RIGHT_ELBOW,
    "l_wrist": L.LEFT_WRIST,       "r_wrist": L.RIGHT_WRIST,
    "l_index": L.LEFT_INDEX,       "r_index": L.RIGHT_INDEX,
    "l_thumb": L.LEFT_THUMB,       "r_thumb": L.RIGHT_THUMB,
    "l_pinky": L.LEFT_PINKY,       "r_pinky": L.RIGHT_PINKY,
    "nose": L.NOSE,
}


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    name = sys.argv[2] if len(sys.argv) > 2 else time.strftime("%H%M%S")
    here = os.path.dirname(os.path.abspath(__file__))
    outdir = os.path.join(here, "sessions")
    os.makedirs(outdir, exist_ok=True)

    cap = open_camera(pick_camera())
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    vid = cv2.VideoWriter(os.path.join(outdir, name + ".mp4"),
                          cv2.VideoWriter_fourcc(*"mp4v"), 30, (w, h))
    jf = open(os.path.join(outdir, name + ".jsonl"), "w")

    pose = mp.solutions.pose.Pose(model_complexity=1,     # 1, not 0: this is
                                  min_detection_confidence=0.5,   # analysis,
                                  min_tracking_confidence=0.5,    # not the
                                  smooth_landmarks=True)          # hot path

    print(f">>> RECORDING {secs:.0f}s to sessions/{name} <<<", flush=True)
    t0 = time.perf_counter()
    n = 0
    while time.perf_counter() - t0 < secs:
        ok, frame = cap.read()
        if not ok:
            continue
        frame = cv2.flip(frame, 1)
        vid.write(frame)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        res = pose.process(rgb)
        row = {"i": n, "t": round(time.perf_counter() - t0, 4)}
        if res.pose_landmarks:
            lm = res.pose_landmarks.landmark
            for key, idx in POINTS.items():
                p = lm[idx]
                row[key] = [round(p.x, 4), round(p.y, 4), round(p.z, 4),
                            round(p.visibility, 3)]
        jf.write(json.dumps(row) + "\n")
        n += 1
    cap.release(); vid.release(); jf.close()
    dur = time.perf_counter() - t0
    print(f"done: {n} frames in {dur:.1f}s = {n/dur:.1f} fps")
    print(f"  sessions/{name}.mp4  sessions/{name}.jsonl")


if __name__ == "__main__":
    main()
