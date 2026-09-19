#!/usr/bin/env python3
"""持续把已连接 Joy-Con 的按键、摇杆、陀螺仪和 Ring-Con 弯曲打印到终端。"""

from __future__ import annotations

import argparse
import array
import fcntl
import os
import select
import struct
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from ringcon_hid import (
    JoyCon,
    disable_ringcon,
    enable_ringcon,
    find_right_hidraw,
    flex_action,
)

INPUT_DIR = Path("/dev/input")
SYS_INPUT = Path("/sys/class/input")
EVENT_STRUCT = struct.Struct("llHHi")
HID_REPORT_SIZE = 64
HID_IMU_REPORT = 0x30
HID_IMU_REPORT_LEN = 49

EV_SYN, EV_KEY, EV_ABS = 0x00, 0x01, 0x03
SYN_REPORT = 0
ABS_X, ABS_Y, ABS_Z = 0x00, 0x01, 0x02
ABS_RX, ABS_RY, ABS_RZ = 0x03, 0x04, 0x05

STICK_MAX = 32767
STICK_DEADZONE = 1500
STICK_PRINT_DELTA = 800
GYRO_MOVE_DPS = 30.0
GYRO_STILL_DPS = 12.0
GYRO_PRINT_HZ = 12.0
ACCEL_RES_PER_G = 4096.0
GYRO_RES_PER_DPS = 14.247
EVDEV_GYRO_RES_PER_DPS = 14247.0

BTN_SOUTH = 0x130
BTN_EAST = 0x131
BTN_NORTH = 0x133
BTN_WEST = 0x134
BTN_Z = 0x135
BTN_TL = 0x136
BTN_TR = 0x137
BTN_TL2 = 0x138
BTN_TR2 = 0x139
BTN_SELECT = 0x13A
BTN_START = 0x13B
BTN_MODE = 0x13C
BTN_THUMBL = 0x13D
BTN_THUMBR = 0x13E
BTN_DPAD_UP = 0x220
BTN_DPAD_DOWN = 0x221
BTN_DPAD_LEFT = 0x222
BTN_DPAD_RIGHT = 0x223

LEFT_BUTTONS = {
    BTN_TL: "L",
    BTN_TL2: "ZL",
    BTN_TR: "SL",
    BTN_TR2: "SR",
    BTN_SELECT: "Minus",
    BTN_THUMBL: "左摇杆键",
    BTN_DPAD_UP: "上",
    BTN_DPAD_DOWN: "下",
    BTN_DPAD_LEFT: "左",
    BTN_DPAD_RIGHT: "右",
    BTN_Z: "Capture",
}

RIGHT_BUTTONS = {
    BTN_EAST: "A",
    BTN_SOUTH: "B",
    BTN_NORTH: "X",
    BTN_WEST: "Y",
    BTN_TR: "R",
    BTN_TR2: "ZR",
    BTN_TL: "SL",
    BTN_TL2: "SR",
    BTN_START: "Plus",
    BTN_THUMBR: "右摇杆键",
    BTN_MODE: "Home",
}

STICK_AXES = {
    ABS_X: "x",
    ABS_Y: "y",
    ABS_RX: "x",
    ABS_RY: "y",
}


def _ioc_read(type_code: str, nr: int, size: int) -> int:
    return (2 << 30) | (size << 16) | (ord(type_code) << 8) | nr


def eviocgabs(axis: int) -> int:
    return _ioc_read("E", 0x40 + axis, 24)


HIDIOCGRAWNAME = _ioc_read("H", 0x04, 256)


@dataclass
class StickState:
    x: int = 0
    y: int = 0
    last_printed: tuple[int, int] | None = None
    dirty: bool = False

    def set_axis(self, axis: str, value: int) -> None:
        if axis == "x":
            self.x = value
        elif axis == "y":
            self.y = value
        self.dirty = True

    def consume_if_changed(self) -> tuple[int, int] | None:
        if not self.dirty:
            return None
        self.dirty = False
        if abs(self.x) < STICK_DEADZONE and abs(self.y) < STICK_DEADZONE:
            current = (0, 0)
        else:
            current = (self.x, self.y)
        if self.last_printed is None:
            changed = current != (0, 0)
        else:
            dx = abs(current[0] - self.last_printed[0])
            dy = abs(current[1] - self.last_printed[1])
            changed = dx >= STICK_PRINT_DELTA or dy >= STICK_PRINT_DELTA
        if not changed:
            return None
        self.last_printed = current
        return current


@dataclass
class ImuState:
    ax: float = 0.0
    ay: float = 0.0
    az: float = 0.0
    gx: float = 0.0
    gy: float = 0.0
    gz: float = 0.0
    dirty: bool = False
    moving: bool = False
    last_print: float = 0.0


@dataclass
class Device:
    path: Path
    name: str
    side: str
    fd: int
    kind: str
    buttons: dict[int, str] = field(default_factory=dict)
    stick: StickState = field(default_factory=StickState)
    imu: ImuState = field(default_factory=ImuState)
    accel_res: float = ACCEL_RES_PER_G
    gyro_res: float = EVDEV_GYRO_RES_PER_DPS
    ringcon: bool = False
    last_flex: int | None = None
    hid: JoyCon | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="在终端持续打印 Joy-Con 操作")
    parser.add_argument("--no-gyro", action="store_true", help="不读取陀螺仪")
    parser.add_argument(
        "--raw-imu",
        action="store_true",
        help="不滤波，尽量输出每一帧体感数据",
    )
    parser.add_argument(
        "--ringcon",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="右 Joy-Con 已接 Ring-Con 时初始化 MCU，并在弯曲变化时输出 flex",
    )
    return parser.parse_args()


def side_of(name: str) -> str:
    if "(L)" in name:
        return "L"
    if "(R)" in name:
        return "R"
    return "?"


def buttons_for(name: str) -> dict[int, str]:
    if "(L)" in name:
        return LEFT_BUTTONS
    if "(R)" in name:
        return RIGHT_BUTTONS
    return {**LEFT_BUTTONS, **RIGHT_BUTTONS}


def iter_named_events() -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    if not SYS_INPUT.exists():
        return found
    for event_dir in sorted(SYS_INPUT.glob("event*")):
        name_path = event_dir / "device" / "name"
        if not name_path.exists():
            continue
        name = name_path.read_text(encoding="utf-8", errors="replace").strip()
        node = INPUT_DIR / event_dir.name
        if node.exists():
            found.append((node, name))
    return found


def try_open(path: Path, *, read_write: bool = False) -> int | None:
    flags = os.O_RDWR if read_write else os.O_RDONLY
    try:
        return os.open(path, flags | os.O_NONBLOCK)
    except PermissionError:
        return None
    except OSError:
        return None


def abs_resolution(fd: int, axis: int, default: float) -> float:
    buf = array.array("i", [0] * 6)
    try:
        fcntl.ioctl(fd, eviocgabs(axis), buf, True)
    except OSError:
        return default
    res = buf[5]
    return float(res) if res else default


def hidraw_name(fd: int) -> str:
    buf = bytearray(256)
    try:
        fcntl.ioctl(fd, HIDIOCGRAWNAME, buf, True)
    except OSError:
        return ""
    return bytes(buf).split(b"\x00", 1)[0].decode("utf-8", errors="replace")


def open_pad_devices() -> tuple[list[Device], list[str]]:
    devices: list[Device] = []
    skipped: list[str] = []
    for path, name in iter_named_events():
        if "Joy-Con" not in name or "(IMU)" in name:
            continue
        fd = try_open(path)
        if fd is None:
            skipped.append(f"{path} ({name})")
            continue
        devices.append(
            Device(
                path=path,
                name=name,
                side=side_of(name),
                fd=fd,
                kind="pad",
                buttons=buttons_for(name),
            )
        )
    return devices, skipped


def open_imu_evdev(already: set[str]) -> tuple[list[Device], list[str]]:
    devices: list[Device] = []
    skipped: list[str] = []
    for path, name in iter_named_events():
        if "Joy-Con" not in name or "(IMU)" not in name:
            continue
        side = side_of(name)
        if side in already:
            continue
        fd = try_open(path)
        if fd is None:
            skipped.append(f"{path} ({name})")
            continue
        devices.append(
            Device(
                path=path,
                name=name,
                side=side,
                fd=fd,
                kind="imu-evdev",
                accel_res=abs_resolution(fd, ABS_X, ACCEL_RES_PER_G),
                gyro_res=abs_resolution(fd, ABS_RX, EVDEV_GYRO_RES_PER_DPS),
            )
        )
        already.add(side)
    return devices, skipped


def open_imu_hidraw(already: set[str]) -> list[Device]:
    devices: list[Device] = []
    for path in sorted(Path("/dev").glob("hidraw*")):
        fd = try_open(path)
        if fd is None:
            continue
        name = hidraw_name(fd)
        if "Joy-Con" not in name:
            os.close(fd)
            continue
        side = side_of(name)
        if side in already:
            os.close(fd)
            continue
        devices.append(
            Device(
                path=path,
                name=f"{name} hidraw IMU",
                side=side,
                fd=fd,
                kind="imu-hidraw",
                accel_res=ACCEL_RES_PER_G,
                gyro_res=GYRO_RES_PER_DPS,
            )
        )
        already.add(side)
    return devices


def open_ringcon_device() -> tuple[Device | None, str]:
    path = find_right_hidraw()
    if path is None:
        return None, "找不到 Joy-Con (R) 的 hidraw 节点"
    fd = try_open(path, read_write=True)
    if fd is None:
        return None, f"无法读写 {path}（需要 hidraw 写权限）"
    jc = JoyCon(path, fd=fd)
    notes: list[str] = []

    def note(msg: str) -> None:
        notes.append(msg)
        print(f"  Ring-Con  {msg}", flush=True)

    print("正在初始化 Ring-Con …", flush=True)
    ready = enable_ringcon(jc, note, imu_rounds=1)
    if not ready:
        os.close(fd)
        detail = notes[-1] if notes else "初始化失败"
        return None, detail
    return (
        Device(
            path=path,
            name="Joy-Con (R) hidraw Ring-Con",
            side="R",
            fd=fd,
            kind="imu-hidraw",
            accel_res=ACCEL_RES_PER_G,
            gyro_res=GYRO_RES_PER_DPS,
            ringcon=True,
            hid=jc,
        ),
        "",
    )


def format_ts(sec: int, usec: int) -> str:
    local = time.localtime(sec)
    return time.strftime("%H:%M:%S", local) + f".{usec // 1000:03d}"


def now_ts() -> str:
    current = time.time()
    sec = int(current)
    usec = int((current - sec) * 1_000_000)
    return format_ts(sec, usec)


def format_stick(value: int) -> str:
    return f"{value / STICK_MAX:+.2f}"


def emit(ts: str, side: str, action: str, detail: str) -> None:
    print(f"{ts}  {side:<2}  {action:<8}  {detail}", flush=True)


def handle_key(dev: Device, sec: int, usec: int, code: int, value: int) -> None:
    if value == 2:
        return
    label = dev.buttons.get(code, f"按键 0x{code:03x}")
    state = "按下" if value else "松开"
    emit(format_ts(sec, usec), dev.side, label, state)


def handle_pad_abs(dev: Device, code: int, value: int) -> None:
    axis = STICK_AXES.get(code)
    if axis is None:
        return
    dev.stick.set_axis(axis, value)


def flush_stick(dev: Device, sec: int, usec: int) -> None:
    current = dev.stick.consume_if_changed()
    if current is None:
        return
    x, y = current
    emit(format_ts(sec, usec), dev.side, "摇杆", f"x={format_stick(x)}  y={format_stick(y)}")


def gyro_magnitude(imu: ImuState) -> float:
    return (imu.gx * imu.gx + imu.gy * imu.gy + imu.gz * imu.gz) ** 0.5


def maybe_print_imu(dev: Device, ts: str, *, raw: bool) -> None:
    imu = dev.imu
    if not imu.dirty:
        return
    imu.dirty = False
    mag = gyro_magnitude(imu)
    now = time.monotonic()
    min_interval = 0.0 if raw else 1.0 / GYRO_PRINT_HZ
    if now - imu.last_print < min_interval:
        return
    if raw or mag >= GYRO_MOVE_DPS:
        imu.moving = True
        imu.last_print = now
        emit(
            ts,
            dev.side,
            "陀螺仪",
            f"gx={imu.gx:+6.1f}  gy={imu.gy:+6.1f}  gz={imu.gz:+6.1f}  °/s"
            f"  |ω|={mag:5.1f}"
            f"  ax={imu.ax:+.2f}  ay={imu.ay:+.2f}  az={imu.az:+.2f} g",
        )
        return
    if imu.moving and mag < GYRO_STILL_DPS:
        imu.moving = False
        imu.last_print = now
        emit(ts, dev.side, "陀螺仪", "静止")


def handle_imu_abs(dev: Device, code: int, value: int) -> None:
    imu = dev.imu
    if code == ABS_X:
        imu.ax = value / dev.accel_res
    elif code == ABS_Y:
        imu.ay = value / dev.accel_res
    elif code == ABS_Z:
        imu.az = value / dev.accel_res
    elif code == ABS_RX:
        imu.gx = value / dev.gyro_res
    elif code == ABS_RY:
        imu.gy = value / dev.gyro_res
    elif code == ABS_RZ:
        imu.gz = value / dev.gyro_res
    else:
        return
    imu.dirty = True


def parse_hidraw_imu(
    data: bytes, *, ringcon: bool = False
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    if len(data) < HID_IMU_REPORT_LEN or data[0] != HID_IMU_REPORT:
        return None
    ax = ay = az = gx = gy = gz = 0.0
    accel_n = 0
    for i in range(3):
        offset = 13 + i * 12
        sample = struct.unpack_from("<hhhhhh", data, offset)
        if not (ringcon and i == 2):
            ax += sample[0]
            ay += sample[1]
            az += sample[2]
            accel_n += 1
        gx += sample[3]
        gy += sample[4]
        gz += sample[5]
    if accel_n == 0:
        return None
    ax /= accel_n * ACCEL_RES_PER_G
    ay /= accel_n * ACCEL_RES_PER_G
    az /= accel_n * ACCEL_RES_PER_G
    gx /= 3.0 * GYRO_RES_PER_DPS
    gy /= 3.0 * GYRO_RES_PER_DPS
    gz /= 3.0 * GYRO_RES_PER_DPS
    return (ax, ay, az), (gx, gy, gz)


def maybe_print_ringcon(dev: Device, flex: int) -> None:
    if flex == dev.last_flex:
        return
    dev.last_flex = flex
    action, value = flex_action(flex)
    emit(now_ts(), dev.side, "Ring-Con", f"flex={flex:3d}  {action}  {value:+.2f}")


def apply_imu_sample(
    dev: Device,
    accel: tuple[float, float, float],
    gyro: tuple[float, float, float],
) -> None:
    imu = dev.imu
    imu.ax, imu.ay, imu.az = accel
    imu.gx, imu.gy, imu.gz = gyro
    imu.dirty = True


def read_evdev(dev: Device, *, raw_imu: bool) -> None:
    while True:
        try:
            chunk = os.read(dev.fd, EVENT_STRUCT.size)
        except BlockingIOError:
            return
        except OSError as exc:
            print(f"{dev.name} 读取失败：{exc}", file=sys.stderr, flush=True)
            return
        if len(chunk) < EVENT_STRUCT.size:
            return
        sec, usec, ev_type, code, value = EVENT_STRUCT.unpack(chunk)
        if dev.kind == "pad":
            if ev_type == EV_KEY:
                handle_key(dev, sec, usec, code, value)
            elif ev_type == EV_ABS:
                handle_pad_abs(dev, code, value)
            elif ev_type == EV_SYN and code == SYN_REPORT:
                flush_stick(dev, sec, usec)
            continue
        if ev_type == EV_ABS:
            handle_imu_abs(dev, code, value)
        elif ev_type == EV_SYN and code == SYN_REPORT:
            maybe_print_imu(dev, format_ts(sec, usec), raw=raw_imu)


def read_hidraw(dev: Device, *, raw_imu: bool, enable_imu: bool) -> None:
    while True:
        try:
            chunk = os.read(dev.fd, HID_REPORT_SIZE)
        except BlockingIOError:
            return
        except OSError as exc:
            print(f"{dev.name} 读取失败：{exc}", file=sys.stderr, flush=True)
            return
        if not chunk:
            return
        if dev.ringcon and len(chunk) > 40 and chunk[0] in (HID_IMU_REPORT, 0x31):
            maybe_print_ringcon(dev, chunk[40])
        if not enable_imu:
            continue
        parsed = parse_hidraw_imu(chunk, ringcon=dev.ringcon)
        if parsed is None:
            continue
        apply_imu_sample(dev, parsed[0], parsed[1])
        maybe_print_imu(dev, now_ts(), raw=raw_imu)


def close_all(devices: list[Device]) -> None:
    for dev in devices:
        if dev.hid is not None:
            disable_ringcon(dev.hid)
        try:
            os.close(dev.fd)
        except OSError:
            pass


def main() -> int:
    args = parse_args()
    print("正在查找 Joy-Con …", flush=True)

    while True:
        devices: list[Device] = []
        skipped_pads: list[str] = []
        skipped_imu: list[str] = []
        imu_sides: set[str] = set()
        if args.ringcon:
            ring_dev, err = open_ringcon_device()
            if ring_dev is None:
                print(f"Ring-Con 初始化失败：{err}", file=sys.stderr, flush=True)
            else:
                devices.append(ring_dev)
                imu_sides.add(ring_dev.side)
                print("Ring-Con 已连接，弯曲变化时会输出 flex（拉伸为负，挤压为正）。", flush=True)
        pads, skipped_pads = open_pad_devices()
        devices.extend(pads)
        if not args.no_gyro:
            imu_devs, skipped_imu = open_imu_evdev(imu_sides)
            devices.extend(imu_devs)
            devices.extend(open_imu_hidraw(imu_sides))
        if devices:
            break
        print("还没有可读的 Joy-Con，2 秒后重试。", flush=True)
        time.sleep(2)

    print("开始监听：", flush=True)
    for dev in devices:
        extra = " ringcon" if dev.ringcon else ""
        print(f"  [{dev.side}] {dev.name}  {dev.path}  ({dev.kind}{extra})", flush=True)
    imu_ok = {dev.side for dev in devices if dev.kind.startswith("imu")}
    skipped = list(skipped_pads)
    if not imu_ok:
        skipped.extend(skipped_imu)
    if skipped:
        print("没有权限读取：", file=sys.stderr)
        for item in skipped:
            print(f"  {item}", file=sys.stderr)
        if skipped_imu and not imu_ok:
            print(
                "可以把当前用户加入 input 组，或按 docs/linux-notes.md 安装 IMU udev 规则后重连手柄。",
                file=sys.stderr,
            )
    print("按 Ctrl+C 结束。\n", flush=True)

    fd_map = {dev.fd: dev for dev in devices}
    enable_imu = not args.no_gyro
    try:
        while True:
            ready, _, _ = select.select(list(fd_map), [], [], 1.0)
            for fd in ready:
                dev = fd_map[fd]
                if dev.kind == "imu-hidraw":
                    read_hidraw(dev, raw_imu=args.raw_imu, enable_imu=enable_imu)
                else:
                    read_evdev(dev, raw_imu=args.raw_imu)
    except KeyboardInterrupt:
        print("\n已停止。", flush=True)
        return 0
    finally:
        close_all(devices)


if __name__ == "__main__":
    raise SystemExit(main())
