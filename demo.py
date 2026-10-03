"""Filmable demo. The operator drives the stages from the keyboard.

Camera on the head, laptop carried behind, no audio. The detection and the
tracking are real; only the stage transitions are triggered by hand, so the
video shows the interaction at the pace a person actually performs it.

    python demo.py

    Q    the query "water bottle" types itself, then the real detector runs
    W    horizontal pass registered  -> indicator turns YELLOW
    E    vertical pass registered    -> indicator turns GREEN
    R    reset to the start
    ESC  quit            (never q: q is a stage trigger)

Records from the moment it starts, to sessions/demo-<time>.mp4
"""
import os
import time

import cv2
import numpy as np

from sweep import pick_camera, open_camera
from track import Lock
from redetect import Anchor

QUERY = "water bottle"

RED = (60, 60, 235)
YELLOW = (60, 215, 245)
GREEN = (90, 220, 90)
WHITE = (255, 255, 255)
GREY = (140, 140, 140)

STAGES = [
    ("idle",       GREY,   ""),
    ("searching",  WHITE,  "searching"),
    ("found",      RED,    "found it - sweep left to right"),
    ("horizontal", YELLOW, "on target - now sweep up and down"),
    ("vertical",   GREEN,  "reach"),
]


def banner(frame, colour, text, w, h):
    """A bar the camera can actually read back on a shaky head-mounted shot."""
    cv2.rectangle(frame, (0, 0), (w, 64), (24, 24, 24), -1)
    cv2.rectangle(frame, (0, 60), (w, 64), colour, -1)
    if text:
        cv2.putText(frame, text, (22, 43), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, colour, 2, cv2.LINE_AA)
    cv2.circle(frame, (w - 44, 32), 16, colour, -1)


def type_in(frame, shown, w, h):
    cv2.rectangle(frame, (0, h - 76), (w, h), (24, 24, 24), -1)
    cv2.putText(frame, "> " + shown, (22, h - 28), cv2.FONT_HERSHEY_SIMPLEX,
                1.1, WHITE, 2, cv2.LINE_AA)


def main():
    from detect import Detector
    detector = Detector()

    cap = open_camera(pick_camera())
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    os.makedirs("sessions", exist_ok=True)
    name = time.strftime("demo-%H%M%S")
    writer = cv2.VideoWriter(f"sessions/{name}.mp4",
                             cv2.VideoWriter_fourcc(*"mp4v"), 30, (w, h))
    print(f"recording to sessions/{name}.mp4", flush=True)

    cv2.namedWindow("crosshair", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("crosshair", w, h)

    stage = 0
    lock = None
    anchor = None           # background re-detection, keeps the box honest
    typed_chars = 0          # how much of QUERY has "appeared" so far
    type_started = None
    searched = False

    while True:
        ok, frame = cap.read()
        if not ok:
            continue
        frame = cv2.flip(frame, 1)

        # the query types itself out, one character at a time
        if type_started is not None:
            elapsed = time.perf_counter() - type_started
            typed_chars = min(len(QUERY), int(elapsed / 0.055))
            if typed_chars == len(QUERY) and not searched:
                searched = True
                r = detector.find(frame, QUERY)
                if r is not None:
                    lock = Lock(frame, r[3], QUERY, r[2])
                    anchor = Anchor(detector, QUERY)
                    stage = 2
                    print(f"locked {QUERY} score {r[2]:.2f}", flush=True)
                else:
                    stage = 1
                    searched = False       # keep trying on later frames

        if lock is not None:
            lock.update(frame)

        if anchor is not None:
            fresh = anchor.take()
            if fresh is not None:
                box, score = fresh
                # Re-seed the tracker on the detector's answer. Cheap, and it
                # is the only thing that can undo drift.
                lock = Lock(frame, box, QUERY, score)
            anchor.offer(frame)

        name_, colour, text = STAGES[stage]

        if lock is not None:
            x, y, bw, bh = lock.bbox
            cv2.rectangle(frame, (x, y), (x + bw, y + bh), colour, 3)
            cx = x + bw // 2
            cy = y + bh // 2
            cv2.line(frame, (cx, 0), (cx, h), colour, 2)
            if stage >= 3:
                cv2.line(frame, (0, cy), (w, cy), colour, 2)
            cv2.putText(frame, QUERY, (x, max(22, y - 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, colour, 2, cv2.LINE_AA)

        banner(frame, colour, text, w, h)
        if type_started is not None:
            type_in(frame, QUERY[:typed_chars], w, h)

        writer.write(frame)
        cv2.imshow("crosshair", frame)
        k = cv2.waitKey(1) & 0xFF

        if k == 27:                       # ESC
            break
        elif k == ord('q') and type_started is None:
            type_started = time.perf_counter()
            stage = 1
        elif k == ord('w') and lock is not None:
            stage = 3
        elif k == ord('e') and lock is not None:
            stage = 4
        elif k == ord('r'):
            if anchor is not None:
                anchor.close()
            stage, lock, anchor, typed_chars = 0, None, None, 0
            type_started, searched = None, False

    if anchor is not None:
        anchor.close()
    cap.release(); writer.release(); cv2.destroyAllWindows()
    print(f"saved sessions/{name}.mp4", flush=True)


if __name__ == "__main__":
    main()
