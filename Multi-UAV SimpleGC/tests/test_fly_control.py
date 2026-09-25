from pathlib import Path
from types import SimpleNamespace
import csv
import unittest

import flyControl


class FakeMav:
    def __init__(self):
        self.calls = []

    def mission_clear_all_send(self, *args):
        self.calls.append(("mission_clear_all_send", args))

    def mission_count_send(self, *args):
        self.calls.append(("mission_count_send", args))

    def mission_item_send(self, *args):
        self.calls.append(("mission_item_send", args))

    def mission_item_int_send(self, *args):
        self.calls.append(("mission_item_int_send", args))

    def mission_set_current_send(self, *args):
        self.calls.append(("mission_set_current_send", args))

    def command_long_send(self, *args):
        self.calls.append(("command_long_send", args))


class FakeMaster:
    def __init__(self, messages):
        self.target_system = 1
        self.target_component = 1
        self.mav = FakeMav()
        self.messages = list(messages)

    def recv_match(self, type=None, blocking=False, timeout=None):
        if not self.messages:
            return None
        return self.messages.pop(0)

    def motors_armed(self):
        return False


class FakeMessage(SimpleNamespace):
    def __init__(self, message_type, **kwargs):
        super().__init__(**kwargs)
        self._message_type = message_type

    def get_type(self):
        return self._message_type


class FlyControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(__file__).parent / ".tmp" / self._testMethodName
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for path in self.tmp_dir.glob("*"):
            path.unlink()
        self.tmp_dir.rmdir()

    def test_build_mission_plan_adds_takeoff_before_waypoints(self):
        task = {
            "agent_id": "agent_1",
            "waypoints": [
                {"t": 0, "lat": 39.1, "lng": 116.1, "alt": 20},
                {"t": 1, "lat": 39.2, "lng": 116.2, "alt": 25},
            ],
        }

        mission_plan = flyControl.build_mission_plan(task)

        self.assertEqual(
            mission_plan,
            [
                {"command": "home", "lat": 39.1, "lng": 116.1, "alt": 0},
                {"command": "takeoff", "lat": 39.1, "lng": 116.1, "alt": 20},
                {"command": "waypoint", "lat": 39.1, "lng": 116.1, "alt": 20},
                {"command": "waypoint", "lat": 39.2, "lng": 116.2, "alt": 25},
            ],
        )

    def test_build_status_frame_uses_data_example_shape(self):
        messages = {
            "GLOBAL_POSITION_INT": SimpleNamespace(
                lat=399789466,
                lon=1163261748,
                relative_alt=12340,
                vx=123,
                vy=-456,
                vz=789,
            ),
            "ATTITUDE": SimpleNamespace(
                roll=0.1,
                pitch=-0.2,
                yaw=1.0,
                rollspeed=0.01,
                pitchspeed=-0.02,
                yawspeed=0.03,
            ),
        }

        frame = flyControl.build_status_frame(messages, elapsed_time=1.5)

        self.assertEqual(frame["t"], 1.5)
        self.assertEqual(
            frame["pos"],
            {"lat": 39.9789466, "lng": 116.3261748, "alt": 12.34},
        )
        self.assertEqual(frame["vel"]["vx"], 1.23)
        self.assertEqual(frame["vel"]["vy"], -4.56)
        self.assertEqual(frame["vel"]["vz"], 7.89)
        self.assertAlmostEqual(frame["vel"]["ground_speed"], 4.722975756871931)
        self.assertIn("quat", frame["orientation"])
        self.assertEqual(
            frame["angular_vel"],
            {"p": 0.01, "q": -0.02, "r": 0.03},
        )

    def test_save_task_record_writes_task_named_csv(self):
        frames = [
            {
                "t": 1.5,
                "pos": {"lat": 39.9789, "lng": 116.3262, "alt": 12.34},
                "vel": {"vx": 1.2, "vy": 3.4, "vz": -0.5, "ground_speed": 3.6},
                "orientation": {"quat": {"x": 0.1, "y": 0.2, "z": 0.3, "w": 0.4}},
                "angular_vel": {"p": 0.01, "q": 0.02, "r": 0.03},
            }
        ]

        file_path = flyControl.save_task_record("agent_1_0", frames, self.tmp_dir)

        self.assertEqual(file_path, self.tmp_dir / "agent_1_0.csv")
        with file_path.open("r", encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["t"], "1.5")
        self.assertEqual(rows[0]["pos.lat"], "39.9789")
        self.assertEqual(rows[0]["orientation.quat.w"], "0.4")
        self.assertEqual(rows[0]["angular_vel.r"], "0.03")

    def test_build_task_completion_message_with_next_task(self):
        message = flyControl.build_task_completion_message(
            current_agent_id="agent_1",
            frame_count=123,
            next_agent_id="agent_2",
        )

        self.assertEqual(
            message,
            "当前任务agent_1已完成，记录数据123帧，开始下一个任务agent_2，",
        )

    def test_build_task_completion_message_for_last_task(self):
        message = flyControl.build_task_completion_message(
            current_agent_id="agent_1",
            frame_count=123,
            next_agent_id=None,
        )

        self.assertEqual(message, "当前任务agent_1已完成，记录数据123帧，所有任务已完成。")

    def test_build_record_progress_message(self):
        message = flyControl.build_record_progress_message(
            agent_id="agent_1_0",
            current_waypoint=3,
            total_waypoints=12,
            frame_count=45,
            flight_mode="AUTO",
            armed=True,
            lat=39.9789466,
            lng=116.3261748,
            alt=12.34,
        )

        self.assertEqual(
            message,
            "\r当前任务agent_1_0，当前飞行航点3，总航点数12，已记录数据45帧，"
            "模式AUTO，ARM已解锁，高度12.34m，经纬度39.9789,116.3262",
        )

    def test_upload_mission_replies_to_float_mission_request_with_float_item(self):
        master = FakeMaster(
            [
                FakeMessage("MISSION_REQUEST", seq=0),
                FakeMessage("MISSION_ACK"),
            ]
        )

        flyControl.upload_mission(
            master,
            [{"command": "waypoint", "lat": 39.1, "lng": 116.1, "alt": 20}],
            verbose=False,
        )

        call_names = [call[0] for call in master.mav.calls]
        self.assertIn("mission_clear_all_send", call_names)
        self.assertIn("mission_count_send", call_names)
        self.assertIn("mission_item_send", call_names)
        self.assertNotIn("mission_item_int_send", call_names)
        self.assertIn("mission_set_current_send", call_names)

    def test_upload_mission_marks_first_item_current(self):
        master = FakeMaster(
            [
                FakeMessage("MISSION_REQUEST", seq=0),
                FakeMessage("MISSION_ACK"),
            ]
        )

        flyControl.upload_mission(
            master,
            [{"command": "takeoff", "lat": 39.1, "lng": 116.1, "alt": 20}],
            verbose=False,
        )

        mission_item_call = [
            call for call in master.mav.calls if call[0] == "mission_item_send"
        ][0]
        current_arg = mission_item_call[1][5]
        self.assertEqual(current_arg, 1)

    def test_get_start_mission_seq_skips_home_item(self):
        mission_plan = [
            {"command": "home", "lat": 39.1, "lng": 116.1, "alt": 0},
            {"command": "takeoff", "lat": 39.1, "lng": 116.1, "alt": 20},
        ]

        self.assertEqual(flyControl.get_start_mission_seq(mission_plan), 1)

    def test_set_current_mission_waits_for_vehicle_confirmation(self):
        master = FakeMaster([FakeMessage("MISSION_CURRENT", seq=0)])

        flyControl.set_current_mission(master, seq=0, timeout=0.1, verbose=False)

        call_names = [call[0] for call in master.mav.calls]
        self.assertIn("mission_set_current_send", call_names)

    def test_wait_until_armed_times_out_instead_of_waiting_forever(self):
        master = FakeMaster([])

        with self.assertRaises(TimeoutError):
            flyControl.wait_until_armed(master, timeout=0.01)

    def test_wait_until_armed_reports_statustext_on_timeout(self):
        master = FakeMaster([FakeMessage("STATUSTEXT", text="PreArm: GPS not healthy")])

        with self.assertRaisesRegex(TimeoutError, "PreArm: GPS not healthy"):
            flyControl.wait_until_armed(master, timeout=0.01, verbose=False)


if __name__ == "__main__":
    unittest.main()
