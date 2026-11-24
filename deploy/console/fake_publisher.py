#!/usr/bin/env python3
"""fake_publisher — эмулятор узла для проверки мониторинга без железа.

Публикует системную телеметрию и статистику лидара от имени узла.
Пароль брокера: env ROVER_MQTT_PASS (не коммитить).
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

print(f"fake node '{NODE}' publishing to {BROKER}")
t = 0
while True:
    sys_tele = {
        "cpu": 20 + 15 * math.sin(t / 60) + random.uniform(-3, 3),
        "mem": 45 + 5 * math.sin(t / 120) + random.uniform(-1, 1),
        "temp": 48 + 6 * math.sin(t / 90) + random.uniform(-0.5, 0.5),
        "uptime": round(t / 3600, 3),
        "ts": time.time(),
    }
    lidar_tele = {
        "rate_hz": 7.9 + random.uniform(-0.2, 0.2),
        "packets_ok": int(t * 8),
        "packets_lost": random.randint(0, 3),
        "rpm": 360 + random.uniform(-5, 5),
        "ts": time.time(),
    }
    client.publish(f"rover/{NODE}/telemetry/system", json.dumps(sys_tele))
    client.publish(f"rover/{NODE}/telemetry/lidar", json.dumps(lidar_tele))
    t += 1
    time.sleep(1)
