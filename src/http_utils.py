from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


class HttpError(RuntimeError):
    pass


_SENSITIVE_QUERY_KEYS = {
    "apikey", "api_key", "api-key", "key", "token", "access_token",
    "authorization", "auth", "secret", "client_secret",
}


def redact_url(url: str) -> str:
    """Return a URL safe for logs by masking credential-like query values."""
    try:
        parts = urlsplit(url)
        safe_query = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            normalized = key.strip().lower()
            safe_query.append((key, "***" if normalized in _SENSITIVE_QUERY_KEYS else value))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe_query), parts.fragment))
    except Exception:
        return "<redacted-url>"


def get_bytes(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: int = 30,
    headers: dict[str, str] | None = None,
    retries: int = 2,
) -> bytes:
    if params:
        url = f"{url}?{urlencode(params)}"
    req_headers = {
        "User-Agent": "industry-capital-radar/0.3.1 contact: github-actions",
        "Accept": "*/*",
    }
    if headers:
        req_headers.update(headers)

    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urlopen(Request(url, headers=req_headers), timeout=timeout) as resp:
                return resp.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(min(8.0, 1.5 * (2 ** attempt)))

    error_type = type(last).__name__ if last is not None else "UnknownError"
    raise HttpError(f"GET failed: {redact_url(url)}: {error_type}")


def get_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: int = 30,
    headers: dict[str, str] | None = None,
    retries: int = 2,
) -> Any:
    raw = get_bytes(url, params, timeout=timeout, headers=headers, retries=retries)
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        preview = raw[:300]
        raise HttpError(f"Invalid JSON from {redact_url(url)}: {preview!r}") from exc
