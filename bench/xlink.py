"""A stand-in for the ssh -Y link, for measurements: a TCP display that forwards to a local X server, delaying each
direction and limiting the bandwidth from the client to the server, and counting the bytes both ways. The same
counter for every way of drawing (Qt's xcb, either bridge), so their traffic compares.

    python bench/xlink.py --display 150 --to 99 [--delay-ms 8] [--mbps 25] --stats /tmp/.../link.json

Listens on 127.0.0.1:6000+display only. Clients use DISPLAY=localhost:<display> with a cookie for that display in
their XAUTHORITY (the X server's own cookie). --stats is rewritten (atomically) when the counters change:
{"up": bytes client to server, "down": ..., "connections": n}. The delay applies to each chunk as it arrives; the
bandwidth paces the upward direction (what images need). Measured through ssh -Y to the user's XQuartz: 14-16 ms
round trips and 17-29 MB/s (docs/measured.md, the prototype's F2).
"""
import argparse
import collections
import json
import os
import socket
import threading
import time


class Pipe:
    """One direction of one connection: read, hold for `delay`, pace at `rate` bytes/s (0: no limit), write."""

    def __init__(self, src, dst, delay, rate, count, name):
        self.src, self.dst, self.delay, self.rate, self.count = src, dst, delay, rate, count
        self.q: collections.deque = collections.deque()
        self.cv = threading.Condition()
        self.done = False
        threading.Thread(target=self._read, daemon=True, name=f"{name}-r").start()
        threading.Thread(target=self._write, daemon=True, name=f"{name}-w").start()

    def _read(self):
        try:
            while True:
                data = self.src.recv(1 << 16)
                if not data:
                    break
                with self.cv:
                    self.q.append((time.perf_counter() + self.delay, data))
                    self.cv.notify()
        except OSError:
            pass
        with self.cv:
            self.done = True
            self.cv.notify()

    def _write(self):
        free = 0.0                                      # when the paced link can take the next byte
        try:
            while True:
                with self.cv:
                    while not self.q and not self.done:
                        self.cv.wait()
                    if not self.q:
                        break
                    due, data = self.q.popleft()
                now = time.perf_counter()
                if self.rate:
                    free = max(free, now) + len(data) / self.rate
                    due = max(due, free)
                if due > now:
                    time.sleep(due - now)
                self.dst.sendall(data)
                self.count(len(data))
        except OSError:
            pass
        try:
            self.dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--display", type=int, required=True)
    ap.add_argument("--to", type=int, required=True, help="the local X server's display number")
    ap.add_argument("--delay-ms", type=float, default=0.0, help="one way, each direction")
    ap.add_argument("--mbps", type=float, default=0.0, help="MB/s from client to server; 0: no limit")
    ap.add_argument("--stats", required=True)
    a = ap.parse_args()
    counts = dict(up=0, down=0, connections=0)
    lock = threading.Lock()
    changed = threading.Event()

    def counter(key):
        def add(n):
            with lock:
                counts[key] += n
            changed.set()
        return add

    def dump():
        while True:
            changed.wait()
            changed.clear()
            with lock:
                d = dict(counts)
            tmp = a.stats + ".tmp"
            with open(tmp, "w") as f:
                json.dump(d, f)
            os.replace(tmp, a.stats)
            time.sleep(0.005)

    threading.Thread(target=dump, daemon=True).start()
    changed.set()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 6000 + a.display))
    srv.listen(16)
    delay, rate = a.delay_ms / 1e3, a.mbps * 1e6
    print(f"xlink: localhost:{a.display} -> :{a.to}, {a.delay_ms} ms each way, "
          f"{a.mbps or 'unlimited'} MB/s up", flush=True)
    while True:
        c, _ = srv.accept()
        c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(f"/tmp/.X11-unix/X{a.to}")
        with lock:
            counts["connections"] += 1
        n = counts["connections"]
        Pipe(c, s, delay, rate, counter("up"), f"up{n}")
        Pipe(s, c, delay, 0.0, counter("down"), f"down{n}")


if __name__ == "__main__":
    main()
