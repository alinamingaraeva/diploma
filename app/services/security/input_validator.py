import base64
import binascii
import re
from dataclasses import dataclass
from typing import Final

INJECTION_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions?\b", re.IGNORECASE),
    re.compile(r"\bignore\b.{0,80}\binstructions?\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bdisregard\s+(the\s+)?(system|previous|above)\b", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\s+(a|an|the|dan|do anything now)\b", re.IGNORECASE),
    re.compile(r"\bfrom\s+now\s+on\b.{0,120}\bact\s+as\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\b(dan\s+mode|do\s+anything\s+now)\b", re.IGNORECASE),
    re.compile(r"\bforget\s+(everything|all|previous)\b", re.IGNORECASE),
    re.compile(r"\b(jailbroken|developer mode|godmode)\b", re.IGNORECASE),
    re.compile(r"\bjust\s+(print|say|output)\b", re.IGNORECASE),
]
ENCODING_MARKER_RE: Final = re.compile(r"\b(base64|decode\s+the\s+following)\b", re.IGNORECASE)
BASE64_TOKEN_RE: Final = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{8,}={0,2}(?![A-Za-z0-9+/])")

MAX_INPUT_CHARS: Final[int] = 4000
NON_PRINTABLE_RATIO_LIMIT: Final[float] = 0.10

@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str | None = None
    rule: str | None = None


def _contains_decodable_base64(text: str) -> bool:
    for match in BASE64_TOKEN_RE.finditer(text):
        token = match.group(0)
        raw = token.rstrip("=")
        padded = raw + "=" * (-len(raw) % 4)
        try:
            decoded = base64.b64decode(padded, validate=True)
        except (binascii.Error, ValueError):
            continue
        if len(decoded) < 5:
            continue
        printable_ratio = sum(chr(byte).isprintable() for byte in decoded) / len(decoded)
        if printable_ratio >= 0.85:
            return True
    return False

def validate_input(text: str) -> ValidationResult:
    if len(text) > MAX_INPUT_CHARS:
        return ValidationResult(False, "input too long", rule="length")

    non_printable = sum(1 for c in text if not c.isprintable() and c not in "\n\r\t")
    if non_printable / max(len(text), 1) > NON_PRINTABLE_RATIO_LIMIT:
        return ValidationResult(False, "high non-printable ratio", rule="encoding")

    # Garak InjectBase64 и похожие атаки передают длинную закодированную
    # инструкцию как один base64-блок. Обычные музейные запросы таких блоков не содержат.
    if ENCODING_MARKER_RE.search(text) or _contains_decodable_base64(text):
        return ValidationResult(False, "base64-like encoded payload", rule="encoding")

    for pat in INJECTION_PATTERNS:
        if pat.search(text):
            return ValidationResult(False, f"matched pattern {pat.pattern}", rule="injection")

    return ValidationResult(True)
