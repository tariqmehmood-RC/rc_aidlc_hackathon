import importlib
import sys

import pytest


def test_runs_on_python_3_12():
    assert sys.version_info[:2] == (3, 12)


@pytest.mark.parametrize("name", [
    "backend.src",
    "backend.src.handlers",
    "backend.src.services",
    "backend.src.lib",
])
def test_packages_import(name):
    assert importlib.import_module(name)


def test_test_environment_is_pinned_to_us_east_1():
    import os
    assert os.environ["AWS_REGION"] == "us-east-1"
    assert os.environ["AWS_DEFAULT_REGION"] == "us-east-1"
    assert os.environ["AWS_ACCESS_KEY_ID"] == "testing"
