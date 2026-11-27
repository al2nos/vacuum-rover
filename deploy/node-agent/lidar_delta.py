#!/usr/bin/env python3
"""rover-lidar — декодер лидара 3irobotics Delta (2A / 2C PRO) в файл скана.

Читает /dev/ttyS0 (115200 8N1), разбирает кадры протокола Delta и раз в
оборот пишет скан в $ROVER_SCAN_FILE в формате docs/protocol.md:
    {"start": 0, "step": 1, "rpm": 360, "r": [мм × 360], "ts": ...}

Поддерживаются:
  * версия 0x01 (Delta-2A/2B/2D/2G): start_angle, шаг 360/(16·N);
  * версия 0x11/0x13 (Delta-2C PRO): start_angle + end_angle, интерполяция.

0xAE (только скорость) — лидар вне окна измерений: у Delta-2C PRO нет
внутренней стабилизации оборотов, мотор нужно крутить ШИМ с PID на ~7 Гц
(референс: kaiaai/LDS, `LDS_DELTA_2C_115200`, pwm 0.6 + PID). Постоянное
напряжение даёт «сколько получится»: 3.3 В → ~9.3 Гц → только 0xAE,
измерений нет. Норма — 0xAD с точками при ~7 Гц.
"""
import json
import os
import select
import sys
import time

DEV = os.environ.get("ROVER_LIDAR_DEV", "/dev/ttyS0")
BAUD = int(os.environ.get("ROVER_LIDAR_BAUD", "115200"))
SCAN_FILE = os.environ.get("ROVER_SCAN_FILE", "/run/rover/scan.json")
STATS_FILE = os.environ.get("ROVER_LIDAR_STATS", "/run/rover/lidar_stats.json")
BINS = 360
# Кадр Delta-2C: 8 байт заголовка + 7 (freq/off/start/end) + до 40 отсчётов
# по 3 байта + CRC. У 2A было 28 отсчётов, у 2C встречается до 29 и больше,
# поэтому старый лимит 95 байт резал валидные кадры 2C.
MAX_FRAME = 8 + 7 + 40 * 3 + 2


def log(msg):
    print(f"[lidar] {msg}", flush=True)


def write_json_atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def open_serial():
    import termios  # только для Linux-узла; модуль импортируется и на хосте

    fd = os.open(DEV, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = 0
    a[1] = 0
    a[3] = 0
    a[2] = (a[2] | termios.CREAD | termios.CLOCAL) & ~termios.CRTSCTS
    a[2] = (a[2] & ~termios.CSIZE) | termios.CS8
    a[2] &= ~(termios.PARENB | termios.CSTOPB)
    a[4] = a[5] = termios.B115200
    termios.tcsetattr(fd, termios.TCSANOW, a)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


class DeltaDecoder:
    def __init__(self):
        self.buf = bytearray()
        self.reset_scan()
        self.packets_ok = 0
        self.packets_bad = 0
        self.frames_meas = 0
        self.frames_speed = 0
        self.speed_hz = 0.0
        self.last_scan_ts = 0.0
        self.last_start = None
        self.lost_edges = 0

    # --- разбор потока -------------------------------------------------
    def feed(self, data):
        self.buf += data
        scans = []
        while True:
            i = self.buf.find(b"\xaa")
            if i < 0:
                self.buf.clear()
                break
            if i:
                del self.buf[:i]
            if len(self.buf) < 4:
                break
            plen = (self.buf[1] << 8) | self.buf[2]
            if not (9 <= plen <= MAX_FRAME) or self.buf[3] not in (0x01, 0x11, 0x13):
                del self.buf[:1]
                continue
            total = plen + 2
            if len(self.buf) < total:
                break
            frame = bytes(self.buf[:total])
            if frame[4] != 0x61 or frame[5] not in (0xAD, 0xAE):
                del self.buf[:1]
                continue
            chk = (frame[plen] << 8) | frame[plen + 1]
            if (sum(frame[:plen]) & 0xFFFF) != chk:
                self.packets_bad += 1
                del self.buf[:1]
                continue
            self.packets_ok += 1
            del self.buf[:total]
            scan = self.handle_frame(frame, plen)
            if scan is not None:
                scans.append(scan)
        return scans

    def handle_frame(self, f, plen):
        ver = f[3]
        dtype = f[5]
        dlen = (f[6] << 8) | f[7]
        freq = f[8] / 20.0
        self.speed_hz = freq

        if dtype == 0xAE:
            self.frames_speed += 1
            return None

        self.frames_meas += 1
        start = ((f[11] << 8) | f[12]) / 100.0
        if ver == 0x01:
            n = (dlen - 5) // 3
            step = 360.0 / (16 * n) if n else 0.0
            angles = [start + k * step for k in range(n)]
        else:
            end = ((f[13] << 8) | f[14]) / 100.0
            n = (dlen - 7) // 3
            span = (end - start) % 360.0
            angles = [start + span * (k + 0.5) / n for k in range(n)] if n else []

        base = 15 if ver != 0x01 else 13
        for k, ang in enumerate(angles):
            off = base + k * 3
            if off + 2 >= plen:
                break
            q = f[off]
            d_mm = ((f[off + 1] << 8) | f[off + 2]) * 0.25
            if q == 0 or d_mm <= 0 or d_mm > 8000:
                continue
            idx = int(ang) % BINS
            self.r[idx] = int(round(d_mm))

        # оборот закончился, когда start_angle резко откатился назад
        wrap = self.last_start is not None and start < self.last_start - 90.0
        self.last_start = start
        if not wrap:
            return None
        scan = {
            "start": 0.0,
            "step": 360.0 / BINS,
            "rpm": int(round(self.speed_hz * 60)),
            "r": list(self.r),
            "ts": round(time.time(), 3),
        }
        self.lost_edges = sum(1 for v in self.r if v == 0)
        self.reset_scan()
        self.last_scan_ts = time.time()
        return scan

    def reset_scan(self):
        self.r = [0] * BINS


def main():
    os.makedirs(os.path.dirname(SCAN_FILE) or "/run/rover", exist_ok=True)
    fd = open_serial()
    log(f"open {DEV} @ {BAUD}, scan -> {SCAN_FILE}")
    dec = DeltaDecoder()
    next_stats = time.time() + 5.0
    while True:
        try:
            r, _, _ = select.select([fd], [], [], 0.5)
            if r:
                data = os.read(fd, 8192)
                for scan in dec.feed(data):
                    write_json_atomic(SCAN_FILE, scan)
        except OSError as e:
            log(f"read error: {e}; reopening")
            try:
                os.close(fd)
            except OSError:
                pass
            time.sleep(1)
            fd = open_serial()

        now = time.time()
        if now >= next_stats:
            next_stats = now + 5.0
            stats = {
                "speed_hz": round(dec.speed_hz, 2),
                "rpm": int(round(dec.speed_hz * 60)),
                "packets_ok": dec.packets_ok,
                "packets_bad": dec.packets_bad,
                "frames_meas": dec.frames_meas,
                "frames_speed": dec.frames_speed,
                "scan_age": round(now - dec.last_scan_ts, 1) if dec.last_scan_ts else None,
                "ts": round(now, 3),
            }
            try:
                write_json_atomic(STATS_FILE, stats)
            except OSError:
                pass
            log(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
