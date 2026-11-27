#!/usr/bin/env python3
"""rover_bridge — ROS <-> MQTT мост для пультa управления.

ROS -> MQTT (телеметрия для консоли/сайта):
  /map        -> rover/<node>/telemetry/map   {data:[float], info:{...}}
  /odom       -> rover/<node>/telemetry/odom  {x,y,z,w}

MQTT -> ROS (управление):
  rover/<node>/cmd/teleop -> /cmd_vel (Twist)

См. docs/protocol.md
"""
import json
import math
import os

import paho.mqtt.client as mqtt
import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import OccupancyGrid
from nav_msgs.msg import Odometry
from rcl_interfaces.msg import Log
from rclpy.node import Node

MQTT_HOST = os.environ.get("ROVER_MQTT_HOST", "10.77.0.1")
MQTT_PORT = int(os.environ.get("ROVER_MQTT_PORT", 1883))
NODE = os.environ.get("ROVER_NODE", "tinker")
USER = os.environ.get("ROVER_MQTT_USER", NODE)
PASS = os.environ.get("ROVER_MQTT_PASS", "")


class RoverBridge(Node):
    def __init__(self):
        super().__init__("rover_bridge")
        self.map_sub = self.create_subscription(OccupancyGrid, "/map", self.map_cb, 10)
        self.odom_sub = self.create_subscription(Odometry, "/odom", self.odom_cb, 10)
        self.log_sub = self.create_subscription(Log, "/rosout", self.log_cb, 10)
        self.cmd_sub = self.create_subscription(Twist, "/cmd_vel", self.cmd_cb, 10)

        self.mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self.mqttc.username_pw_set(USER, PASS)

        def on_connect(client, userdata, flags, rc):
            self.get_logger().info(f"mqtt connected, rc={rc}")
            client.subscribe(f"rover/{NODE}/cmd/teleop")

        def on_message(client, userdata, msg):
            if msg.topic != f"rover/{NODE}/cmd/teleop":
                return
            try:
                payload = json.loads(msg.payload)
            except ValueError:
                return
            t = Twist()
            t.linear.x = float(payload.get("vx") or 0.0)
            t.angular.z = float(payload.get("wz") or 0.0)
            self.get_logger().info(f"[bridge] cmd_vel vx={t.linear.x} wz={t.angular.z}")
            self.cmd_sub.publish(t)

        self.mqttc.on_connect = on_connect
        self.mqttc.on_message = on_message
        self.mqttc.connect(MQTT_HOST, MQTT_PORT)
        self.mqttc.loop_start()

    def map_cb(self, msg):
        try:
            # передаём только занятые ячейки: полный grid (сотни КБ JSON) не нужен пульту
            occupied = [i for i, v in enumerate(msg.data) if v >= 50]
            payload = {
                "occupied": occupied,
                "info": {
                    "width": int(msg.info.width),
                    "height": int(msg.info.height),
                    "resolution": float(msg.info.resolution),
                    "origin": {
                        "x": float(msg.info.origin.position.x),
                        "y": float(msg.info.origin.position.y),
                        "z": float(msg.info.origin.position.z),
                    },
                },
            }
            self.mqttc.publish(f"rover/{NODE}/telemetry/map", json.dumps(payload))
        except Exception as e:
            self.get_logger().warn(f"[bridge] map err: {e}")

    def odom_cb(self, msg):
        try:
            q = msg.pose.pose.orientation
            yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                             1.0 - 2.0 * (q.y * q.y + q.z * q.z))
            self.mqttc.publish(
                f"rover/{NODE}/telemetry/odom",
                json.dumps({
                    "x": float(msg.pose.pose.position.x),
                    "y": float(msg.pose.pose.position.y),
                    "z": float(msg.pose.pose.position.z),
                    "yaw": float(yaw),
                }),
            )
        except Exception as e:
            self.get_logger().warn(f"[bridge] odom err: {e}")

    def log_cb(self, msg):
        try:
            self.mqttc.publish(
                f"rover/{NODE}/telemetry/log",
                json.dumps({"line": str(msg.msg), "name": str(msg.name)}),
            )
        except Exception as e:
            self.get_logger().warn(f"[bridge] log err: {e}")

    def cmd_cb(self, msg):
        self.get_logger().info(f"[bridge] cmd_vel vx={msg.linear.x} wz={msg.angular.z}")


def main(args=None):
    rclpy.init(args=args)
    node = RoverBridge()
    node.get_logger().info(
        f"rover_bridge started: mqtt={MQTT_HOST}:{MQTT_PORT} node={NODE}"
    )
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
