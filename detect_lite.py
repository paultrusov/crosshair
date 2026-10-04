"""Open-vocabulary detection sized for a Raspberry Pi 5 CPU.

Same contract as detect.Detector.find, so track.Lock and redetect.Anchor take
it unchanged. The difference is the model: detect.py runs OWLv2 base/16 at
960x960 on Metal; on a Pi CPU that is tens of seconds a query. OWL-ViT base/32
at 768x768 is roughly a tenth of the work and still takes any word you say.

    python detect_lite.py "water bottle" "mug"     # point the camera first
"""
import time

import numpy as np
import torch
from PIL import Image
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

MODEL = "google/owlvit-base-patch32"


class Detector:
    def __init__(self, model=MODEL, threads=3):
        # Leave a core for the camera loop. torch takes every core by default,
        # and the background re-detect would then starve pose tracking.
        torch.set_num_threads(threads)
        print(f"loading {model} on cpu ({threads} threads) ...", flush=True)
        t0 = time.time()
        self.proc = AutoProcessor.from_pretrained(model)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(model).eval()
        print(f"detector ready in {time.time()-t0:.1f}s", flush=True)

    def _post(self, out, h, w, threshold):
        sizes = torch.tensor([[h, w]])
        # The grounded name is the current one; older transformers only have
        # the plain one. Either returns scores and pixel boxes.
        fn = getattr(self.proc, "post_process_grounded_object_detection", None)
        if fn is not None:
            try:
                return fn(outputs=out, target_sizes=sizes, threshold=threshold)[0]
            except TypeError:
                pass
        return self.proc.post_process_object_detection(
            outputs=out, target_sizes=sizes, threshold=threshold)[0]

    @torch.inference_mode()
    def find(self, frame_bgr, phrase, threshold=0.1):
        """Return (cx, cy, score, box) in normalised coords, or None."""
        h, w = frame_bgr.shape[:2]
        img = Image.fromarray(np.ascontiguousarray(frame_bgr[:, :, ::-1]))
        queries = [f"a photo of a {phrase}", f"a {phrase}", phrase]
        inp = self.proc(text=[queries], images=img, return_tensors="pt")
        out = self.model(**inp)
        res = self._post(out, h, w, threshold)
        if len(res["scores"]) == 0:
            return None
        i = int(torch.argmax(res["scores"]))
        x0, y0, x1, y1 = [float(v) for v in res["boxes"][i]]
        x0, x1 = max(0.0, x0), min(float(w), x1)
        y0, y1 = max(0.0, y0), min(float(h), y1)
        return (
            ((x0 + x1) / 2) / w,
            ((y0 + y1) / 2) / h,
            float(res["scores"][i]),
            (x0 / w, y0 / h, x1 / w, y1 / h),
        )


if __name__ == "__main__":
    import sys, cv2
    from sweep import open_camera

    phrases = sys.argv[1:] or ["water bottle", "chair", "person"]
    cap = open_camera(0, 640, 480)
    frame = None
    for _ in range(15):
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
    cap.release()
    if frame is None:
        print("camera gave no frames"); sys.exit(1)
    d = Detector()
    for p in phrases:
        t0 = time.time()
        r = d.find(frame, p)
        dt = time.time() - t0
        if r:
            print(f"  {p:22} -> x={r[0]:.3f} y={r[1]:.3f} score={r[2]:.3f}  [{dt:.2f}s]")
        else:
            print(f"  {p:22} -> not found                        [{dt:.2f}s]")
