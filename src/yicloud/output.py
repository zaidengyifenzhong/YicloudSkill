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
    if isinstance(value, dict):
        if "name" in value and sensitive_key(value["name"]) and "value" in value and not show:
            value = dict(value, value="[REDACTED]")
        return {
            k: ("[REDACTED]" if sensitive_key(k) and not show else redact(v, secrets, show))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v, secrets, show) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        if not show:
            value = re.sub(r"(?i)(Bearer|Basic)\s+[A-Za-z0-9+/=._-]+", r"\1 [REDACTED]", value)
        return value
    return value


def secret_values(value):
    result = []
    if isinstance(value, dict):
        if sensitive_key(value.get("name", "")) and isinstance(value.get("value"), str):
            result.append(value["value"])
        for key, item in value.items():
            if sensitive_key(key) and isinstance(item, str) and item:
                result.append(item)
            result.extend(secret_values(item))
    elif isinstance(value, list):
        for item in value:
            result.extend(secret_values(item))
    return result
