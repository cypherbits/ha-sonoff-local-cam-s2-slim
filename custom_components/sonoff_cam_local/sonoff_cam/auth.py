"""Digest authentication used by the SONOFF CAM-S2 local JSON-RPC service.

The camera protects its RPC methods with an HTTP-Digest-like challenge that is
carried *inside* the JSON-RPC protocol instead of in HTTP headers.

Handshake (reverse-engineered from the device's own web UI bundle, see
``docs/PROTOCOL.md``)::

    -> {"jsonrpc":"2.0","id":2,"method":"System.GetStatus","params":{},"src":"web"}
    <- {"id":2,"error":{"code":401,
            "message":"{\\"auth_type\\":\\"digest\\",\\"nonce\\":\\"6acf...\\",
                        \\"nc\\":1,\\"realm\\":\\"sonoffcams2-aa:bb:cc:..\\",
                        \\"algorithm\\":\\"SHA-256\\"}"}}

The client then answers with::

    auth = {
        "username": "admin",
        "realm": <realm>,
        "nonce": <nonce>,
        "cnonce": <16 random chars>,
        "nc": <nonce count>,
        "response": SHA256(f"{HA1}:{nonce}:{nc}:{cnonce}:auth:{HA2}"),
        "algorithm": "SHA-256",
    }
    HA1 = SHA256("admin:<realm>:<password>")
    HA2 = SHA256("<Service>:<Action>")   # "Motion.GetConfig" -> "Motion:GetConfig"

Every subsequent request repeats the same ``auth`` object with an incremented
``nc`` (nonce count) and a fresh ``cnonce``.
"""

from __future__ import annotations

import hashlib
import json
import random
import string
from dataclasses import dataclass
from typing import Any, Optional

USERNAME = "admin"
DEFAULT_ALGORITHM = "SHA-256"

#: Constant baked into the camera web UI. Its first 32 characters are the AES-256
#: key and its first 16 characters the IV used to protect the `ap_pass` field of
#: ``Sonoff.SetAuth`` / ``Sonoff.ReSetAuth``.
AP_CRYPTO_KEY = "4734126394e66948529a9c7023e0ebf25ffcab5b940834f8322e0ca8928e63bf"

#: Algorithms the device advertises. Only SHA-256 has been observed in the
#: stock firmware; MD5 is kept because the RTSP service uses it.
_HASH_NAMES = {"SHA-256": "sha256", "MD5": "md5", "SHA-1": "sha1"}


def hash_hex(text: str, algorithm: str = DEFAULT_ALGORITHM) -> str:
    """Return the lowercase hex digest of ``text`` using ``algorithm``."""
    name = _HASH_NAMES.get(algorithm.upper(), algorithm.lower().replace("-", ""))
    try:
        digest = hashlib.new(name, text.encode("utf-8"))
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"unsupported hash algorithm: {algorithm!r}") from exc
    return digest.hexdigest()


def compute_ha1(user: str, realm: str, password: str, algorithm: str = DEFAULT_ALGORITHM) -> str:
    """``HA1 = H(user:realm:password)``."""
    return hash_hex(f"{user}:{realm}:{password}", algorithm)


def compute_ha2(method: str, algorithm: str = DEFAULT_ALGORITHM) -> str:
    """``HA2 = H(Service:Action)``.

    The RPC method ``"Motion.GetConfig"`` becomes ``"Motion:GetConfig"``. Methods
    without a dot (rare, used for reset flows) become ``"<method>:"`` so the
    shape stays identical.
    """
    if "." in method:
        service, _, action = method.partition(".")
        canonical = f"{service}:{action}"
    else:
        canonical = f"{method}:"
    return hash_hex(canonical, algorithm)


def random_cnonce(length: int = 16) -> str:
    """Generate a client nonce matching the web UI's alphabet (A-Za-z0-9)."""
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


@dataclass
class AuthChallenge:
    """Parsed digest challenge advertised by the device."""

    nonce: str
    realm: str = ""
    algorithm: str = DEFAULT_ALGORITHM
    auth_type: str = "digest"
    nc: int = 1

    @property
    def ready(self) -> bool:
        """A challenge is usable once a nonce and realm are known."""
        return bool(self.nonce)

    @classmethod
    def from_payload(cls, payload: Any) -> Optional["AuthChallenge"]:
        """Parse a challenge from a dict, or from a JSON string.

        Returns ``None`` when ``payload`` does not look like a challenge.
        """
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return None
        if not isinstance(payload, dict) or "nonce" not in payload:
            return None
        raw_nc = payload.get("nc", 1)
        try:
            nc = int(raw_nc)
        except (TypeError, ValueError):
            nc = 1
        return cls(
            nonce=str(payload["nonce"]),
            realm=str(payload.get("realm") or ""),
            algorithm=str(payload.get("algorithm") or DEFAULT_ALGORITHM),
            auth_type=str(payload.get("auth_type") or "digest"),
            nc=max(nc, 1),
        )


def ap_password(password: str) -> str:
    """Return the ``ap_pass`` blob required by ``Sonoff.SetAuth``.

    Mirrors the web UI: ``AES-256-CBC(JSON.stringify(password))`` with the key
    and IV derived from :data:`AP_CRYPTO_KEY`, Base64-encoded (no salt, PKCS#7).
    Note that ``JSON.stringify`` wraps the password in double quotes, so the
    plaintext includes them.
    """
    import base64
    import json

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "computing ap_pass requires the optional 'cryptography' package"
        ) from exc

    key = AP_CRYPTO_KEY[:32].encode("utf-8")
    iv = AP_CRYPTO_KEY[:16].encode("utf-8")
    padded = PKCS7(128).padder()
    payload = padded.update(json.dumps(password).encode("utf-8")) + padded.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(payload) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("ascii")


def build_auth(
    method: str,
    password: str,
    challenge: AuthChallenge,
    *,
    nc: int,
    user: str = USERNAME,
    realm: Optional[str] = None,
    cnonce: Optional[str] = None,
) -> dict:
    """Build the ``auth`` object that answers a digest challenge.

    ``realm`` defaults to the challenge realm but callers may override it with
    the device id when the challenge omits the realm (the first 401 for
    ``System.GetStatus`` returns an empty realm).
    """
    effective_realm = realm if realm is not None else challenge.realm
    algorithm = challenge.algorithm or DEFAULT_ALGORITHM
    nonce = challenge.nonce
    cnonce = cnonce or random_cnonce()

    ha1 = compute_ha1(user, effective_realm, password, algorithm)
    ha2 = compute_ha2(method, algorithm)
    response = hash_hex(f"{ha1}:{nonce}:{nc}:{cnonce}:auth:{ha2}", algorithm)

    return {
        "username": user,
        "realm": effective_realm,
        "nonce": nonce,
        "cnonce": cnonce,
        "nc": nc,
        "response": response,
        "algorithm": algorithm,
    }
