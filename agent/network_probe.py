from __future__ import annotations

import socket
import time
from dataclasses import dataclass


@dataclass
class TcpProbeResult:
    success: bool
    latency_ms: int | None = None
    error_message: str | None = None


def tcp_connect_probe(host: str, port: int, timeout_seconds: int = 5) -> TcpProbeResult:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            latency_ms = max(0, int((time.perf_counter() - started) * 1000))
            return TcpProbeResult(success=True, latency_ms=latency_ms)
    except OSError as exc:
        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        return TcpProbeResult(success=False, latency_ms=latency_ms, error_message=str(exc))
