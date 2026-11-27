"""Append-only JOURNAL.md writer with acknowledged byte-range clearing (NA-60).

Contract:
- Appends entries under timestamp header.
- Argus collects and sends back an acknowledgment receipt with byte range and hash.
- Clear/truncate only acknowledged byte ranges; entries appended during collection are preserved.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Optional, Tuple


class JournalManager:
    def __init__(self, journal_path: str | Path, noob_name: str = "lynx"):
        self.journal_path = Path(journal_path)
        self.noob_name = noob_name
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.journal_path.exists():
            self.journal_path.write_text(f"# {self.noob_name.capitalize()} Daily Journal\n\n", encoding="utf-8")

    def append_entry(self, text: str, header: Optional[str] = None) -> int:
        """Append an entry with timestamp. Returns current file size in bytes."""
        ts_str = header or time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n## {ts_str}\n\n{text.strip()}\n"
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(entry)
        return self.journal_path.stat().st_size

    def prepare_collection(self) -> Tuple[int, str, str]:
        """Return (byte_count, sha256_hash, content_slice) for Argus collection."""
        data = self.journal_path.read_bytes()
        byte_count = len(data)
        digest = hashlib.sha256(data).hexdigest()
        return byte_count, digest, data.decode("utf-8", errors="replace")

    def acknowledge_and_trim(self, acknowledged_bytes: int, expected_hash: str) -> bool:
        """Safely trim the acknowledged prefix if the hash matches.
        
        Preserves any new entries that were appended while collection was underway!
        """
        data = self.journal_path.read_bytes()
        if len(data) < acknowledged_bytes:
            return False
        
        prefix = data[:acknowledged_bytes]
        if hashlib.sha256(prefix).hexdigest() != expected_hash:
            return False

        remaining = data[acknowledged_bytes:]
        # Overwrite file with remaining uncollected portion
        header = f"# {self.noob_name.capitalize()} Daily Journal (continued)\n\n".encode("utf-8")
        self.journal_path.write_bytes(header + remaining)
        return True
