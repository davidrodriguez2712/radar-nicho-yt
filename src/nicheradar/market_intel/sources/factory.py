import time
from collections.abc import Callable

import httpx

from nicheradar.config import Settings
from nicheradar.market_intel.sources.dealbaron import USER_AGENT, DealBaronSource
from nicheradar.market_intel.sources.synthetic import synthetic_transport

SYNTHETIC_BASE = "https://dealbaron.test"


def build_source(
    config: Settings, *, sleep: Callable[[float], None] = time.sleep
) -> DealBaronSource:
    """Synthetic mode never opens a socket: it serves packaged fixtures in-process."""
    if config.mode == "synthetic":
        client = httpx.Client(transport=synthetic_transport(), base_url=SYNTHETIC_BASE)
        return DealBaronSource(
            client,
            base_url=SYNTHETIC_BASE,
            max_pages=config.market_intel_max_pages,
            delay_seconds=0,
            sleep=lambda seconds: None,
        )
    client = httpx.Client(
        timeout=20,
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    )
    return DealBaronSource(
        client,
        base_url=config.market_intel_base_url,
        max_pages=config.market_intel_max_pages,
        delay_seconds=config.market_intel_request_delay_seconds,
        sleep=sleep,
    )
