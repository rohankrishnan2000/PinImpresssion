"""Optional local launcher channel; CLI runs do not start a reader thread.

Only QUIT is accepted on stdin. Hardware actions remain on the tracker thread.
Closing the launcher pipe requests a clean quit, too.
"""
import json
import queue
import sys
import threading

PREFIX = 'PIN_IMPRESSION_STATUS '


class SessionControl:
    def __init__(self, stream=None, output=None):
        self.stream = sys.stdin if stream is None else stream
        self.output = sys.stdout if output is None else output
        self.commands = queue.SimpleQueue()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        try:
            for line in self.stream:
                if line.strip() == 'QUIT':
                    self.commands.put('quit')
                    return
        finally:
            self.commands.put('quit')

    def quit_requested(self):
        try:
            return self.commands.get_nowait() == 'quit'
        except queue.Empty:
            return False

    def report(self, state, **details):
        try:
            print(PREFIX + json.dumps({'state': state, **details}), file=self.output, flush=True)
        except (BrokenPipeError, OSError):
            self.commands.put('quit')
