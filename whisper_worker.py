"""Whisper in its own process.

Why: faster-whisper (ctranslate2) and torch each link a separate OpenMP
runtime. In one process they do not merely warn, they deadlock on model load.
KMP_DUPLICATE_LIB_OK silences the warning and does not fix the hang.

Protocol: a wav path per line on stdin, one line of transcript per line out.
Loads the model once and stays warm, so a transcription costs ~0.5s, not the
8s a fresh subprocess would.
"""
import sys

from faster_whisper import WhisperModel


def main():
    model_name = sys.argv[1] if len(sys.argv) > 1 else "small.en"
    m = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=4)
    print("READY", flush=True)
    for line in sys.stdin:
        path = line.strip()
        if not path:
            continue
        try:
            segs, _ = m.transcribe(path, beam_size=1, language="en",
                                   vad_filter=True)
            print(" ".join(s.text for s in segs).strip().replace("\n", " "),
                  flush=True)
        except Exception as e:
            print(f"ERR {e}", flush=True)


if __name__ == "__main__":
    main()
