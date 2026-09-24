# Pin Impression — hand position and keyboard control

This project lives in `TL/PinImpresssion/`. This version makes **hand position following the default** and
moves continuous rotation into a camera-free keyboard mode.

The working hardware configuration is preserved: **STEP D3, DIR D2, EN D4,
MICROSTEPS = 1**. The Uno sketch and serial transport are copied unchanged from
the working repository. An Uno already running that sketch needs no new upload.

## Start with the setup window

From your existing Python environment:

```bash
cd /Users/yangq/Desktop/TL/PinImpresssion
python launcher.py
```

1. Choose **position** (hand tracking) or **manual** (A/D keyboard).
2. Choose **preview** to test without a motor, or **motor** and select the
   Arduino port. Refresh lists available ports; you can also type a port name.
3. Choose the camera index and Right/Left hand label. Full camera frame is
   checked by default; uncheck it to use the saved/default rectangle.
4. Use the **Tuning** tab for horizontal travel, speed, direction, microsteps,
   resolution and optional smoothing. Keep microsteps matched to the driver.
5. **Save settings** remembers choices for future GUI launches. Opening a session
   applies current values but does not automatically save them.
6. Click **Open session**. The control window opens paused. Click **Start motion**
   there (or M); click **Pause** to hold. Keyboard mode still uses held A/D.
7. **End session** closes the control window and returns you to setup. Changes to
   setup are applied by opening a new session; reconnecting defines startup zero
   again, so establish the mechanism's center before a live session.

Both windows show session state. Connection/detector errors appear in the setup
window's details box. Clicking away from the control window still pauses motion;
click Start motion when ready to resume. Opening setup alone does not connect to
hardware or request camera access.

The launcher uses Python's Tk interface and the existing project requirements;
there is no new pip dependency. If your Python lacks Tk, install Tk support for
that Python distribution or continue with the terminal commands below. Use the
same Python environment that successfully ran the tracker. This is a Python
setup application, not a packaged standalone executable.

See [TUNING.md](TUNING.md) for saved-settings precedence and
[ARCHITECTURE.md](ARCHITECTURE.md) for how the UI stays separate from motor control
and how a second axis can be added later.

## Terminal setup and preview

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

When drawing with B, the rectangle is saved beside the script as `tracking_boundary.json`, using
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

## Keys and on-screen buttons

The control window has clickable Start/Pause, Draw boundary, Smoothing, and
End session buttons. Keyboard shortcuts remain available.

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
`--normalized`, and the old `--smoothing` option are not used by this version.
See [TUNING.md](TUNING.md) for the replacement settings.

## Files

| File | Purpose |
| --- | --- |
| `launcher.py` | Setup window, saved choices, session status |
| `launcher_settings.py` | Preferences and conversion to existing terminal options |
| `launcher_process.py`, `session_control.py` | Session startup, status and clean shutdown |
| `hand_tracker.py` | Camera tracking, keyboard-only mode, window and buttons/keys |
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
setting. This version does not change driver wiring/current adjustment.

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

The tests cover mapping, serial behavior, window events, preferences, and a real
camera-free child session opened and closed through the launcher. Native Tk
layout inspection through desktop automation was unavailable. Camera/motor
operation and Windows/Linux GUI behavior still need testing on those systems.
