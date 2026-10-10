"""Listen to the pose UDP stream and print what is arriving."""
from __future__ import annotations
import argparse
import json
import socket
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5006)
    ap.add_argument("--seconds", type=float, default=0, help="0 = until Ctrl-C")
    a = ap.parse_args()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("127.0.0.1", a.port))
    except OSError as e:
        print(f"Cannot listen on {a.port}: {e}")
        print("Something else already holds the port — almost certainly Unity in "
              "Play mode. Stop Play and try again.")
        return
    s.settimeout(1.0)
    print(f"Listening on 127.0.0.1:{a.port}. Start the replay in another terminal. "
          f"Ctrl-C to stop.\n")

    n, bytes_total, t0, last = 0, 0, time.time(), 0.0
    try:
        while True:
            if a.seconds and time.time() - t0 > a.seconds:
                break
            try:
                data, _ = s.recvfrom(65535)
            except socket.timeout:
                if n == 0:
                    print("  ...nothing yet. Is replay_to_unity.py running?")
                continue
            n += 1
            bytes_total += len(data)
            now = time.time()
            if now - last < 1.0:
                continue
            last = now
            p = json.loads(data)
            st = p.get("state") or {}
            print(f"[{n:5d} packets, {bytes_total/1024:.0f} kB, "
                  f"{n/max(now-t0, 1e-6):.1f}/s]  present={p.get('present')}  "
                  f"segments={len(p.get('seg', {}))}  "
                  f"root={p.get('root')}  phase={st.get('phase')}  "
                  f"rep={st.get('rep')}  depth={st.get('depth_mm')}")
            if st.get("cue"):
                print(f"        live cue: {st['cue']}")
            if p.get("rep"):
                print(f"        REP FINISHED: {p['rep'].get('variation')} "
                      f"score={p['rep'].get('score')}")
    except KeyboardInterrupt:
        pass
    finally:
        s.close()
        dt = max(time.time() - t0, 1e-6)
        print(f"\n{n} packets in {dt:.1f} s ({n/dt:.1f}/s, "
              f"{bytes_total/1024:.0f} kB total).")
        if n == 0:
            print("Nothing arrived. Check that replay_to_unity.py is running and "
                  "that it is not using --no-send.")


if __name__ == "__main__":
    main()
