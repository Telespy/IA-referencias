"""Canonical cleanup before any bibliographic parsing.

The original string is never discarded. This module only creates a parser-safe
representation and records every transformation for auditability.
"""
import html
import re
import unicodedata


def _clean_url_fragment(fragment: str) -> str:
    value = html.unescape(fragment or "")
    value = value.replace("\\/", "/").replace("\\:", ":")
    value = re.sub(r"\\\s*(?:\r?\n)?\s*", "", value)
    value = re.sub(r"\s+", "", value)
    return value.rstrip(".,;\\ ")


def normalize_reference_input(raw: str) -> tuple[str, list[dict]]:
    value = str(raw or "")
    steps = []

    def changed(code, before, after):
        nonlocal value
        if before != after:
            steps.append({"code": code, "before": before, "after": after})
            value = after

    before = value
    value = unicodedata.normalize("NFC", value)
    value = value.replace("\u200b", "").replace("\ufeff", "").replace("\u00ad", "")
    changed("UNICODE_NORMALIZED", before, value)

    before = value
    value = html.unescape(value)
    changed("HTML_ENTITIES_DECODED", before, value)

    before = value
    value = re.sub(r"(?i)https?\\://", lambda m: m.group(0).replace("\\", ""), value)
    value = value.replace("\\/", "/")
    changed("ESCAPED_URL_FIXED", before, value)

    # Markdown emphasis is presentation, never bibliographic data.
    before = value
    value = re.sub(r"(?<!\\)(\*\*|__)(.+?)\1", r"\2", value, flags=re.S)
    value = re.sub(r"(?<!\\)(\*|_)([^\n]+?)\1", r"\2", value)
    changed("MARKDOWN_REMOVED", before, value)

    # Repair line-wrapped URLs only inside the Disponivel em field.
    before = value
    def url_field(match):
        prefix, body = match.group(1), match.group(2)
        candidate = _clean_url_fragment(body)
        return prefix + candidate
    value = re.sub(
        r"(?is)(Dispon[ií]vel\s+em:\s*)(.*?)(?=\s*Acesso\s+em:|$)",
        url_field,
        value,
    )
    changed("WRAPPED_URL_REPAIRED", before, value)

    before = value
    # Remove remaining explicit line continuation backslashes, preserving a word boundary.
    value = re.sub(r"\\\s*\r?\n\s*", "", value)
    value = re.sub(r"[\r\n\t]+", " ", value)
    value = re.sub(r"\s{2,}", " ", value).strip()
    changed("WHITESPACE_NORMALIZED", before, value)

    return value, steps
