"""El relevo que corre dentro del contenedor debe ser Python válido (no hay SSH en las pruebas)."""

import ast

from scripts import pilots_tunnel


def test_the_container_relay_is_valid_python_and_targets_the_internal_port() -> None:
    ast.parse(pilots_tunnel.RELAY)
    assert f"127.0.0.1',{pilots_tunnel.INTERNAL_PORT}" in pilots_tunnel.RELAY


def test_the_tunnel_only_listens_on_localhost() -> None:
    source = open(pilots_tunnel.__file__).read()
    assert 'bind(("127.0.0.1"' in source and "0.0.0.0" not in source
