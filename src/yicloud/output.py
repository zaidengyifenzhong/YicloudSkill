import re
from urllib.parse import quote, quote_plus

# Normalize credential keys, but do not hide token counts, tokenizers or metrics.
SENSITIVE = re.compile(
    r"(?:secret|password|passwd|credential|authorization|privatekey|publickey|accesskey|signature)",
    re.IGNORECASE,
)


def sensitive_key(key):
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    return (
        bool(SENSITIVE.search(normalized))
        or normalized.endswith("token")
        or normalized in {"apikey", "ogwsign", "xogwsign"}
    )


def _secret_pattern(secrets):
    patterns = {}
    for secret in secrets:
        values = {secret}
        authorization = re.fullmatch(r"(?:Bearer|Basic)\s+(\S+)", secret, re.IGNORECASE)
        if authorization:
            values.add(authorization[1])
        for value in values:
            patterns[re.escape(value)] = len(value)
            for encoded in {quote(value), quote(value, safe=""), quote_plus(value)}:
                # Only percent-escape hex digits are case insensitive. Credential
                # letters outside escapes must retain their exact case.
                pattern = re.sub(
                    r"%[0-9A-F]{2}",
                    lambda match: (
                        "%"
                        + "".join(f"[{c.lower()}{c}]" if c in "ABCDEF" else c for c in match[0][1:])
                    ),
                    re.escape(encoded),
                )
                patterns[pattern] = len(encoded)
    return (
        re.compile("|".join(sorted(patterns, key=patterns.get, reverse=True))) if patterns else None
    )


def redact(value, secrets=(), show=False):
    hidden = {secret for secret in secrets if secret}
    if not show:
        hidden.update(secret_values(value))
    # Collect once across the whole response so sibling URLs and messages cannot
    # repeat an identified secret. Longer values must be replaced before prefixes.
    pattern = _secret_pattern(secret for secret in hidden if secret)

    def walk(item):
        if isinstance(item, dict):
            if "name" in item and sensitive_key(item["name"]) and "value" in item and not show:
                item = dict(item, value="[REDACTED]")
            return {
                k: ("[REDACTED]" if sensitive_key(k) and not show else walk(v))
                for k, v in item.items()
            }
        if isinstance(item, (list, tuple)):
            return [walk(v) for v in item]
        if isinstance(item, str):
            if pattern:
                item = pattern.sub("[REDACTED]", item)
            if not show:
                item = re.sub(r"(?i)(Bearer|Basic)\s+[A-Za-z0-9+/=._-]+", r"\1 [REDACTED]", item)
        return item

    return walk(value)


def secret_values(value):
    result = []

    def visit(item, *, sensitive=False, leaf=False):
        if isinstance(item, dict):
            named_secret = sensitive_key(item.get("name", ""))
            for key, child in item.items():
                credential = sensitive_key(key)
                value_field = str(key).lower() == "value" and (sensitive or named_secret)
                visit(
                    child,
                    sensitive=sensitive or credential or value_field,
                    leaf=credential or value_field,
                )
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child, sensitive=sensitive, leaf=leaf)
        elif isinstance(item, str) and item and leaf:
            result.append(item)

    visit(value)
    return result
