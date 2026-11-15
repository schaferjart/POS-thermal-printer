"""Device-token check via printer.check_device over PostgREST.

Uses only the publishable key (apikey header, no Authorization: sb_ keys are
not JWTs) and Content-Profile: printer, like device/printerd.py. The renderer
holds no Supabase secret key.
"""

import os

import requests


class AuthUnavailable(Exception):
    """Could not ask Supabase (not configured, unreachable, function missing)."""


def check_device(token: str) -> bool:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
    if not url or not key:
        raise AuthUnavailable("SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY not set")
    try:
        r = requests.post(f"{url}/rest/v1/rpc/check_device", json={"device_token": token},
                          headers={"apikey": key, "Content-Profile": "printer"}, timeout=10)
    except requests.RequestException as e:
        raise AuthUnavailable(f"Supabase unreachable: {type(e).__name__}") from None
    if r.status_code != 200:
        # 404 = migration not applied; never treat it as a valid device.
        raise AuthUnavailable(f"check_device: HTTP {r.status_code} {r.text[:200]}")
    return r.json() is True
