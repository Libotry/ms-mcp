import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parent / ".trae" / "skills" / "auto-tuning" / "scripts" / "check_real_profiling_env.py"


def load_module():
    spec = importlib.util.spec_from_file_location("check_real_profiling_env", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AutoTuningEnvCheckTests(unittest.TestCase):
    def test_validate_artifacts_rejects_empty_directory(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = module.validate_profiling_artifacts(Path(tmp_dir))
        self.assertFalse(result["ok"])
        self.assertIn("profiling artifact", result["reason"].lower())

    def test_validate_artifacts_accepts_non_empty_supported_file(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact = Path(tmp_dir) / "trace_view.json"
            artifact.write_text('{"traceEvents": []}', encoding="utf-8")
            result = module.validate_profiling_artifacts(Path(tmp_dir))
        self.assertTrue(result["ok"])
        self.assertEqual(result["artifact_count"], 1)

    def test_framework_requirements_flag_missing_commands_and_packages(self):
        module = load_module()

        def command_exists(_name):
            return False

        def import_exists(_module_name):
            return False

        result = module.evaluate_framework_requirements(
            framework="pytorch",
            command_exists=command_exists,
            import_exists=import_exists,
        )

        self.assertFalse(result["ok"])
        missing = set(result["missing"])
        self.assertIn("msprof", missing)
        self.assertIn("torch_npu", missing)

    def test_ascend_environment_requires_visible_device_command(self):
        module = load_module()

        def command_exists(_name):
            return False

        result = module.evaluate_ascend_environment(command_exists=command_exists)

        self.assertFalse(result["ok"])
        self.assertIn("npu-smi", result["reason"])


if __name__ == "__main__":
    unittest.main()