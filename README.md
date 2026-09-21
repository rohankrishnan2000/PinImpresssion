# Horizontal hand-following motor prototype

Camera → Python hand tracker → USB → Elegoo Uno R3 → Panucatt SD8825 → stepper.

This is a separate working copy in `/Users/yangq/Desktop/TL/`. The repository
inside `PinImpresssion/` is unchanged. Both camera-only and preview modes work
without connecting a motor. Live mode requires uploading the included Arduino
sketch and wiring the driver first.

## Files

| File | Purpose |
| --- | --- |
| `hand_tracker.py` | Camera, hand detection, display, and start/pause control |
| `motor_config.py` | Adjustable defaults and recorded hardware ratings |
| `motion_control.py` | Centered horizontal pixels → target shaft angle |
| `motor_serial.py` | Angle → driver steps; acknowledged USB messages to the Uno |
| `uno_hand_follow/uno_hand_follow.ino` | Uno program: STEP/DIR pulses, acceleration, and command timeout |
| `requirements.txt` | Python dependencies |
| `test_motion_control.py`, `test_motor_serial.py` | Hardware-free mapping and USB-protocol tests |

## Settings to change

Edit `motor_config.py`, then restart the tracker. These are the initial values:

```python
POWER_SUPPLY_VOLTAGE_V = 12.0
POWER_SUPPLY_MAX_CURRENT_A = 1.5
POWER_SUPPLY_CONFIRMED = False

DEGREES_PER_PIXEL = 0.1
SPEED_FACTOR = 1.0
BASE_SPEED_DEGREES_S = 90.0
ACCELERATION_DEGREES_S2 = 180.0
MICROSTEPS = 8
```

**The power-supply entries are unconfirmed reference values only.** They do not
control voltage, current, or motor speed. Update them after checking the actual
supply label; changing them never reconfigures the driver. Supply current
capacity (estimated 1.5 A) is distinct from the motor's rated phase current (1.0 A).

The two main software controls are independent:

- `DEGREES_PER_PIXEL`: how far to turn. At 0.1, x = +100 pixels requests +10°.
- `SPEED_FACTOR`: how fast to approach the target. At 1.0, the limit is 90°/s;
  at 0.5 it is 45°/s. Acceleration ramps the motion toward this limit.

`REVERSE_MOTOR` reverses direction. `CONTROL_HAND` selects `right` or `left`.
`MICROSTEPS` must match the physical mode-pin wiring; editing the number does
not change the driver hardware. The 1.8° motor has 200 full steps/revolution.
At 1/8 microstepping, 1600 pulses request one revolution, or 0.225° per pulse.
Targets are rounded to the nearest pulse.

The Uno rejects speeds above 2000 pulses/s and acceleration above 5000 pulses/s².
These are firmware limits, not measured capabilities of your mechanical setup.

## Wiring and current limit

Follow the SD8825's printed labels. Its motor-output order differs from some
other DRV8825 carriers. The Panucatt Rev 1 guide specifies 3–5.5 V logic power,
an 8–35 V motor supply, and `current limit = 2 × VREF` for its 0.10 Ω sense
resistors. For the photographed 1.0 A motor, that corresponds to **VREF = 0.50 V**;
confirm the board matches that guide before setting it with a multimeter.
Do not use the supply's 1.5 A rating as the motor's current-limit setting.
[Panucatt user guide, mirrored manufacturer document](https://manualzilla.com/doc/5669131/sd8825-users-guide).

| SD8825 label | Connection for this sketch |
| --- | --- |
| STEP | Uno D3 |
| DIR | Uno D2 |
| EN | Uno D4; also use a 10 kΩ pull-up to Uno 5 V to keep it disabled during reset |
| RST, SLP | Uno 5 V |
| VDD | Uno 5 V (logic supply) |
| GND | Common ground with Uno GND and motor-supply negative |
| VMOT | Confirmed motor-supply positive; never an Uno I/O or 5 V pin |
| 1A | Motor black (A+) |
| 1B | Motor green (A−) |
| 2A | Motor red (B+) |
| 2B | Motor blue (B−) |
| M0, M1 | Uno 5 V for the default 1/8 microstepping |
| M2 | GND for the default 1/8 microstepping |

The mode signals correspond to TI's DRV8825 mode table. The sketch uses 3 µs
STEP pulses and active-low enable. [TI DRV8825 datasheet](https://www.ti.com/lit/ds/symlink/drv8825.pdf).

Keep the existing onboard VREF jumper in place; leave the extra DEC and FLT
pads unconnected for this prototype. Use the driver heatsink as described in
its guide. Connect or disconnect motor wires with power off. Provide local
VMOT bulk decoupling according to the driver setup; do not rely on long supply
leads alone. Check supply polarity and its actual rating before powering up.

## Python setup and preview

Run from **TL**, not the repository subfolder:

```bash
cd /Users/yangq/Desktop/TL
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python hand_tracker.py --motor-preview
```

Use a Python version supported by the pinned MediaPipe package. The hand model
downloads into `models/` on first use. On macOS, grant the app running Python
camera access in System Settings → Privacy & Security → Camera.

Omit `--motor-preview` for the original camera-only behavior. The tracker
averages the wrist and four finger-base landmarks, smooths that palm position,
and expresses it around image center with +x to the right and +y upward.
The motor uses only smoothed x in **pixels**. The `n` key changes displayed
units without changing motor commands. Requested resolution affects how many
pixels correspond to a given hand displacement; calibration is still pending.

## Upload the Uno program

1. In Arduino IDE, install **AccelStepper by Mike McCauley** from Library Manager.
   The sketch was compiled against version 1.64.
2. Open `uno_hand_follow/uno_hand_follow.ino`.
3. Select **Arduino Uno** and the connected Uno's port, then upload.
4. Close Serial Monitor before starting Python so the port is available.

The pin constants and 750 ms command timeout are at the top of the sketch.
The power supply is not programmed into this sketch.

## Live operation

First test the motor shaft with the belt/load disconnected. This prototype has
no end switches, homing, or mechanical travel boundaries. Each new USB session
declares the stationary shaft's current position to be zero; it does not find
the middle of the belt. Before testing an attached mechanism, establish its
center and permitted travel separately.

Find the Uno's port:

```bash
.venv/bin/python -m serial.tools.list_ports
```

Use that port in place of `/dev/cu.usbmodemXXXX`:

```bash
.venv/bin/python hand_tracker.py --motor-port /dev/cu.usbmodemXXXX --speed-factor 0.5
```

- Live mode starts **paused**. Put the selected hand near screen center and
  press **m** in the camera window to start following. Press **m** again to pause.
- **q / Esc** exits; **n** toggles displayed units; **s** saves a screenshot.
- A stationary hand produces a stationary target, not continuous rotation.
- Losing the selected hand requests a hold at the current commanded position.
  A second hand cannot take over unless it has the selected label; duplicate
  labels also request a hold. Reappearance resumes following when armed.
- Hand loss and pause cancel pulses immediately and retain holding torque after
  movement has begun. A sudden stop can lose physical position under inertia.
- Quit, malformed commands, and a command gap over **750 ms** disarm the driver
  and release torque. After a timeout or USB reset, Python exits on the error;
  restart and establish zero again. The motor does not automatically reconnect.

This is **open-loop control**: the display is a requested angle, and the Uno
counts issued steps. Neither measures actual shaft/belt position or detects a
stall. Motor feedback and physical travel limits remain future work.

Additional options include `--degrees-per-pixel`, `--speed-factor`,
`--acceleration`, `--microsteps`, `--control-hand`, `--reverse-motor`, and the
original camera/resolution/smoothing options. Preview and live mode are mutually
exclusive; use `--help` for the full list.

## Protocol and verification

At 115200 baud, Python sends one acknowledged line at a time, up to 20 times/s:
`HELLO`, `CONFIG <steps/s> <steps/s²>`, `TARGET <absolute steps>`, `HOLD`, `STOP`.
Each move uses the latest target; stale commands are not queued by Python.
The Uno runs AccelStepper continuously between incoming characters.
[AccelStepper documentation](https://www.airspayce.com/mikem/arduino/AccelStepper/classAccelStepper.html).

Run the Python tests without a camera or connected motor:

```bash
python3 -m unittest -v test_motion_control test_motor_serial
```

The software checks and Uno compilation do not establish physical accuracy,
available torque, acceptable temperature, or an appropriate speed for the belt.
