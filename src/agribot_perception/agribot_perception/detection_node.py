"""Backward-compatible entrypoint for legacy detection_node launches.

This now delegates to the SAHI-enabled lifecycle perception node.
"""

from agribot_perception.perception_node import main


if __name__ == "__main__":
    main()
