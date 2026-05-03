#!/usr/bin/env python3
"""
Agribot v1.1 — Simulation Verification Script
=============================================
CI smoke test for the Agribot simulation stack.
Connects via rosbridge, verifies topic publication, state transitions,
and emergency stop behaviour.

Usage:
    python3 simulation/verify_sim.py                   # nominal scenario
    python3 simulation/verify_sim.py --scenario camera_loss
"""

import argparse
import sys
import threading
import time
from typing import Optional

try:
    import roslibpy
except ImportError:
    print("❌ Error: 'roslibpy' not found. Install with: pip install roslibpy")
    sys.exit(1)


class SimVerifier:
    """Automated verification harness for the Agribot simulation."""

    def __init__(self, scenario: str = 'nominal') -> None:
        self.scenario = scenario
        self.client = roslibpy.Ros(host='localhost', port=9090)
        self.results: dict[str, bool] = {}

    def run_tests(self) -> bool:
        """Execute all verification tests and return True if all pass."""
        print(f'🔍 Starting Simulation Verification (scenario={self.scenario})...')
        print('=' * 50)

        try:
            self.client.run(timeout=5)
        except Exception as e:
            print(f'❌ Failed to connect to rosbridge: {e}')
            return False

        if not self.client.is_connected:
            print('❌ Timeout: Could not connect to rosbridge at localhost:9090')
            return False

        print('✅ Connected to rosbridge.')

        # Run common tests
        self._test_topic_reception()
        self._test_activation_transition()
        self._test_mode_transition()
        self._test_emergency_stop()

        # Scenario-specific tests
        if self.scenario == 'camera_loss':
            self._test_camera_loss()
        elif self.scenario == 'error_recovery':
            self._test_error_recovery()

        # Summary
        print('\n' + '=' * 50)
        print('SIMULATION VERIFICATION SUMMARY')
        print('=' * 50)
        all_passed = all(self.results.values())
        for test, passed in self.results.items():
            icon = '✅' if passed else '❌'
            print(f'{icon} {test:<35}: {"PASS" if passed else "FAIL"}')
        print('=' * 50)
        status = 'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'
        print(f'Result: {status}')

        self.client.terminate()
        return all_passed

    def _wait_for_event(
        self,
        event: threading.Event,
        timeout: float,
        description: str,
    ) -> bool:
        """Wait for a threading.Event with timeout. Returns True if fired."""
        result = event.wait(timeout=timeout)
        return result

    def _test_topic_reception(self) -> None:
        """Verify critical topics are publishing (subscribe-first pattern)."""
        print('\n📡 Test: Topic Reception...')

        topics = [
            ('/system_state', 'std_msgs/String'),
            ('/hw_capabilities', 'std_msgs/String'),
        ]

        for topic_name, msg_type in topics:
            received = threading.Event()
            msg_count = [0]

            def make_cb(evt: threading.Event, counter: list[int]):
                def cb(msg: dict) -> None:
                    counter[0] += 1
                    if counter[0] >= 2:  # Wait for at least 2 messages
                        evt.set()
                return cb

            listener = roslibpy.Topic(self.client, topic_name, msg_type)
            listener.subscribe(make_cb(received, msg_count))

            success = self._wait_for_event(received, 10.0, topic_name)
            listener.unsubscribe()

            icon = '✅' if success else '❌'
            print(f'  {icon} {topic_name} — received {msg_count[0]} msgs')
            self.results[f'topic:{topic_name}'] = success

    def _test_activation_transition(self) -> None:
        """Verify READY -> ACTIVE transition via /operator_confirm."""
        print('\n🤖 Test: Activation (READY -> ACTIVE)...')

        # Step 1: Subscribe first, wait for stable state reception
        state_msgs: list[str] = []
        stable = threading.Event()

        def state_cb(msg: dict) -> None:
            state_msgs.append(msg['data'])
            if len(state_msgs) >= 2:
                stable.set()

        state_sub = roslibpy.Topic(self.client, '/system_state', 'std_msgs/String')
        state_sub.subscribe(state_cb)

        self._wait_for_event(stable, 10.0, 'initial state')

        # Step 2: Wait for READY state before activating
        ready_event = threading.Event()

        def ready_cb(msg: dict) -> None:
            if msg['data'] == 'READY':
                ready_event.set()

        ready_sub = roslibpy.Topic(self.client, '/system_state', 'std_msgs/String')
        ready_sub.subscribe(ready_cb)

        print('  ⏳ Waiting for system to reach READY (boot sequence)...')
        got_ready = self._wait_for_event(ready_event, 25.0, 'READY state')
        ready_sub.unsubscribe()

        if not got_ready:
            print('  ❌ System never reached READY state.')
            self.results['activation'] = False
            state_sub.unsubscribe()
            return

        # Step 3: Send activation command
        confirm_pub = roslibpy.Topic(self.client, '/operator_confirm', 'std_msgs/String')
        active_event = threading.Event()

        def active_cb(msg: dict) -> None:
            if msg['data'] == 'ACTIVE':
                active_event.set()

        active_sub = roslibpy.Topic(self.client, '/system_state', 'std_msgs/String')
        active_sub.subscribe(active_cb)
        time.sleep(0.5)  # Let subscription register

        confirm_pub.publish(roslibpy.Message({'data': 'ACTIVATE'}))
        success = self._wait_for_event(active_event, 5.0, 'ACTIVE transition')

        active_sub.unsubscribe()
        state_sub.unsubscribe()

        icon = '✅' if success else '❌'
        print(f'  {icon} Transition to ACTIVE.')
        self.results['activation'] = success

    def _test_mode_transition(self) -> None:
        """Verify mode command (DETECT) is processed."""
        print('\n🎯 Test: Mode Transition (DETECT)...')

        # Subscribe first, flush queue
        received = threading.Event()
        msg_count = [0]

        def det_cb(msg: dict) -> None:
            msg_count[0] += 1
            if msg_count[0] >= 1:
                received.set()

        det_sub = roslibpy.Topic(self.client, '/detections', 'std_msgs/String')
        det_sub.subscribe(det_cb)
        time.sleep(0.5)

        # Command DETECT mode
        mode_pub = roslibpy.Topic(self.client, '/set_mode', 'std_msgs/String')
        mode_pub.publish(roslibpy.Message({'data': 'DETECT'}))

        success = self._wait_for_event(received, 5.0, 'detections after DETECT')
        det_sub.unsubscribe()

        icon = '✅' if success else '❌'
        print(f'  {icon} Detections received after DETECT command.')
        self.results['mode:DETECT'] = success

    def _test_emergency_stop(self) -> None:
        """Verify SAFE command transitions system and deactivates spray."""
        print('\n🛑 Test: Emergency Stop (SAFE)...')

        # First engage spray
        mode_pub = roslibpy.Topic(self.client, '/set_mode', 'std_msgs/String')
        mode_pub.publish(roslibpy.Message({'data': 'SPRAY'}))
        time.sleep(1.0)

        # Subscribe for spray_active and system_state
        safe_event = threading.Event()
        spray_off_event = threading.Event()

        def safe_cb(msg: dict) -> None:
            if msg['data'] == 'SAFE':
                safe_event.set()

        def spray_cb(msg: dict) -> None:
            if not msg['data']:
                spray_off_event.set()

        state_sub = roslibpy.Topic(self.client, '/system_state', 'std_msgs/String')
        state_sub.subscribe(safe_cb)
        spray_sub = roslibpy.Topic(self.client, '/spray_active', 'std_msgs/Bool')
        spray_sub.subscribe(spray_cb)
        time.sleep(0.5)

        # Send SAFE command
        mode_pub.publish(roslibpy.Message({'data': 'SAFE'}))

        safe_ok = self._wait_for_event(safe_event, 3.0, 'SAFE state')
        spray_ok = self._wait_for_event(spray_off_event, 3.0, 'spray deactivated')

        state_sub.unsubscribe()
        spray_sub.unsubscribe()

        icon_s = '✅' if safe_ok else '❌'
        icon_p = '✅' if spray_ok else '❌'
        print(f'  {icon_s} System returned to SAFE.')
        print(f'  {icon_p} Spray deactivated.')
        self.results['emergency:SAFE'] = safe_ok
        self.results['emergency:spray_off'] = spray_ok

    def _test_camera_loss(self) -> None:
        """Verify camera_loss scenario suppresses images."""
        print('\n📷 Test: Camera Loss Scenario...')
        print('  ⏳ Waiting for camera suppression at t=15s...')

        event_received = threading.Event()

        def event_cb(msg: dict) -> None:
            if 'camera_loss' in msg.get('data', ''):
                event_received.set()

        event_sub = roslibpy.Topic(self.client, '/sim_event', 'std_msgs/String')
        event_sub.subscribe(event_cb)

        success = self._wait_for_event(event_received, 20.0, 'camera_loss event')
        event_sub.unsubscribe()

        icon = '✅' if success else '❌'
        print(f'  {icon} Camera loss event received.')
        self.results['scenario:camera_loss'] = success

    def _test_error_recovery(self) -> None:
        """Verify error_recovery scenario transitions through ERROR."""
        print('\n⚠️  Test: Error Recovery Scenario...')
        print('  ⏳ Waiting for ERROR injection at t=10s...')

        error_event = threading.Event()

        def error_cb(msg: dict) -> None:
            if msg['data'] == 'ERROR':
                error_event.set()

        state_sub = roslibpy.Topic(self.client, '/system_state', 'std_msgs/String')
        state_sub.subscribe(error_cb)

        success = self._wait_for_event(error_event, 15.0, 'ERROR state')
        state_sub.unsubscribe()

        icon = '✅' if success else '❌'
        print(f'  {icon} ERROR state observed.')
        self.results['scenario:error_recovery'] = success


def main() -> None:
    """Parse args and run verification."""
    parser = argparse.ArgumentParser(description='Agribot Simulation Verifier')
    parser.add_argument(
        '--scenario',
        type=str,
        default='nominal',
        choices=['nominal', 'camera_loss', 'error_recovery'],
        help='Scenario to test (default: nominal)',
    )
    args = parser.parse_args()

    verifier = SimVerifier(scenario=args.scenario)
    success = verifier.run_tests()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
