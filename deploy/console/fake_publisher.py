#!/usr/bin/env python3
"""fake_publisher — эмулятор узла для проверки мониторинга без железа.

Публикует системную телеметрию, статистику лидара и полные сканы
(360 лучей, виртуальная комната 6×4 м + подвижный объект) от имени
узла. Пароль брокера: env ROVER_MQTT_PASS (не коммитить).
"""
import json
import math
import os
import random
import sys
import time

import paho.mqtt.client as mqtt

NODE = sys.argv[1] if len(sys.argv) > 1 else "tinker"
BROKER = "10.77.0.1"
USER = "agent"
PASS = os.environ.get("ROVER_MQTT_PASS", "")

client = mqtt.Client()
client.username_pw_set(USER, PASS)
client.will_set(f"rover/{NODE}/status", "offline", retain=True)
client.connect(BROKER, 1883)
client.loop_start()
client.publish(f"rover/{NODE}/status", "online", retain=True)


def make_scan(t):
    """Эмуляция скана 360°: комната 6×4 м + подвижный объект + шум. r в мм, 0 = нет отражения."""
    N = 360
    r = []
    for i in range(N):
        a = math.radians(i)
        dx, dy = math.sin(a), -math.cos(a)   # 0° — вперёд
        # стены прямоугольной комнаты: пересечение луча с границами x±3, y±2
        hits = []
        for wall, pos in ((dx, 3.0), (dy, 2.0)):
            if abs(wall) < 1e-6:
                continue
            for s in (1, -1):
                d = (pos * s) / wall
                if d > 0:
                    px, py = dx * d, dy * d
                    if abs(px) <= 3.001 and abs(py) <= 2.001:
                        hits.append(d)
        d = min(hits) if hits else 0
        # подвижный «стул»: цилиндр радиусом 0.25 м на окружности
        cx, cy = 1.5 * math.cos(t / 10), 1.2 * math.sin(t / 7)
        # расстояние до окружности вдоль луча (приближённо — проекция)
        rx, ry = cx, cy
        proj = rx * dx + ry * dy
        if proj > 0:
            perp2 = rx * rx + ry * ry - proj * proj
            rr = 0.25 ** 2
            if perp2 < rr:
                hit = proj - math.sqrt(rr - perp2)
                if hit < d or d == 0:
                    d = hit
        if d and random.random() > 0.02:   # 2% лучей теряются
            r.append(int(d * 1000 + random.uniform(-15, 15)))
        else:
            r.append(0)
    return r


print(f"fake node '{NODE}' publishing to {BROKER}")
print("fake lidar: 360 лучей, ~4 сканов/с")
t = 0
scan_tick = 0
last_slow = 0.0
while True:
    now = time.time()
    # медленная телеметрия: 1 Гц
    if now - last_slow >= 1.0:
        last_slow = now
        sys_tele = {
            "cpu": 20 + 15 * math.sin(t / 60) + random.uniform(-3, 3),
            "mem": 45 + 5 * math.sin(t / 120) + random.uniform(-1, 1),
            "temp": 48 + 6 * math.sin(t / 90) + random.uniform(-0.5, 0.5),
            "uptime": round(t / 3600, 3),
            "ts": now,
        }
        lidar_tele = {
            "rate_hz": 7.9 + random.uniform(-0.2, 0.2),
            "packets_ok": int(t * 8),
            "packets_lost": random.randint(0, 3),
            "rpm": 360 + random.uniform(-5, 5),
            "ts": now,
        }
        client.publish(f"rover/{NODE}/telemetry/system", json.dumps(sys_tele))
        client.publish(f"rover/{NODE}/telemetry/lidar", json.dumps(lidar_tele))
        t += 1
    # скан лидара: каждые ~0.25 с (≈4 сканов/с)
    if scan_tick % 2 == 0:
        scan = {"start": 0.0, "step": 1.0,
                "rpm": round(360 + random.uniform(-5, 5)),
                "r": make_scan(now)}
        client.publish(f"rover/{NODE}/telemetry/lidar", json.dumps(scan))
    scan_tick = (scan_tick + 1) % 8
    time.sleep(0.125)
