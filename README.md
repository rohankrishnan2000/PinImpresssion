# Pin Impression — boundary and keyboard draft

This project lives in `TL/PinImpresssion/`. This version makes **hand position following the default** and
moves continuous rotation into a camera-free keyboard mode.

The working hardware configuration is preserved: **STEP D3, DIR D2, EN D4,
MICROSTEPS = 1**. The Uno sketch and serial transport are copied unchanged from
the working repository. An Uno already running that sketch needs no new upload.

## Start here

Use your existing Python environment with the project dependencies, or create a
new environment with Python 3.13. The pinned dependencies were tested on 3.13.
These commands assume that environment's interpreter is named `python`:

```bash
cd /Users/yangq/Desktop/TL/PinImpresssion
python -m pip install -r requirements.txt
python hand_tracker.py --motor-preview
```

`pygame-ce` is the new dependency. It supplies window-local key-down/key-up events
and mouse drawing. This avoids needing global keyboard permissions. Preview
never opens a motor port. The first camera run downloads the MediaPipe model
if `models/hand_landmarker.task` is missing; manual mode needs neither the model
nor the camera. Grant camera access to the application running Python if asked.

1. Press **B** and drag a rectangle around the usable hand area. Release the
   mouse to save it. B again cancels editing. Tiny rectangles are rejected.
2. Check the hand label; the controlling hand defaults to **Right**. Use
   `--control-hand left` if appropriate.
3. Move the palm across the rectangle: left edge → left angle, middle → 0°,
   right edge → right angle. A fixed palm location gives a fixed target.
4. Leave **F** off initially. Toggle it on only if you want smoothing.
5. Check the motor range in `motor_config.py` before connecting the mechanism.

The rectangle is saved beside the script as `tracking_boundary.json`, using
normalized image coordinates. It survives resolution changes. Redraw it after
moving the camera or changing framing. A changed mirror setting rejects the
saved calibration and displays the default rectangle with a notice.

## Run with the motor

Establish the mechanism's center before opening a live session. Opening USB
usually resets the Uno; the sketch declares the shaft's current position zero.
It does not locate the middle of the belt. The default ±90° range is a test
setting, not a measurement of available travel.

Find the port, close Arduino Serial Monitor, then start:

```bash
python -m serial.tools.list_ports
python hand_tracker.py --motor-port YOUR_PORT
```

Replace `YOUR_PORT` with the listed port (`/dev/cu.usbmodem...` on macOS or
`COM...` on Windows). Live operation starts paused. Put the selected palm near
the rectangle's center and press **M** in the tracker window. M pauses again.

A missing/ambiguous hand or a palm outside any edge of the rectangle issues
HOLD: it cancels the previous target at the current commanded position. It does
not drive back to center. When the hand returns, following resumes if armed,
using the same absolute position map. Changing the boundary pauses the motor;
press M after drawing to resume. Losing window focus also pauses and requires M.

## Continuous rotation without a camera

Exit the hand tracker before launching the keyboard mode on the same port:

```bash
python hand_tracker.py --mode manual --motor-port YOUR_PORT
```

Press M to arm, then **hold A** for left rotation or **hold D** for right.
Release to stop. Holding both keys stops. Click back into the window and press
M after focus loss; held keys are cleared and a fresh A/D press is required.
To test the controls without hardware, replace `--motor-port YOUR_PORT` with
`--motor-preview`.

This is continuous shaft rotation with **no mechanical travel limits**. The
hand-position angle range does not restrict keyboard rotation. Test an unloaded
shaft, or supervise the belt travel directly until physical limits are added.
Start at the 90°/s default; change `MANUAL_SPEED_DEGREES_S` or `--manual-speed` to
adjust it. `--reverse-motor` reverses either mode.

## Keys

| Key | Action |
| --- | --- |
| M | Start/pause (also allows keyboard preview testing) |
| B | Position mode: draw/save the camera boundary; B again cancels |
| F | Position mode: smoothing on/off, starts off |
| A / D | Manual mode: hold left/right; release to stop |
| W / S | Reserved for a future vertical axis; no action |
| P | Save a screenshot beside the script |
| Q / Esc | Exit and stop/disarm the motor |

Position and manual modes are selected at launch. A/D do not override the hand
in position mode. `--mode spin`, `--degrees-per-pixel`, `--deadzone`, `--max-spin`,
`--normalized`, and the old `--smoothing` option are not used by this draft.
See [TUNING.md](TUNING.md) for the replacement settings.

## Files

| File | Purpose |
| --- | --- |
| `hand_tracker.py` | Camera tracking, keyboard-only mode, window and keys |
| `tracking_control.py` | Saved boundary, position mapping, held-key state |
| `tracking_filter.py` | Optional time-based adaptive smoothing |
| `motor_config.py` | Tunable defaults and hardware reference values |
| `motor_serial.py` | Existing acknowledged USB commands and degree-to-step conversion |
| `motion_control.py` | Existing command type and legacy mappers; main uses the new boundary mapper |
| `uno_hand_follow/uno_hand_follow.ino` | Unchanged, working Uno firmware |
| `TUNING.md` | What to change, units, effects, and calibration examples |
| `test_*.py` | Mapping, input-event, filtering and USB tests without hardware |

## Hardware and limitations

Keep the existing SD8825 wiring and physical full-step mode. The motor label
says 1.8° and 1.0 A per phase; the supply is recorded as an unconfirmed 12 V,
1.5 A supply. Editing those reference entries cannot alter voltage or current.
Do not substitute the supply's current rating for the motor's phase-current
setting. This draft does not change driver wiring/current adjustment.

Position commands are rounded to full steps (1.8° per pulse). Smoothing cannot
make the physical driver take smaller steps. Change microstepping only by
matching the hardware setting and software value together.

The display shows requested position, not measured position. There is no homing,
encoder or stall detection. HOLD stops pulses immediately, retaining holding
torque after motion starts; inertia can cause lost physical position. Quit,
serial failure, or a 750 ms command timeout disarms the driver and releases
holding torque. After a timeout, restart and establish zero again.

## Verification

```bash
python -m unittest discover -v
```

46 tests passed, including actual window-event handling with a virtual display,
key release, focus loss, rectangle saving, smoothing toggle, and camera-error
cleanup. The display was inspected using a synthetic frame. This does not
replace a real-camera and motor test on the board.
