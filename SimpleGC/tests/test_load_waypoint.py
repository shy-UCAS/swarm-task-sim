from pathlib import Path
import json
import unittest

import loadWaypoint


class LoadWaypointTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(__file__).parent / ".tmp" / self._testMethodName
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for path in self.tmp_dir.glob("*"):
            if path.exists():
                path.unlink()
        self.tmp_dir.rmdir()

    def test_loads_trajectories_agents_as_mission_tasks(self):
        data_path = self.tmp_dir / "trajectories.json"
        data_path.write_text(
            json.dumps(
                {
                    "trajectories": {
                        "agent_b": {
                            "frames": [
                                {
                                    "t": 2,
                                    "pos": {"lat": 39.2, "lng": 116.2, "alt": 12},
                                },
                                {
                                    "t": 1,
                                    "pos": {"lat": 39.1, "lng": 116.1, "alt": 10},
                                },
                            ]
                        },
                        "agent_a": {
                            "frames": [
                                {
                                    "t": 0,
                                    "pos": {"lat": 38.1, "lng": 115.1, "alt": 8},
                                }
                            ]
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        tasks = loadWaypoint.load_mission_tasks(data_path)

        self.assertEqual([task["agent_id"] for task in tasks], ["agent_a", "agent_b"])
        self.assertEqual(
            tasks[1]["waypoints"],
            [
                {"t": 1, "lat": 39.1, "lng": 116.1, "alt": 10},
                {"t": 2, "lat": 39.2, "lng": 116.2, "alt": 12},
            ],
        )

    def test_loads_raw_coordinate_agents_as_mission_tasks(self):
        data_path = self.tmp_dir / "raw.json"
        data_path.write_text(
            json.dumps(
                {
                    "uavs_coords_raw": {
                        "agent_1": {
                            "lats": [39.1, 39.2],
                            "lngs": [116.1, 116.2],
                            "ts": [0, 1],
                            "extras": [{"frame_id": 0}],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        tasks = loadWaypoint.load_mission_tasks(data_path)

        self.assertEqual(
            tasks,
            [
                {
                    "agent_id": "agent_1",
                    "waypoints": [
                        {
                            "t": 0,
                            "lat": 39.1,
                            "lng": 116.1,
                            "alt": 20,
                            "extra": {"frame_id": 0},
                        },
                        {"t": 1, "lat": 39.2, "lng": 116.2, "alt": 20},
                    ],
                }
            ],
        )

    def test_uses_default_relative_alt_when_trajectory_alt_is_missing(self):
        data_path = self.tmp_dir / "missing_alt.json"
        data_path.write_text(
            json.dumps(
                {
                    "trajectories": {
                        "agent_1": {
                            "frames": [
                                {"t": 0, "pos": {"lat": 39.1, "lng": 116.1}}
                            ]
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        tasks = loadWaypoint.load_mission_tasks(data_path)

        self.assertEqual(tasks[0]["waypoints"][0]["alt"], 20)


if __name__ == "__main__":
    unittest.main()
