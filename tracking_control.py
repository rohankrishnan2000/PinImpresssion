"""Camera-independent boundary mapping and held-key controls."""
from dataclasses import dataclass
import json
import math
from pathlib import Path
from motion_control import MotorCommand


@dataclass(frozen=True)
class Boundary:
    left: float = 0.15
    top: float = 0.15
    right: float = 0.85
    bottom: float = 0.85

    def __post_init__(self):
        values = (self.left, self.top, self.right, self.bottom)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   and math.isfinite(v) and 0 <= v <= 1 for v in values):
            raise ValueError("Boundary coordinates must be finite numbers from 0 to 1")
        if self.right - self.left < 0.05 or self.bottom - self.top < 0.05:
            raise ValueError("Boundary must span at least 5% of the image in each direction")

    def contains(self, point):
        return (point is not None and len(point) == 2
                and all(math.isfinite(v) for v in point)
                and self.left <= point[0] <= self.right
                and self.top <= point[1] <= self.bottom)

    def horizontal(self, x):
        """Normalized boundary coordinate: left=-1, middle=0, right=+1."""
        return max(-1.0, min(1.0, 2 * (x - self.left) / (self.right - self.left) - 1))

    @classmethod
    def from_drag(cls, start, end):
        return cls(min(start[0], end[0]), min(start[1], end[1]),
                   max(start[0], end[0]), max(start[1], end[1]))

    def save(self, path, mirrored):
        path = Path(path)
        payload = {"version": 1, "mirrored": mirrored,
                   "rect": [self.left, self.top, self.right, self.bottom]}
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n")
        temporary.replace(path)

    @classmethod
    def load(cls, path, mirrored):
        data = json.loads(Path(path).read_text())
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("Unsupported boundary file format")
        if data.get("mirrored") is not mirrored:
            raise ValueError("Saved boundary uses a different mirror setting; redraw with B")
        rect = data.get("rect")
        if not isinstance(rect, list) or len(rect) != 4:
            raise ValueError("Boundary file must contain four coordinates")
        return cls(*rect)


class BoundedPositionMapper:
    def __init__(self, boundary, minimum=-90.0, maximum=90.0, speed=90.0, reverse=False):
        if not all(math.isfinite(v) for v in (minimum, maximum, speed)):
            raise ValueError("Position limits and speed must be finite")
        if not minimum < 0 < maximum or speed <= 0:
            raise ValueError("Position limits must straddle zero and speed must be positive")
        self.boundary, self.minimum, self.maximum = boundary, minimum, maximum
        self.speed, self.reverse = speed, reverse

    def command(self, raw_point, filtered_point=None):
        # Gate using RAW coordinates: smoothing must never prolong motion outside.
        if not self.boundary.contains(raw_point):
            return MotorCommand(None, self.speed)
        point = raw_point if filtered_point is None else filtered_point
        if len(point) != 2 or not all(math.isfinite(v) for v in point):
            return MotorCommand(None, self.speed)
        x = self.boundary.horizontal(point[0]) * (-1 if self.reverse else 1)
        target = x * self.maximum if x >= 0 else -x * self.minimum
        return MotorCommand(target, self.speed)


def select_hand(hands, selected):
    """hands = [(label, normalized palm), ...]; ambiguity deliberately holds."""
    matches = [point for label, point in hands if label.lower() == selected]
    return matches[0] if len(matches) == 1 else None


class ManualKeys:
    def __init__(self):
        self.held = set()

    def press(self, key):
        if key in ("a", "d"):
            self.held.add(key)

    def release(self, key):
        self.held.discard(key)

    def clear(self):
        self.held.clear()

    def speed(self, maximum, reverse=False):
        direction = int("d" in self.held) - int("a" in self.held)
        return direction * maximum * (-1 if reverse else 1)


def point_in_view(position, rect, clamp=False):
    """Map window pixels to normalized camera coordinates, excluding letterboxes."""
    left, top, width, height = rect
    if width <= 0 or height <= 0:
        return None
    x, y = (position[0] - left) / width, (position[1] - top) / height
    if clamp:
        return max(0.0, min(1.0, x)), max(0.0, min(1.0, y))
    return (x, y) if 0 <= x <= 1 and 0 <= y <= 1 else None
