from __future__ import annotations

from typing import Any, Tuple


_ERROR_STATUS = {"fail", "failed", "error"}


def validate_agent_response(resp: Any, *, raw_status_code: int | None = None) -> Tuple[bool, str]:
    """
    Return (ok, reason). ok=False if response indicates error.
    - raw_status_code: HTTP status code if available from transport layer.
    - resp: parsed payload (dict/str/etc.)
    """
    if raw_status_code is not None:
        try:
            code = int(raw_status_code)
        except Exception:
            code = None
        if code is not None and code != 200:
            return False, f"http status {code}"

    if isinstance(resp, dict):
        for key in ("code", "status_code", "statusCode"):
            if key in resp:
                try:
                    code = int(resp.get(key))
                except Exception:
                    code = None
                if code is not None and code != 200:
                    return False, f"{key} {code}"

        status = resp.get("status")
        if isinstance(status, str) and status.lower() in _ERROR_STATUS:
            return False, f"status {status}"

    return True, ""
