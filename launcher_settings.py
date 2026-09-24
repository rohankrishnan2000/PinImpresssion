"""Versioned UI preferences and the adapter to the existing CLI.

No GUI, camera, serial connection, or motor control belongs in this module.
New axes get their own settings section and an explicit CLI/backend adapter.
"""
from contextlib import redirect_stderr
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path

import motor_config as config

AXES = {'x': 'Horizontal (X)'}


def defaults():
    return {
        'mode': 'position', 'output': 'preview', 'port': '', 'camera': '0',
        'control_hand': config.CONTROL_HAND, 'full_frame': True,
        'smooth': config.SMOOTHING_ENABLED, 'mirror': True,
        'width': '1280', 'height': '720',
        'filter_min_cutoff': str(config.FILTER_MIN_CUTOFF_HZ),
        'filter_beta': str(config.FILTER_BETA),
        'filter_derivative_cutoff': str(config.FILTER_DERIVATIVE_CUTOFF_HZ),
        'axes': {'x': {
            'position_min': str(config.POSITION_MIN_DEGREES),
            'position_max': str(config.POSITION_MAX_DEGREES),
            'speed_factor': str(config.SPEED_FACTOR),
            'manual_speed': str(config.MANUAL_SPEED_DEGREES_S),
            'acceleration': '',  # Blank keeps the backend's mode-specific default.
            'microsteps': str(config.MICROSTEPS), 'reverse': config.REVERSE_MOTOR,
        }},
    }


def _merge(base, changes):
    """Only known keys/types are accepted; never interpret saved data as code."""
    if not isinstance(changes, dict):
        raise ValueError('Settings must be a JSON object')
    result = deepcopy(base)
    for key, value in changes.items():
        if key not in base:
            raise ValueError(f'Unknown setting: {key}')
        expected = base[key]
        if isinstance(expected, dict):
            result[key] = _merge(expected, value)
        elif type(value) is not type(expected):
            raise ValueError(f'Incorrect type for setting: {key}')
        else:
            result[key] = value
    return result


def to_argv(settings):
    s = _merge(defaults(), settings)
    if s['mode'] not in ('position', 'manual') or s['output'] not in ('preview', 'motor'):
        raise ValueError('Choose a valid operating mode and output')
    argv = ['--mode', s['mode']]
    if s['output'] == 'motor':
        if not s['port'].strip():
            raise ValueError('Select or enter the Arduino port, or choose Preview')
        argv += ['--motor-port', s['port'].strip()]
    else:
        argv += ['--motor-preview']
    for flag in ('camera', 'control_hand', 'width', 'height', 'filter_min_cutoff',
                 'filter_beta', 'filter_derivative_cutoff'):
        # --key=value also handles signed numbers and unusual port-like strings.
        argv.append('--' + flag.replace('_', '-') + '=' + s[flag].strip())
    argv += ['--smooth' if s['smooth'] else '--no-smooth']
    if not s['mirror']:
        argv.append('--no-mirror')
    if s['full_frame']:
        argv.append('--full-frame')
    x = s['axes']['x']
    for flag in ('position_min', 'position_max', 'speed_factor', 'manual_speed', 'microsteps'):
        argv.append('--' + flag.replace('_', '-') + '=' + x[flag].strip())
    if x['acceleration'].strip():
        argv.append('--acceleration=' + x['acceleration'].strip())
    argv.append('--reverse-motor' if x['reverse'] else '--no-reverse-motor')
    # The launcher always starts paused. The existing CLI remains authoritative.
    from hand_tracker import arguments
    error = StringIO()
    with redirect_stderr(error):
        try:
            arguments(argv)
        except SystemExit as exc:
            message = error.getvalue().strip().split('error:')[-1].strip()
            raise ValueError(message or 'Invalid launch settings') from exc
    return argv


def _overrides(current, base):
    result = {}
    for key, value in current.items():
        if isinstance(value, dict):
            difference = _overrides(value, base[key])
            if difference:
                result[key] = difference
        elif value != base[key]:
            result[key] = value
    return result


def save(path, settings):
    to_argv(settings)
    path = Path(path)
    payload = {'version': 1, 'settings': _overrides(settings, defaults())}
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def load(path):
    path = Path(path)
    if not path.exists():
        return defaults()
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1:
        raise ValueError('Unsupported settings file version')
    result = _merge(defaults(), data.get('settings'))
    to_argv(result)
    return result
