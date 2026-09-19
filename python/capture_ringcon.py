#!/usr/bin/env python3
"""按 Ringcon-Driver 的协议初始化右 Joy-Con MCU，并录制 Ring-Con 弯曲数据。"""

from __future__ import annotations

import argparse
import struct
import time
from pathlib import Path

from ringcon_hid import JoyCon, enable_ringcon, find_right_hidraw, try_unbind_nintendo

ROOT = Path(__file__).resolve().parent.parent
DATA_LOGS = ROOT / "data" / "logs"


def imu_samples(pkt: bytes) -> list[tuple[int, int, int, int, int, int]]:
    samples = []
    if len(pkt) < 13 + 36:
        return samples
    for index in range(3):
        samples.append(struct.unpack_from("<hhhhhh", pkt, 13 + index * 12))
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化并录制 Ring-Con")
    parser.add_argument("--seconds", type=float, default=70.0)
    parser.add_argument("--device", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--init-only", action="store_true")
    parser.add_argument("--no-unbind", action="store_true")
    args = parser.parse_args()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = DATA_LOGS
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.out) if args.out else out_dir / f"ringcon-{stamp}.log"
    csv_path = log_path.with_suffix(".csv")

    if not args.no_unbind:
        for line in try_unbind_nintendo():
            print(f"META  {line}", flush=True)

    device = Path(args.device) if args.device else find_right_hidraw()
    if device is None:
        raise SystemExit("找不到 Joy-Con (R) 的 hidraw 节点")
    jc = JoyCon(device)
    ready = False
    with log_path.open("w", encoding="utf-8") as log, csv_path.open("w", encoding="utf-8") as csv:
        log.write(f"# device={device}\n")
        csv.write("t,rid,conn,flex,ay2,ax2,az2,ax0,ay0,az0,gx0,gy0,gz0\n")

        def note(msg: str) -> None:
            line = f"{time.time():.6f}  META  {msg}"
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()

        note(f"open {device}")
        ready = enable_ringcon(jc, note)
        if args.init_only:
            note(f"init-only done ready={ready}")
            jc.close()
            print(f"wrote {log_path}", flush=True)
            return 0 if ready else 2

        note(f"recording {args.seconds:.0f}s — 现在挤/松健身环  ready={ready}")
        start = time.time()
        n_pkt = 0
        last_flex = None
        while time.time() - start < args.seconds:
            pkt = jc.read(0.2)
            if not pkt:
                continue
            n_pkt += 1
            t = time.time() - start
            rid = pkt[0]
            conn = pkt[2] if len(pkt) > 2 else -1
            flex = pkt[40] if len(pkt) > 40 else -1
            samples = imu_samples(pkt)
            ay2 = samples[2][1] if len(samples) == 3 else ""
            ax2 = samples[2][0] if len(samples) == 3 else ""
            az2 = samples[2][2] if len(samples) == 3 else ""
            ax0 = ay0 = az0 = gx0 = gy0 = gz0 = ""
            if samples:
                ax0, ay0, az0, gx0, gy0, gz0 = samples[0]
            csv.write(
                f"{t:.4f},{rid},{conn},{flex},{ay2},{ax2},{az2},{ax0},{ay0},{az0},{gx0},{gy0},{gz0}\n"
            )
            if rid in (0x30, 0x31) and flex != last_flex:
                print(f"{t:6.2f}s  flex={flex:3d}  ay2={ay2}  conn=0x{conn:02x}", flush=True)
                last_flex = flex
            if rid == 0x21 or n_pkt % 40 == 0:
                log.write(f"{t:.4f}  {rid:02x}  flex={flex}  ay2={ay2}  conn={conn:02x}\n")

        note(f"done packets={n_pkt} ready={ready}")
        jc.subcmd(0x22, bytes([0x00]))
        jc.subcmd(0x03, bytes([0x30]))

    jc.close()
    print(f"wrote {log_path}", flush=True)
    print(f"wrote {csv_path}", flush=True)
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
