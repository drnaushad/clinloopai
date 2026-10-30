"""Small bounded transport primitives; never include source payloads in failures."""
import ipaddress
import json
from urllib.parse import urlsplit


def origin(url: str) -> tuple:
    """An HTTP origin without embedded credentials, fragments or control characters."""
    if not isinstance(url, str) or any(ord(c) < 33 or ord(c) == 127 for c in url):
        raise ValueError("Invalid service endpoint")
    parsed = urlsplit(url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None or parsed.fragment):
        raise ValueError("Invalid service endpoint")
    return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == "https" else 80)


def secure_endpoint(url: str) -> str:
    """HTTPS for identifiable outbound content; HTTP only for loopback tests."""
    scheme, host, _ = origin(url)
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host == "localhost"
    if scheme != "https" and not loopback:
        raise ValueError("Service endpoint must use HTTPS; HTTP is limited to loopback testing")
    return url


def bounded_json(response, max_bytes: int):
    """Consume streamed JSON up to an explicit decompressed byte budget."""
    raw = bytearray()
    for chunk in response.iter_content(8192):
        raw.extend(chunk)
        if len(raw) > max_bytes:
            raise ValueError("Service response exceeds the size limit")
    return json.loads(raw)
