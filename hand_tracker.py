"""Hand position follows a saved camera boundary; --mode manual uses A/D only.

M arm/pause, B draw boundary, F smoothing, P screenshot, Q/Esc quit.
A/D hold left/right in manual mode. W/S are reserved for the future vertical axis.
"""
import argparse
from contextlib import ExitStack
import math
from pathlib import Path
import time
import urllib.request

import motor_config as config
from motion_control import MotorCommand
from motor_serial import MotorConnectionError, UnoMotor
from tracking_control import (Boundary, BoundedPositionMapper, ManualKeys,
                              point_in_view, select_hand)
from tracking_filter import AdaptivePalmFilter

ROOT = Path(__file__).resolve().parent
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/1/hand_landmarker.task")
PALM_LANDMARKS = (0, 5, 9, 13, 17)


def arguments(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("position", "manual"), default="position")
    motor = ap.add_mutually_exclusive_group()
    motor.add_argument("--motor-port", help="Uno USB port; starts paused unless --start-armed")
    motor.add_argument("--motor-preview", action="store_true", help="preview only (also the default)")
    ap.add_argument("--start-armed", action="store_true")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--hands", type=int, choices=(1, 2), default=2)
    ap.add_argument("--model", type=Path, default=ROOT / "models/hand_landmarker.task")
    ap.add_argument("--boundary-file", type=Path, default=ROOT / "tracking_boundary.json")
    ap.add_argument("--no-mirror", action="store_true")
    ap.add_argument("--control-hand", choices=("left", "right"), default=config.CONTROL_HAND)
    ap.add_argument("--position-min", type=float, default=config.POSITION_MIN_DEGREES)
    ap.add_argument("--position-max", type=float, default=config.POSITION_MAX_DEGREES)
    ap.add_argument("--speed-factor", type=float, default=config.SPEED_FACTOR,
                    help="position-mode speed multiplier; does not change travel range")
    ap.add_argument("--manual-speed", type=float, default=config.MANUAL_SPEED_DEGREES_S)
    ap.add_argument("--acceleration", type=float, default=None)
    ap.add_argument("--microsteps", type=int, choices=(1, 2, 4, 8, 16, 32), default=config.MICROSTEPS)
    ap.add_argument("--reverse-motor", action=argparse.BooleanOptionalAction, default=config.REVERSE_MOTOR)
    ap.add_argument("--smooth", action=argparse.BooleanOptionalAction, default=config.SMOOTHING_ENABLED)
    ap.add_argument("--filter-min-cutoff", type=float, default=config.FILTER_MIN_CUTOFF_HZ)
    ap.add_argument("--filter-beta", type=float, default=config.FILTER_BETA)
    ap.add_argument("--filter-derivative-cutoff", type=float, default=config.FILTER_DERIVATIVE_CUTOFF_HZ)
    args = ap.parse_args(argv)
    args.speed = (config.BASE_SPEED_DEGREES_S * args.speed_factor
                  if args.mode == "position" else args.manual_speed)
    if args.acceleration is None:
        args.acceleration = (config.ACCELERATION_DEGREES_S2 if args.mode == "position"
                             else config.MANUAL_ACCELERATION_DEGREES_S2)
    try:
        if args.width <= 0 or args.height <= 0:
            raise ValueError("Camera dimensions must be positive")
        if args.control_hand not in ("left", "right"):
            raise ValueError("CONTROL_HAND must be left or right")
        BoundedPositionMapper(Boundary(), args.position_min, args.position_max, args.speed)
        AdaptivePalmFilter(args.filter_min_cutoff, args.filter_beta, args.filter_derivative_cutoff)
        # Apply the same protocol validation in preview as when connected.
        if not math.isfinite(config.MOTOR_STEP_ANGLE_DEGREES) or config.MOTOR_STEP_ANGLE_DEGREES <= 0:
            raise ValueError("Motor step angle must be finite and positive")
        steps_per_degree = args.microsteps / config.MOTOR_STEP_ANGLE_DEGREES
        for name, value, limit in (("speed", args.speed, UnoMotor.MAX_SPEED_STEPS_S),
                                   ("acceleration", args.acceleration, UnoMotor.MAX_ACCEL_STEPS_S2)):
            if not math.isfinite(value) or not 1 <= value * steps_per_degree <= limit:
                raise ValueError(f"{name} must correspond to 1..{limit} driver steps/s" +
                                 (" squared" if name == "acceleration" else ""))
        if max(abs(args.position_min), abs(args.position_max)) * steps_per_degree > UnoMotor.MAX_TARGET_STEPS:
            raise ValueError("Position range exceeds the Uno protocol limit")
    except ValueError as exc:
        ap.error(str(exc))
    return args


class Camera:
    """Loaded only for position mode; manual mode never imports camera libraries."""
    def __init__(self, args, cleanup):
        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import (HandLandmarker, HandLandmarkerOptions,
                                                   HandLandmarksConnections, RunningMode)
        self.cv2, self.mp, self.mirror = cv2, mp, not args.no_mirror
        self.connections = [(c.start, c.end) for c in HandLandmarksConnections.HAND_CONNECTIONS]
        if not args.model.exists():
            args.model.parent.mkdir(parents=True, exist_ok=True)
            print(f"Downloading hand model to {args.model}")
            urllib.request.urlretrieve(MODEL_URL, args.model)
        self.cap = cv2.VideoCapture(args.camera)
        cleanup.callback(self.cap.release)
        if not self.cap.isOpened():
            raise ValueError(f"Cannot open camera {args.camera}. Check camera permissions and --camera.")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        options = HandLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(args.model)),
                                       running_mode=RunningMode.VIDEO, num_hands=args.hands,
                                       min_hand_detection_confidence=0.5,
                                       min_hand_presence_confidence=0.5,
                                       min_tracking_confidence=0.5)
        self.detector = cleanup.enter_context(HandLandmarker.create_from_options(options))
        self.last_timestamp = -1
        self.read()  # Warm up BEFORE opening USB: avoids firmware's 750 ms timeout.

    def read(self):
        cv2, mp = self.cv2, self.mp
        ok, frame = self.cap.read()
        if not ok:
            raise ValueError("Camera stopped delivering frames; motor session stopped")
        if self.mirror:
            frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        timestamp = max(self.last_timestamp + 1, int(time.monotonic() * 1000))
        self.last_timestamp = timestamp
        result = self.detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp)
        h, w = frame.shape[:2]
        hands = []
        for index, landmarks in enumerate(result.hand_landmarks):
            label = result.handedness[index][0].category_name
            palm = tuple(sum(getattr(landmarks[j], axis) for j in PALM_LANDMARKS) / len(PALM_LANDMARKS)
                         for axis in ("x", "y"))
            hands.append((label, palm))
            points = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
            for a, b in self.connections:
                cv2.line(rgb, points[a], points[b], (210, 210, 210), 2, cv2.LINE_AA)
            cv2.putText(rgb, label, (int(palm[0] * w) + 12, int(palm[1] * h) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
        return rgb, hands


class View:
    def __init__(self, pg):
        self.pg = pg
        pg.display.init()
        pg.font.init()
        self.screen = pg.display.set_mode((1140, 720), pg.RESIZABLE)
        pg.display.set_caption("Pin Impression | Hand position & keyboard control")
        self.font = pg.font.Font(None, 24)
        self.title = pg.font.Font(None, 32)
        self.rect = (0, 0, 1, 1)

    def draw(self, frame, boundary, raw, filtered, drag, lines, manual=False):
        pg = self.pg
        self.screen.fill((17, 22, 30))
        ww, wh = self.screen.get_size()
        panel_width = min(330, max(240, ww // 3))
        area = pg.Rect(16, 64, max(1, ww - panel_width - 40), max(1, wh - 110))
        if frame is not None:
            h, w = frame.shape[:2]
            scale = min(area.width / w, area.height / h)
            size = max(1, round(w * scale)), max(1, round(h * scale))
            surface = pg.image.frombuffer(frame.tobytes(), (w, h), "RGB")
            view = pg.Rect(0, 0, *size)
            view.center = area.center
            self.screen.blit(pg.transform.smoothscale(surface, size), view)
            self.rect = tuple(view)
            def pixel(p):
                return round(view.x + p[0] * view.width), round(view.y + p[1] * view.height)
            tl, br = pixel((boundary.left, boundary.top)), pixel((boundary.right, boundary.bottom))
            bounds = pg.Rect(tl, (br[0] - tl[0], br[1] - tl[1]))
            color = (99, 231, 171) if boundary.contains(raw) else (255, 192, 98)
            pg.draw.rect(self.screen, color, bounds, 2)
            cx = (bounds.left + bounds.right) // 2
            pg.draw.line(self.screen, color, (cx, bounds.top), (cx, bounds.bottom), 1)
            for text, x in (("LEFT", bounds.left), ("ZERO", cx), ("RIGHT", bounds.right - 48)):
                self.screen.blit(self.font.render(text, True, color), (x + 3, bounds.top + 4))
            if raw is not None:
                pg.draw.circle(self.screen, (255, 220, 110), pixel(raw), 7, 2)
            if filtered is not None:
                pg.draw.circle(self.screen, (99, 231, 171), pixel(filtered), 4)
            if drag is not None:
                start, end = pixel(drag[0]), pixel(drag[1])
                rect = pg.Rect(start, (end[0] - start[0], end[1] - start[1]))
                rect.normalize()
                pg.draw.rect(self.screen, (105, 180, 255), rect, 3)
        else:
            self.rect = tuple(area)
            pg.draw.rect(self.screen, (29, 38, 50), area, border_radius=12)
            for i, text in enumerate(("CAMERA-FREE CONTROL", "Hold A   <     >   Hold D",
                                      "Release to stop", "W / S reserved for axis 2")):
                self.screen.blit(self.title.render(text, True, (219, 230, 243)),
                                 (area.x + 28, area.y + 80 + i * 55))
        heading = "KEYBOARD MOTION" if manual else "HAND POSITION"
        self.screen.blit(self.title.render(heading, True, (235, 241, 249)), (20, 20))
        x, y = ww - panel_width, 72
        for line in lines:
            # Word wrapping also works when the user resizes the window.
            words, row = line.split(), ""
            for word in words + [None]:
                candidate = f"{row} {word}".strip() if word is not None else ""
                if word is None or self.font.size(candidate)[0] > panel_width - 16:
                    self.screen.blit(self.font.render(row, True, (216, 225, 239)), (x, y))
                    y += 24
                    row = word or ""
                else:
                    row = candidate
            y += 8
        pg.display.flip()


def run(args):
    import pygame as pg
    with ExitStack() as cleanup:
        cleanup.callback(pg.quit)
        view = View(pg)
        manual = args.mode == "manual"
        boundary = Boundary()
        note = "Press M, then hold A or D" if manual else "B: draw and save your boundary"
        if not manual and args.boundary_file.exists():
            try:
                boundary = Boundary.load(args.boundary_file, not args.no_mirror)
                note = "Saved boundary loaded"
            except (ValueError, OSError) as exc:
                note = f"Using default rectangle: {exc}"
                print(note)
        mapper = BoundedPositionMapper(boundary, args.position_min, args.position_max,
                                       args.speed, args.reverse_motor)
        camera = None if manual else Camera(args, cleanup)
        motor = None
        if args.motor_port:
            motor = UnoMotor(args.motor_port, args.speed, args.acceleration, args.microsteps)
            cleanup.callback(motor.close)
            print("Uno connected; its current shaft position is zero. M starts/pauses.")
        armed, smooth = args.start_armed, args.smooth
        keys, clock = ManualKeys(), pg.time.Clock()
        smoothing = AdaptivePalmFilter(args.filter_min_cutoff, args.filter_beta,
                                        args.filter_derivative_cutoff)
        editing, drag_start, drag_end = False, None, None
        running, frame = True, None
        hold = MotorCommand(None, args.speed)

        def pause():
            nonlocal armed
            armed = False
            keys.clear()
            smoothing(None, time.monotonic())
            if motor:
                motor.update(hold, force=True)

        while running:
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    running = False
                    break
                if event.type in (pg.WINDOWFOCUSLOST, pg.WINDOWMINIMIZED):
                    pause()
                    drag_start = drag_end = None
                    note = "Paused after focus loss. Press M to resume."
                elif event.type == pg.KEYDOWN:
                    if getattr(event, "repeat", False):
                        continue
                    if event.key in (pg.K_q, pg.K_ESCAPE):
                        running = False
                        break
                    if event.key == pg.K_m and not editing:
                        if armed:
                            pause()
                        else:
                            keys.clear()  # Require a fresh A/D press after arming.
                            armed = True
                    elif event.key == pg.K_f and not manual:
                        smooth = not smooth
                        smoothing(None, time.monotonic())
                    elif event.key == pg.K_b and not manual:
                        pause()
                        editing = not editing
                        drag_start = drag_end = None
                        note = "Drag a rectangle on the image; B cancels." if editing else "Boundary edit canceled"
                    elif event.key == pg.K_p:
                        path = ROOT / time.strftime("hand_%Y%m%d_%H%M%S.png")
                        pg.image.save(view.screen, str(path))
                        note = f"Saved {path.name}"
                    elif manual and armed and event.key in (pg.K_a, pg.K_d):
                        keys.press(pg.key.name(event.key))
                    # W/S intentionally have no action.
                elif event.type == pg.KEYUP and manual:
                    keys.release(pg.key.name(event.key))
                    if keys.speed(args.manual_speed) == 0 and motor:
                        motor.update(hold, force=True)
                elif editing and event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                    drag_start = point_in_view(event.pos, view.rect)
                    drag_end = drag_start
                elif editing and event.type == pg.MOUSEMOTION and drag_start:
                    drag_end = point_in_view(event.pos, view.rect, clamp=True)
                elif editing and event.type == pg.MOUSEBUTTONUP and event.button == 1 and drag_start:
                    drag_end = point_in_view(event.pos, view.rect, clamp=True)
                    try:
                        candidate = Boundary.from_drag(drag_start, drag_end)
                        candidate.save(args.boundary_file, not args.no_mirror)
                        boundary = mapper.boundary = candidate
                        editing = False
                        note = "Boundary saved. Press M when ready."
                    except (ValueError, OSError) as exc:
                        note = str(exc)
                    drag_start = drag_end = None
            if not running:
                break
            raw = filtered = None
            if manual:
                speed = keys.speed(args.manual_speed, args.reverse_motor) if armed else 0.0
                if motor:
                    if speed:
                        motor.spin(speed)
                    else:
                        motor.update(hold)
                status = f"Rotation: {speed:+.0f} deg/s"
            else:
                frame, hands = camera.read()
                raw = select_hand(hands, args.control_hand)
                if not boundary.contains(raw):
                    smoothing(None, time.monotonic())
                filtered = smoothing(raw, time.monotonic()) if smooth and boundary.contains(raw) else raw
                command = mapper.command(raw, filtered)
                if motor:
                    motor.update(command if armed and not editing else hold)
                if raw is None:
                    status = f"HOLD: {args.control_hand} hand missing or ambiguous"
                elif command.target_degrees is None:
                    status = "HOLD: palm outside boundary"
                else:
                    status = f"Target: {command.target_degrees:+.1f} degrees"
            lines = [("LIVE MOTOR" if motor else "PREVIEW - no motor") +
                     (" / ACTIVE" if armed else " / PAUSED"), status]
            if not manual:
                left_angle, right_angle = ((args.position_max, args.position_min) if args.reverse_motor
                                           else (args.position_min, args.position_max))
                lines += [f"Left {left_angle:g} / center 0 / right {right_angle:g} deg",
                          f"Speed limit: {args.speed:g} deg/s", f"Hand: {args.control_hand}",
                          f"F: smoothing {'ON' if smooth else 'OFF'}", "B: draw boundary"]
            else:
                lines += ["A: hold left | D: hold right", "Both held: stop", "W/S: reserved",
                          "Continuous motion has no travel limit"]
            lines += ["M: start / pause", "P: screenshot | Q/Esc: quit", note]
            if editing:
                lines.append("DRAW BOUNDARY - MOTOR PAUSED")
            view.draw(frame, boundary, raw, filtered,
                      (drag_start, drag_end) if drag_start else None, lines, manual)
            clock.tick(60)


def main(argv=None):
    run(arguments(argv))


if __name__ == "__main__":
    try:
        main()
    except (MotorConnectionError, ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    except KeyboardInterrupt:
        pass
