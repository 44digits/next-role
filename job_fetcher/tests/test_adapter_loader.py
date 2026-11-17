import tempfile
import unittest
from pathlib import Path

from job_fetcher.adapters import UnknownAdapterError
from job_fetcher.cli import build_adapter_registry
from job_fetcher.config import ConfigurationError


class AdapterLoaderTests(unittest.TestCase):
    def test_loads_and_registers_local_adapter_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            plugin = Path(directory) / "sample.py"
            plugin.write_text(
                "def register(registry):\n    registry.register('sample', object())\n",
                encoding="utf-8",
            )

            registry = build_adapter_registry(Path(directory))

            self.assertIsNotNone(registry.resolve("sample"))

    def test_requires_a_registration_function(self):
        with tempfile.TemporaryDirectory() as directory:
            plugin = Path(directory) / "invalid.py"
            plugin.write_text("value = 1\n", encoding="utf-8")

            with self.assertRaisesRegex(ConfigurationError, "register"):
                build_adapter_registry(Path(directory))

    def test_missing_adapter_directory_is_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "not-created"
            registry = build_adapter_registry(missing)

            with self.assertRaises(UnknownAdapterError):
                registry.resolve("sample")


if __name__ == "__main__":
    unittest.main()
