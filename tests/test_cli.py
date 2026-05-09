from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "superteam_codex" / "cli.py"


class CliTests(unittest.TestCase):
    def test_cli_go_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "sms_minimal"
            shutil.copytree(FIXTURES / "sms_minimal", project)

            go = subprocess.run(
                [sys.executable, str(CLI), "--project", str(project), "go", "Build", "SMS"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            go_data = json.loads(go.stdout)
            self.assertTrue(go_data["ok"])
            self.assertEqual(go_data["source_pack"]["feature_ui_map_status"], "blocked_missing_frames")

            status = subprocess.run(
                [sys.executable, str(CLI), "--project", str(project), "status"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            status_data = json.loads(status.stdout)
            self.assertTrue(status_data["active"])

    def test_cli_doctor_fails_on_missing_frame(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "sms_minimal"
            shutil.copytree(FIXTURES / "sms_minimal", project)
            subprocess.run(
                [sys.executable, str(CLI), "--project", str(project), "go", "Build", "SMS"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            doctor = subprocess.run(
                [sys.executable, str(CLI), "--project", str(project), "doctor"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(doctor.returncode, 1)
            self.assertEqual(json.loads(doctor.stdout)["health"], "fail")

    def test_cli_g1_event_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "sms_minimal"
            shutil.copytree(FIXTURES / "sms_minimal", project)
            subprocess.run(
                [sys.executable, str(CLI), "--project", str(project), "go", "Build", "SMS"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            status = subprocess.run(
                [sys.executable, str(CLI), "--project", str(project), "g1-status"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(json.loads(status.stdout)["active_event"], "G1.START")

            answer = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--project",
                    str(project),
                    "g1-answer",
                    "做一个门店管理系统",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(json.loads(answer.stdout)["next_event"], "G1.Q2")


if __name__ == "__main__":
    unittest.main()
