"""Release smoke options never start Docker when merely parsed."""

import pytest

from scripts.smoke_compose import arguments


def test_default_smoke_builds_its_own_images() -> None:
    args = arguments([])
    assert args.backend_image is None and args.worker_image is None and args.dashboard_image is None
    assert args.platform is None


def test_release_smoke_accepts_exact_image_pair_and_platform() -> None:
    args = arguments(
        [
            "--backend-image",
            "backend@sha256:" + "a" * 64,
            "--worker-image",
            "worker@sha256:" + "c" * 64,
            "--dashboard-image",
            "dashboard@sha256:" + "b" * 64,
            "--platform",
            "linux/amd64",
        ]
    )
    assert args.backend_image == "backend@sha256:" + "a" * 64
    assert args.worker_image == "worker@sha256:" + "c" * 64
    assert args.dashboard_image == "dashboard@sha256:" + "b" * 64
    assert args.platform == "linux/amd64"


@pytest.mark.parametrize("option", ["--backend-image", "--worker-image", "--dashboard-image"])
def test_release_smoke_rejects_half_a_release(option: str) -> None:
    with pytest.raises(SystemExit) as error:
        arguments([option, "candidate:1"])
    assert error.value.code == 2


def test_release_smoke_rejects_unsupported_platform() -> None:
    with pytest.raises(SystemExit) as error:
        arguments(["--platform", "linux/s390x"])
    assert error.value.code == 2
