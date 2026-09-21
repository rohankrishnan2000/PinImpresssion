"""Real-time hand tracker: reports hand position in a coordinate system
whose origin (0, 0) is the center of the screen.

Axes follow the math convention, not the image convention:
    +x -> right,  +y -> up

The camera feed is mirrored (selfie view), so moving your real hand to the
right moves the reported point in the +x direction.

Keys: q / ESC quit · s screenshot · n units · m start/pause motor (live mode)
"""

import argparse
import os
import time
import urllib.request
from collections import deque
from contextlib import ExitStack
import math

import motor_config as config
from motion_control import HorizontalMotorMapper, select_control_x
from motor_serial import UnoMotor, MotorConnectionError

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    HandLandmarker,
    HandLandmarkerOptions,
    HandLandmarksConnections,
    RunningMode,
)

MODEL_PATH = "models/hand_landmarker.task"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/1/hand_landmarker.task")

# Landmarks that make up the rigid part of the palm. Averaging them gives a
# far steadier "hand position" than any single point, which jitters as the
# fingers move.
PALM_LANDMARKS = (0, 5, 9, 13, 17)

CONNECTIONS = [(c.start, c.end) for c in HandLandmarksConnections.HAND_CONNECTIONS]

# BGR
COLOR_BONE = (210, 210, 210)
COLOR_JOINT = (80, 220, 255)
COLOR_AXES = (70, 70, 70)
COLOR_LEFT = (255, 170, 70)
COLOR_RIGHT = (120, 255, 140)
COLOR_TEXT = (245, 245, 245)


def ensure_model(path):
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    print(f"downloading hand landmark model -> {path}")
    urllib.request.urlretrieve(MODEL_URL, path)
    return path


class Smoother:
    """Exponential moving average, so the readout doesn't flicker."""

    def __init__(self, alpha=0.4):
        self.alpha = alpha
        self.value = None

    def __call__(self, point):
        if point is None:
            self.value = None
            return None
        if self.value is None:
            self.value = np.asarray(point, dtype=np.float32)
        else:
            self.value += self.alpha * (np.asarray(point, dtype=np.float32) - self.value)
        return self.value

    def reset(self):
        self.value = None


def to_centered(px, py, width, height):
    """Pixel coords (origin top-left, +y down) -> centered coords (+y up)."""
    return px - width / 2.0, height / 2.0 - py


def draw_axes(frame, width, height):
    cx, cy = width // 2, height // 2
    for x in range(0, width, 40):
        cv2.line(frame, (x, cy - 4), (x, cy + 4), COLOR_AXES, 1)
    for y in range(0, height, 40):
        cv2.line(frame, (cx - 4, y), (cx + 4, y), COLOR_AXES, 1)
    cv2.line(frame, (0, cy), (width, cy), COLOR_AXES, 1)
    cv2.line(frame, (cx, 0), (cx, height), COLOR_AXES, 1)
    cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)
    cv2.putText(frame, "(0,0)", (cx + 10, cy + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 220), 1, cv2.LINE_AA)
    cv2.putText(frame, "+x", (width - 34, cy - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_AXES, 1, cv2.LINE_AA)
    cv2.putText(frame, "+y", (cx + 8, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_AXES, 1, cv2.LINE_AA)


def draw_skeleton(frame, landmarks, width, height):
    pts = [(int(lm.x * width), int(lm.y * height)) for lm in landmarks]
    for a, b in CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], COLOR_BONE, 2, cv2.LINE_AA)
    for p in pts:
        cv2.circle(frame, p, 3, COLOR_JOINT, -1, cv2.LINE_AA)
    return pts


def draw_marker(frame, px, py, label, text, color):
    px, py = int(px), int(py)
    cv2.circle(frame, (px, py), 11, color, 2, cv2.LINE_AA)
    cv2.circle(frame, (px, py), 3, color, -1, cv2.LINE_AA)
    cv2.line(frame, (frame.shape[1] // 2, frame.shape[0] // 2), (px, py), color, 1, cv2.LINE_AA)
    cv2.putText(frame, label, (px + 16, py - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    cv2.putText(frame, text, (px + 16, py + 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)


def panel(frame, lines):
    """Translucent info panel in the top-left corner."""
    pad, lh = 10, 22
    w = min(frame.shape[1], 430)
    h = pad * 2 + lh * len(lines)
    overlay = frame[0:h, 0:w].copy()
    cv2.rectangle(overlay, (0, 0), (w, h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.6, frame[0:h, 0:w], 0.4, 0, frame[0:h, 0:w])
    for i, line in enumerate(lines):
        cv2.putText(frame, line, (pad, pad + lh * (i + 1) - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT, 1, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    ap.add_argument("--hands", type=int, default=2, help="max hands to track (default 2)")
    ap.add_argument("--model", default=MODEL_PATH)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--normalized", action="store_true",
                    help="start in normalized units (-1..1) instead of pixels")
    ap.add_argument("--no-mirror", action="store_true", help="don't mirror the camera")
    ap.add_argument("--smoothing", type=float, default=0.4,
                    help="0 = frozen, 1 = no smoothing (default 0.4)")
    motor_mode = ap.add_mutually_exclusive_group()
    motor_mode.add_argument("--motor-preview", action="store_true",
                    help="display horizontal motor targets; does not connect to hardware")
    motor_mode.add_argument("--motor-port", metavar="PORT",
                    help="Uno serial port; press m in the camera window to start movement")
    ap.add_argument("--control-hand", choices=("left", "right"), default=config.CONTROL_HAND,
                    help="hand that controls the motor (default from motor_config.py)")
    ap.add_argument("--degrees-per-pixel", type=float, default=config.DEGREES_PER_PIXEL,
                    help="motor rotation per centered x pixel")
    ap.add_argument("--speed-factor", type=float, default=config.SPEED_FACTOR,
                    help="multiplier for BASE_SPEED_DEGREES_S in motor_config.py")
    ap.add_argument("--acceleration", type=float, default=config.ACCELERATION_DEGREES_S2,
                    help="motor acceleration in degrees per second squared")
    ap.add_argument("--microsteps", type=int, choices=(1, 2, 4, 8, 16, 32), default=config.MICROSTEPS,
                    help="must match the physical driver mode pins")
    ap.add_argument("--reverse-motor", action=argparse.BooleanOptionalAction, default=config.REVERSE_MOTOR,
                    help="reverse the motor target direction")
    args = ap.parse_args()

    try:
        motor_mapper = HorizontalMotorMapper(args.degrees_per_pixel, args.speed_factor,
                                             args.reverse_motor)
    except ValueError as exc:
        ap.error(str(exc))
    if not 0 <= args.smoothing <= 1:
        ap.error("--smoothing must be between 0 and 1")
    if not math.isfinite(args.acceleration) or args.acceleration <= 0:
        ap.error("--acceleration must be finite and greater than zero")
    if args.control_hand not in ("left", "right"):
        ap.error("CONTROL_HAND must be left or right")

    ensure_model(args.model)

    with ExitStack() as cleanup:
        cap = cv2.VideoCapture(args.camera)
        cleanup.callback(cap.release)
        cleanup.callback(cv2.destroyAllWindows)
        if not cap.isOpened():
            raise SystemExit(
                f"Could not open camera {args.camera}. On macOS, grant your terminal "
                "camera access in System Settings > Privacy & Security > Camera."
            )
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=args.model),
            running_mode=RunningMode.VIDEO,
            num_hands=args.hands,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        smoothers = {}
        fps_times = deque(maxlen=30)
        normalized = args.normalized
        window = "Hand Tracker  -  origin at center"
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)

        with HandLandmarker.create_from_options(options) as landmarker:
            motor = None
            armed = False
            if args.motor_port:
                motor = UnoMotor(args.motor_port, motor_mapper.max_speed,
                                 args.acceleration, args.microsteps)
                cleanup.callback(motor.close)
                print("Uno connected; current shaft position is zero. Press m to start/pause.")
                print(f"Recorded supply: {config.POWER_SUPPLY_VOLTAGE_V} V, "
                      f"{config.POWER_SUPPLY_MAX_CURRENT_A} A capacity; "
                      f"confirmed={config.POWER_SUPPLY_CONFIRMED}. These are reference values only.")
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if not args.no_mirror:
                    frame = cv2.flip(frame, 1)

                h, w = frame.shape[:2]
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = landmarker.detect_for_video(mp_image, int(time.perf_counter() * 1000))

                draw_axes(frame, w, h)

                hand_lines = []
                control_positions = []
                seen = set()
                labels = [result.handedness[i][0].category_name if result.handedness else f"Hand {i}"
                          for i in range(len(result.hand_landmarks))]
                for i, landmarks in enumerate(result.hand_landmarks):
                    # `handedness` is reported for the real hand; mirroring the image
                    # flips which side of the frame it appears on, not which hand it is.
                    label = labels[i]
                    # Keep smoothing attached to the same hand if detection order changes.
                    key = label if labels.count(label) == 1 else f"{label}{i}"
                    seen.add(key)

                    draw_skeleton(frame, landmarks, w, h)

                    palm = np.mean([[landmarks[j].x, landmarks[j].y] for j in PALM_LANDMARKS], axis=0)
                    smoother = smoothers.setdefault(key, Smoother(args.smoothing))
                    sx, sy = smoother((palm[0] * w, palm[1] * h))

                    x, y = to_centered(sx, sy, w, h)
                    control_positions.append((label, float(x)))
                    if normalized:
                        text = f"({x / (w / 2):+.3f}, {y / (h / 2):+.3f})"
                    else:
                        text = f"({x:+.0f}, {y:+.0f})"

                    color = COLOR_LEFT if label.lower().startswith("l") else COLOR_RIGHT
                    draw_marker(frame, sx, sy, label, text, color)
                    hand_lines.append(f"{label:<5} {text}")

                for stale in set(smoothers) - seen:
                    del smoothers[stale]

                fps_times.append(time.perf_counter())
                fps = (len(fps_times) - 1) / (fps_times[-1] - fps_times[0]) if len(fps_times) > 1 else 0.0

                lines = [f"{w}x{h}   {fps:4.1f} fps",
                         "units: " + ("normalized -1..1" if normalized else "pixels from center")]
                lines += hand_lines or ["no hand detected"]
                if args.motor_preview or motor is not None:
                    command = motor_mapper.command(select_control_x(control_positions, args.control_hand))
                    if motor is not None:
                        motor.update(command if armed else motor_mapper.command(None))
                        lines.append("MOTOR LIVE: " + ("FOLLOWING" if armed else "PAUSED") + " [m]")
                    else:
                        lines.append(f"MOTOR PREVIEW ONLY ({args.control_hand})")
                    if command.target_degrees is None:
                        lines.append("HOLD: selected hand missing/ambiguous")
                    else:
                        lines.append(f"target: {command.target_degrees:+.1f} deg")
                    lines.append(f"speed limit: {command.max_speed_degrees_s:.1f} deg/s")
                panel(frame, lines)

                cv2.imshow(window, frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if key == ord("m") and motor is not None:
                    armed = not armed
                    if not armed:
                        motor.update(motor_mapper.command(None), force=True)
                if key == ord("n"):
                    normalized = not normalized
                if key == ord("s"):
                    name = time.strftime("hand_%Y%m%d_%H%M%S.png")
                    cv2.imwrite(name, frame)
                    print(f"saved {name}")



if __name__ == "__main__":
    try:
        main()
    except (MotorConnectionError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    except KeyboardInterrupt:
        pass
