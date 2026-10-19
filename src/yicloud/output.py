import re

# Match nested API fields, including newly issued credentials. Known values are removed from strings.
SENSITIVE = re.compile(
    r"secret|token|password|credential|authorization|private.?key|public.?key|access.?key|signature|_ogw_sign",
    re.IGNORECASE,
)


def redact(value, secrets=(), show=False):
    if isinstance(value, dict):
        if (
            "name" in value
            and SENSITIVE.search(str(value["name"]))
            and "value" in value
            and not show
        ):
            value = dict(value, value="[REDACTED]")
        return {
            k: ("[REDACTED]" if SENSITIVE.search(str(k)) and not show else redact(v, secrets, show))
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
        for key, item in value.items():
            if SENSITIVE.search(str(key)) and isinstance(item, str) and item:
                result.append(item)
            result.extend(secret_values(item))
    elif isinstance(value, list):
        for item in value:
            result.extend(secret_values(item))
    return result
