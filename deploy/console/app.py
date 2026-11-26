#!/usr/bin/env python3
"""rover-console — онлайн-мониторинг и пульт управления ровером.

Принимает телеметрию узлов по MQTT, хранит историю в SQLite,
раздаёт live-данные в браузер по WebSocket, публикует команды
телеуправления и конфигурации обратно в MQTT. Сканы лидара хранит
только последние (в SQLite — скаляры), считает активность датчиков
и шлёт сканы в браузер по WebSocket.

Секреты: переменная окружения ROVER_MQTT_PASS (systemd EnvironmentFile
/opt/rover-console/.env на VDS). В репозиторий — никогда.

Деплой на VDS: /opt/rover-console (venv + systemd rover-console.service),
nginx проксирует /console/ → 127.0.0.1:8080.
См. протокол: docs/protocol.md
"""
import asyncio
import json
import os
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path

import paho.mqtt.client as mqtt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "data" / "rover.db"
STATIC = BASE / "static"
MQTT_HOST = os.environ.get("ROVER_MQTT_HOST", "10.77.0.1")
MQTT_PORT = 1883
MQTT_USER = "console"
MQTT_PASS = os.environ.get("ROVER_MQTT_PASS", "")
RETENTION_DAYS = 7
ONLINE_TIMEOUT = 15.0

TOPIC_TELEMETRY = "rover/+/telemetry/+"
TOPIC_CONFIG = "rover/+/config"
TOPIC_STATUS = "rover/+/status"

# --- state ---
db_lock = threading.Lock()
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.execute("PRAGMA journal_mode=WAL")
db.execute(
    """CREATE TABLE IF NOT EXISTS metrics(
       node TEXT, metric TEXT, ts REAL, value REAL)"""
)
db.execute("CREATE INDEX IF NOT EXISTS idx_metrics ON metrics(node, metric, ts)")
db.commit()

nodes: dict = {}          # name -> {online, last_seen, metrics:{}, config}
ws_clients: set = set()
loop: asyncio.AbstractEventLoop | None = None
SCAN_RATE_WINDOW = 30.0   # окно подсчёта частоты сообщений, сек


def node_state(name):
    return nodes.setdefault(
        name, {"online": False, "last_seen": 0.0,
               "metrics": {}, "config": None,
               "scan": None,            # последний скан лидара {r,start,step,...}
               "map": None,             # последняя SLAM-карта {data, info}
               "msgs": {},              # source -> deque timestamps
               "last_scan_sent": 0.0})


def msg_rate(st, source):
    q = st["msgs"].get(source)
    if not q:
        return 0.0
    now = time.time()
    while q and q[0] < now - SCAN_RATE_WINDOW:
        q.popleft()
    return round(len(q) / SCAN_RATE_WINDOW, 2)


# --- mqtt ---
def on_connect(client, _u, _f, rc):
    client.subscribe([(TOPIC_TELEMETRY, 0), (TOPIC_CONFIG, 0),
                      (TOPIC_STATUS, 0)])


def on_message(client, _u, msg):
    parts = msg.topic.split("/")
    if len(parts) != 4:
        return
    _, node, kind, name = parts
    st = node_state(node)
    now = time.time()

    if kind == "telemetry":
        try:
            payload = json.loads(msg.payload)
        except ValueError:
            return
        # учёт активности по источникам (system / lidar / ...)
        q = st["msgs"].setdefault(name, deque())
        q.append(now)
        if name == "lidar" and isinstance(payload.get("r"), list):
            # полный скан: храним последний, в SQLite не пишем (только счётчики)
            st["scan"] = {"r": payload["r"],
                          "start": float(payload.get("start", 0.0)),
                          "step": float(payload.get("step", 1.0)),
                          "rpm": payload.get("rpm"),
                          "t": now}
            st["last_seen"] = now
            st["online"] = True
            if loop and now - st["last_scan_sent"] > 0.12:  # ~8 сканов/с макс
                st["last_scan_sent"] = now
                loop.call_soon_threadsafe(broadcast, {
                    "type": "scan", "node": node, **st["scan"]})
            # скаляры скана (rpm, rate_hz, потери) — как обычные метрики
            for metric, value in payload.items():
                if metric in ("ts", "r", "start", "step") \
                        or not isinstance(value, (int, float)):
                    continue
                st["metrics"][metric] = value
            return
        if name == "map":
            st["map"] = {"data": payload.get("data") or [], "info": payload.get("info") or {}}
            st["online"] = True
            if loop:
                loop.call_soon_threadsafe(broadcast, {
                    "type": "map", "node": node,
                    "data": st["map"]["data"], "info": st["map"]["info"]})
            return
        if name == "log":
            line = str(payload.get("line") or "")
            if loop:
                loop.call_soon_threadsafe(broadcast, {
                    "type": "log", "node": node, "line": line})
            return
        for metric, value in payload.items():
            if metric == "ts" or not isinstance(value, (int, float)):
                continue
            st["metrics"][metric] = value
            st["last_seen"] = now
            st["online"] = True
            with db_lock:
                db.execute("INSERT INTO metrics VALUES(?,?,?,?)",
                           (node, metric, now, float(value)))
            if loop:
                loop.call_soon_threadsafe(broadcast, {
                    "type": "metric", "node": node,
                    "metric": metric, "value": value, "ts": now})
    elif kind == "config":
        try:
            st["config"] = json.loads(msg.payload or b"{}")
        except ValueError:
            st["config"] = None
    elif kind == "status":
        st["online"] = msg.payload == b"online"
        st["last_seen"] = now


def broadcast(msg: dict):
    dead = []
    for ws in ws_clients:
        try:
            asyncio.ensure_future(ws.send_json(msg))
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.discard(ws)


mqttc = mqtt.Client()
mqttc.username_pw_set(MQTT_USER, MQTT_PASS)
mqttc.on_connect = on_connect
mqttc.on_message = on_message
mqttc.connect(MQTT_HOST, MQTT_PORT)
mqttc.loop_start()


# --- web ---
app = FastAPI(title="rover-console")


@app.on_event("startup")
async def startup():
    global loop
    loop = asyncio.get_running_loop()
    with db_lock:
        db.execute("DELETE FROM metrics WHERE ts < ?",
                   (time.time() - RETENTION_DAYS * 86400,))
        db.commit()


@app.get("/api/nodes")
def api_nodes():
    now = time.time()
    out = []
    for name, st in nodes.items():
        online = st["online"] and now - st["last_seen"] < ONLINE_TIMEOUT
        scan = st["scan"]
        out.append({"name": name, "online": online,
                    "last_seen": st["last_seen"],
                    "sys_hz": msg_rate(st, "system"),
                    "lidar_hz": msg_rate(st, "lidar"),
                    "scan_points": len(scan["r"]) if scan else 0,
                    "scan_age": round(now - scan["t"], 1) if scan else None,
                    **st["metrics"]})
    return JSONResponse(out)


@app.get("/api/history")
def api_history(node: str, metric: str, minutes: int = 30):
    since = time.time() - min(minutes, 24 * 60) * 60
    with db_lock:
        rows = db.execute(
            "SELECT ts, value FROM metrics WHERE node=? AND metric=? AND ts>? ORDER BY ts",
            (node, metric, since)).fetchall()
    return JSONResponse({"node": node, "metric": metric,
                         "ts": [r[0] for r in rows],
                         "value": [r[1] for r in rows]})


@app.get("/api/config/{node}")
def api_get_config(node: str):
    st = nodes.get(node)
    return JSONResponse({"config": st["config"] if st else None})


@app.post("/api/config/{node}")
async def api_set_config(node: str, body: dict):
    mqttc.publish(f"rover/{node}/config/set",
                  json.dumps(body), retain=True)
    return JSONResponse({"ok": True, "node": node})


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") == "teleop":
                node = msg.get("node", "tinker")
                mqttc.publish(f"rover/{node}/cmd/teleop", json.dumps(
                    {"vx": float(msg.get("vx", 0)),
                     "wz": float(msg.get("wz", 0)), "ts": time.time()}))
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(websocket)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
