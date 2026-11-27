#!/usr/bin/env python3
"""rover_tf — каркас TF-дерева ровера для SLAM/Nav2.

Сейчас:
  base_link -> lidar   (static, identity: лидар считаем в центре корпуса)
  odom -> base_link    (dynamic, identity 20 Гц: одометрии колёс ещё нет)

Когда появится моторный контроллер с энкодерами, odom->base_link надо будет
публиковать из реальной одометрии, а не identity.
"""
import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster


def make(parent, child, stamp):
    t = TransformStamped()
    t.header.stamp = stamp
    t.header.frame_id = parent
    t.child_frame_id = child
    t.transform.rotation.w = 1.0
    return t


class RoverTf(Node):
    def __init__(self):
        super().__init__("rover_tf")
        self.static = StaticTransformBroadcaster(self)
        self.dyn = TransformBroadcaster(self)
        self.odom_pub = self.create_publisher(Odometry, "/odom", 10)
        now = self.get_clock().now().to_msg()
        self.static.sendTransform([
            make("base_link", "lidar", now),
            make("base_link", "base_footprint", now),
        ])
        self.timer = self.create_timer(0.05, self.tick)

    def tick(self):
        now = self.get_clock().now().to_msg()
        self.dyn.sendTransform(make("odom", "base_link", now))
        o = Odometry()
        o.header.stamp = now
        o.header.frame_id = "odom"
        o.child_frame_id = "base_link"
        o.pose.pose.orientation.w = 1.0
        self.odom_pub.publish(o)


def main(args=None):
    rclpy.init(args=args)
    node = RoverTf()
    node.get_logger().info("rover_tf: base_link->lidar/base_footprint (static), odom->base_link (20 Hz)")
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
