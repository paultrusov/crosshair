# Crosshair

A chest-worn camera that watches your own arm and tells you the moment your
hand crosses the thing you asked for.

Lookout does this for 7 fixed object categories with the phone in your hand.
This does it for any word you say, with both hands free.

## Split

- **Laptop is the brain.** Camera plugs in here, all vision runs here.
- **Pi is dumb on purpose.** It owns the buzzers and the button and nothing
  else. When something breaks you only have to ask "is the laptop sending it"
  or "is the Pi beeping", never both.
- **Wired, not wifi.** Use the ethernet adapter. Hackathon wifi is where
  timing bugs go to become unreproducible.

## Setup

Laptop (already done on Paul's Mac, env name `crosshair`):

    conda create -y -n crosshair python=3.11
    conda activate crosshair
    pip install mediapipe opencv-python numpy pyserial sounddevice

MediaPipe has no build for Python 3.13. The 3.11 env is not optional.

Pi:

    scp -r pi/ <user>@<pi>:~/crosshair-pi
    ssh <user>@<pi>
    cd ~/crosshair-pi && ./setup_pi.sh
    python3 buzzbox.py

## Standalone: no laptop (branch `standalone-pi`)

Everything on the Pi 5: webcam, mic, button and motor all plug into it, and it
starts by itself at boot. This is the flow from the writeup:

| Step | You feel | Box (with `--show`) |
|---|---|---|
| press the button, say the word, press again | one tick each press | |
| found and in frame | three vibrations | red |
| move your arm up or down until level with it | three vibrations | yellow |
| sweep sideways across it | one buzz each time you cross it | green |
| not found / lost the lock | one long / two long | |

Long press resets.

Wiring: motor (Grove vibration motor module, it has its own driver) or the
buzzer on **D5**, button on **D18**, USB webcam and USB mic (the Brio's own mic
works) in the Pi's USB ports. A bare FA-130 motor cannot run off a GPIO pin;
see Dead ends.

On the Pi, once, with internet:

    git clone -b standalone-pi https://github.com/paultrusov/crosshair
    cd crosshair && ./pi/setup_standalone.sh          # OUT=buzzer ./pi/... for the buzzer

Then test by hand and reboot:

    ~/crosshair-venv/bin/python haptics.py            # every signal, then the button
    ~/crosshair-venv/bin/python onboard.py            # Ctrl-C to stop
    sudo reboot                                       # now it runs at power-on
    journalctl -u crosshair -f                        # what it is doing

Do not run `buzzbox.py` at the same time; both want D5.

What it gives up to fit the Pi: OWL-ViT base/32 (`detect_lite.py`) instead of
OWLv2, 640x480 instead of 720p, background re-detect every 3 s instead of
1.2 s, whisper `base.en` instead of `small.en`. The crossing still fires early
by the measured loop time, which is longer on the Pi. None of the numbers in
"Measured on this hardware" apply to this build; measure it again on the Pi.

## Wiring

| Part      | Grove port | BCM |
|-----------|-----------|-----|
| Buzzer    | D5        | 5   |
| Button    | D18       | 18  |

## Run

    python main.py                      # the whole thing
    python main.py --host crosshair.local   # beeps from the Pi instead
    python main.py --voice              # the same beeps, plus spoken context

SPACE to talk, SPACE again when done. r resets, q quits.

To turn the speech on, copy `.env.example` to `.env`, put your key in
`XAI_API_KEY`, and run with `--voice`. With no key `--voice` still works and
speaks through macOS `say`, offline and free, so a demo cannot die of an expired
key. The beeps are identical either way, because they are the part that has to
be on time.

Parts, runnable alone when something is misbehaving:

    python camera_check.py              # which camera, and can it see a sweep
    python fov_test.py 15               # headless version of the same
    python bench.py                     # fps and end-to-end latency
    python listen.py 4                  # say something, see what it heard
    python detect.py "ketchup" "mug"    # point the camera, see what it finds
    python sweep.py                     # crossing logic with a hand-placed target
    python tones.py                     # just the sounds
    python speak.py                     # just the speech, out loud
    python speak.py --test              # proves the no-key fallback

## Sound design

| Signal | Meaning |
|---|---|
| two fast 1800Hz beeps | found it, start sweeping |
| one 700Hz beep | your hand is on it, now |
| pulse train, rising pitch and rate | closing in on the reach |

Beeps carry everything that is timed. Speech, with `--voice`, carries only what
a beep cannot say: which object it locked and roughly where it is, that it
cannot see the thing you asked for, and that it lost the lock. Nothing on the
crossing path goes through it, because a speech API round trip is two orders of
magnitude slower than the millisecond the crossing beep has to hit.

## Measured on this hardware

Logitech Brio 101 at 1280x720, on a MacBook whose conda is x86 under Rosetta,
so these are pessimistic:

| | |
|---|---|
| sustained | 29.8 fps |
| pose inference | 14.3 ms |
| **end to end** | **33.6 ms**, p95 36.3 ms |
| wrist found | 98% of frames |
| field of view | hand crossed 66% of frame width, 0 dropouts |
| open-vocab detection | ~0.9 s per query, run once at lock |

For comparison, YOLO nano on a Pi 5 is 67-128 ms for a *closed* 80-class
model. That gap is the whole reason the vision runs on the laptop.

Proof the open vocabulary claim is real: on a random frame of the hackathon
room it found a **thermostat** at 0.83 confidence. Thermostat is not a COCO
class and not one of Lookout's seven categories.

## Dead ends, do not revisit

- The two FA-130 motors in the kit. MLH had no motor driver board, and a Pi
  GPIO pin gives ~16 mA against the ~200 mA a motor wants. Buzzers replaced
  them. This is not a downgrade: the 2025 Scientific Reports study with 41
  blind participants found auditory guidance significantly *faster* than
  vibrotactile (4198 ms vs 4784 ms).
- Running the vision on the Pi. See the numbers above.
- The vertical sweep. From a sternum camera, how high an object looks is
  mostly a function of how far away it is. Distance goes on the pulse rate
  during the reach instead.

## Traps already paid for, do not rediscover

- **MediaPipe has no build for Python 3.13.** The 3.11 env is not optional.
- **This conda is x86 under Rosetta**, which caps torch at 2.2.2, which in
  turn caps transformers below 4.50.
- **faster-whisper and torch each link their own OpenMP.** In one process they
  do not warn, they deadlock on model load. `KMP_DUPLICATE_LIB_OK` silences
  the message and does not fix the hang. Whisper runs in its own process.
- **Intel MKL prints a banner to stdout**, so a subprocess handshake must scan
  for its marker rather than trust the first line.
- **Camera index 0 opens and returns no frames** (Continuity camera), another
  index returns all-black frames, and the indices shift when devices attach.
  `pick_camera()` scores on image variance after warming up.
- **The stock `config.txt` already contains `dtoverlay=dwc2,dr_mode=host`**
  under `[cm5]`, so a loose grep for dwc2 silently skips adding gadget mode.
- **`tr -dc ... | head -c N` makes tr take SIGPIPE**, which under
  `set -o pipefail` kills a shell script with no message at all.
- **A Pi 5 will not boot off a laptop USB port.** It wants 5 A.

## Claims to never make on stage

- "Other tools only describe the scene." False. Lookout gives spoken
  direction and distance; Apple's Magnifier gives haptics that intensify with
  proximity. A judge can disprove it in 30 seconds.
- "Your hand lands on the object." We deliver a bearing, not a 3D point. The
  honest version is better: your search area goes from the whole counter to a
  few inches.
