"""Túnel desde el Mac hacia la API de NicheRadar (que no tiene dominio público).

Abre 127.0.0.1:<puerto> en ESTE Mac; cada conexión se reenvía por SSH al puerto interno del
contenedor de la API (``docker exec`` + un relevo TCP mínimo). No publica nada en el servidor
ni deja procesos allí, y solo escucha en localhost. Apúntale ``NR_SYNC_URL``:

    uv run python scripts/pilots_tunnel.py            # mantiene el túnel (Ctrl+C para cerrar)
    NR_SYNC_URL=http://127.0.0.1:18000 NR_SYNC_TOKEN=nrc_… \\
        uv run python scripts/channel_sync.py fetch --channel-dir <canal>
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import socket
import subprocess
import sys
import threading
from pathlib import Path

HOST = "root@194.61.28.253"
SERVICE = "proy1-credito-riesgo_nicheradar-api"
INTERNAL_PORT = 8000
SSH = [
    "ssh",
    "-i",
    str(Path.home() / ".ssh/id_ed25519"),
    "-o",
    "IdentitiesOnly=yes",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "ServerAliveInterval=15",
    HOST,
]
# Relevo que corre DENTRO del contenedor: stdin/stdout <-> 127.0.0.1:8000.
RELAY = (
    "import socket,sys,threading\n"
    f"s=socket.create_connection(('127.0.0.1',{INTERNAL_PORT}))\n"
    "i=sys.stdin.buffer;o=sys.stdout.buffer\n"
    "def up():\n"
    " while True:\n"
    "  d=i.read1(65536)\n"
    "  if not d:break\n"
    "  s.sendall(d)\n"
    " s.shutdown(socket.SHUT_WR)\n"
    "threading.Thread(target=up,daemon=True).start()\n"
    "while True:\n"
    " d=s.recv(65536)\n"
    " if not d:break\n"
    " o.write(d);o.flush()\n"
)


def find_container() -> str:
    command = shlex.join(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.swarm.service.name={SERVICE}",
            "--format",
            "{{.ID}}",
        ]
    )
    result = subprocess.run([*SSH, command], capture_output=True, text=True, timeout=30)
    ids = result.stdout.split()
    if result.returncode or len(ids) != 1 or not re.fullmatch(r"[a-f0-9]{12,64}", ids[0]):
        raise SystemExit("no se encontró un único contenedor de la API (¿SSH o servicio caído?)")
    return ids[0]


def pump_in(client: socket.socket, process: subprocess.Popen[bytes]) -> None:
    assert process.stdin is not None
    try:
        while data := client.recv(65536):
            process.stdin.write(data)
            process.stdin.flush()
    except OSError:
        pass
    finally:
        try:
            process.stdin.close()
        except OSError:
            pass


def serve(client: socket.socket, container: str) -> None:
    remote = shlex.join(["docker", "exec", "-i", container, "python", "-c", RELAY])
    process = subprocess.Popen(
        [*SSH, remote], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    threading.Thread(target=pump_in, args=(client, process), daemon=True).start()
    assert process.stdout is not None
    try:
        while data := os.read(process.stdout.fileno(), 65536):
            client.sendall(data)
    except OSError:
        pass
    finally:
        client.close()
        process.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=18000, help="puerto local (127.0.0.1)")
    args = parser.parse_args()
    container = find_container()
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", args.port))
    listener.listen(8)
    print(f"túnel listo: http://127.0.0.1:{args.port} -> API de NicheRadar", flush=True)
    try:
        while True:
            client, _ = listener.accept()
            threading.Thread(target=serve, args=(client, container), daemon=True).start()
    except KeyboardInterrupt:
        return 0
    finally:
        listener.close()


if __name__ == "__main__":
    sys.exit(main())
