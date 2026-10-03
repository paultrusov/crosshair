"""Open-vocabulary object detection. Say any word, get a bearing.

This is the part Google Lookout cannot do. Lookout's Find mode works on seven
fixed categories. OWL-ViT takes the literal string the user said, so "ketchup"
and "my blue mug" are both expressible.

Runs locally on Metal. No API key, no internet, nothing to fail on conference
wifi while a judge is watching.

Called ONCE, at lock. The object is not moving; only the hand is. Running a
detector per frame would cost the whole latency budget for nothing.
"""
import time

import numpy as np
import torch
from PIL import Image
from transformers import Owlv2Processor, Owlv2ForObjectDetection

MODEL = "google/owlv2-base-patch16-ensemble"


class Detector:
    def __init__(self, model=MODEL, device=None):
        if device is None:
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.device = device
        print(f"loading {model} on {device} ...", flush=True)
        t0 = time.time()
        self.proc = Owlv2Processor.from_pretrained(model)
        self.model = Owlv2ForObjectDetection.from_pretrained(model).to(device).eval()
        print(f"detector ready in {time.time()-t0:.1f}s", flush=True)

    @torch.no_grad()
    def find(self, frame_bgr, phrase, threshold=0.12):
        """Return (cx, cy, score, box) in normalised coords, or None.

        cx is what the sweep compares against. Everything else is for drawing
        and for the writeup.
        """
        h, w = frame_bgr.shape[:2]
        img = Image.fromarray(frame_bgr[:, :, ::-1])
        # Several phrasings of the same thing: OWL-ViT is sensitive to the
        # prompt, and "a photo of X" is what it was trained against.
        queries = [f"a photo of a {phrase}", f"a {phrase}", phrase]
        inp = self.proc(text=[queries], images=img, return_tensors="pt").to(self.device)
        out = self.model(**inp)
        res = self.proc.post_process_grounded_object_detection(
            outputs=out,
            target_sizes=torch.tensor([[h, w]]).to(self.device),
            threshold=threshold,
        )[0]
        if len(res["scores"]) == 0:
            return None
        i = int(torch.argmax(res["scores"]))
        x0, y0, x1, y1 = [float(v) for v in res["boxes"][i]]
        return (
            ((x0 + x1) / 2) / w,
            ((y0 + y1) / 2) / h,
            float(res["scores"][i]),
            (x0 / w, y0 / h, x1 / w, y1 / h),
        )


if __name__ == "__main__":
    import sys, cv2
    from sweep import pick_camera

    phrases = sys.argv[1:] or ["water bottle", "laptop", "chair", "person"]
    cam = pick_camera()
    cap = cv2.VideoCapture(cam)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    frame = None
    for _ in range(15):
        ok, f = cap.read()
        if ok and f is not None:
            frame = f                  # keep the last GOOD frame, not the last
    cap.release()                      # read, which can be a failed one
    if frame is None:
        print("camera gave no frames"); sys.exit(1)
    cv2.imwrite("/tmp/detect_frame.jpg", frame)
    print(f"frame {frame.shape[1]}x{frame.shape[0]} saved to /tmp/detect_frame.jpg\n")

    d = Detector()
    for p in phrases:
        t0 = time.time()
        r = d.find(frame, p)
        dt = time.time() - t0
        if r:
            print(f"  {p:22} -> x={r[0]:.3f} y={r[1]:.3f} score={r[2]:.3f}  [{dt:.2f}s]")
        else:
            print(f"  {p:22} -> not found                        [{dt:.2f}s]")
