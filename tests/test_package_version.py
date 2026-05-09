from __future__ import annotations

import json
import unittest
from pathlib import Path

import superteam_codex


ROOT = Path(__file__).resolve().parents[1]


class PackageVersionTests(unittest.TestCase):
    def test_manifest_pyproject_and_runtime_versions_match(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertEqual(manifest["version"], superteam_codex.__version__)
        self.assertIn(f'version = "{superteam_codex.__version__}"', pyproject)
        self.assertIn(f"Version: {superteam_codex.__version__}", (ROOT / "VERSION.md").read_text(encoding="utf-8"))

    def test_complete_g1_g7_skill_surface_exists(self) -> None:
        expected = {
            "g1",
            "g2",
            "g3",
            "g4",
            "g5",
            "g6",
            "g7",
            "execute",
            "review",
            "verify",
            "finish",
        }
        missing = [name for name in expected if not (ROOT / "skills" / name / "SKILL.md").exists()]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
