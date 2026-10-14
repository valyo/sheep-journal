"""Ear tag numbers.

A Swedish sheep ear tag reads e.g. SE123456-2023-00051: country, production site
number (PPN), the year the tag was used, and the individual number. The app stores
PPN and individual number separately (without "SE"); the year is kept on the animal.
"""

import re

_TAG_RE = re.compile(r"(?:([A-Z]{2}))?(\d+)-(?:(\d{4})-)?(\d+)")


def parse_tag(text):
    """'SE123456-2023-00051' -> ('123456', 2023, '00051'). None if not a tag number."""
    if not text:
        return None
    match = _TAG_RE.fullmatch(re.sub(r"\s", "", str(text).upper()))
    if not match:
        return None
    country, ppn, year, individual = match.groups()
    if country and country != "SE":
        ppn = country + ppn
    return ppn, int(year) if year else None, individual


def animal_ref(ppn, individual_number):
    """The short reference used for mothers and links: '34567-19011'."""
    return f"{ppn}-{individual_number}"


def tag_label(ppn, individual_number, year=None):
    """The number as printed on the tag: 'SE123456-2023-00051'."""
    prefix = f"SE{ppn}" if ppn.isdigit() else ppn
    middle = f"-{year}" if year else ""
    return f"{prefix}{middle}-{individual_number}"


def normalize_ref(text):
    """Turn whatever was typed for a parent into '34567-19011' if it is a tag number."""
    parsed = parse_tag(text)
    if parsed:
        return animal_ref(parsed[0], parsed[2])
    return text.strip() if text and text.strip() else None
