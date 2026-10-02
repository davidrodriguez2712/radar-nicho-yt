"""Explicit one-unit YouTube API connection diagnostic."""

import argparse
import asyncio
import json
import logging
import re
from datetime import UTC, datetime

from pydantic import ValidationError

from nicheradar.config import Settings
from nicheradar.integrations.contracts import Operation, ProviderError
from nicheradar.integrations.youtube import YouTubeProvider

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


def main() -> None:
    parser = argparse.ArgumentParser(description="Conexión de NicheRadar con YouTube Data API")
    parser.add_argument(
        "--check-video",
        metavar="VIDEO_ID",
        help="Consultar un video público por ID; consume una unidad de cuota y no guarda datos",
    )
    args = parser.parse_args()
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        config = Settings()
        if args.check_video is None:
            print(
                json.dumps(
                    {
                        "status": "configured"
                        if config.youtube_api_key and config.youtube_auth_scope
                        else "configuration_missing",
                        "credential_material_present": config.youtube_api_key is not None,
                        "account_scope_configured": config.youtube_auth_scope is not None,
                        "network_requests": 0,
                        "quota_units": 0,
                    }
                )
            )
            return
        if not VIDEO_ID.fullmatch(args.check_video):
            raise ProviderError("invalid_video_id", not_sent=True)
        if config.youtube_api_key is None:
            raise ProviderError("authentication_required", not_sent=True)
        if config.youtube_auth_scope is None:
            raise ProviderError("account_scope_required", not_sent=True)
        checked_at = datetime.now(UTC)
        batch = asyncio.run(
            YouTubeProvider(
                config.youtube_api_key,
                config.youtube_auth_scope,
                enabled=True,
            ).fetch(Operation.VIDEOS, {"id": args.check_video}, checked_at)
        )
        report = {
            "status": "connection_checked",
            "network_requests": 1,
            "quota_units": 1,
            "resources_returned": len(batch.videos),
            "validated_at": checked_at.isoformat(),
        }
    except (ProviderError, ValidationError, KeyboardInterrupt) as error:
        code = error.code if isinstance(error, ProviderError) else "invalid_configuration"
        sent = bool(args.check_video and isinstance(error, ProviderError) and not error.not_sent)
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error_code": code,
                    "network_requests": int(sent),
                    "quota_units": 1 if sent else 0,
                }
            )
        )
        raise SystemExit(1) from None
    finally:
        logging.disable(previous_logging)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
