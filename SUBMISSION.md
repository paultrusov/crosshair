# Crosshair — Devpost submission copy

Paste each block into the matching field.

---

## Project name

**Crosshair**

---

## Elevator pitch  (Devpost caps this at 200 characters)

> Say the name of anything. A camera on your chest finds it and beeps the instant your own hand crosses it, so you can reach straight to it. Any word, both hands free.

(166 characters)

---

## Inspiration

Blind people do not usually have trouble knowing what is on a counter. They have trouble getting a hand on it. Those are different problems, and almost every tool solves the first one.

The gap shows up plainly in how people describe the workaround. A Be My Eyes volunteer, trying to talk someone's camera onto a dropped object: "To the right. To the right again. Nope, to the left a little bit... that's too far." Words are a bad channel for a targeting task. The person giving directions cannot feel how far "a little" is, and the person receiving them cannot check.

Google Lookout already does better than words for seven object categories. Apple's Magnifier does it for doors, people and furniture. Neither can hear "ketchup".

---

## What it does

You say what you are looking for. Any noun, no list to pick from. The camera on your chest finds it and locks on. Two high beeps mean it has it.

Then you sweep your arm across the space in front of you, and the moment your hand crosses the object's bearing, you hear one low beep. Not a description of where it is. A signal at the instant your own hand is pointing at it.

Then you reach, and the pulses speed up and rise in pitch as your hand closes in.

The device never takes your hands. You are not holding a phone and aiming it. The camera is on your body, it watches your own arm, and the hot-or-cold game it plays is one your body already knows how to play.

**What it honestly delivers:** a bearing, not a point in space. Your search area goes from the whole counter to a few inches. The last inch is what hands are for.

---

## How we built it

Everything runs locally on a laptop. No cloud, no API key, no internet. That is a product decision, not a shortcut: a tool for finding your own things in your own kitchen should not stop working when the wifi does.

**Finding the object.** OWL-ViT open-vocabulary detection takes the literal string you said, so "ketchup" and "the blue mug" are both expressible. It costs about 900 ms per query, which sounds fatal for a real-time system and is not, because of the next part.

**Keeping it.** The object does not move. The camera does, constantly, because it is strapped to a person. So the detector runs once to answer *what and where*, and a CSRT correlation tracker follows the object at 9 ms a frame from there. Detector for identity, tracker for position.

That alone was not enough. A head-mounted camera walking across a room drifts the tracker off the object and nothing pulls it back, so on film the box ends up floating over a window. We added a background worker thread that re-runs the real detector every 1.2 seconds and snaps the box back onto the truth. Measured cost to the main loop: 9.1 ms a frame, 110 fps sustainable. The video never stalls and the lock never wanders for more than about a second.

**Finding the hand.** MediaPipe Pose, wrist landmark. Pose rather than Hands because at arm's length, with motion blur, and with the hand often turned away from the camera, Hands drops out and Pose does not.

**Calling the crossing.** The naive version fires when the wrist's x position crosses the object's. That lands late: a hand sweeping a counter crosses a given bearing in well under 100 ms. So we track the hand's angular velocity and fire early by the measured pipeline latency, which we instrument live and print on screen.

**Hearing you.** faster-whisper, running offline, in its own process. Push to talk, because a hackathon room is loud enough that an always-listening mic transcribes the people at the next table. It did, twice, during testing.

**Measured on the actual hardware** (Logitech Brio 101, 1280x720):

| | |
|---|---|
| sustained | 29.8 fps, and 59 fps once we switched to MJPEG |
| end to end | **33.6 ms**, p95 36.3 ms |
| wrist found | 100% of frames, 0 dropouts across a full arm sweep |
| field of view | hand crossed 66% of the frame and never left it |
| detection | ~0.9 s, once, at lock |

For scale: YOLO nano on a Raspberry Pi 5 is 67 to 128 ms for a *closed* 80-class model.

---

## Challenges we ran into

**The hardware lied, twice, without erroring once.**

A webcam on a USB 2.0 hub cannot carry 720p uncompressed. It enumerates. macOS lists it. ffmpeg hangs forever. And OpenCV silently hands back the built-in laptop camera instead, with no error at all, so the software looks broken while the camera is fine. Switching to MJPEG capture is a fifth the bandwidth, fixed it, and doubled the framerate as a side effect.

Then OpenCV turned out to enumerate cameras in the **reverse order to macOS**. `system_profiler` and `ffmpeg` both list the built-in first; OpenCV returns the external at index 0. We proved it by covering the lens and seeing which index went dark. Picking the camera by name against the system list chose exactly the wrong one.

**Two libraries that will not share a process.** faster-whisper and PyTorch each link their own OpenMP runtime. Loaded together they do not warn, they deadlock on model load. The documented `KMP_DUPLICATE_LIB_OK` workaround silences the warning and does nothing for the hang. Whisper now runs in an isolated worker process, and the handshake has to scan stdout for its ready marker because Intel MKL prints a banner first.

**Our own best idea was half wrong.** "Detect once, cache the bearing, the object isn't moving" is correct about the object and wrong about the camera. On a chest mount the bearing changes with every step. We only found it because the first demo take looked convincing for five seconds and then obviously broken.

**A Raspberry Pi 5 ate two hours and shipped nothing.** The plan was buzzers on GPIO. The SD card turned out to be blank, a Pi 5 will not boot off a laptop USB port, and the campus network blocks the multicast that mDNS needs, so the Pi was unfindable even if it were healthy. We cut it. The sound comes from the laptop, and the project is better for it.

---

## Accomplishments that we're proud of

**The open vocabulary is real and we can prove it in one shot.** Pointed at a random corner of the venue, it located a **thermostat at 0.83 confidence**. Thermostat is not a COCO class. It is not one of Lookout's seven categories. No detector we are aware of ships with it. That single result is the difference between this and a lookup table.

**33 ms end to end.** The whole product is a sound landing at an exact instant, so latency is not a performance metric here, it is the feature. We budgeted 125 ms and came in at a quarter of it.

**We let the evidence pick the output channel.** The obvious build for this is a vibrating wearable, and we had the motors. Then we read the only serious study of this exact interaction (Trant et al., 41 blind and partially sighted participants, 2025) and it found audio significantly *faster* than vibration, 4198 ms against 4784 ms. We switched to sound. It is a worse story and a better device.

---

## What we learned

**A device that enumerates is not a device that works.** Three separate times, the camera, the microphone, and the Pi all appeared in system listings and delivered nothing. Every one of them cost us an hour of debugging code that was already correct. Now the camera picker reads frames before trusting an index, and the mic picker opens a stream before trusting a name.

**Prior art research is a build decision, not a slide.** Reading the two feelSpace papers before writing code is what told us the camera loop had never actually been closed in either study. In both, a researcher in the next room operated the device by keyboard. That is the gap we built into, and we would not have found it by guessing.

**Timing beats information.** Our first instinct was to say more: direction, distance, a description. The thing that actually works is one short beep at the right millisecond.

---

## What's next for Crosshair

**Talk to blind users. This is the first item for a reason.** Nobody who is blind has used this. We know what that makes it, and there is a well-aimed critique of exactly this failure mode in the literature. Cornell Student Disability Services and the local NFB chapter are the Monday morning calls.

**Depth.** Two bearings locate a ray, not a point: the ketchup behind the milk sits on the same line as the milk. An ultrasonic sensor on the wrist would give true hand-to-object distance and close that hole with real data instead of a proxy.

**Onto the body properly.** Right now the compute is a laptop in a bag. The vision is 33 ms on a laptop and 10x that on a Pi 5, so the honest path is a phone, not a single-board computer.

**Shrink the lock time.** 900 ms from "say it" to "found it" is acceptable and not good. Caching detections per room, or a distilled detector, could halve it.

---

## Built With

```
python, opencv, mediapipe, owl-vit, transformers, pytorch, faster-whisper, numpy, sounddevice, csrt, logitech-brio, macos
```

---

## Try it out

- GitHub: https://github.com/<user>/crosshair
- Demo video: (link once uploaded)

---

## 60-second video script

Footage you have: the 21s screen-capture demo (`demo-181302.mp4`), the 18.5s
7-Eleven clip (`IMG_4716.mov`), six device photos.

| time | footage | voiceover |
|---|---|---|
| 0:00-0:08 | **7-Eleven clip, opening.** Blindfolded, device on, standing at the fruit case | "Blind people don't struggle to know what's on the shelf. They struggle to get a hand on it." |
| 0:08-0:16 | Device photos: the strap, the camera at the sternum | "This is a webcam on a chest strap. You say the name of anything you want." |
| 0:16-0:34 | **Screen demo, uncut.** Query types out, red box lands on the bottle, hand sweeps in, yellow, green, grab | "It finds it, then beeps the moment your own hand crosses it. Not a description of where it is. A signal at the instant you're already pointing at it." |
| 0:34-0:48 | **7-Eleven clip, the reach and the grab.** Hand out, sweeping along the case, closing on the kiwi, lifting it | "Blindfolded, in a shop, on a shelf he's never seen. He asked for kiwi." |
| 0:48-0:56 | Screen with the live HUD, fps and ms counter visible | "Thirty-three milliseconds end to end. Entirely offline. No cloud, no API key." |
| 0:56-1:00 | Final frame of the kiwi in his hand, title card | "Crosshair. Any word. Both hands free." |

Cuts worth making: start on the 7-Eleven clip, not the screen capture, because a
person in a shop reads instantly and a screen recording does not. End on the
kiwi. Use `demo-181302.mp4`, not the earlier takes where the box drifts.

---

## Images to upload to Devpost, in this order

1. The kiwi grab (final frame of the 7-Eleven clip) — this is the thumbnail
2. The reach along the fruit case
3. The person wearing the device, front
4. Device close-up on the table
5. A screen capture showing the box locked on the bottle with the HUD visible

---

## At the judging table

Three sentences, in this order:

1. "Google Lookout already does this for seven fixed object categories, with your phone in your hand. We do it for any word you say, with both hands free."
2. "The detector runs once to say what it is, a tracker follows it at 9 milliseconds a frame, and a background thread re-detects every second so the lock can't drift. End to end it's 33 milliseconds, and the whole thing runs offline."
3. "Here, put this on." (Hand it over. Let them do it.)

**"Did you test this with a blind person?"**

> "No, and that's the honest limitation of a 36-hour build. What we did instead was build on the one study that ran this interaction with 41 blind participants, and we changed our design because of it: they found audio guidance significantly faster than vibration, so we dropped the vibrating wearable we'd planned. Monday we're calling Cornell Student Disability Services and the local NFB chapter, because every usability claim we have is a hypothesis until then.

Never answer that question defensively, and never answer it with a guess about what blind users would want.
