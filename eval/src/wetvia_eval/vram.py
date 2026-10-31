"""Piekmeting via nvidia-smi. Zonder die binary is de meting afwezig, niet verzonnen."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from threading import Event, Lock, Thread


def parse_nvidia_smi_memory_mib(text: str) -> int | None:
    readings: list[int] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.isdigit():
            readings.append(int(stripped))
    if not readings:
        return None
    return max(readings)


def query_nvidia_smi_mib(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int | None:
    try:
        completed = runner(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return parse_nvidia_smi_memory_mib(completed.stdout)


def peak_mib(readings: list[int | None]) -> int | None:
    present = [value for value in readings if value is not None]
    if not present:
        return None
    return max(present)


class VramSampler:
    """Sample GPU memory while a request is active, then retain its peak."""

    def __init__(
        self,
        probe: Callable[[], int | None] = query_nvidia_smi_mib,
        *,
        interval_seconds: float = 0.25,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._probe = probe
        self._interval_seconds = interval_seconds
        self._stop = Event()
        self._lock = Lock()
        self._readings: list[int | None] = []
        self._thread: Thread | None = None

    @property
    def readings(self) -> list[int | None]:
        with self._lock:
            return list(self._readings)

    @property
    def peak_mib(self) -> int | None:
        return peak_mib(self.readings)

    def start(self) -> None:
        self._sample()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self._sample()

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            self._sample()

    def _sample(self) -> None:
        reading = self._probe()
        with self._lock:
            self._readings.append(reading)
