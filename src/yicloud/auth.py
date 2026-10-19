import base64
import hashlib
import hmac
from urllib.parse import parse_qsl

from .errors import AuthenticationError


def sign(timestamp, public_key, secret_key, query, body):
    pairs = sorted(parse_qsl(query, keep_blank_values=True), key=lambda item: item[0])
    canonical = "".join(k + v for k, v in pairs)
    message = str(timestamp).encode() + public_key.encode() + canonical.encode() + body
    return hmac.new(secret_key.encode(), message, hashlib.sha256).hexdigest()


def headers(account, timestamp, query, body):
    result = {
        "Content-Type": "application/json",
        "User-Agent": "yicloud-skill/0.1.0",
        "X-OGW-REGION-ID": account.region,
    }
    if account.token:
        result["Authorization"] = account.token
    elif account.public_key and account.secret_key:
        if account.service_account:
            credentials = f"{account.public_key}:{account.secret_key}".encode()
            result["Authorization"] = "Basic " + base64.b64encode(credentials).decode()
        else:
            result.update(
                {
                    "X-OGW-TICK": str(timestamp),
                    "X-OGW-PUBLIC-KEY": account.public_key,
                    "X-OGW-SIGN": sign(
                        timestamp, account.public_key, account.secret_key, query, body
                    ),
                }
            )
    else:
        raise AuthenticationError(
            "Configure a token or complete public/secret key pair using account add"
        )
    return result
