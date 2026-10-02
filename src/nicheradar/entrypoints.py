import subprocess
import sys
from importlib.resources import files

import uvicorn

from nicheradar.config import Settings


def api() -> None:
    config = Settings()
    uvicorn.run(
        "nicheradar.api:create_app",
        factory=True,
        host=config.api_host,
        port=config.api_port,
        access_log=False,
    )


def dashboard() -> None:
    config = Settings()
    script = str(files("nicheradar").joinpath("dashboard.py"))
    raise SystemExit(
        subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                script,
                "--server.address",
                config.dashboard_host,
                "--server.port",
                str(config.dashboard_port),
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
                *sys.argv[1:],
            ]
        )
    )
