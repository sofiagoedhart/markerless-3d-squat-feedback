"""Receive settings and commands sent from Unity."""
from __future__ import annotations
import json
import socket
import threading

VALID_TARGETS = ("partial", "parallel", "deep")


class ControlListener:
    def __init__(self, host="127.0.0.1", port=5007, target="parallel", reps=8):
        self.addr = (host, int(port))
        self.target = target
        self.reps = int(reps)
        self._dirty = False
        self._start = False
        self._end = False
        self._calib = False
        self._lock = threading.Lock()
        self._sock = None
        self._thread = None
        self._run = False

    def start(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.bind(self.addr)
            self._sock.settimeout(0.5)
        except OSError as e:
            print(f"[control] could not listen on {self.addr[1]}: {e} — "
                  f"settings from Unity will be ignored this run.")
            self._sock = None
            return self
        self._run = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[control] listening for settings on {self.addr[0]}:{self.addr[1]}")
        return self

    def _loop(self):
        while self._run:
            try:
                data, _ = self._sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                msg = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            with self._lock:
                t = msg.get("target")
                if isinstance(t, str) and t in VALID_TARGETS and t != self.target:
                    self.target = t
                    self._dirty = True
                    print(f"[control] target -> {t}")
                if msg.get("cmd") == "start":
                    self._start = True
                    print("[control] start")
                if msg.get("cmd") == "calibrate":
                    self._calib = True
                    print("[control] calibrate")
                if msg.get("cmd") == "endset":
                    self._end = True
                    print("[control] end of set")
                r = msg.get("reps")
                if isinstance(r, int) and 3 <= r <= 20 and r != self.reps:
                    self.reps = r
                    self._dirty = True
                    print(f"[control] reps -> {r}")

    def take(self) -> bool:
        """True exactly once after each change, so callers can react and not re-apply the same setting on every frame."""
        with self._lock:
            d, self._dirty = self._dirty, False
            return d

    def take_start(self) -> bool:
        """True once per Start press."""
        with self._lock:
            s, self._start = self._start, False
            return s

    def take_calibrate(self) -> bool:
        """True once per Enter pressed on Unity's pre-calibration screen."""
        with self._lock:
            c, self._calib = self._calib, False
            return c

    def take_end(self) -> bool:
        """True once for each set that Unity has ended."""
        with self._lock:
            e, self._end = self._end, False
            return e

    def stop(self):
        self._run = False
        try:
            if self._sock:
                self._sock.close()
        except OSError:
            pass


if __name__ == "__main__":
    import time
    c = ControlListener().start()
    print("Send a test message from another terminal:\n"
          "  python -c \"import socket,json;"
          "socket.socket(2,2).sendto(json.dumps({'target':'deep','reps':5}).encode(),"
          "('127.0.0.1',5007))\"\nCtrl-C to stop.")
    try:
        while True:
            if c.take():
                print("  changed ->", c.target, c.reps)
            time.sleep(0.2)
    except KeyboardInterrupt:
        c.stop()
