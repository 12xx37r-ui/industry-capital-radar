from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class HttpError(RuntimeError):
    pass


def get_bytes(url: str, params: dict[str, Any] | None = None, *, timeout: int = 30,
              headers: dict[str, str] | None = None, retries: int = 2) -> bytes:
    if params:
        url = f"{url}?{urlencode(params)}"
    req_headers = {
        "User-Agent": "industry-capital-radar/0.2 contact: github-actions",
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
                time.sleep(1.5 * (attempt + 1))
    raise HttpError(f"GET failed: {url}: {last}")


def get_json(url: str, params: dict[str, Any] | None = None, *, timeout: int = 30,
             headers: dict[str, str] | None = None, retries: int = 2) -> Any:
    raw = get_bytes(url, params, timeout=timeout, headers=headers, retries=retries)
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        preview = raw[:300]
        raise HttpError(f"Invalid JSON from {url}: {preview!r}") from exc
