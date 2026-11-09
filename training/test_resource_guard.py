import time

import pytest
from resource_guard import ResourceGuard, violation


def test_unsafe_hardware_conditions_stop_the_run():
    normal = {"temperature_c": 45, "gpu_used_mib": 2400, "ram_available_mib": 4096}
    assert violation(normal) is None
    for key, value in [
        ("temperature_c", 75),
        ("gpu_used_mib", 6656),
        ("ram_available_mib", 1535),
    ]:
        assert violation({**normal, key: value}) is not None


def test_stop_file_monitor_error_and_stale_samples_fail_closed(tmp_path):
    directory = tmp_path / "run"
    directory.mkdir()
    guard = ResourceGuard.__new__(ResourceGuard)
    guard.directory = directory
    guard.started = time.monotonic()
    guard.max_seconds = 7200
    guard.samples = [{"elapsed_s": 0}]
    guard.error = None
    guard.check()
    stop = tmp_path / "STOP"
    stop.touch()
    with pytest.raises(RuntimeError, match="STOP"):
        guard.check()
    stop.unlink()
    guard.error = "Monitoring failed"
    with pytest.raises(RuntimeError, match="Monitoring failed"):
        guard.check()
    guard.error = None
    guard.started -= 11
    with pytest.raises(RuntimeError, match="stale"):
        guard.check()
