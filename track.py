"""Keep a lock on the object while the camera moves.

The one-shot detection insight was right about the object and wrong about the
camera: the object does not move, but the camera is strapped to a person's
chest, so the object's bearing in frame changes constantly. Caching a bearing
at lock time means the dot drifts off the thing the moment you breathe.

Re-running the detector per frame is not an option at ~900 ms a go. So the
detector runs once to say WHAT and WHERE, and a correlation tracker follows
it at ~9 ms a frame from there. Detector for identity, tracker for position.
"""
import cv2


class Lock:
    """A tracked object. `centre` is what the sweep compares a wrist against."""

    def __init__(self, frame, box_norm, phrase, score, make=None):
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = box_norm
        self.phrase = phrase
        self.score = score
        self.alive = True
        self.lost_frames = 0
        bbox = (int(x0 * w), int(y0 * h),
                max(8, int((x1 - x0) * w)), max(8, int((y1 - y0) * h)))
        # make: a tracker factory. CSRT by default; the Pi build can pass KCF,
        # which is several times cheaper and drifts more.
        self.tracker = (make or cv2.TrackerCSRT_create)()
        self.tracker.init(frame, bbox)
        self.bbox = bbox
        self._wh = (w, h)

    @property
    def centre(self):
        x, y, bw, bh = self.bbox
        w, h = self._wh
        return (x + bw / 2) / w, (y + bh / 2) / h

    def update(self, frame):
        ok, bbox = self.tracker.update(frame)
        if ok:
            self.bbox = tuple(int(v) for v in bbox)
            self.lost_frames = 0
        else:
            # Hold the last known position rather than dropping the lock the
            # instant a hand passes in front of it, which happens on every
            # single sweep by design.
            self.lost_frames += 1
            if self.lost_frames > 45:
                self.alive = False
        return self.alive

    def draw(self, frame):
        x, y, bw, bh = self.bbox
        colour = (0, 0, 255) if self.lost_frames == 0 else (0, 140, 255)
        cv2.rectangle(frame, (x, y), (x + bw, y + bh), colour, 2)
        cx = x + bw // 2
        cv2.line(frame, (cx, 0), (cx, frame.shape[0]), colour, 2)
        label = self.phrase if self.lost_frames == 0 else f"{self.phrase}?"
        cv2.putText(frame, label, (x, max(18, y - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)
