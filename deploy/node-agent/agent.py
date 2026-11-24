#!/usr/bin/env python3
"""rover-agent — агент узла: телеметрия на VDS, приём команд.

Ставится на узлы ровера (Tinker Board 2 и др.).
Креды брокера: env ROVER_MQTT_USER / ROVER_MQTT_PASS (по умолчанию
user = имя узла). См. протокол: docs/protocol.md
"""
import json
import os
import time

import paho.mqtt.client as mqtt
import psutil

NODE = os.environ.get("ROVER_NODE", "tinker")
BROKER = os.environ.get("ROVER_BROKER", "10.77.0.1")
USER = os.environ.get("ROVER_MQTT_USER", NODE)
PASS = os.environ.get("ROVER_MQTT_PASS", "")
TELE_PERIOD = 1.0
TELEOP_TIMEOUT = 0.5

config = {}
last_teleop = 0.0


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


client = mqtt.Client()
client.username_pw_set(USER, PASS)
client.will_set(f"rover/{NODE}/status", "offline", retain=True)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, 1883)
client.loop_start()

boot = time.time()
print(f"rover-agent: node={NODE} broker={BROKER}")

while True:
    tele = {
        "cpu": round(psutil.cpu_percent(), 1),
        "mem": round(psutil.virtual_memory().percent, 1),
        "temp": read_temp(),
        "uptime": round((time.time() - boot) / 3600, 2),
        "ts": time.time(),
    }
    client.publish(f"rover/{NODE}/telemetry/system", json.dumps(tele))
    if time.time() - last_teleop > TELEOP_TIMEOUT:
        pass  # здесь позже: стоп моторов при потере телеуправления
    time.sleep(TELE_PERIOD)
