"""The Lambda bundle has what the functions need and nothing it should not (task 5.3)."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "backend" / "build" / "lambda"
HANDLERS = [
    "briefs_read.create_brief_handler", "briefs_read.get_brief_handler", "briefs_read.list_briefs_handler",
    "briefs_write.update_brief_handler", "briefs_write.confirm_brief_handler", "briefs_write.approve_brief_handler",
    "briefs_write.retry_brief_handler", "rules_cases.rules_handler", "rules_cases.case_studies_handler",
    "worker.handler",
]


@pytest.fixture(scope="module")
def bundle():
    if os.environ.get("SKIP_BUNDLE_BUILD") != "1":
        subprocess.run([str(ROOT / "scripts" / "build_backend.sh")], check=True, capture_output=True, timeout=300)
    assert BUNDLE.is_dir()
    return BUNDLE


def files(bundle):
    return [p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()]


def test_handlers_and_data_files_are_in_the_bundle(bundle):
    for name in HANDLERS:
        module, func = name.split(".")
        source = (bundle / "backend" / "src" / "handlers" / f"{module}.py").read_text(encoding="utf-8")
        assert f"{func} =" in source or f"def {func}(" in source, name
    assert (bundle / "data" / "case_studies.json").is_file()
    assert (bundle / "data" / "attendee_profiles.json").is_file()
    assert (bundle / "backend" / "__init__.py").is_file()


def test_runtime_dependencies_are_linux_arm64(bundle):
    for pkg in ("aws_lambda_powertools", "jsonschema", "defusedxml", "referencing", "rpds"):
        assert (bundle / pkg).is_dir(), pkg
    native = list(bundle.rglob("*.so"))
    assert native and all("aarch64" in p.name for p in native)


def test_nothing_that_must_stay_out_is_bundled(bundle):
    names = files(bundle)
    forbidden = [n for n in names if any(part in n.split("/") for part in (".venv", "tests", "__pycache__", "node_modules"))]
    assert forbidden == []
    assert not [n for n in names if n.split("/")[-1].startswith(".env")]
    assert not (bundle / "boto3").exists()          # provided by the Lambda runtime
    assert not (bundle / "backend" / "local_run.py").exists()
    assert not [n for n in names if n.startswith("backend/tests")]


def test_data_paths_resolve_like_in_the_repo(bundle):
    # profiles.py and case_study_matcher.py find data/ three levels up from their own folder.
    profiles = bundle / "backend" / "src" / "lib" / "profiles.py"
    assert (profiles.resolve().parents[3] / "data" / "attendee_profiles.json").is_file()


def test_bundle_is_small(bundle):
    size = sum((bundle / n).stat().st_size for n in files(bundle))
    assert size < 50 * 1024 * 1024
