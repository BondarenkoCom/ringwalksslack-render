import re


def normalize_text(text):
    return " ".join((text or "").lower().split())


def quote_term(term):
    clean = (term or "").strip().replace('"', '\\"')
    if " " in clean:
        return f'"{clean}"'
    return clean


def build_query(settings):
    matcher = settings["matcher"]
    timing = [quote_term(x) for x in matcher["timing_phrases"] if x.strip()]
    targets = [quote_term(x) for x in matcher["fighter_names"] + matcher["target_terms"] if x.strip()]
    parts = []
    if timing:
        parts.append(f"({' OR '.join(timing)})")
    if targets:
        parts.append(f"({' OR '.join(targets)})")
    if settings["search"].get("ignore_retweets", True):
        parts.append("-is:retweet")
    if settings["search"].get("ignore_replies"):
        parts.append("-is:reply")
    language = settings["search"].get("language", "").strip()
    if language:
        parts.append(f"lang:{language}")
    return " ".join(parts)


def matches_tweet(text, settings):
    body = normalize_text(text)
    matcher = settings["matcher"]
    has_timing = any(has_phrase(body, x) for x in matcher["timing_phrases"])
    has_target = any(has_phrase(body, x) for x in matcher["fighter_names"] + matcher["target_terms"])
    return has_timing and has_target


def build_tweet_url(tweet_id):
    return f"https://x.com/i/web/status/{tweet_id}"


def has_phrase(body, phrase):
    value = normalize_text(phrase)
    pattern = r"(?<!\w)" + re.escape(value).replace(r"\ ", r"\s+") + r"(?!\w)"
    return re.search(pattern, body) is not None
