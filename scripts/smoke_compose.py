"""Opt-in local Compose smoke test. Creates only a uniquely named synthetic project."""

import argparse
import os
import secrets
import socket
import subprocess
from uuid import uuid4

import httpx


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-image", help="Use an already-built local backend image")
    parser.add_argument("--worker-image", help="Use an already-built local worker image")
    parser.add_argument("--dashboard-image", help="Use an already-built local dashboard image")
    parser.add_argument("--platform", choices=["linux/amd64", "linux/arm64"])
    args = parser.parse_args(argv)
    supplied = [args.backend_image, args.worker_image, args.dashboard_image]
    if any(supplied) and not all(supplied):
        parser.error("provide all three release images, or none to build smoke images")
    return args


def main() -> None:
    args = arguments()
    project = "nicheradar-smoke-" + uuid4().hex[:12]
    api_port, dashboard_port = free_port(), free_port()
    while dashboard_port == api_port:
        dashboard_port = free_port()
    env = {key: value for key, value in os.environ.items() if not key.startswith("NR_")}
    token = secrets.token_urlsafe(40)
    env.update(
        POSTGRES_PASSWORD=secrets.token_urlsafe(40),
        NR_SERVICE_TOKEN=token,
        NR_DASHBOARD_PASSWORD=secrets.token_urlsafe(40),
        NR_LOCAL_API_PORT=str(api_port),
        NR_LOCAL_DASHBOARD_PORT=str(dashboard_port),
        NR_BACKEND_IMAGE=args.backend_image or project + "-backend:local",
        NR_WORKER_IMAGE=args.worker_image or project + "-worker:local",
        NR_DASHBOARD_IMAGE=args.dashboard_image or project + "-dashboard:local",
    )
    if args.platform:
        env["DOCKER_DEFAULT_PLATFORM"] = args.platform
    # Do not load a developer's .env into the isolated test deployment.
    command = ["docker", "compose", "--env-file", os.devnull, "-p", project, "-f", "compose.yaml"]
    build_options = ["--no-build", "--pull", "never"] if args.backend_image else ["--build"]
    print(f"Isolated synthetic project: {project}", flush=True)
    subprocess.run([*command, "config", "--quiet"], env=env, check=True)
    try:
        subprocess.run(
            [*command, "up", *build_options, "--wait", "--wait-timeout", "180"],
            env=env,
            check=True,
        )
        with httpx.Client(
            base_url=f"http://127.0.0.1:{api_port}",
            timeout=10,
            headers={"Authorization": f"Bearer {token}"},
            trust_env=False,
        ) as client:
            status = client.get("/api/v1/status")
            status.raise_for_status()
            assert status.json()["radar_paused"] is True
            assert status.json()["mode"] == "synthetic"
            profile = client.get("/api/v1/profile").json()
            version = profile.pop("version_number")
            profile["weekly_hours"] = "17"
            response = client.put(
                "/api/v1/profile", json={"profile": profile, "expected_version": version}
            )
            response.raise_for_status()
            unauthenticated = httpx.get(
                f"http://127.0.0.1:{api_port}/api/v1/opportunities", timeout=10, trust_env=False
            )
            assert unauthenticated.status_code == 401
            subprocess.run(
                [
                    *command,
                    "up",
                    "-d",
                    "--no-build",
                    "--pull",
                    "never",
                    "--force-recreate",
                    "--wait",
                    "--wait-timeout",
                    "180",
                    "api",
                    "worker",
                    "dashboard",
                ],
                env=env,
                check=True,
            )
            assert client.get("/api/v1/profile").json()["weekly_hours"] == "17"
            assert client.get("/api/v1/status").json()["radar_paused"] is True
            assert client.get("/api/v1/consumption").json()["confirmed"] == []
        assert (
            httpx.get(
                f"http://127.0.0.1:{dashboard_port}/_stcore/health", timeout=10, trust_env=False
            ).status_code
            == 200
        )
        print(
            "PASS: authenticated API, paused worker, healthy dashboard and persistent profile; "
            "zero provider calls.",
            flush=True,
        )
    finally:
        # Only this script's random project and its synthetic test volume are removed.
        subprocess.run([*command, "down", "--volumes", "--remove-orphans"], env=env, check=True)


if __name__ == "__main__":
    main()
