#!/usr/bin/env python3
"""Joy-Con hidraw 上的 Ring-Con MCU 初始化（对齐 Ringcon-Driver）。"""

from __future__ import annotations

import fcntl
import os
import select
import time
from collections.abc import Callable
from pathlib import Path

OUTPUT_LEN = 49
NEUTRAL_RUMBLE = bytes([0x00, 0x01, 0x40, 0x40, 0x00, 0x01, 0x40, 0x40])
FLEX_REST = 10
FLEX_PULL = 0
FLEX_PUSH = 20
CRC_TABLE = [
    0x00, 0x07, 0x0E, 0x09, 0x1C, 0x1B, 0x12, 0x15, 0x38, 0x3F, 0x36, 0x31, 0x24, 0x23, 0x2A, 0x2D,
    0x70, 0x77, 0x7E, 0x79, 0x6C, 0x6B, 0x62, 0x65, 0x48, 0x4F, 0x46, 0x41, 0x54, 0x53, 0x5A, 0x5D,
    0xE0, 0xE7, 0xEE, 0xE9, 0xFC, 0xFB, 0xF2, 0xF5, 0xD8, 0xDF, 0xD6, 0xD1, 0xC4, 0xC3, 0xCA, 0xCD,
    0x90, 0x97, 0x9E, 0x99, 0x8C, 0x8B, 0x82, 0x85, 0xA8, 0xAF, 0xA6, 0xA1, 0xB4, 0xB3, 0xBA, 0xBD,
    0xC7, 0xC0, 0xC9, 0xCE, 0xDB, 0xDC, 0xD5, 0xD2, 0xFF, 0xF8, 0xF1, 0xF6, 0xE3, 0xE4, 0xED, 0xEA,
    0xB7, 0xB0, 0xB9, 0xBE, 0xAB, 0xAC, 0xA5, 0xA2, 0x8F, 0x88, 0x81, 0x86, 0x93, 0x94, 0x9D, 0x9A,
    0x27, 0x20, 0x29, 0x2E, 0x3B, 0x3C, 0x35, 0x32, 0x1F, 0x18, 0x11, 0x16, 0x03, 0x04, 0x0D, 0x0A,
    0x57, 0x50, 0x59, 0x5E, 0x4B, 0x4C, 0x45, 0x42, 0x6F, 0x68, 0x61, 0x66, 0x73, 0x74, 0x7D, 0x7A,
    0x89, 0x8E, 0x87, 0x80, 0x95, 0x92, 0x9B, 0x9C, 0xB1, 0xB6, 0xBF, 0xB8, 0xAD, 0xAA, 0xA3, 0xA4,
    0xF9, 0xFE, 0xF7, 0xF0, 0xE5, 0xE2, 0xEB, 0xEC, 0xC1, 0xC6, 0xCF, 0xC8, 0xDD, 0xDA, 0xD3, 0xD4,
    0x69, 0x6E, 0x67, 0x60, 0x75, 0x72, 0x7B, 0x7C, 0x51, 0x56, 0x5F, 0x58, 0x4D, 0x4A, 0x43, 0x44,
    0x19, 0x1E, 0x17, 0x10, 0x05, 0x02, 0x0B, 0x0C, 0x21, 0x26, 0x2F, 0x28, 0x3D, 0x3A, 0x33, 0x34,
    0x4E, 0x49, 0x40, 0x47, 0x52, 0x55, 0x5C, 0x5B, 0x76, 0x71, 0x78, 0x7F, 0x6A, 0x6D, 0x64, 0x63,
    0x3E, 0x39, 0x30, 0x37, 0x22, 0x25, 0x2C, 0x2B, 0x06, 0x01, 0x08, 0x0F, 0x1A, 0x1D, 0x14, 0x13,
    0xAE, 0xA9, 0xA0, 0xA7, 0xB2, 0xB5, 0xBC, 0xBB, 0x96, 0x91, 0x98, 0x9F, 0x8A, 0x8D, 0x84, 0x83,
    0xDE, 0xD9, 0xD0, 0xD7, 0xC2, 0xC5, 0xCC, 0xCB, 0xE6, 0xE1, 0xE8, 0xEF, 0xFA, 0xFD, 0xF4, 0xF3,
]

NoteFn = Callable[[str], None]


def crc8(data: bytes) -> int:
    value = 0
    for byte in data:
        value = CRC_TABLE[value ^ byte]
    return value


def hidraw_name(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        buf = bytearray(256)
        ioctl = (2 << 30) | (256 << 16) | (ord("H") << 8) | 0x04
        fcntl.ioctl(fd, ioctl, buf, True)
        return bytes(buf).split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    finally:
        os.close(fd)


def find_right_hidraw() -> Path | None:
    for path in sorted(Path("/dev").glob("hidraw*")):
        try:
            name = hidraw_name(path)
        except OSError:
            continue
        if name == "Joy-Con (R)":
            return path
    return None


def try_unbind_nintendo() -> list[str]:
    notes: list[str] = []
    driver = Path("/sys/bus/hid/drivers/nintendo")
    if not driver.exists():
        return notes
    for device in driver.glob("*:057E:2007.*"):
        unbind = driver / "unbind"
        try:
            unbind.write_text(device.name)
            notes.append(f"unbound {device.name}")
        except OSError as exc:
            notes.append(f"无法解绑 {device.name}: {exc}")
    return notes


def flex_action(flex: int) -> tuple[str, float]:
    """返回动作名和相对中性点的归一化值：拉伸为负，挤压为正。"""
    span = float(FLEX_PUSH - FLEX_REST)
    value = (flex - FLEX_REST) / span
    if flex < FLEX_REST:
        return "拉伸", value
    if flex > FLEX_REST:
        return "挤压", value
    return "静止", 0.0


class JoyCon:
    def __init__(self, path: Path, fd: int | None = None) -> None:
        self.path = path
        self.fd = fd if fd is not None else os.open(path, os.O_RDWR | os.O_NONBLOCK)
        self.owns_fd = fd is None
        self.counter = 0

    def close(self) -> None:
        if self.owns_fd:
            os.close(self.fd)

    def read(self, timeout: float) -> bytes | None:
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return None
        try:
            return os.read(self.fd, 362)
        except BlockingIOError:
            return None

    def write_out(self, buf: bytes) -> int:
        payload = bytes(buf[:OUTPUT_LEN] if len(buf) >= OUTPUT_LEN else buf)
        try:
            return os.write(self.fd, payload)
        except OSError:
            padded = payload + bytes(64 - len(payload))
            return os.write(self.fd, padded)

    def _blank(self) -> bytearray:
        buf = bytearray(OUTPUT_LEN)
        buf[0] = 0x01
        buf[1] = self.counter & 0xF
        self.counter = (self.counter + 1) & 0xF
        return buf

    def subcmd(self, cmd: int, data: bytes = b"") -> None:
        buf = self._blank()
        buf[2:10] = NEUTRAL_RUMBLE
        buf[10] = cmd
        buf[11 : 11 + len(data)] = data
        self.write_out(buf)

    def wait_ack(self, cmd: int, predicate, tries: int = 12, timeout: float = 0.064) -> bytes | None:
        for _ in range(tries):
            pkt = self.read(timeout)
            if not pkt:
                continue
            if pkt[0] == 0x21 and len(pkt) > 14 and pkt[14] == cmd and predicate(pkt):
                return pkt
        return None

    def subcmd_ack(self, cmd: int, data: bytes = b"", tries: int = 12) -> bytes | None:
        self.subcmd(cmd, data)
        return self.wait_ack(cmd, lambda pkt: True, tries=tries)

    def mcu_cmd(self, cmd: int, data: bytes = b"") -> None:
        buf = self._blank()
        buf[10] = cmd
        buf[11 : 11 + len(data)] = data
        self.write_out(buf)

    def mcu_21(self, sub: int, mode: int) -> None:
        buf = self._blank()
        buf[10] = 0x21
        buf[11] = 0x21
        buf[12] = sub
        buf[13] = mode
        buf[48] = crc8(bytes(buf[12:48]))
        self.write_out(buf)


def ring_config() -> bytes:
    cfg = bytearray(38)
    cfg[0:5] = bytes([0x06, 0x03, 0x25, 0x06, 0x00])
    cfg[8:13] = bytes([0x1C, 0x16, 0xED, 0x34, 0x36])
    cfg[16:24] = bytes([0x0A, 0x64, 0x0B, 0xE6, 0xA9, 0x22, 0x00, 0x00])
    cfg[24] = 0x04
    cfg[32:37] = bytes([0x90, 0xA8, 0xE1, 0x34, 0x36])
    return bytes(cfg)


def mcu_init(jc: JoyCon, note: NoteFn) -> bool:
    note("MCU 22 01")
    found = False
    for _ in range(12):
        jc.subcmd(0x22, bytes([0x01]))
        if jc.wait_ack(0x22, lambda pkt: pkt[13] == 0x80):
            found = True
            break
    note("MCU 22 01 " + ("ok" if found else "timeout"))

    note("MCU 21 21 00 03")
    found = False
    for _ in range(12):
        jc.mcu_21(0x00, 0x03)
        pkt = jc.wait_ack(
            0x21,
            lambda p: len(p) > 22 and p[15] == 0x01 and p[22] == 0x03,
        )
        if pkt:
            note(f"MCU mode3 ack={pkt[13:28].hex()}")
            found = True
            break
    if not found:
        note("MCU mode3 timeout")

    note("MCU 21 21 01 01")
    found = False
    for _ in range(12):
        jc.mcu_21(0x01, 0x01)
        pkt = jc.wait_ack(
            0x21,
            lambda p: len(p) > 17 and p[15] == 0x09 and p[17] == 0x01,
        )
        if pkt:
            note(f"MCU ext-ready ack={pkt[13:28].hex()}")
            found = True
            break
    if not found:
        note("MCU ext-ready timeout")

    note("GET_EXTERNAL_DEVICE_INFO 0x59")
    last = "no reply"
    for attempt in range(28):
        jc.mcu_cmd(0x59)
        pkt = jc.wait_ack(0x59, lambda p: len(p) > 16)
        if not pkt:
            continue
        status = pkt[15]
        ext = pkt[16]
        last = f"try={attempt} status=0x{status:02x} ext=0x{ext:02x} raw={pkt[13:24].hex()}"
        if ext == 0x20:
            note(last)
            return True
    note(f"没有检测到 Ring-Con（{last}）")
    return False


def enable_ringcon(jc: JoyCon, note: NoteFn, *, imu_rounds: int = 2) -> bool:
    note("vibration on")
    jc.subcmd_ack(0x48, bytes([0x01]))
    note("IMU on")
    jc.subcmd_ack(0x40, bytes([0x01]))
    note("report mode 0x30")
    jc.subcmd_ack(0x03, bytes([0x30]))

    detected = False
    for round_i in range(max(1, imu_rounds)):
        note(f"MCU init round {round_i + 1}")
        ok = mcu_init(jc, note)
        if ok:
            detected = True
        elif not detected:
            return False
        note("IMU 40 03")
        ack = None
        for _ in range(10):
            jc.subcmd(0x40, bytes([0x03]))
            ack = jc.wait_ack(0x40, lambda p: True)
            if ack:
                break
        if not ack:
            note("IMU 40 03 timeout")
            continue
        note("IMU 40 02 / 01")
        jc.subcmd(0x40, bytes([0x02]))
        jc.subcmd(0x40, bytes([0x01]))
        if round_i == 0:
            continue
        break
    if not detected:
        return False

    note("SET_EXTERNAL_FORMAT_CONFIG 0x5C")
    found = False
    for _ in range(10):
        jc.mcu_cmd(0x5C, ring_config())
        if jc.wait_ack(0x5C, lambda p: True):
            found = True
            break
    note("0x5C " + ("ok" if found else "timeout"))

    note("ENABLE_EXTERNAL_POLLING 0x5A")
    found = False
    for _ in range(10):
        jc.mcu_cmd(0x5A, bytes([0x04, 0x01, 0x01, 0x02]))
        if jc.wait_ack(0x5A, lambda p: True):
            found = True
            break
    note("0x5A " + ("ok" if found else "timeout"))
    return found


def disable_ringcon(jc: JoyCon) -> None:
    try:
        jc.subcmd(0x22, bytes([0x00]))
        jc.subcmd(0x03, bytes([0x30]))
        time.sleep(0.05)
    except OSError:
        pass
