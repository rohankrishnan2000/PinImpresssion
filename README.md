# Hand Tracker

Real-time webcam hand tracking that reports your hand's position with the
**center of the screen as the origin (0, 0)**, and draws it live.

Axes use the math convention: `+x` is right, `+y` is **up**. The video is
mirrored (selfie view), so moving your hand right increases `x`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The hand landmark model downloads automatically to `models/` on first run.

## Run

```bash
.venv/bin/python hand_tracker.py
```

On macOS you must grant your terminal camera access:
**System Settings → Privacy & Security → Camera**, then restart the terminal.

### Keys

| key | action |
| --- | --- |
| `q` / `Esc` | quit |
| `n` | toggle pixels ↔ normalized (-1..1) units |
| `s` | save a screenshot |

### Options

```
--camera N        camera index (default 0)
--hands N         max hands to track (default 2)
--normalized      start in normalized units
--no-mirror       disable the selfie mirror
--smoothing F     0 = frozen, 1 = raw/jittery (default 0.4)
--width/--height  requested capture resolution
```

## How it works

1. OpenCV grabs frames and mirrors them.
2. MediaPipe's `HandLandmarker` (VIDEO mode, so it tracks between frames) returns
   21 normalized landmarks per hand.
3. The hand's position is the centroid of the five rigid palm landmarks
   (wrist + the four finger MCP joints) — steadier than any single point, which
   would drift as you move your fingers.
4. That point is smoothed with an exponential moving average, then converted:
   `x = px - w/2`, `y = h/2 - py`.

Reusable pieces: `to_centered()` for the conversion and `Smoother` for the EMA.
