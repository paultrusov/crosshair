"""Hour-1 gate: can the camera see a hand sweep across a counter?

Run it, strap/hold the camera where it will sit on the chest, and sweep your
arm left to right at normal reaching distance. Watch the two numbers.

  IN FRAME  -> the wrist is visible, good
  LOST      -> the wrist left the frame, the sweep is wider than the lens

If you cannot keep the wrist in frame across a 60cm sweep, no amount of code
fixes it. Move the mount up toward the collarbone, angle it down harder, or
get a wider lens.
"""
import sys, time
import cv2

def list_cameras(max_idx=6):
    found = []
    for i in range(max_idx):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok:
                found.append((i, frame.shape[1], frame.shape[0]))
            cap.release()
    return found

def main():
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if idx is None:
        cams = list_cameras()
        if not cams:
            print("No camera found. Plug the webcam in.")
            return
        print("Cameras found (index, width, height):")
        for c in cams:
            print("  ", c)
        idx = cams[-1][0]
        print(f"\nUsing index {idx}. Pass a different index as an argument to override.")

    cap = cv2.VideoCapture(idx)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Capturing {w}x{h}. Press q to quit.")

    t0, n, fps = time.time(), 0, 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        n += 1
        if n % 10 == 0:
            fps = 10.0 / (time.time() - t0)
            t0 = time.time()

        # centre line and third-markers, so you can see how much arc you have
        cv2.line(frame, (w // 2, 0), (w // 2, h), (0, 255, 0), 1)
        for frac in (0.15, 0.85):
            x = int(w * frac)
            cv2.line(frame, (x, 0), (x, h), (0, 140, 255), 1)
        cv2.putText(frame, f"{w}x{h}  {fps:4.1f} fps", (12, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(frame, "sweep your hand between the orange lines", (12, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 140, 255), 2)

        cv2.imshow("camera check", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
