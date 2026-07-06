"""Load regulatory frameworks into a corpus of Provision records.

For each requested framework: ensure the source is downloaded and cached, parse
it into Provisions, and collect them. Unreachable or unparseable frameworks are
skipped with a warning so one bad source never breaks the whole ingest.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

from .config import RegulusConfig
from .ingest.base import Provision
from .sources import FRAMEWORK_SOURCES, fetchable_sources


class StandardsLoader:
    def __init__(self, config: RegulusConfig | None = None) -> None:
        self.config = config or RegulusConfig()

    def load(self, framework_ids: Sequence[str] | None = None, force_download: bool = False) -> List[Provision]:
        from .download import download_to_cache

        if framework_ids:
            selected = {fid: FRAMEWORK_SOURCES[fid] for fid in framework_ids if fid in FRAMEWORK_SOURCES}
        elif self.config.frameworks:
            selected = {fid: FRAMEWORK_SOURCES[fid] for fid in self.config.frameworks if fid in FRAMEWORK_SOURCES}
        else:
            selected = fetchable_sources()

        provisions: List[Provision] = []
        for fid, source in selected.items():
            if not source.fetchable or not source.url:
                print(f"[SKIP] {source.name}: not fetchable ({source.note or 'no source url'}).")
                continue
            dest = Path(self.config.cache_dir) / source.cache_filename
            try:
                download_to_cache(source.url, dest, force=force_download)
                raw = dest.read_bytes()
                parsed = source.parser.parse(raw, source.url)
            except Exception as exc:  # noqa: BLE001 — one bad source shouldn't abort ingest
                print(f"[WARN] Failed to ingest {source.name}: {exc}")
                continue
            print(f"[DONE] {source.name}: {len(parsed)} provisions.")
            provisions.extend(parsed)

        print(f"[DONE] Loaded {len(provisions)} provisions from {len(selected)} framework(s).")
        return provisions
