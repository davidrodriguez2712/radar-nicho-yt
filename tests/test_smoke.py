"""Real process smoke tests: localhost only, synthetic, no provider credentials."""

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.smoke
@pytest.mark.parametrize(
    "service,path,port_var",
    [
        ("nicheradar-api", "/health/live", "NR_API_PORT"),
        ("nicheradar-dashboard", "/_stcore/health", "NR_DASHBOARD_PORT"),
    ],
)
def test_service_starts(service: str, path: str, port_var: str, tmp_path: Path) -> None:
    port = free_port()
    env = {key: value for key, value in os.environ.items() if not key.startswith("NR_")}
    env.update({port_var: str(port), "NR_MODE": "synthetic", "NR_RADAR_PAUSED": "true"})
    with subprocess.Popen(
        [service], cwd=tmp_path, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ) as process:
        try:
            with httpx.Client(timeout=0.5, trust_env=False) as client:
                for _ in range(100):
                    if process.poll() is not None:
                        pytest.fail(f"{service} exited before becoming healthy")
                    try:
                        response = client.get(f"http://127.0.0.1:{port}{path}")
                        if response.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    pytest.fail(f"{service} did not become healthy")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
