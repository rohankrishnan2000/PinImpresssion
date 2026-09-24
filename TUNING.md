# Tuning the boundary / keyboard draft

Applies to `TL/PinImpresssion/`. Edit these files in the repo, then restart Python.
Command-line options override defaults for that run.

## What to tune first

1. **Boundary:** press B and draw the usable rectangle. Set up the camera in its
   final location before drawing. The entire palm need not fit: its center point
   (average of wrist and four knuckles) must be inside.
2. **Travel:** set `POSITION_MIN_DEGREES` and `POSITION_MAX_DEGREES` to match
   available motion on either side of startup zero. Center the mechanism first.
3. **Direction:** change `REVERSE_MOTOR` if increasing hand x moves the wrong way.
4. **Speed:** use `SPEED_FACTOR` to change how fast it approaches the target.
5. **Optional smoothing:** F toggles it; it is initially off.

## Position mode — motor_config.py

| Setting | Default | Effect / launch override |
| --- | --- | --- |
| `POSITION_MIN_DEGREES` | `-90.0` | Negative angle limit relative to startup zero; `--position-min` |
| `POSITION_MAX_DEGREES` | `90.0` | Positive angle limit; `--position-max` |
| `BASE_SPEED_DEGREES_S` | `90.0` | Base approach speed in degrees/s |
| `SPEED_FACTOR` | `1.0` | Multiplies that speed; `--speed-factor` |
| `ACCELERATION_DEGREES_S2` | `180.0` | Position acceleration in degrees/s²; `--acceleration` |
| `CONTROL_HAND` | `"right"` | Follow the displayed Right or Left label; `--control-hand` |
| `REVERSE_MOTOR` | `False` | Reverse the input direction; `--reverse-motor` / `--no-reverse-motor` |

The min/max must straddle zero. They can be asymmetric, for example -60°/+120°.
The rectangle midpoint still maps to zero: each half is scaled to its respective
angle limit. Reverse flips the input before mapping, retaining those same limits.

With ±90° and normal direction:

| Horizontal point within rectangle | Target |
| --- | --- |
| Left edge | -90° |
| One-quarter across | -45° |
| Center | 0° |
| Three-quarters across | +45° |
| Right edge | +90° |

Holding a hand at three-quarters keeps requesting +45°. It does not accumulate
rotation. Y is used only to decide whether the palm lies inside the rectangle;
it cannot drive a second axis yet. Raw coordinates gate the boundary even with
smoothing enabled, so smoothing cannot keep a previous target active outside it.

Changing the camera resolution does not change these angle targets for the same
normalized point. Moving the camera, changing its field of view or changing hand
depth can change where a physical hand appears; this is a 2D camera calibration.

**Speed and travel are separate:** `--speed-factor 0.5` reduces the default
speed limit to 45°/s without changing the angle range. A narrower rectangle
makes the same hand movement cover more of that range. A wider rectangle makes
it cover less. `DEGREES_PER_PIXEL` is no longer used by the main script.

For a directly driven timing-belt pulley, once you know its tooth count and
belt pitch:

```text
travel per shaft revolution = pulley teeth × belt pitch (mm)
angle from center = 360 × distance from center (mm) / travel per revolution
```

Include any gearing if it is not directly driven. Leave clearance at both ends.
The program cannot determine this distance from the camera rectangle alone.
These target limits are not end switches, homing, or measured carriage feedback.

## Keyboard mode — motor_config.py

| Setting | Default | Effect / launch override |
| --- | --- | --- |
| `MANUAL_SPEED_DEGREES_S` | `90.0` | Constant requested speed while A or D is held; `--manual-speed` |
| `MANUAL_ACCELERATION_DEGREES_S2` | `180.0` | Ramp toward requested rotation speed; `--acceleration` |
| `REVERSE_MOTOR` | `False` | Reverse A/D direction |

Run with `--mode manual`. 90°/s is a quarter turn per second; 360°/s is one turn
per second. It never opens the camera. M arms, A/D rotate while held, releasing
stops. Both held stop. W/S do nothing and are reserved for later.

Release/pause sends HOLD immediately, cancelling pulses rather than ramping
through extra travel. Such a stop can lose physical position under load. The
acceleration parameter controls spin-up and changes of requested speed, not this
immediate HOLD. Keyboard rotation has no travel boundary; test accordingly.

The old `MAX_SPIN_DEGREES_S`, `SPIN_ACCELERATION_DEGREES_S2`, `SPIN_DEADZONE_PX`,
and `SPIN_FULL_SPEED_FRACTION` remain for legacy mapper code/tests only. Changing
them has no effect on this main script. Use `MANUAL_*` instead.

## Smoothing — motor_config.py and tracking_filter.py

| Setting | Default | Effect / launch override |
| --- | --- | --- |
| `SMOOTHING_ENABLED` | `False` | Starting state; F toggles during use; `--smooth` / `--no-smooth` |
| `FILTER_MIN_CUTOFF_HZ` | `1.0` | Lower reduces resting jitter but adds slow-motion lag; `--filter-min-cutoff` |
| `FILTER_BETA` | `5.0` | Higher responds faster during movement; `--filter-beta` |
| `FILTER_DERIVATIVE_CUTOFF_HZ` | `1.0` | Velocity-estimate filtering; normally leave alone; `--filter-derivative-cutoff` |

This is an adaptive, time-based filter on normalized palm coordinates. X and Y
are filtered independently. Toggling F, losing the hand, or leaving the rectangle
resets its history. It is optional and does not calibrate the position map.
The yellow ring shows the raw palm; the green dot shows the control point.
Implementation: `tracking_filter.py`, based on the
[1 Euro filter equations](https://gery.casiez.net/1euro/).

## Camera / display — hand_tracker.py

| Launch option | Default | Purpose |
| --- | --- | --- |
| `--camera` | `0` | Camera device index |
| `--width`, `--height` | `1280`, `720` | Requested resolution; actual frame size may differ |
| `--hands` | `2` | Maximum detected hands, 1 or 2 |
| `--no-mirror` | Off | Disable selfie mirroring; redraw boundary and check hand label |
| `--boundary-file` | `tracking_boundary.json` beside script | Saved rectangle; includes mirror setting |
| `--model` | `models/hand_landmarker.task` beside script | Detector model, automatically downloaded if missing |
| `--mode` | `position` | Hand position or camera-free `manual` |
| `--start-armed` | Off | Skip initial M; omit during setup |

Detection, presence and tracking confidence remain 0.5 in `Camera.__init__`.
Ordinary tuning does not require editing those values or `PALM_LANDMARKS`.
A missing or duplicate selected-hand label holds. This selects by reported
handedness, not a persistent identity across multiple people.

B starts boundary editing and pauses the motor; drag and release to save.
F toggles smoothing, M starts/pauses, P saves a screenshot, Q/Esc quits.
**S is now reserved**, so it no longer saves screenshots. The old normalized
readout/EMA/spin flags have been replaced by the boundary UI and settings above.

## Preserved hardware and USB settings

| File / constant | Current value | Meaning |
| --- | --- | --- |
| Uno `STEP_PIN` | `3` | Existing STEP wire on D3; keep it |
| Uno `DIR_PIN` | `2` | Existing DIR wire on D2; keep it |
| Uno `ENABLE_PIN` | `4` | Existing active-low enable wire on D4 |
| Config `MICROSTEPS` | `1` | Full-step; must match physical driver mode pins |
| Config `MOTOR_STEP_ANGLE_DEGREES` | `1.8` | Motor label; 200 full steps per revolution |
| Config `SERIAL_BAUD` / Uno baud | `115200` | Both ends must match |
| Config `COMMAND_RATE_HZ` | `20.0` | Valid range 5–50; does not change camera FPS |
| Uno `COMMAND_TIMEOUT_MS` | `750` | Disarms when valid commands stop |
| Uno `RAMP_INTERVAL_US` | `2000` | Continuous-speed ramp timing |
| Uno / serial `MAX_SPEED_STEPS_S` | `4000` | Numeric protocol speed ceiling |
| Uno / serial `MAX_ACCEL_STEPS_S2` | `5000` | Numeric protocol acceleration ceiling |
| Uno / serial `MAX_TARGET_STEPS` | `1000000` | Numeric target bound, not belt travel |

The Arduino firmware is unchanged. Firmware edits require re-uploading;
Python settings require restarting. Protocol limits must match in firmware and
`motor_serial.py`. They are not verified motor/load capabilities.

```text
steps per degree = MICROSTEPS / 1.8
driver pulses per revolution = 200 × MICROSTEPS
```

Targets are rounded to the nearest driver step. Full-step resolution is 1.8°;
software smoothing cannot remove this quantization. Do not change MICROSTEPS
without matching the physical driver mode. Preview validates speed and
acceleration against the same pulse limits as live mode.

## Supply entries are records, not electrical controls

In `motor_config.py`: `POWER_SUPPLY_VOLTAGE_V = 12.0`,
`POWER_SUPPLY_MAX_CURRENT_A = 1.5`, `POWER_SUPPLY_CONFIRMED = False`,
`MOTOR_RATED_PHASE_CURRENT_A = 1.0`.

Replace the first two with the actual supply-label values and confirm the flag
once checked. These entries do not change electrical output. Driver phase-current
limit is adjusted on the hardware, independently of the supply's current capacity.

## Example commands

```bash
# Preview the saved boundary / position map
python hand_tracker.py --motor-preview

# Slow position approach, same travel range
python hand_tracker.py --motor-port YOUR_PORT --speed-factor 0.5

# Different angular travel and optional smoothing
python hand_tracker.py --motor-preview --position-min -60 --position-max 120 --smooth

# Camera-free continuous rotation
python hand_tracker.py --mode manual --motor-port YOUR_PORT --manual-speed 90
```

Record tested changes one at a time. Live zero is the shaft position when the
USB session opens. Restarting, losing steps or moving the belt manually can
invalidate that reference; re-establish the mechanism's center before resuming.
