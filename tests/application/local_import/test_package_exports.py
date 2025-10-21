from __future__ import annotations

import importlib


def test_local_import_package_exposes_public_api(monkeypatch) -> None:
    package = importlib.reload(importlib.import_module("features.photonest.application.local_import"))
    direct_logger = importlib.import_module(
        "features.photonest.application.local_import.logger"
    ).LocalImportTaskLogger

    original_import = package.import_module
    calls = []

    def _instrumented_import(name: str, package_name: str | None = None):
        calls.append((name, package_name))
        return original_import(name, package_name)

    monkeypatch.setattr(package, "import_module", _instrumented_import)

    exported_logger = package.LocalImportTaskLogger

    assert exported_logger is direct_logger
    assert (".logger", package.__name__) in calls


def test_local_import_package_invalid_attribute() -> None:
    package = importlib.reload(importlib.import_module("features.photonest.application.local_import"))

    assert not hasattr(package, "NonExisting")
    try:
        getattr(package, "NonExisting")
    except AttributeError as exc:
        assert "NonExisting" in str(exc)
    else:  # pragma: no cover - defensive programming
        raise AssertionError("AttributeError was not raised")
