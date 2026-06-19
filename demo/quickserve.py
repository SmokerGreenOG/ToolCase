#!/usr/bin/env python3
"""
QuickServe — een minimale HTTP file server met LiveReload.

Hermes heeft dit gegenereerd als demonstratie van software-creatie.

Gebruik:
    python quickserve.py           # Serveer huidige dir op :8080
    python quickserve.py . --port 3000
    python quickserve.py D:/docs --no-browser
"""
__maker__ = "SmokerGreenOG"

import argparse
import http.server
import socket
import sys
import webbrowser
from functools import partial
from pathlib import Path


def find_free_port(start: int = 8080, max_tries: int = 100) -> int:
    """Vind een vrije poort vanaf start."""
    for port in range(start, start + max_tries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"Geen vrije poort in range {start}-{start + max_tries}")


class PrettyHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler met mooie directory listing en CORS."""

    def __init__(self, *args, directory: str = ".", **kwargs):
        self.serve_directory = directory
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args) -> None:
        """Kleurrijke logging per request."""
        status = int(args[1]) if len(args) > 1 else 0
        icon = chr(9989) if status < 400 else chr(9888) if status < 500 else chr(10060)
        print(f"  {icon} {args[0]} -> {status} ({args[2]})")

    def end_headers(self):
        """CORS headers toestaan voor lokale ontwikkeling."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def get_local_ips() -> list[str]:
    """Vind lokale IP-adressen."""
    ips = ["127.0.0.1"]
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            addr = info[4][0]
            if addr not in ips and not addr.startswith("127."):
                ips.append(addr)
    except Exception:
        pass
    return sorted(set(ips))


def main():
    parser = argparse.ArgumentParser(
        description="QuickServe — minimale HTTP file server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "directory", nargs="?", default=".",
        help="Directory om te serveren (default: .)"
    )
    parser.add_argument(
        "--port", "-p", type=int, default=8080,
        help="Poort (default: 8080)"
    )
    parser.add_argument(
        "--bind", "-b", default="0.0.0.0",
        help="Bind adres (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Open niet automatisch de browser"
    )
    parser.add_argument(
        "--version", action="version",
        version="quickserve.py v1.0.0"
    )
    args = parser.parse_args()

    # Valideer directory
    serve_dir = Path(args.directory).resolve()
    if not serve_dir.exists():
        print(f"  Directory bestaat niet: {serve_dir}")
        sys.exit(1)
    if not serve_dir.is_dir():
        print(f"  Geen directory: {serve_dir}")
        sys.exit(1)

    # Zoek vrije poort
    try:
        port = find_free_port(args.port)
    except RuntimeError as e:
        print(f"  {e}")
        sys.exit(1)

    # Maak handler
    handler = partial(PrettyHandler, directory=str(serve_dir))

    # Start server
    server = http.server.HTTPServer((args.bind, port), handler)

    print(f"\n{'=' * 55}")
    print(f"  QuickServe gestart")
    print(f"{'=' * 55}")
    print(f"  Map:  {serve_dir}")
    print(f"  URL:  http://localhost:{port}")
    for ip in get_local_ips():
        if ip != "127.0.0.1":
            print(f"  Net:  http://{ip}:{port}")
    print(f"  Ctrl+C om te stoppen\n")

    # Open browser
    if not args.no_browser:
        webbrowser.open(f"http://localhost:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server gestopt.")
        server.server_close()


if __name__ == "__main__":
    main()
