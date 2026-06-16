import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agentic_eval_ops.io import load_scenario


class IoAndCliTests(unittest.TestCase):
    def test_load_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scenario.json"
            path.write_text(
                json.dumps(
                    {
                        "scenario_id": "load-test",
                        "domain": "voice_agent",
                        "events": [{"type": "message", "content": "confirm summary"}],
                    }
                ),
                encoding="utf-8",
            )

            scenario = load_scenario(path)

            self.assertEqual(scenario.scenario_id, "load-test")
            self.assertEqual(scenario.domain, "voice_agent")

    def test_cli_markdown(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agentic_eval_ops.cli",
                "evaluate",
                "examples/vapi_voice_call.json",
                "--format",
                "markdown",
            ],
            cwd=Path(__file__).resolve().parents[1],
            env={"PYTHONPATH": "src"},
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("# Evaluation: vapi-appointment-intake", result.stdout)


if __name__ == "__main__":
    unittest.main()
