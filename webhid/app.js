import { HID_FILTER_L, HID_FILTER_R, HID_FILTERS, JoyCon, flexAction, sideOf } from "./joycon.js";

const $ = (id) => document.getElementById(id);
const KEYS = {
  L: ["上", "下", "左", "右", "L", "ZL", "SL", "SR", "Minus", "Capture", "Stick"],
  R: ["A", "B", "X", "Y", "R", "ZR", "SL", "SR", "Plus", "Home", "Stick"],
};

const ui = {
  reconnect: $("reconnect"),
  connectL: $("connect-l"),
  connectR: $("connect-r"),
  connectBoth: $("connect-both"),
  disconnect: $("disconnect"),
  wantRingcon: $("want-ringcon"),
  log: $("log"),
};

const pads = { L: null, R: null };
const views = {
  L: bindCard("L"),
  R: bindCard("R"),
};

function bindCard(side) {
  const root = document.querySelector(`[data-side="${side}"]`);
  const el = (name) => root.querySelector(`[data-el="${name}"]`);
  return {
    side,
    root,
    connect: root.querySelector("[data-connect]"),
    status: el("status"),
    pad: el("pad"),
    ctx: el("pad").getContext("2d"),
    keys: el("keys"),
    gyroMag: el("gyro-mag"),
    gyroBar: el("gyro-bar"),
    gx: el("gx"),
    gy: el("gy"),
    gz: el("gz"),
    ax: el("ax"),
    ay: el("ay"),
    az: el("az"),
    flexLabel: el("flex-label"),
    flexKnob: el("flex-knob"),
  };
}

function log(message) {
  const time = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  ui.log.textContent += `${time}  ${message}\n`;
  ui.log.scrollTop = ui.log.scrollHeight;
}

function hidAvailable() {
  return Boolean(navigator.hid);
}

function fmt(n, digits = 2) {
  return Number.isFinite(n) ? n.toFixed(digits) : "—";
}

function setPills(node, items) {
  node.replaceChildren(
    ...items.map(([text, cls]) => {
      const el = document.createElement("span");
      el.className = `pill${cls ? ` ${cls}` : ""}`;
      el.textContent = text;
      return el;
    }),
  );
}

function anyConnected() {
  return Boolean(pads.L || pads.R);
}

function setBusy(busy) {
  const disabled = busy;
  ui.connectL.disabled = disabled || Boolean(pads.L);
  ui.connectR.disabled = disabled || Boolean(pads.R);
  ui.connectBoth.disabled = disabled || (pads.L && pads.R);
  ui.reconnect.disabled = disabled;
  ui.disconnect.disabled = disabled || !anyConnected();
  views.L.connect.disabled = disabled || Boolean(pads.L);
  views.R.connect.disabled = disabled || Boolean(pads.R);
}

function renderKeys(view, frame) {
  const on = new Set(frame?.buttons || []);
  view.keys.replaceChildren(
    ...KEYS[view.side].map((label) => {
      const el = document.createElement("span");
      el.className = `key${on.has(label) ? " on" : ""}`;
      el.textContent = label;
      return el;
    }),
  );
}

function drawPad(view, frame) {
  const ctx = view.ctx;
  const w = view.pad.width;
  const h = view.pad.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#10131a";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#2c3342";
  ctx.beginPath();
  ctx.arc(w / 2, h / 2, 52, 0, Math.PI * 2);
  ctx.stroke();
  if (!frame) {
    return;
  }
  const sx = w / 2 + (frame.stick?.x || 0) * 48;
  const sy = h / 2 - (frame.stick?.y || 0) * 48;
  ctx.fillStyle = "#e60012";
  ctx.beginPath();
  ctx.arc(sx, sy, 10, 0, Math.PI * 2);
  ctx.fill();
  if (frame.imu) {
    const tx = w / 2 + frame.imu.ay * 36;
    const ty = h / 2 + frame.imu.ax * 36;
    ctx.strokeStyle = "#3dd68c";
    ctx.beginPath();
    ctx.moveTo(w / 2, h / 2);
    ctx.lineTo(tx, ty);
    ctx.stroke();
  }
}

function renderFrame(view, frame, pad) {
  const mag = frame?.imu ? Math.hypot(frame.imu.gx, frame.imu.gy, frame.imu.gz) : 0;
  view.gyroMag.textContent = `${fmt(mag, 1)} °/s`;
  view.gyroBar.style.width = `${Math.min(100, mag / 2)}%`;
  view.gx.textContent = `${fmt(frame?.imu?.gx, 1)} °/s`;
  view.gy.textContent = `${fmt(frame?.imu?.gy, 1)} °/s`;
  view.gz.textContent = `${fmt(frame?.imu?.gz, 1)} °/s`;
  view.ax.textContent = `${fmt(frame?.imu?.ax)} g`;
  view.ay.textContent = `${fmt(frame?.imu?.ay)} g`;
  view.az.textContent = `${fmt(frame?.imu?.az)} g`;
  if (view.flexLabel) {
    const showFlex = pad?.joy.ringcon && frame?.flex != null;
    if (showFlex) {
      const action = flexAction(frame.flex);
      view.flexLabel.textContent = `raw ${frame.flex}  ${action.name}  ${action.value >= 0 ? "+" : ""}${fmt(action.value)}`;
      view.flexKnob.style.left = `${Math.max(0, Math.min(100, (frame.flex / 20) * 100))}%`;
    } else {
      view.flexLabel.textContent = pad ? "未初始化" : "—";
      view.flexKnob.style.left = "50%";
    }
  }
  renderKeys(view, frame);
  drawPad(view, frame);
}

function refreshCard(side) {
  const view = views[side];
  const pad = pads[side];
  view.root.classList.toggle("empty", !pad);
  if (!pad) {
    setPills(view.status, [["未连接", "warn"]]);
    renderFrame(view, null, null);
    setBusy(false);
    return;
  }
  const items = [[pad.joy.device.productName || `Joy-Con (${side})`, "ok"]];
  if (pad.joy.ringcon) {
    items.push(["Ring-Con", "ok"]);
  }
  if (pad.lastFrame) {
    items.push([`${pad.lastFrame.hz} Hz`, ""]);
    items.push([
      `电量 ${pad.lastFrame.battery.label}${pad.lastFrame.battery.charging ? " 充电" : ""}`,
      "",
    ]);
    items.push([`conn 0x${pad.lastFrame.conn.toString(16).padStart(2, "0")}`, ""]);
  }
  setPills(view.status, items);
  setBusy(false);
}

function filterFor(side) {
  return side === "L" ? HID_FILTER_L : HID_FILTER_R;
}

async function attachDevice(device) {
  const side = sideOf(device);
  if (side !== "L" && side !== "R") {
    log(`忽略未知设备 ${device.productName || "HID"}`);
    return;
  }
  if (pads[side]) {
    log(`${side} 柄已经打开`);
    return;
  }
  const joy = new JoyCon(device, { note: (msg) => log(`[${side}] ${msg}`) });
  const pad = { side, joy, lastFrame: null, lastStatusAt: 0 };
  pads[side] = pad;
  const view = views[side];
  joy.onFrame = (frame) => {
    pad.lastFrame = frame;
    renderFrame(view, frame, pad);
    const now = performance.now();
    if (now - pad.lastStatusAt > 250) {
      pad.lastStatusAt = now;
      refreshCard(side);
    }
  };
  joy.onDisconnect = () => {
    log(`${device.productName || side} 已断开`);
    if (pads[side]?.joy === joy) {
      pads[side] = null;
    }
    refreshCard(side);
  };
  await joy.open();
  try {
    if (side === "R" && ui.wantRingcon.checked) {
      const ok = await joy.enableRingcon();
      log(ok ? "Ring-Con 初始化成功，弯曲时 flex 会变化。" : "Ring-Con 初始化失败，仍可读按键和 IMU。");
    } else {
      await joy.enableStandard();
      log(`[${side}] 已打开 IMU / 标准输入 0x30。`);
    }
  } catch (err) {
    log(`[${side}] 初始化出错：${err.message || err}`);
  }
  refreshCard(side);
}

async function pickSide(side) {
  if (!hidAvailable()) {
    log("当前浏览器没有 WebHID。请用 Chrome 或 Edge，并通过 http://localhost 打开。");
    return [];
  }
  if (pads[side]) {
    log(`${side} 柄已经连接`);
    return [];
  }
  try {
    return await navigator.hid.requestDevice({ filters: [filterFor(side)] });
  } catch (err) {
    if (err.name !== "NotFoundError") {
      log(`选择 ${side} 柄失败：${err.message || err}`);
    }
    return [];
  }
}

async function connectSide(side) {
  setBusy(true);
  const devices = await pickSide(side);
  for (const device of devices) {
    await attachDevice(device);
  }
  setBusy(false);
}

async function connectBoth() {
  setBusy(true);
  const queued = [];
  if (!pads.L) {
    log("请选择 Joy-Con (L)。选完后会再弹出右柄。");
    queued.push(...(await pickSide("L")));
  }
  if (!pads.R) {
    log("请选择 Joy-Con (R)。");
    queued.push(...(await pickSide("R")));
  }
  for (const device of queued) {
    await attachDevice(device);
  }
  if (!pads.L || !pads.R) {
    const missing = [!pads.L && "左", !pads.R && "右"].filter(Boolean).join(" / ");
    log(`双手柄未齐，还缺：${missing}。可再点对应按钮。`);
  } else {
    log("左右柄都已连接。");
  }
  setBusy(false);
}

async function reconnectGranted() {
  if (!hidAvailable()) {
    return;
  }
  setBusy(true);
  const devices = await navigator.hid.getDevices();
  const joycons = devices.filter((device) =>
    HID_FILTERS.some(
      (filter) => filter.vendorId === device.vendorId && filter.productId === device.productId,
    ),
  );
  if (!joycons.length) {
    log("没有已授权的 Joy-Con，请先点连接左柄 / 右柄。");
    setBusy(false);
    return;
  }
  for (const device of joycons) {
    await attachDevice(device);
  }
  setBusy(false);
}

async function disconnectAll() {
  setBusy(true);
  const closing = [pads.L, pads.R].filter(Boolean);
  pads.L = null;
  pads.R = null;
  for (const pad of closing) {
    await pad.joy.close();
  }
  refreshCard("L");
  refreshCard("R");
  log("已断开。");
}

function boot() {
  renderKeys(views.L, null);
  renderKeys(views.R, null);
  drawPad(views.L, null);
  drawPad(views.R, null);
  if (!hidAvailable()) {
    log("navigator.hid 不可用。请用 Chrome 打开本页（localhost 或 HTTPS）。");
    log("启动：python3 -m http.server 8765 --directory webhid");
    setBusy(true);
    ui.disconnect.disabled = true;
    return;
  }
  if (location.protocol === "file:") {
    log("file:// 不能用 WebHID。请用：python3 -m http.server 8765 --directory webhid");
  }
  log("WebHID 可用。可分别连接左/右柄，或一次连双手柄。");
  ui.connectL.addEventListener("click", () => connectSide("L"));
  ui.connectR.addEventListener("click", () => connectSide("R"));
  ui.connectBoth.addEventListener("click", connectBoth);
  ui.reconnect.addEventListener("click", reconnectGranted);
  ui.disconnect.addEventListener("click", disconnectAll);
  views.L.connect.addEventListener("click", () => connectSide("L"));
  views.R.connect.addEventListener("click", () => connectSide("R"));
  window.addEventListener("pagehide", () => {
    pads.L?.joy.close();
    pads.R?.joy.close();
  });
}

boot();
