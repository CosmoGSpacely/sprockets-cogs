import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SC = ROOT / "scripts" / "sc"


class Stage115ScDispatcherTests(unittest.TestCase):
    def run_sc(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SC), *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_no_args_prints_operator_summary(self):
        result = self.run_sc()

        self.assertEqual(result.returncode, 0)
        self.assertIn("Sprockets-Cogs operator command surface", result.stdout)
        self.assertIn("friction", result.stdout)
        self.assertIn("This dispatcher only delegates", result.stdout)

    def test_command_help_names_owner_and_mapping(self):
        result = self.run_sc("--help", "review")

        self.assertEqual(result.returncode, 0)
        self.assertIn("Jane", result.stdout)
        self.assertIn("scripts/review", result.stdout)

    def test_unknown_command_fails_loudly(self):
        result = self.run_sc("bogus")

        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown command", result.stderr)

    def test_review_delegates_to_jane_script(self):
        result = self.run_sc("review", "--count")

        self.assertEqual(result.returncode, 0)
        self.assertIn("item(s) waiting", result.stdout)

    def test_friction_delegates_to_uniblab_script(self):
        result = self.run_sc("friction")

        self.assertEqual(result.returncode, 0)
        self.assertIn("Sprockets-Cogs friction summary", result.stdout)


if __name__ == "__main__":
    unittest.main()
