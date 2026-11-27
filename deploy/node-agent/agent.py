#!/usr/bin/env python3
"""rover-agent — агент узла: телеметрия на VDS, приём команд.

Ставится на узлы ровера (Tinker Board 2 и др.).
Креды брокера: env ROVER_MQTT_USER / ROVER_MQTT_PASS (по умолчанию
user = имя узла). Сканы лидаров пробрасывает из файлов декодеров:

  ROVER_SCAN_FILE / ROVER_LIDAR_STATS        — лидар №1 (topic telemetry/lidar)
  ROVER_LIDAR_EXTRA="lidar2:<scan>:<stats>"  — доп. лидары (telemetry/lidar2)

Формат ROVER_LIDAR_EXTRA: `имя:путь_скана:путь_статистики`, несколько
через запятую. См. протокол: docs/protocol.md
"""
import json
import os
import threading
import time

import paho.mqtt.client as mqtt
import psutil

NODE = os.environ.get("ROVER_NODE", "tinker")
BROKER = os.environ.get("ROVER_BROKER", "10.77.0.1")
USER = os.environ.get("ROVER_MQTT_USER", NODE)
PASS = os.environ.get("ROVER_MQTT_PASS", "")
SCAN_FILE = os.environ.get("ROVER_SCAN_FILE", "/run/rover/scan.json")
STATS_FILE = os.environ.get("ROVER_LIDAR_STATS", "/run/rover/lidar_stats.json")
TELE_PERIOD = 1.0
TELEOP_TIMEOUT = 0.5
SCAN_POLL = 0.05

config = {}
last_teleop = 0.0


def parse_lidars():
    """[{name, scan, stats, mtime}] — лидар №1 + доп. из ROVER_LIDAR_EXTRA."""
    lidars = [{"name": "lidar", "scan": SCAN_FILE,
               "stats": STATS_FILE, "mtime": 0.0}]
    extra = os.environ.get("ROVER_LIDAR_EXTRA", "").strip()
    for item in filter(None, (x.strip() for x in extra.split(","))):
        parts = item.split(":")
        if len(parts) != 3:
            print(f"[lidar] bad ROVER_LIDAR_EXTRA item: {item}")
            continue
        name, scan, stats = parts
        lidars.append({"name": name, "scan": scan, "stats": stats, "mtime": 0.0})
    return lidars


LIDARS = parse_lidars()


def read_temp():
    try:
        for z in psutil.sensors_temperatures().get("cpu_thermal", []):
            return round(z.current, 1)
        for zones in psutil.sensors_temperatures().values():
            for z in zones:
                return round(z.current, 1)
    except Exception:
        pass
    return 0.0


def on_connect(client, _u, _f, rc):
    client.publish(f"rover/{NODE}/status", "online", retain=True)
    client.subscribe(f"rover/{NODE}/config/set")
    client.subscribe(f"rover/{NODE}/cmd/teleop")


def on_message(client, _u, msg):
    global config, last_teleop
    try:
        payload = json.loads(msg.payload)
    except ValueError:
        return
    if msg.topic.endswith("/config/set"):
        config.update(payload)
        client.publish(f"rover/{NODE}/config", json.dumps(config), retain=True)
        print(f"[config] applied: {payload}")
    elif msg.topic.endswith("/cmd/teleop"):
        last_teleop = time.time()
        print(f"[teleop] vx={payload.get('vx')} wz={payload.get('wz')}")


try:  # paho-mqtt 2.x: явно просим старый API колбэков
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
except (AttributeError, TypeError):
    client = mqtt.Client()
client.username_pw_set(USER, PASS)
client.will_set(f"rover/{NODE}/status", "offline", retain=True)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, 1883)
client.loop_start()


def publish_scan(lidar):
    """Проброс последнего скана: декодер пишет {start,step,rpm,r:[мм]} в файл."""
    try:
        mtime = os.path.getmtime(lidar["scan"])
        if mtime == lidar["mtime"]:
            return
        with open(lidar["scan"]) as f:
            scan = json.load(f)
        scan["r"] = [int(v) for v in scan["r"]]
        lidar["mtime"] = mtime
        client.publish(f"rover/{NODE}/telemetry/{lidar['name']}", json.dumps(scan))
    except (OSError, ValueError, KeyError):
        pass


def scan_loop():
    # сканы идут с частотой вращения (~7-8 Гц) — опрашиваем файлы часто
    while True:
        for lidar in LIDARS:
            publish_scan(lidar)
        time.sleep(SCAN_POLL)


threading.Thread(target=scan_loop, daemon=True).start()

boot = time.time()
print(f"rover-agent: node={NODE} broker={BROKER} lidars="
      f"{[x['name'] for x in LIDARS]}")

while True:
    tele = {
        "cpu": round(psutil.cpu_percent(), 1),
        "mem": round(psutil.virtual_memory().percent, 1),
        "temp": read_temp(),
        "uptime": round((time.time() - boot) / 3600, 2),
        "ts": time.time(),
    }
    client.publish(f"rover/{NODE}/telemetry/system", json.dumps(tele))
    # скалярная статистика лидаров (без поля r) — раз в секунду
    for lidar in LIDARS:
        try:
            with open(lidar["stats"]) as f:
                client.publish(f"rover/{NODE}/telemetry/{lidar['name']}",
                               json.dumps(json.load(f)))
        except (OSError, ValueError):
            pass
    if time.time() - last_teleop > TELEOP_TIMEOUT:
        pass  # здесь позже: стоп моторов при потере телеуправления
    time.sleep(TELE_PERIOD)
