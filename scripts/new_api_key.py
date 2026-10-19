"""Generate a per-tenant API key for the VisionGuard service.

The key is printed once so you can store it server-side (for example in
VISIONGUARD_API_KEYS) and hand it to the tenant. It is never written to
disk or logged by this script.

Usage:
    python scripts/new_api_key.py --tenant acme
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from visionguard.gateway.policy import generate_api_key


def main():
    p = argparse.ArgumentParser(
        description="Generate a VisionGuard tenant API key")
    p.add_argument("--tenant", required=True, help="tenant name")
    p.add_argument("--bytes", type=int, default=32,
                   help="random bytes before urlsafe encoding (default 32)")
    a = p.parse_args()

    key = generate_api_key(a.bytes)
    print("New API key for tenant '%s':" % a.tenant)
    print()
    print("  %s" % key)
    print()
    print("Server side (merge into any existing mapping):")
    print("  export VISIONGUARD_API_KEYS='%s'"
          % json.dumps({a.tenant: key}))
    print()
    print("Client side:")
    print("  curl -H 'X-API-Key: %s' -F image=@plate.png "
          "'http://localhost:8000/inspect?tenant=%s'" % (key, a.tenant))


if __name__ == "__main__":
    main()
