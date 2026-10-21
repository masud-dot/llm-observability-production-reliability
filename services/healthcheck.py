"""Container health check: exit 0 if /healthz answers on a port.

python -m services.healthcheck 8000
"""

import sys
import urllib.request


def main(port: str) -> int:
    url = f"http://localhost:{port}/healthz"
    try:
        with urllib.request.urlopen(url, timeout=2):
            return 0
    except OSError:
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
