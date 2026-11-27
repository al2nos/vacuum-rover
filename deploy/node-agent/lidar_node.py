#!/usr/bin/env python3
"""rover_lidar — ROS2 node: читает /run/rover/scan.json (lidar_delta) -> /scan (LaserScan)."""
import json
import math
import os
import time

import rclpy
from rclpy.time import Time
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Header

SCAN_FILE = os.environ.get("ROVER_SCAN_FILE", "/run/rover/scan.json")
SCAN_TOPIC = os.environ.get("ROVER_SCAN_TOPIC", "/scan")
FRAME_ID = os.environ.get("ROVER_SCAN_FRAME", "lidar")


class RoverLidarNode(Node):
    def __init__(self):
        super().__init__("rover_lidar_node")
        self.scan_pub = self.create_publisher(LaserScan, SCAN_TOPIC, 10)
        self.timer = self.create_timer(0.05, self.timer_cb)
        self.last_publish_t = 0.0
        self.published = 0
        self.last_err_t = 0.0
        self.last_scan_ts = None

    def timer_cb(self):
        try:
            with open(SCAN_FILE, "r") as f:
                scan = json.load(f)
            # scan.json перезаписывается ~6 раз/с; публикуем только новый скан
            scan_ts = scan.get("ts")
            if scan_ts is not None and scan_ts == self.last_scan_ts:
                return
            self.last_scan_ts = scan_ts
            r = scan.get("r") or []
            n = len(r)
            ranges = []
            for v in r:
                ranges.append(float(v) / 1000.0 if v else float("inf"))
            msg = LaserScan()
            msg.header = Header()
            if scan_ts is not None:
                msg.header.stamp = Time(seconds=float(scan_ts)).to_msg()
            else:
                msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = FRAME_ID
            msg.angle_min = 0.0
            msg.angle_max = 2.0 * math.pi
            msg.angle_increment = (2.0 * math.pi) / n if n > 1 else 0.0
            msg.range_min = 0.01
            msg.range_max = 20.0
            msg.ranges = ranges
            msg.intensities = [0.0] * len(ranges)
            msg.scan_time = 0.167
            msg.time_increment = msg.scan_time / len(ranges) if ranges else 0.0
            self.last_publish_t = time.time()
            self.published += 1
            self.scan_pub.publish(msg)
        except Exception as e:
            now = time.time()
            if now - self.last_err_t > 5.0:
                self.last_err_t = now
                self.get_logger().warning(f"lidar scan read err: {e}")


def main(args=None):
    rclpy.init(args=args)
    node = RoverLidarNode()
    node.get_logger().info(f"rover_lidar_node started, publishing {SCAN_TOPIC} from {SCAN_FILE}")
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
