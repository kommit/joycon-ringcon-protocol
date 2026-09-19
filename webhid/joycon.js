/** Joy-Con / Ring-Con WebHID，协议对齐 python/ringcon_hid.py。 */

export const VID_NINTENDO = 0x057e;
export const PID_JOYCON_L = 0x2006;
export const PID_JOYCON_R = 0x2007;

export const HID_FILTER_L = { vendorId: VID_NINTENDO, productId: PID_JOYCON_L };
export const HID_FILTER_R = { vendorId: VID_NINTENDO, productId: PID_JOYCON_R };
export const HID_FILTERS = [HID_FILTER_L, HID_FILTER_R];

const OUTPUT_LEN = 49;
const PAYLOAD_LEN = OUTPUT_LEN - 1;
const NEUTRAL_RUMBLE = [0x00, 0x01, 0x40, 0x40, 0x00, 0x01, 0x40, 0x40];
const FLEX_REST = 10;
const FLEX_PUSH = 20;
const ACCEL_RES = 4096;
const GYRO_RES = 14.247;

const CRC_TABLE = [
  0x00, 0x07, 0x0e, 0x09, 0x1c, 0x1b, 0x12, 0x15, 0x38, 0x3f, 0x36, 0x31, 0x24, 0x23, 0x2a, 0x2d,
  0x70, 0x77, 0x7e, 0x79, 0x6c, 0x6b, 0x62, 0x65, 0x48, 0x4f, 0x46, 0x41, 0x54, 0x53, 0x5a, 0x5d,
  0xe0, 0xe7, 0xee, 0xe9, 0xfc, 0xfb, 0xf2, 0xf5, 0xd8, 0xdf, 0xd6, 0xd1, 0xc4, 0xc3, 0xca, 0xcd,
  0x90, 0x97, 0x9e, 0x99, 0x8c, 0x8b, 0x82, 0x85, 0xa8, 0xaf, 0xa6, 0xa1, 0xb4, 0xb3, 0xba, 0xbd,
  0xc7, 0xc0, 0xc9, 0xce, 0xdb, 0xdc, 0xd5, 0xd2, 0xff, 0xf8, 0xf1, 0xf6, 0xe3, 0xe4, 0xed, 0xea,
  0xb7, 0xb0, 0xb9, 0xbe, 0xab, 0xac, 0xa5, 0xa2, 0x8f, 0x88, 0x81, 0x86, 0x93, 0x94, 0x9d, 0x9a,
  0x27, 0x20, 0x29, 0x2e, 0x3b, 0x3c, 0x35, 0x32, 0x1f, 0x18, 0x11, 0x16, 0x03, 0x04, 0x0d, 0x0a,
  0x57, 0x50, 0x59, 0x5e, 0x4b, 0x4c, 0x45, 0x42, 0x6f, 0x68, 0x61, 0x66, 0x73, 0x74, 0x7d, 0x7a,
  0x89, 0x8e, 0x87, 0x80, 0x95, 0x92, 0x9b, 0x9c, 0xb1, 0xb6, 0xbf, 0xb8, 0xad, 0xaa, 0xa3, 0xa4,
  0xf9, 0xfe, 0xf7, 0xf0, 0xe5, 0xe2, 0xeb, 0xec, 0xc1, 0xc6, 0xcf, 0xc8, 0xdd, 0xda, 0xd3, 0xd4,
  0x69, 0x6e, 0x67, 0x60, 0x75, 0x72, 0x7b, 0x7c, 0x51, 0x56, 0x5f, 0x58, 0x4d, 0x4a, 0x43, 0x44,
  0x19, 0x1e, 0x17, 0x10, 0x05, 0x02, 0x0b, 0x0c, 0x21, 0x26, 0x2f, 0x28, 0x3d, 0x3a, 0x33, 0x34,
  0x4e, 0x49, 0x40, 0x47, 0x52, 0x55, 0x5c, 0x5b, 0x76, 0x71, 0x78, 0x7f, 0x6a, 0x6d, 0x64, 0x63,
  0x3e, 0x39, 0x30, 0x37, 0x22, 0x25, 0x2c, 0x2b, 0x06, 0x01, 0x08, 0x0f, 0x1a, 0x1d, 0x14, 0x13,
  0xae, 0xa9, 0xa0, 0xa7, 0xb2, 0xb5, 0xbc, 0xbb, 0x96, 0x91, 0x98, 0x9f, 0x8a, 0x8d, 0x84, 0x83,
  0xde, 0xd9, 0xd0, 0xd7, 0xc2, 0xc5, 0xcc, 0xcb, 0xe6, 0xe1, 0xe8, 0xef, 0xfa, 0xfd, 0xf4, 0xf3,
];

const BUTTON_MAP = {
  L: [
    [5, 0, "下"],
    [5, 1, "上"],
    [5, 2, "右"],
    [5, 3, "左"],
    [5, 4, "SR"],
    [5, 5, "SL"],
    [5, 6, "L"],
    [5, 7, "ZL"],
    [4, 0, "Minus"],
    [4, 3, "Stick"],
    [4, 5, "Capture"],
  ],
  R: [
    [3, 0, "Y"],
    [3, 1, "X"],
    [3, 2, "B"],
    [3, 3, "A"],
    [3, 4, "SR"],
    [3, 5, "SL"],
    [3, 6, "R"],
    [3, 7, "ZR"],
    [4, 1, "Plus"],
    [4, 2, "Stick"],
    [4, 4, "Home"],
  ],
};

export function crc8(bytes) {
  let value = 0;
  for (const byte of bytes) {
    value = CRC_TABLE[value ^ byte];
  }
  return value;
}

export function hexBytes(bytes, start = 0, end = bytes.length) {
  return Array.from(bytes.subarray(start, end))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join(" ");
}

export function flexAction(flex) {
  const value = (flex - FLEX_REST) / (FLEX_PUSH - FLEX_REST);
  if (flex < FLEX_REST) {
    return { name: "拉伸", value };
  }
  if (flex > FLEX_REST) {
    return { name: "挤压", value };
  }
  return { name: "静止", value: 0 };
}

export function sideOf(device) {
  if (device.productId === PID_JOYCON_L) {
    return "L";
  }
  if (device.productId === PID_JOYCON_R) {
    return "R";
  }
  const name = device.productName || "";
  if (name.includes("(L)")) {
    return "L";
  }
  if (name.includes("(R)")) {
    return "R";
  }
  return "?";
}

export function describeHidReports(device) {
  const lines = [];
  for (const collection of device.collections || []) {
    for (const report of collection.outputReports || []) {
      const bits = report.items.reduce(
        (sum, item) => sum + item.reportSize * item.reportCount,
        0,
      );
      lines.push(`out 0x${report.reportId.toString(16)} ${bits / 8} 字节`);
    }
    for (const report of collection.inputReports || []) {
      const bits = report.items.reduce(
        (sum, item) => sum + item.reportSize * item.reportCount,
        0,
      );
      lines.push(`in  0x${report.reportId.toString(16)} ${bits / 8} 字节`);
    }
  }
  return lines;
}

function ringConfig() {
  const cfg = new Uint8Array(38);
  cfg.set([0x06, 0x03, 0x25, 0x06, 0x00], 0);
  cfg.set([0x1c, 0x16, 0xed, 0x34, 0x36], 8);
  cfg.set([0x0a, 0x64, 0x0b, 0xe6, 0xa9, 0x22, 0x00, 0x00], 16);
  cfg[24] = 0x04;
  cfg.set([0x90, 0xa8, 0xe1, 0x34, 0x36], 32);
  return cfg;
}

function decodeStick(pkt, offset) {
  const x = pkt[offset] | ((pkt[offset + 1] & 0x0f) << 8);
  const y = (pkt[offset + 1] >> 4) | (pkt[offset + 2] << 4);
  return {
    rawX: x,
    rawY: y,
    x: (x - 2048) / 2048,
    y: (y - 2048) / 2048,
  };
}

function int16le(pkt, offset) {
  const value = pkt[offset] | (pkt[offset + 1] << 8);
  return value & 0x8000 ? value - 0x10000 : value;
}

function parseButtons(pkt, side) {
  const pressed = [];
  for (const [byte, bit, label] of BUTTON_MAP[side] || []) {
    if (pkt[byte] & (1 << bit)) {
      pressed.push(label);
    }
  }
  return pressed;
}

function parseImu(pkt, { skipFlexAccel = false } = {}) {
  if (pkt.length < 49) {
    return null;
  }
  let ax = 0;
  let ay = 0;
  let az = 0;
  let gx = 0;
  let gy = 0;
  let gz = 0;
  let accelN = 0;
  for (let i = 0; i < 3; i += 1) {
    const offset = 13 + i * 12;
    const sax = int16le(pkt, offset);
    const say = int16le(pkt, offset + 2);
    const saz = int16le(pkt, offset + 4);
    const sgx = int16le(pkt, offset + 6);
    const sgy = int16le(pkt, offset + 8);
    const sgz = int16le(pkt, offset + 10);
    if (!(skipFlexAccel && i === 2)) {
      ax += sax;
      ay += say;
      az += saz;
      accelN += 1;
    }
    gx += sgx;
    gy += sgy;
    gz += sgz;
  }
  if (accelN === 0) {
    return null;
  }
  return {
    ax: ax / (accelN * ACCEL_RES),
    ay: ay / (accelN * ACCEL_RES),
    az: az / (accelN * ACCEL_RES),
    gx: gx / (3 * GYRO_RES),
    gy: gy / (3 * GYRO_RES),
    gz: gz / (3 * GYRO_RES),
  };
}

function batteryOf(pkt) {
  const level = (pkt[2] & 0xf0) >> 4;
  const charging = Boolean(pkt[2] & 0x01);
  const labels = {
    8: "满",
    6: "高",
    4: "中",
    2: "低",
    1: "危",
    0: "空",
  };
  return { level, charging, label: labels[level] || String(level) };
}

export class JoyCon {
  constructor(device, { note = () => {} } = {}) {
    this.device = device;
    this.note = note;
    this.side = sideOf(device);
    this.counter = 0;
    this.ringcon = false;
    this.closed = false;
    this.ackWaiters = [];
    this.onFrame = null;
    this.onDisconnect = null;
    this.stats = { reports: 0, lastHz: 0, hzWindow: [] };
    this._onInput = (event) => this._handleInput(event);
    this._onHidDisconnect = (event) => {
      if (event.device !== this.device) {
        return;
      }
      this.closed = true;
      this.onDisconnect?.();
    };
  }

  async open() {
    if (!this.device.opened) {
      await this.device.open();
    }
    this.device.addEventListener("inputreport", this._onInput);
    navigator.hid.addEventListener("disconnect", this._onHidDisconnect);
    this.note(
      `已打开 ${this.device.productName || "Joy-Con"} ` +
        `(${this.side}) ${this.device.vendorId.toString(16)}:${this.device.productId
          .toString(16)
          .padStart(4, "0")}`,
    );
    for (const line of describeHidReports(this.device)) {
      this.note(line);
    }
  }

  async close() {
    if (this.closed) {
      return;
    }
    this.closed = true;
    this.device.removeEventListener("inputreport", this._onInput);
    navigator.hid.removeEventListener("disconnect", this._onHidDisconnect);
    try {
      await this.disableRingcon();
    } catch {
      // 断开后可能已经无法写报告。
    }
    try {
      await this.device.close();
    } catch {
      // 系统已断开时 close 会失败。
    }
  }

  _blank() {
    const buf = new Uint8Array(OUTPUT_LEN);
    buf[0] = 0x01;
    buf[1] = this.counter & 0x0f;
    this.counter = (this.counter + 1) & 0x0f;
    return buf;
  }

  async writeOut(buf) {
    const payload = buf.length >= OUTPUT_LEN ? buf.subarray(1, OUTPUT_LEN) : buf.subarray(1);
    try {
      await this.device.sendReport(buf[0], payload);
    } catch (first) {
      const padded = new Uint8Array(PAYLOAD_LEN);
      padded.set(payload.subarray(0, Math.min(payload.length, PAYLOAD_LEN)));
      try {
        await this.device.sendReport(buf[0], padded);
      } catch {
        throw first;
      }
    }
  }

  async subcmd(cmd, data = []) {
    const buf = this._blank();
    buf.set(NEUTRAL_RUMBLE, 2);
    buf[10] = cmd;
    buf.set(data, 11);
    await this.writeOut(buf);
  }

  async mcuCmd(cmd, data = []) {
    const buf = this._blank();
    buf[10] = cmd;
    buf.set(data, 11);
    await this.writeOut(buf);
  }

  async mcu21(sub, mode) {
    const buf = this._blank();
    buf[10] = 0x21;
    buf[11] = 0x21;
    buf[12] = sub;
    buf[13] = mode;
    buf[48] = crc8(buf.subarray(12, 48));
    await this.writeOut(buf);
  }

  waitAck(cmd, predicate = () => true, { tries = 12, timeoutMs = 64 } = {}) {
    return new Promise((resolve) => {
      const waiter = { cmd, predicate, resolve, timer: 0 };
      waiter.timer = setTimeout(() => {
        this.ackWaiters = this.ackWaiters.filter((item) => item !== waiter);
        resolve(null);
      }, tries * timeoutMs);
      this.ackWaiters.push(waiter);
    });
  }

  async sendAndWait(sendFn, cmd, predicate = () => true, opts = {}) {
    const pending = this.waitAck(cmd, predicate, opts);
    await sendFn();
    return pending;
  }

  async subcmdAck(cmd, data = [], tries = 12) {
    return this.sendAndWait(() => this.subcmd(cmd, data), cmd, () => true, { tries });
  }

  _handleInput(event) {
    const body = new Uint8Array(
      event.data.buffer,
      event.data.byteOffset,
      event.data.byteLength,
    );
    const pkt = new Uint8Array(body.length + 1);
    pkt[0] = event.reportId;
    pkt.set(body, 1);

    if (event.reportId === 0x21) {
      const idx = this.ackWaiters.findIndex(
        (waiter) => pkt.length > 14 && pkt[14] === waiter.cmd && waiter.predicate(pkt),
      );
      if (idx >= 0) {
        const [waiter] = this.ackWaiters.splice(idx, 1);
        clearTimeout(waiter.timer);
        waiter.resolve(pkt);
      }
    }

    if (event.reportId !== 0x30 && event.reportId !== 0x31) {
      return;
    }

    this.stats.reports += 1;
    const now = performance.now();
    this.stats.hzWindow.push(now);
    this.stats.hzWindow = this.stats.hzWindow.filter((t) => now - t < 1000);
    this.stats.lastHz = this.stats.hzWindow.length;

    const imu = parseImu(pkt, { skipFlexAccel: this.ringcon });
    const stickOffset = this.side === "L" ? 6 : 9;
    const frame = {
      reportId: event.reportId,
      pkt,
      side: this.side,
      timer: pkt[1],
      conn: pkt[2],
      battery: batteryOf(pkt),
      buttons: parseButtons(pkt, this.side),
      stick: decodeStick(pkt, stickOffset),
      imu,
      flex: pkt.length > 40 ? pkt[40] : null,
      hz: this.stats.lastHz,
    };
    this.onFrame?.(frame);
  }

  async enableStandard() {
    this.note("vibration on");
    await this.subcmdAck(0x48, [0x01]);
    this.note("IMU on");
    await this.subcmdAck(0x40, [0x01]);
    this.note("report mode 0x30");
    await this.subcmdAck(0x03, [0x30]);
  }

  async mcuInit() {
    this.note("MCU 22 01");
    let found = false;
    for (let i = 0; i < 12; i += 1) {
      const ack = await this.sendAndWait(
        () => this.subcmd(0x22, [0x01]),
        0x22,
        (pkt) => pkt[13] === 0x80,
      );
      if (ack) {
        found = true;
        break;
      }
    }
    this.note(`MCU 22 01 ${found ? "ok" : "timeout"}`);

    this.note("MCU 21 21 00 03");
    found = false;
    for (let i = 0; i < 12; i += 1) {
      const pkt = await this.sendAndWait(
        () => this.mcu21(0x00, 0x03),
        0x21,
        (p) => p.length > 22 && p[15] === 0x01 && p[22] === 0x03,
      );
      if (pkt) {
        this.note(`MCU mode3 ack=${hexBytes(pkt, 13, 28)}`);
        found = true;
        break;
      }
    }
    if (!found) {
      this.note("MCU mode3 timeout");
    }

    this.note("MCU 21 21 01 01");
    found = false;
    for (let i = 0; i < 12; i += 1) {
      const pkt = await this.sendAndWait(
        () => this.mcu21(0x01, 0x01),
        0x21,
        (p) => p.length > 17 && p[15] === 0x09 && p[17] === 0x01,
      );
      if (pkt) {
        this.note(`MCU ext-ready ack=${hexBytes(pkt, 13, 28)}`);
        found = true;
        break;
      }
    }
    if (!found) {
      this.note("MCU ext-ready timeout");
    }

    this.note("GET_EXTERNAL_DEVICE_INFO 0x59");
    let last = "no reply";
    for (let attempt = 0; attempt < 28; attempt += 1) {
      const pkt = await this.sendAndWait(
        () => this.mcuCmd(0x59),
        0x59,
        (p) => p.length > 16,
      );
      if (!pkt) {
        continue;
      }
      const status = pkt[15];
      const ext = pkt[16];
      last = `try=${attempt} status=0x${status.toString(16).padStart(2, "0")} ext=0x${ext
        .toString(16)
        .padStart(2, "0")} raw=${hexBytes(pkt, 13, 24)}`;
      if (ext === 0x20) {
        this.note(last);
        return true;
      }
    }
    this.note(`没有检测到 Ring-Con（${last}）`);
    return false;
  }

  async enableRingcon({ imuRounds = 2 } = {}) {
    await this.enableStandard();
    let detected = false;
    const rounds = Math.max(1, imuRounds);
    for (let round = 0; round < rounds; round += 1) {
      this.note(`MCU init round ${round + 1}`);
      const ok = await this.mcuInit();
      if (ok) {
        detected = true;
      } else if (!detected) {
        return false;
      }
      this.note("IMU 40 03");
      let ack = null;
      for (let i = 0; i < 10; i += 1) {
        ack = await this.sendAndWait(() => this.subcmd(0x40, [0x03]), 0x40);
        if (ack) {
          break;
        }
      }
      if (!ack) {
        this.note("IMU 40 03 timeout");
        continue;
      }
      this.note("IMU 40 02 / 01");
      await this.subcmd(0x40, [0x02]);
      await this.subcmd(0x40, [0x01]);
      if (round === 0) {
        continue;
      }
      break;
    }
    if (!detected) {
      return false;
    }

    this.note("SET_EXTERNAL_FORMAT_CONFIG 0x5C");
    let found = false;
    for (let i = 0; i < 10; i += 1) {
      if (await this.sendAndWait(() => this.mcuCmd(0x5C, ringConfig()), 0x5C)) {
        found = true;
        break;
      }
    }
    this.note(`0x5C ${found ? "ok" : "timeout"}`);

    this.note("ENABLE_EXTERNAL_POLLING 0x5A");
    found = false;
    for (let i = 0; i < 10; i += 1) {
      if (await this.sendAndWait(() => this.mcuCmd(0x5A, [0x04, 0x01, 0x01, 0x02]), 0x5A)) {
        found = true;
        break;
      }
    }
    this.note(`0x5A ${found ? "ok" : "timeout"}`);
    this.ringcon = found;
    return found;
  }

  async disableRingcon() {
    this.ringcon = false;
    await this.subcmd(0x22, [0x00]);
    await this.subcmd(0x03, [0x30]);
  }
}
