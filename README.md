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

## Wiring

| Part      | Grove port | BCM |
|-----------|-----------|-----|
| Buzzer    | D5        | 5   |
| Button    | D18       | 18  |

## Run

    python camera_check.py              # which camera, and can it see the sweep
    python sweep.py --host <pi-ip>      # the core loop
    python sweep.py                     # same, silent, no Pi needed

In `sweep.py`: click to place a target, or press space to put it at your
wrist. Sweep across it. Press r to reset, q to quit.

## Sound design

| Signal | Meaning |
|---|---|
| two fast 1800Hz beeps | found it, start sweeping |
| one 700Hz beep | your hand is on it, now |
| pulse train, rising pitch and rate | closing in on the reach |

## Measured on this hardware

- MediaPipe Pose (lite): **8.0 ms/frame**, ~125 fps ceiling.
  For comparison, YOLO nano on a Pi 5 is 67-128 ms. That gap is the whole
  reason the vision runs on the laptop.

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

## Claims to never make on stage

- "Other tools only describe the scene." False. Lookout gives spoken
  direction and distance; Apple's Magnifier gives haptics that intensify with
  proximity. A judge can disprove it in 30 seconds.
- "Your hand lands on the object." We deliver a bearing, not a 3D point. The
  honest version is better: your search area goes from the whole counter to a
  few inches.
