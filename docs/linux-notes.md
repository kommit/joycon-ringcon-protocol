# Linux 上使用 Joy-Con / Ring-Con

本机环境：Arch Linux、BlueZ 5.87、内核 `hid-nintendo`（`CONFIG_HID_NINTENDO=m`）、蓝牙适配器 Intel Wireless-AC 3168（USB `8087:0aa7`，地址 `B0:35:9F:9D:13:0D`）。

本机副本（已 gitignore）放在 `data/bluetooth/`、`data/udev/`。下面给出可直接落地的配置内容。协议细节见 [protocol.md](protocol.md)。

## 蓝牙服务

```bash
sudo systemctl enable --now bluetooth
```

Joy-Con 只在同步/配对模式（两侧按钮）下可被扫描到。用 `bluetoothctl` 扫到的经典名称是 `Joy-Con (L)` / `Joy-Con (R)`。

本仓库这对手柄地址见 `data/joycon.json`。另一对广播名 `BLE_Joy_L` / `BLE_Joy_R` 是 BLE（疑似 Switch 2），SMP 配对会失败，不要和经典这对混用。

AUR 的 `bluez-switch2` 面向 Switch 2 BLE，对这对经典手柄没有帮助。`joycond` 可以把 Joy-Con 合成虚拟手柄，但不负责 Ring-Con MCU。

## Joy-Con (R) 显示已连接又立刻断开

BlueZ 日志常见：

```text
profiles/input/device.c:control_connect_cb() ... Permission denied (13)
```

原因是 `/etc/bluetooth/input.conf` 默认 `ClassicBondedOnly=true`，重配对后 HID 被拦。可在 blueman 里移除设备再配对，或写入：

```ini
# /etc/bluetooth/input.conf
[General]
ClassicBondedOnly=false
UserspaceHID=true
```

```bash
sudo cp data/bluetooth/input.conf /etc/bluetooth/input.conf
sudo systemctl restart bluetooth
```

`UserspaceHID=true` 走 UHID，配合内核 `hid-nintendo`。

## IMU event 节点权限

手柄按键节点带 `ID_INPUT_JOYSTICK`，logind 会给当前 seat 的 `uaccess`。名为 `Joy-Con * (IMU)` 的体感节点没有这个标签，不在 `input` 组的用户会 `EACCES`。hidraw（`/dev/hidraw*`）一般可读。

把用户加入 `input` 组，或安装：

```udev
# /etc/udev/rules.d/99-joycon-imu.rules
ACTION=="add|change", SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="Joy-Con * (IMU)", TAG+="uaccess"
```

```bash
sudo cp data/udev/99-joycon-imu.rules /etc/udev/rules.d/
sudo udevadm control --reload
```

之后重连手柄。

## hid-nintendo 与 MCU

内核驱动会占用 MCU。按协议正确初始化时，不必解绑也能读到 Ring-Con。若 MCU 应答异常，可尝试对右柄解绑（需要 root）：

```bash
# 例：0005:057E:2007.XXXX
echo -n 0005:057E:2007.XXXX | sudo tee /sys/bus/hid/drivers/nintendo/unbind
```

解绑后 hidraw 仍在，用户态独占写 MCU。

## 使用顺序

1. 系统蓝牙已启动，Joy-Con 已经典配对并连接。
2. 把 Ring-Con 卡到 **右** Joy-Con 下轨。建议先连上蓝牙，再卡环。
3. 监听：

```bash
python3 python/watch_joycon.py --ringcon
```

4. 录弯曲日志（写入 `data/logs/`）：

```bash
python3 python/capture_ringcon.py
```

真机 Switch 能识别、Linux 读不到 flex 时，优先核对 MCU CRC 是否在 `buf[48]`、`0x59` 是否返回 `ext=0x20`，而不是再换更底层的抓包方式。hidraw 已经是原始 HID。
