import base64
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "extract_imagegen.py"
FIXTURES = ROOT / "tests" / "fixtures"
RED_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
)
BLUE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYPj/HwADAgH/5ncLrgAAAABJRU5ErkJggg=="
)


def run_extract(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(arg) for arg in args)],
        text=True,
        capture_output=True,
        check=False,
    )


class ExtractImagegenTests(unittest.TestCase):
    def test_default_writes_last_image_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.png"
            result = run_extract(FIXTURES / "rollout-two-images.jsonl", dest)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(dest.read_bytes(), BLUE_PNG)
            self.assertIn("OK", result.stdout)

    def test_index_selects_specific_image_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.png"
            result = run_extract(FIXTURES / "rollout-two-images.jsonl", dest, "--index=0")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(dest.read_bytes(), RED_PNG)

    def test_all_writes_every_image_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.png"
            result = run_extract(FIXTURES / "rollout-two-images.jsonl", dest, "--all")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((Path(tmp) / "out-0.png").read_bytes(), RED_PNG)
            self.assertEqual((Path(tmp) / "out-1.png").read_bytes(), BLUE_PNG)

    def test_missing_image_result_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.png"
            result = run_extract(FIXTURES / "rollout-no-image.jsonl", dest)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no image_generation_call result", result.stderr)
            self.assertFalse(dest.exists())

    def test_non_png_result_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.png"
            result = run_extract(FIXTURES / "rollout-not-png.jsonl", dest)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not a PNG", result.stderr)
            self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
