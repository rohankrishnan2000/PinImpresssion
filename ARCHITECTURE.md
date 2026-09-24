# Interface and future axis changes

## Keep operation independent of the setup window

- `launcher.py` owns the Tk setup form and display of session status. It never
  connects to a camera, opens a motor port, or generates motor targets.
- `launcher_settings.py` owns the versioned preferences format and the single
  adapter from form values to existing command-line options. It validates them
  through `hand_tracker.arguments`, the same path used by terminal users.
- `launcher_process.py` starts `hand_tracker.py` with the current Python
  interpreter and an argument list (no shell). The child has its own main thread
  and display loop. Keeping Tk and Pygame in separate processes avoids competing
  GUI event loops and lets the setup window stay responsive during detector startup.
- `session_control.py` is an optional local pipe: the parent may request QUIT;
  the child reports paused/active state after initialization. It cannot accept
  position commands or bypass motor validation. EOF requests quit too.
- `hand_tracker.py` still owns runtime control. Its clickable buttons translate
  into the same actions as M/B/F/Q, including the same pause/focus-loss behavior.
- `tracking_control.py`, `tracking_filter.py`, `motor_serial.py`, and the Uno
  firmware retain their existing responsibilities. No setup-window logic belongs
  in the motor protocol.

Terminal launches start no pipe-reader thread. Original flags and defaults are
preserved; `--full-frame` is an additional opt-in flag. The GUI selects full frame
by default, as an explicit launcher setting. `--launcher-control` is an internal
flag used by the launcher; omit it when launching from a terminal.

## Settings precedence and storage

`motor_config.py` supplies defaults. `launcher_settings.json` stores only saved
GUI overrides, with `version: 1`. Unsaved changes apply only to the current launch.
Click Save settings to retain them; Use defaults loads the current code defaults,
then Save settings clears the overrides. Saved settings do not affect direct CLI
launches. CLI arguments remain the source of the final validated session options.

Axis-specific values are under `settings.axes.x`; camera, hand selection, and
session/output choices sit outside that dictionary. UI axis groups are generated
from `AXES`. Unknown keys/types or versions are rejected with an explanation;
malformed files are not overwritten automatically. Add an explicit version
migration when changing the saved-settings schema.

The preferences and boundary files are local and ignored by Git. Port names and
camera indexes can differ between computers. The camera selector accepts a device
index rather than silently opening every camera to probe it.

## Adding vertical motion later

1. Add a Y-axis configuration and settings section (`axes.y`), plus its form
   metadata. Keep shared camera/hand settings outside the axis sections.
2. Extend the CLI/backend adapter and validation to accept the second axis.
3. Extend the position mapper to produce both X and Y targets and map W/S in
   keyboard mode. Preserve A/D for X.
4. Design/update the serial protocol and firmware for two channels, including
   pin assignments, individual limits, and stop behavior for both axes.
5. Add protocol-version negotiation and migrate saved preferences if needed.
6. Test each axis independently and then together, including loss, pause,
   disconnect, boundary handling and any homing/limit switches.

The current firmware still controls exactly one axis. Adding a UI section alone
must never be treated as adding second-axis motor support.

## Shutdown and testing

Normal End session requests a clean exit; the existing motor cleanup sends STOP.
If startup or native capture is stuck, the launcher terminates the child after
3 seconds, and kills it after 6 seconds if necessary. An abruptly terminated
process cannot run Python cleanup; the unchanged Uno watchdog disarms after
750 ms without valid commands. This is not a physical emergency-stop system.

The suite includes original mapping/filter/serial checks, real Pygame events
under a virtual display, GUI-settings compatibility, and a real camera-free child
process opened/closed through the launcher. Tk is provided by many Python
installations but may need installing separately (especially Linux/minimal builds).
The setup window has not been visually verified through desktop automation;
Windows/Linux rendering and physical hardware operation need checks there.
