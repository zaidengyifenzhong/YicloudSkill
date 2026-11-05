import re

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


def redact(value, secrets=(), show=False):
    hidden = {secret for secret in secrets if secret}
    if not show:
        hidden.update(secret_values(value))
    # Collect once across the whole response so sibling URLs and messages cannot
    # repeat an identified secret. Longer values must be replaced before prefixes.
    secrets = sorted((secret for secret in hidden if secret), key=len, reverse=True)

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
            for secret in secrets:
                item = item.replace(secret, "[REDACTED]")
            if not show:
                item = re.sub(r"(?i)(Bearer|Basic)\s+[A-Za-z0-9+/=._-]+", r"\1 [REDACTED]", item)
        return item

    return walk(value)


def secret_values(value):
    result = []
    if isinstance(value, dict):
        if sensitive_key(value.get("name", "")) and isinstance(value.get("value"), str):
            result.append(value["value"])
        for key, item in value.items():
            if sensitive_key(key) and isinstance(item, str) and item:
                result.append(item)
            result.extend(secret_values(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            result.extend(secret_values(item))
    return result
