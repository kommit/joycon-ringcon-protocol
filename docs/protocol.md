# Joy-Con / Ring-Con HID 协议

实现见 `python/ringcon_hid.py`。Linux 侧配对、权限与驱动见 [linux-notes.md](linux-notes.md)。

参考：[Ringcon-Driver](https://github.com/ringrunnermg/Ringcon-Driver)（`joycon.hpp`）、[Nintendo Switch Reverse Engineering](https://github.com/dekuNukem/Nintendo_Switch_Reverse_Engineering)。

## 设备

| 设备 | BT 名称 | VID:PID | 说明 |
| --- | --- | --- | --- |
| 左 Joy-Con | Joy-Con (L) | `057E:2006` | 不接 Ring-Con，跳过 MCU 外设流程 |
| 右 Joy-Con | Joy-Con (R) | `057E:2007` | Ring-Con 卡在下轨 |
| Ring-Con | — | 外设 ID `0x2000` | 弯曲传感器，经右柄 MCU 上报 |

蓝牙经典 HID。输出报告 49 字节（`output_buffer_length = 49`）。输入：标准体感 `0x30` 为 49 字节；MCU/NFC `0x31` 可达 362 字节。

## 输出报告 `0x01`（子命令）

普通子命令（`0x03` / `0x22` / `0x40` / `0x48` 等）：

| 偏移 | 长度 | 内容 |
| --- | --- | --- |
| 0 | 1 | 报告 ID `0x01` |
| 1 | 1 | 计数器，低 4 位循环 |
| 2–9 | 8 | 中性 rumble：`00 01 40 40 00 01 40 40` |
| 10 | 1 | 子命令 |
| 11… | n | 参数 |

MCU 包（`0x21` / `0x59` / `0x5C` / `0x5A`）只把计数器放在 `buf[1]`（`rumble[0]`），其余 rumble 为 0。

子命令应答是输入报告 `0x21`：

| 偏移 | 内容 |
| --- | --- |
| 0 | `0x21` |
| 13 | ACK，成功多为 `0x80` |
| 14 | 回显的子命令 |
| 15… | 载荷 |

`*(u16*)&pkt[0xD] == 0x2280` 即 `pkt[13]=0x80`、`pkt[14]=0x22`。

## MCU CRC

多项式 0x07 的 CRC-8（CCITT 表，初值 0）。**只用于 `21 21` 设模式包**：

```text
buf[10] = 0x21          # 子命令：MCU
buf[11] = 0x21          # MCU 命令
buf[12] = sub           # 0x00 设模式 / 0x01 外设
buf[13] = mode          # 0x03 Ring-Con 模式
buf[48] = crc8(buf[12:48])   # 覆盖 36 字节
```

CRC 必须写在 **`buf[48]`**。写到 `buf[47]` 或只校验 MCU 载荷前 36 字节（不含输出头）都会让 `0x59` 一直返回无外设（`0xFE`）或超时。

## Ring-Con 初始化顺序

建议：蓝牙已连接后再卡上环。只对右 Joy-Con 做 MCU。

1. `0x48 01` 开振动  
2. `0x40 01` 开 IMU  
3. `0x03 30` 输入报告 60 Hz 标准模式  
4. `0x22 01` 恢复 MCU，直到 `0x21` 应答 `0x2280`  
5. MCU `21 21 00 03`（CRC 在 `[48]`），等到 `pkt[15]==0x01` 且 `pkt[22]==0x03`  
6. MCU `21 21 01 01`，等到 `pkt[15]==0x09` 且 `pkt[17]==0x01`  
7. `0x59` 查询外设，直到 `pkt[14]==0x59` 且 `pkt[16]==0x20`  
8. `0x40 03`，应答后再 `0x40 02`、`0x40 01`（Ringcon-Driver 会整段重跑一次以稳住陀螺仪）  
9. `0x5C` + 38 字节格式配置  
10. `0x5A 04 01 01 02` 开始外设轮询  

关闭：`0x22 00`，必要时再 `0x03 30`。

`0x11 01` 可在 `0x31` 大包里问 MCU 状态（`pkt[49]==0x01` 且 `pkt[56]` 为模式），本仓库在 `0x30` 模式下用 `0x21` 应答即可，不必切 `0x31`。

## `0x59` 外设信息

| `pkt[15]` | `pkt[16]` | 含义 |
| --- | --- | --- |
| `0xFE` | — | 未接外设 |
| `0x00` | `0x20` | Ring-Con（`0x20` 为外设 ID / 固件主版本一类字段） |

标准输入里的连接信息 `pkt[2]`：接上环后常见 `0x4B`。

## 弯曲值

初始化成功后，标准输入 `0x30` 的 **`pkt[40]`** 是 Ring-Con flex：

| 原始值 | 动作 |
| --- | --- |
| `0x00`（0） | 拉满 / 拉伸 |
| `0x0A`（10） | 静止 |
| `0x14`（20） | 推满 / 挤压 |

本仓库把相对 10 的偏移归一化到约 `[-1, +1]`：拉伸为负，挤压为正。实测可到 4–21，端点因握持会略超出 0/20。

第三组 IMU 加速度会被 flex 占用；陀螺仪和前两组加速度仍可用。解析 IMU 时应跳过 sample 2 的 accel。

## 输入报告 `0x30` IMU

60 Hz，三组 sample，每组 12 字节，从偏移 13 开始，小端 `int16`：

```text
ax, ay, az, gx, gy, gz
```

换算：加速度 `/ 4096` → g；角速度 `/ 14.247` → °/s。

## `0x5C` 格式配置

子命令 `0x5C`，数据从 `buf[11]` 起 38 字节（与 Ringcon-Driver 一次成功抓包一致）：

```text
06 03 25 06 00 00 00 00
1C 16 ED 34 36 00 00 00
0A 64 0B E6 A9 22 00 00
04 00 00 00 00 00 00 00
90 A8 E1 34 36 00
```

其中若干字段像时间戳/校验，换一组常数也能工作；应答 `pkt[14]==0x5C` 即配置成功。`0x5C` 必须在 `0x5A` 轮询开启之前发送。

## 按键（Linux evdev）

hid-nintendo 映射，左/右不完全对称：

**左：** `BTN_TL`=L，`TL2`=ZL，`TR`/`TR2`=SL/SR，`SELECT`=Minus，`Z`=Capture，方向键，`ABS_X/Y` 摇杆。  
**右：** `EAST/SOUTH/NORTH/WEST`=A/B/X/Y，`TR`/`TR2`=R/ZR，`TL`/`TL2`=SL/SR，`START`=Plus，`MODE`=Home，`ABS_RX/RY` 摇杆。
