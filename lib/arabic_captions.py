"""Arabic caption helpers shared by projects that narrate in Arabic.

Lifted from projects/_reelkit/voice.py and qa.py (the Sard reels) so the next
Arabic project does not re-implement them. Two rules live here on purpose:

* Digits are always Latin 0-9. Arabic-Indic (U+0660-0669) and Persian
  (U+06F0-06F9) digits never reach a caption, a filename or an export.
* A caption chunk is short enough to read at phone size: at most four words and
  28 characters, decided by the words the narrator actually said, not by a
  character budget applied to the script.
"""
from __future__ import annotations

import re
from typing import Iterable, Sequence

_ARABIC_INDIC = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_PERSIAN = {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_NON_LATIN_DIGIT = re.compile("[٠-٩۰-۹]")
_TASHKEEL = re.compile(r"[ً-ْٰـ]")
_ALEF_FORMS = re.compile("[إأآٱ]")

MAX_WORDS_PER_CHUNK = 4
MAX_CHARS_PER_CHUNK = 28


def to_latin_digits(text: str) -> str:
    """Map every Arabic-Indic or Persian digit to its Latin equivalent."""
    return text.translate(_ARABIC_INDIC).translate(_PERSIAN)


def normalize_ar(text: str) -> list[str]:
    """Tokenise Arabic for comparison: strip tashkeel, fold alef/ta-marbuta/ya.

    Returns the list of comparable word tokens. Latin words and digits are
    dropped, which is what a word-error-rate check against a Whisper transcript
    wants — the transcript spells foreign words unpredictably.
    """
    s = _TASHKEEL.sub("", to_latin_digits(text))
    s = _ALEF_FORMS.sub("ا", s).replace("ة", "ه").replace("ى", "ي")
    return re.sub(r"[^ء-ي\s]", " ", s).split()


def wer(reference: Sequence[str], hypothesis: Sequence[str]) -> float:
    """Word error rate between two token lists (Levenshtein / len(reference))."""
    if not reference:
        return 0.0 if not hypothesis else 1.0
    d = list(range(len(hypothesis) + 1))
    for i in range(1, len(reference) + 1):
        prev = d[:]
        d[0] = i
        for j in range(1, len(hypothesis) + 1):
            cost = 0 if reference[i - 1] == hypothesis[j - 1] else 1
            d[j] = min(prev[j] + 1, d[j - 1] + 1, prev[j - 1] + cost)
    return d[-1] / len(reference)


def assert_caption_safe(chunk: str) -> None:
    """Raise ValueError when a caption chunk breaks the readability rules."""
    if _NON_LATIN_DIGIT.search(chunk):
        raise ValueError(f"non-Latin digit in caption: {chunk!r}")
    words = chunk.split()
    if len(words) > MAX_WORDS_PER_CHUNK:
        raise ValueError(f"caption has {len(words)} words (max {MAX_WORDS_PER_CHUNK}): {chunk!r}")
    if len(chunk) > MAX_CHARS_PER_CHUNK:
        raise ValueError(f"caption has {len(chunk)} chars (max {MAX_CHARS_PER_CHUNK}): {chunk!r}")


def chunks_from_words(
    caption_chunks: Iterable[str],
    words: Sequence[tuple[str, float, float]],
    *,
    offset: float = 0.0,
    lead_in: float = 0.6,
) -> list[list]:
    """Time caption chunks from the narrator's own word timestamps.

    ``caption_chunks`` is the script split into display chunks (a chunk that
    starts with ``*`` is a headline chunk, flagged True in the output).
    ``words`` are (word, start, end) triples from Whisper for the same line.
    Each chunk consumes as many transcript words as it has comparable tokens;
    the chunk shows from just before its first word until its last word ends.
    Returns [[text, start, end, is_headline], ...], as the HyperFrames
    composition expects.
    """
    out: list[list] = []
    k = 0
    for raw in caption_chunks:
        text = raw.lstrip("*")
        assert_caption_safe(text)
        n = len(normalize_ar(text))
        sub = words[k:k + n]
        k += n
        if not sub:
            continue
        start = round(offset + max(sub[0][1], sub[0][2] - lead_in), 2)
        end = round(offset + sub[-1][2], 2)
        out.append([text, start, end, raw.startswith("*")])
    return out
