"""Print what the pipeline is streaming to Unity."""
import argparse
import json
import socket


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5006)
    ap.add_argument("--every", type=int, default=10,
                    help="print one packet in every N, so the console stays readable")
    a = ap.parse_args()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", a.port))
    print(f"listening on {a.port} — Ctrl-C to stop")
    n = 0
    try:
        while True:
            data, _ = s.recvfrom(65535)
            n += 1
            if n % a.every:
                continue
            p = json.loads(data.decode())
            state = p.get("state") or {}
            phase = p.get("phase") or state.get("phase") or "-"
            if phase == "CALIB":
                seen = sum(1 for j in (p.get("joints") or []) if j)
                cams = "  ".join(f"cam{c['cam']}:{c['n']:2d}"
                                 for c in (p.get("cams") or []))
                cd = p.get("countdown")
                print(f"[{p['seq']:5d}] CALIB  present={p['present']}  "
                      f"joints={seen:2d}/17  {cams}"
                      + (f"  countdown={cd}" if cd is not None else ""))
            else:
                print(f"[{p['seq']:5d}] {phase:8s} present={p['present']}  "
                      f"segments={len(p.get('seg') or {}):2d}  "
                      f"rep={state.get('rep')}  depth={state.get('depth_mm')}")
    except KeyboardInterrupt:
        print(f"\n{n} packets received")


if __name__ == "__main__":
    main()
