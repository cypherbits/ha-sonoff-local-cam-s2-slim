"""Redaction helpers for dumps of the camera's readable surface.

Several ``Get*`` methods hand back secrets to any authenticated caller: the
device returns the RTSP password inside ``Onvif.GetConfig`` (both as its own
field and embedded in the ``rtsp_hd`` URL) and the AP hotspot password inside
``WiFi.GetConfig``. Anything captured from the device therefore has to be
sanitised before it is written to a file that may be shared.

Two things are handled:

* **sensitive keys** -- ``password``, ``pass``, ``token``, ... are replaced
  wherever they appear, at any nesting depth;
* **inline URL credentials** -- ``rtsp://user:secret@host/path`` is rewritten to
  ``rtsp://user:***REDACTED***@host/path`` inside *any* string value, because
  the camera hands back ready-made connection URLs.

Personal data (the Wi-Fi ``ssid``/``bssid``) is redacted too, and non-secret
values are left untouched so the result stays useful.
"""

from __future__ import annotations

import re
from typing import Any, Dict

#: Placeholder written in place of a secret.
PLACEHOLDER = "***REDACTED***"

#: Keys whose values are credentials and must never be written out. Matching is
#: case-insensitive on the whole key name.
SENSITIVE_KEYS = frozenset(
    {
        "password",
        "pass",
        "passwd",
        "pwd",
        "ha1",
        "ap_pass",
        "token",
        "secret",
        "credential",
        "credentials",
    }
)

#: Keys that identify the owner's network (personal data rather than a secret).
#: Redacted by default so a captured dump does not carry someone's SSID around.
PERSONAL_KEYS = frozenset({"ssid", "bssid"})

#: What :func:`redact` replaces unless the caller passes its own ``keys``.
DEFAULT_KEYS = SENSITIVE_KEYS | PERSONAL_KEYS

#: ``scheme://user:password@`` -- the password group is replaced.
_URL_CREDENTIALS_RE = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)"
    r"(?P<user>[^:/@\s]+):(?P<secret>[^@/\s]+)@"
)


def redact_url_credentials(text: str, placeholder: str = PLACEHOLDER) -> str:
    """Scrub ``scheme://user:password@host`` credentials out of ``text``."""
    return _URL_CREDENTIALS_RE.sub(
        lambda m: f"{m.group('scheme')}{m.group('user')}:{placeholder}@", text
    )


def redact_text(text: str, placeholder: str = PLACEHOLDER) -> str:
    """Scrub every secret this module knows how to find out of a string."""
    return redact_url_credentials(text, placeholder)


def redact(
    value: Any,
    *,
    placeholder: str = PLACEHOLDER,
    keys: frozenset = DEFAULT_KEYS,
) -> Any:
    """Return a copy of ``value`` with credentials replaced.

    Works on dicts, lists/tuples and strings; everything else is returned as is.
    Dict keys are matched case-insensitively against ``keys`` (by default both
    :data:`SENSITIVE_KEYS` and :data:`PERSONAL_KEYS`). A key whose value is
    already ``None`` is left alone -- there is no secret to hide, and keeping the
    null preserves what the device actually reported.
    """
    if isinstance(value, dict):
        redacted: Dict[Any, Any] = {}
        for key, item in value.items():
            name = key.strip().lower() if isinstance(key, str) else key
            if name in keys and item is not None:
                redacted[key] = placeholder
            else:
                redacted[key] = redact(item, placeholder=placeholder, keys=keys)
        return redacted
    if isinstance(value, (list, tuple)):
        return [redact(item, placeholder=placeholder, keys=keys) for item in value]
    if isinstance(value, str):
        return redact_text(value, placeholder)
    return value
