"""Download-and-cache utility for regulatory source documents.

Mirrors the GKN loader pattern: fetch once to a local cache, reuse thereafter.
A browser-like User-Agent is sent because several official sites (EUR-Lex, NIST)
reject default urllib requests.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

_USER_AGENT = "Mozilla/5.0 (compatible; Regulus/0.0; +https://github.com/minw0607/Regulus)"


def download_to_cache(url: str, destination: Path, force: bool = False, timeout: int = 90) -> Path:
    """Ensure ``url`` is cached at ``destination``; return the path.

    Uses an atomic ``.part`` temp file so a partial download never poisons the
    cache. Raises on network failure (callers decide whether to skip).
    """
    destination = Path(destination)
    if destination.exists() and destination.stat().st_size > 0 and not force:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        print(f"[INFO] Downloading {url}")
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            data = response.read()
        tmp.write_bytes(data)
        tmp.replace(destination)
        print(f"[INFO] Cached to {destination} ({destination.stat().st_size / 1e6:.1f} MB)")
    finally:
        if tmp.exists():
            tmp.unlink()
    return destination
