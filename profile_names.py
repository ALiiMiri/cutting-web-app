import unicodedata


def normalize_profile_name(value):
    """Normalize harmless Unicode and whitespace differences in profile names."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.split())
