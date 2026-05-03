"""
Agribot v1.1 — Unit Test: Sim Core CompressedImage Headers
==========================================================
Validates that the camera publisher sets correct ROS message headers.
Run with: python3 -m pytest simulation/tests/test_sim_core_headers.py -v
"""

import time

import rclpy
from rclpy.executors import MultiThreadedExecutor
from sensor_msgs.msg import CompressedImage


def test_compressed_image_headers() -> None:
    """Verify CompressedImage header fields are correctly set."""
    rclpy.init()

    received_msgs: list[CompressedImage] = []
    node = rclpy.create_node('test_header_subscriber')

    def img_cb(msg: CompressedImage) -> None:
        received_msgs.append(msg)

    node.create_subscription(
        CompressedImage, '/image_raw/compressed', img_cb, 5
    )

    executor = MultiThreadedExecutor()
    executor.add_node(node)

    # Spin for up to 3 seconds waiting for at least one message
    deadline = time.time() + 3.0
    while time.time() < deadline and len(received_msgs) == 0:
        executor.spin_once(timeout_sec=0.1)

    assert len(received_msgs) >= 1, (
        'No CompressedImage messages received on /image_raw/compressed'
    )

    msg = received_msgs[0]

    # Bug Fix #2: Verify correct header fields
    assert msg.header.frame_id == 'camera_link', (
        f'Expected frame_id="camera_link", got "{msg.header.frame_id}"'
    )
    assert msg.format == 'jpeg', (
        f'Expected format="jpeg", got "{msg.format}"'
    )
    assert msg.header.stamp.sec > 0, (
        f'Expected stamp.sec > 0, got {msg.header.stamp.sec}'
    )
    assert len(msg.data) > 0, 'CompressedImage data is empty'

    node.destroy_node()
    rclpy.shutdown()
