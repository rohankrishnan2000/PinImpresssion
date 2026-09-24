"""Portable setup window. Run with the same Python used for hand_tracker.py."""
from pathlib import Path
import sys

import launcher_settings as settings
from launcher_process import SessionRunner

ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = ROOT / 'launcher_settings.json'


class Launcher:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk, messagebox
        self.tk, self.ttk, self.messagebox = tk, ttk, messagebox
        self.root, self.runner = root, SessionRunner()
        self.variables, self.axis_variables, self.editable = {}, {}, []
        self.closing = False
        root.title('Pin Impression — Setup')
        root.geometry('800x740')
        root.minsize(680, 600)
        root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(root)
        style.configure('Title.TLabel', font=('TkDefaultFont', 20, 'bold'))
        style.configure('Subtitle.TLabel', foreground='#526372')
        outer = ttk.Frame(root, padding=20)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Pin Impression', style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer, text='Choose your setup, then open the control window.',
                  style='Subtitle.TLabel').pack(anchor='w', pady=(4, 16))
        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill='both', expand=True)
        self.setup = self._scroll_tab('Setup')
        self.tuning = self._scroll_tab('Tuning')
        for frame in (self.setup, self.tuning):
            frame.columnconfigure(1, weight=1)
        self._choice(self.setup, 0, 'Control mode', 'mode', ('position', 'manual'))
        self._choice(self.setup, 1, 'Output', 'output', ('preview', 'motor'))
        ttk.Label(self.setup, text='Position = hand tracking   |   Manual = A/D keyboard',
                  style='Subtitle.TLabel').grid(row=2, column=0, columnspan=3, sticky='w', pady=(0, 10))
        self.port_box = self._choice(self.setup, 3, 'Arduino port', 'port', (), editable=True)
        self.refresh_button = ttk.Button(self.setup, text='Refresh', command=self.refresh_ports)
        self.refresh_button.grid(row=3, column=2, padx=(8, 0))
        self.editable.append((self.refresh_button, 'normal'))
        self._choice(self.setup, 4, 'Camera', 'camera', ('0', '1', '2', '3'), editable=True)
        self._choice(self.setup, 5, 'Follow hand labelled', 'control_hand', ('right', 'left'))
        self._check(self.setup, 6, 'Use the full camera frame (ignore a saved rectangle)', 'full_frame')
        self._check(self.setup, 7, 'Smooth hand movement', 'smooth')
        self._check(self.setup, 8, 'Mirror camera view', 'mirror')
        ttk.Label(self.setup, text='Camera 0 is usually the default. Try another index if needed.\n'
                  'Manual mode never opens a camera. Preview never connects to a motor.\n'
                  'Sessions open paused; click Start motion in the control window.',
                  wraplength=650, style='Subtitle.TLabel').grid(row=9, column=0, columnspan=3,
                                                               sticky='w', pady=(12, 6))
        self.port_note = tk.StringVar()
        ttk.Label(self.setup, textvariable=self.port_note, wraplength=650,
                  style='Subtitle.TLabel').grid(row=10, column=0, columnspan=3, sticky='w')

        # Axis sections are generated independently of camera/session controls.
        # Supporting Y also requires a backend/firmware adapter, not just a widget.
        for index, (axis, title) in enumerate(settings.AXES.items()):
            frame = ttk.LabelFrame(self.tuning, text=title, padding=10)
            frame.grid(row=index, column=0, columnspan=3, sticky='ew', pady=(0, 12))
            frame.columnconfigure(1, weight=1)
            variables = self.axis_variables.setdefault(axis, {})
            for row, (label, key) in enumerate((
                ('Minimum angle (degrees)', 'position_min'),
                ('Maximum angle (degrees)', 'position_max'),
                ('Position speed multiplier', 'speed_factor'),
                ('Keyboard speed (degrees/second)', 'manual_speed'),
                ('Acceleration (blank = mode default)', 'acceleration'),
            )):
                self._entry(frame, row, label, key, variables)
            self._choice(frame, 5, 'Microsteps — must match driver', 'microsteps',
                         ('1', '2', '4', '8', '16', '32'), variables=variables)
            self._check(frame, 6, 'Reverse motor direction', 'reverse', variables)
        base = len(settings.AXES)
        camera_frame = ttk.LabelFrame(self.tuning, text='Camera & optional smoothing', padding=10)
        camera_frame.grid(row=base, column=0, columnspan=3, sticky='ew')
        camera_frame.columnconfigure(1, weight=1)
        for row, (label, key) in enumerate((('Camera width', 'width'), ('Camera height', 'height'),
                                           ('Smoothing minimum cutoff (Hz)', 'filter_min_cutoff'),
                                           ('Smoothing movement response', 'filter_beta'),
                                           ('Velocity filter cutoff (Hz)', 'filter_derivative_cutoff'))):
            self._entry(camera_frame, row, label, key)

        buttons = ttk.Frame(outer)
        buttons.pack(fill='x', pady=(16, 10))
        self.start_button = ttk.Button(buttons, text='Open session', command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(buttons, text='End session', command=self.stop, state='disabled')
        self.stop_button.pack(side='left', padx=8)
        self.save_button = ttk.Button(buttons, text='Save settings', command=self.save)
        self.save_button.pack(side='right')
        self.reset_button = ttk.Button(buttons, text='Use defaults', command=self.reset)
        self.reset_button.pack(side='right', padx=8)
        self.status = tk.StringVar(value='Ready — no camera or motor connection opened')
        ttk.Label(outer, textvariable=self.status, wraplength=720).pack(anchor='w')
        self.log = tk.Text(outer, height=4, state='disabled', wrap='word', font=('TkFixedFont', 10))
        self.log.pack(fill='x', pady=(8, 0))
        try:
            self.set_values(settings.load(SETTINGS_PATH))
        except (ValueError, OSError) as exc:
            self.set_values(settings.defaults())
            self.status.set('Saved settings could not be loaded; using defaults. File not changed.')
            self.append_log(str(exc))
        self.refresh_ports()
        root.after(100, self.poll)

    def _scroll_tab(self, title):
        page = self.ttk.Frame(self.tabs)
        self.tabs.add(page, text=title)
        canvas = self.tk.Canvas(page, highlightthickness=0)
        scrollbar = self.ttk.Scrollbar(page, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        frame = self.ttk.Frame(canvas, padding=16)
        item = canvas.create_window((0, 0), window=frame, anchor='nw')
        frame.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width))
        return frame

    def _choice(self, parent, row, label, key, values, editable=False, variables=None):
        variables = self.variables if variables is None else variables
        variable = self.tk.StringVar()
        variables[key] = variable
        self.ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', padx=(0, 16), pady=5)
        state = 'normal' if editable else 'readonly'
        box = self.ttk.Combobox(parent, textvariable=variable, values=values, state=state, width=28)
        box.grid(row=row, column=1, sticky='ew', pady=5)
        self.editable.append((box, state))
        return box

    def _entry(self, parent, row, label, key, variables=None):
        variables = self.variables if variables is None else variables
        variable = self.tk.StringVar()
        variables[key] = variable
        self.ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', padx=(0, 16), pady=3)
        entry = self.ttk.Entry(parent, textvariable=variable, width=25)
        entry.grid(row=row, column=1, sticky='ew', pady=3)
        self.editable.append((entry, 'normal'))

    def _check(self, parent, row, label, key, variables=None):
        variables = self.variables if variables is None else variables
        variable = self.tk.BooleanVar()
        variables[key] = variable
        check = self.ttk.Checkbutton(parent, text=label, variable=variable)
        check.grid(row=row, column=0, columnspan=3, sticky='w', pady=6)
        self.editable.append((check, 'normal'))

    def values(self):
        values = {key: variable.get() for key, variable in self.variables.items()}
        values['axes'] = {axis: {key: variable.get() for key, variable in variables.items()}
                          for axis, variables in self.axis_variables.items()}
        return values

    def set_values(self, values):
        for key, variable in self.variables.items():
            variable.set(values[key])
        for axis, variables in self.axis_variables.items():
            for key, variable in variables.items():
                variable.set(values['axes'][axis][key])

    def refresh_ports(self):
        try:
            from serial.tools import list_ports
            ports = sorted(list_ports.comports(), key=lambda p: p.device)
            self.port_box.configure(values=[p.device for p in ports])
            self.port_note.set('\n'.join(f'{p.device}: {p.description}' for p in ports[:3]) or
                               'No serial ports found. Connect the Uno and click Refresh, or use Preview.')
            if not self.variables['port'].get() and len(ports) == 1:
                self.variables['port'].set(ports[0].device)
        except (ImportError, OSError) as exc:
            self.port_note.set('Port discovery unavailable; you can type the port manually. ' + str(exc))

    def append_log(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text + '\n')
        if int(self.log.index('end-1c').split('.')[0]) > 160:
            self.log.delete('1.0', '40.0')
        self.log.see('end')
        self.log.configure(state='disabled')

    def busy(self, active):
        for widget, state in self.editable:
            widget.configure(state='disabled' if active else state)
        for button in (self.start_button, self.save_button, self.reset_button):
            button.configure(state='disabled' if active else 'normal')
        self.stop_button.configure(state='normal' if active else 'disabled')

    def start(self):
        try:
            argv = settings.to_argv(self.values())
            self.runner.start(argv, ROOT)
        except (ValueError, OSError) as exc:
            self.status.set('Session not opened')
            self.messagebox.showerror('Check setup', str(exc), parent=self.root)
            return
        self.busy(True)
        self.status.set('Opening session — warming up camera / connecting as selected…')
        self.append_log('Opening ' + self.variables['mode'].get() + ' / ' + self.variables['output'].get())

    def stop(self):
        self.runner.stop()
        self.status.set('Ending session…')
        self.stop_button.configure(state='disabled')

    def save(self):
        try:
            settings.save(SETTINGS_PATH, self.values())
            self.status.set('Settings saved for next time. motor_config.py is unchanged.')
        except (ValueError, OSError) as exc:
            self.messagebox.showerror('Settings not saved', str(exc), parent=self.root)

    def reset(self):
        self.set_values(settings.defaults())
        self.status.set('Defaults loaded. Click Save settings to use these next time.')

    def poll(self):
        for update in self.runner.poll():
            state = update['state']
            if state == 'log':
                self.append_log(update['message'])
            elif state in ('active', 'paused'):
                connection = 'Motor connected' if update.get('motor') else 'Preview — no motor'
                self.status.set(connection + (' | Active' if state == 'active' else
                                             ' | Paused — use Start motion in the control window'))
            elif state == 'ended':
                self.busy(False)
                if update['code'] and not update['requested']:
                    self.status.set('Session failed. See the details below; correct settings and try again.')
                    self.append_log(f'Exit code: {update["code"]}')
                else:
                    self.status.set('Session ended. Ready to open another.')
        if self.closing and not self.runner.running:
            self.root.destroy()
            return
        self.root.after(100, self.poll)

    def close(self):
        self.closing = True
        if self.runner.running:
            self.stop()
        else:
            self.root.destroy()


def main():
    try:
        import tkinter as tk
    except ImportError as exc:
        raise SystemExit('This Python installation has no Tk interface. Install Tk support for it, '
                         'or run hand_tracker.py with the existing terminal options.') from exc
    root = tk.Tk()
    Launcher(root)
    root.mainloop()


if __name__ == '__main__':
    main()
