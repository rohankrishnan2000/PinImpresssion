"""Run the existing tracker as a child process without blocking the setup UI."""
from collections import deque
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from session_control import PREFIX


class SessionRunner:
    def __init__(self):
        self.process = None
        self.events = queue.Queue(maxsize=512)
        self.log = deque(maxlen=120)
        self.stop_time = None
        self.terminated = False

    @property
    def running(self):
        return self.process is not None

    def start(self, argv, directory):
        if self.running:
            raise ValueError('End the current session before opening another')
        directory = Path(directory)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        self.events = queue.Queue(maxsize=512)
        self.log.clear()
        self.stop_time, self.terminated = None, False
        self.process = subprocess.Popen(
            [sys.executable, '-u', str(directory / 'hand_tracker.py'), *argv, '--launcher-control'],
            cwd=str(directory), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
            creationflags=flags,
        )
        self.reader = threading.Thread(target=self._read, args=(self.process.stdout, self.events), daemon=True)
        self.reader.start()

    @staticmethod
    def _read(stream, events):
        try:
            for line in stream:
                try:
                    events.put_nowait(line.rstrip())
                except queue.Full:
                    pass  # Bound memory if a failed library floods output.
        finally:
            stream.close()

    def stop(self):
        if not self.process or self.stop_time is not None:
            return
        self.stop_time = time.monotonic()
        try:
            self.process.stdin.write('QUIT\n')
            self.process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    def poll(self):
        updates = []
        while True:
            try:
                line = self.events.get_nowait()
            except queue.Empty:
                break
            if line.startswith(PREFIX):
                try:
                    status = json.loads(line[len(PREFIX):])
                    if isinstance(status, dict) and status.get('state') in ('active', 'paused'):
                        updates.append(status)
                        continue
                except ValueError:
                    pass
            self.log.append(line)
            updates.append({'state': 'log', 'message': line})
        if self.process:
            code = self.process.poll()
            if code is not None:
                # Wait for the output reader on later UI ticks so final error lines
                # are collected before reporting process completion.
                if self.reader.is_alive() or not self.events.empty():
                    return updates
                self.process.stdin.close()
                self.process = None
                updates.append({'state': 'ended', 'code': code,
                                'requested': self.stop_time is not None})
            elif self.stop_time is not None:
                elapsed = time.monotonic() - self.stop_time
                if elapsed > 6:
                    self.process.kill()
                elif elapsed > 3 and not self.terminated:
                    self.process.terminate()
                    self.terminated = True
        return updates
