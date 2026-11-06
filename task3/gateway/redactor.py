"""Bounded, incremental text redaction with no network dependencies."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern


REDACTION = "[REDACTED]"


@dataclass(frozen=True)
class PatternSpec:
    """A PII regex and the maximum number of characters it can consume."""

    name: str
    regex: Pattern[str]
    max_length: int


# The limits are part of each pattern contract. Bounding them is what makes a
# finite streaming carry possible. The email expression uses the standard
# 64-character local-part limit and a deliberate, practical DNS subset of up to
# three labels; this trades exhaustive RFC coverage for predictable latency.
EMAIL_LOCAL_MAX = 64
EMAIL_LABEL_MAX = 63
EMAIL_DOMAIN_LABELS_MAX = 3
EMAIL_DOMAIN_MAX = EMAIL_DOMAIN_LABELS_MAX * EMAIL_LABEL_MAX + EMAIL_DOMAIN_LABELS_MAX - 1
EMAIL_ATOM = rf"[A-Za-z0-9.!#$%&'*+/=?^_`{{|}}~-]{{1,{EMAIL_LOCAL_MAX}}}"
EMAIL_LABEL = rf"[A-Za-z0-9](?:[A-Za-z0-9-]{{0,{EMAIL_LABEL_MAX - 2}}}[A-Za-z0-9])?"
EMAIL_DOMAIN = rf"(?:{EMAIL_LABEL}\.){{1,{EMAIL_DOMAIN_LABELS_MAX - 1}}}[A-Za-z]{{2,{EMAIL_LABEL_MAX}}}"

PATTERNS: tuple[PatternSpec, ...] = (
    PatternSpec(
        "ssn",
        re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"),
        len("000-00-0000"),
    ),
    PatternSpec(
        "card",
        re.compile(r"(?<!\d)(?<!\d[ -])(?:\d[ -]?){12,18}\d(?![ -]?\d)"),
        19 + 18,  # 19 digits with one optional separator between each pair.
    ),
    PatternSpec(
        "email",
        re.compile(rf"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{{|}}~-]){EMAIL_ATOM}@{EMAIL_DOMAIN}(?![A-Za-z0-9.-])"),
        EMAIL_LOCAL_MAX + 1 + EMAIL_DOMAIN_MAX,
    ),
)

# Derived from the pattern registry so adding a longer pattern automatically
# expands the carry. Keeping this assertion beside the registry makes an
# accidentally unbounded or nonsensical pattern fail during import.
MAX_PATTERN_LEN = max(spec.max_length for spec in PATTERNS)
assert MAX_PATTERN_LEN > 1
TAIL_LENGTH = MAX_PATTERN_LEN - 1


class StreamRedactor:
    """Redact bounded PII patterns identically across arbitrary chunking."""

    def __init__(self) -> None:
        self._buffer = ""
        self.redaction_counts = {spec.name: 0 for spec in PATTERNS}

    @property
    def buffered_characters(self) -> int:
        """Number of raw characters currently retained for boundary safety."""

        return len(self._buffer)

    def _redact(self, text: str) -> str:
        # The patterns are individually precompiled. Sequential substitution is
        # intentional: replacing one adjacent PII item can expose the valid
        # boundary of the next (for example, SSN immediately followed by email).
        for spec in PATTERNS:
            text, count = spec.regex.subn(REDACTION, text)
            self.redaction_counts[spec.name] += count
        return text

    def feed(self, text: str) -> str:
        """Accept text and return only the prefix safe from future extension."""

        if not isinstance(text, str):
            raise TypeError("StreamRedactor.feed expects str")
        if not text:
            return ""

        self._buffer += text
        safe_boundary = max(0, len(self._buffer) - TAIL_LENGTH)

        # Never cut through a match. Although the carry is large enough to hold
        # any entire match, a match can begin immediately before the nominal
        # boundary and end inside the tail.
        for spec in PATTERNS:
            for match in spec.regex.finditer(self._buffer):
                if match.start() < safe_boundary < match.end():
                    safe_boundary = match.start()

        safe_raw = self._buffer[:safe_boundary]
        self._buffer = self._buffer[safe_boundary:]
        return self._redact(safe_raw)

    def flush(self) -> str:
        """Redact and return the final tail, then reset stream state."""

        final = self._redact(self._buffer)
        self._buffer = ""
        return final
