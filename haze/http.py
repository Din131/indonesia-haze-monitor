"""Small HTTP helper with retries (standard library only)."""
import json
import time
import urllib.error
import urllib.request

USER_AGENT = "indonesia-haze-monitor (+https://github.com/Din131/indonesia-haze-monitor)"


def get(url: str, retries: int = 3, backoff: float = 5.0, timeout: int = 60) -> bytes:
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(backoff * attempt)
    # Never echo the URL: it can contain the FIRMS key.
    raise RuntimeError(f"request failed after {retries} attempts: {type(last).__name__}")


def get_json(url: str, **kw):
    return json.loads(get(url, **kw))
