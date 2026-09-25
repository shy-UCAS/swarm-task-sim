from pathlib import Path
from types import SimpleNamespace
import unittest

import main


class MainTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(__file__).parent / ".tmp"
        self.tmp_dir.mkdir(exist_ok=True)

    def tearDown(self):
        for path in self.tmp_dir.glob("*"):
            path.unlink()

    def test_read_connection_urls_ignores_blank_lines(self):
        config = self.tmp_dir / "TCP -local.port"
        config.write_text(
            "tcp://127.0.0.1:11010\n\n  tcp://127.0.0.1:11020  \n",
            encoding="utf-8",
        )

        self.assertEqual(
            main.read_connection_urls(config),
            [
                "tcp:127.0.0.1:11010",
                "tcp:127.0.0.1:11020",
            ],
        )

    def test_get_connection_url_supports_one_based_index(self):
        config = self.tmp_dir / "TCP -local.port"
        config.write_text(
            "tcp://127.0.0.1:11010\n"
            "tcp://127.0.0.1:11020\n",
            encoding="utf-8",
        )

        self.assertEqual(
            main.get_connection_url(config, index=2),
            "tcp:127.0.0.1:11020",
        )

    def test_build_telemetry_snapshot_converts_units(self):
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

        snapshot = main.build_telemetry_snapshot(messages)

        self.assertEqual(snapshot["lat_deg"], 39.9789466)
        self.assertEqual(snapshot["lon_deg"], 116.3261748)
        self.assertEqual(snapshot["relative_alt_m"], 12.34)
        self.assertEqual(snapshot["vx_m_s"], 1.23)
        self.assertEqual(snapshot["vy_m_s"], -4.56)
        self.assertEqual(snapshot["vz_m_s"], 7.89)
        self.assertEqual(snapshot["roll_deg"], 5.729577951308233)
        self.assertEqual(snapshot["pitch_deg"], -11.459155902616466)
        self.assertEqual(snapshot["yaw_deg"], 57.29577951308232)
        self.assertEqual(snapshot["roll_rate_deg_s"], 0.5729577951308232)
        self.assertEqual(snapshot["pitch_rate_deg_s"], -1.1459155902616465)
        self.assertEqual(snapshot["yaw_rate_deg_s"], 1.7188733853924696)


if __name__ == "__main__":
    unittest.main()
