"""Client-side id generation.

ActivityInfo expects clients to generate the ids of new databases, folders,
forms, fields and records. Its documentation recommends CUID2
(https://github.com/paralleldrive/cuid2); this module is a dependency-free
port of that algorithm.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import socket
import string
import threading
import time

__all__ = ["cuid", "is_cuid"]

DEFAULT_LENGTH = 24
_ALPHABET = string.digits + string.ascii_lowercase
_BIG_LENGTH = 32
_INITIAL_COUNT_MAX = 476_782_367


def _to_base36(number: int) -> str:
    if number == 0:
        return "0"
    digits = []
    while number:
        number, remainder = divmod(number, 36)
        digits.append(_ALPHABET[remainder])
    return "".join(reversed(digits))


def _entropy(length: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def _hash(value: str) -> str:
    digest = hashlib.sha3_512(value.encode()).digest()
    # Drop the first character, which is biased (as in the reference implementation).
    return _to_base36(int.from_bytes(digest, "big"))[1:]


def _fingerprint() -> str:
    try:
        host = socket.gethostname()
    except OSError:
        host = ""
    return _hash(f"{host}{os.getpid()}{_entropy(_BIG_LENGTH)}")[:_BIG_LENGTH]


class _Counter:
    def __init__(self) -> None:
        self._value = secrets.randbelow(_INITIAL_COUNT_MAX)
        self._lock = threading.Lock()

    def next(self) -> int:
        with self._lock:
            self._value += 1
            return self._value


_counter = _Counter()
_FINGERPRINT = _fingerprint()


def cuid(length: int = DEFAULT_LENGTH) -> str:
    """Return a new collision-resistant id (CUID2).

    The id starts with a lower-case letter followed by lower-case letters and
    digits, which is the format ActivityInfo accepts for client-generated ids.
    """
    if not 2 <= length <= _BIG_LENGTH:
        raise ValueError(f"length must be between 2 and {_BIG_LENGTH}")

    timestamp = _to_base36(time.time_ns() // 1_000_000)
    count = _to_base36(_counter.next())
    hash_input = f"{timestamp}{_entropy(length)}{count}{_FINGERPRINT}"
    return secrets.choice(string.ascii_lowercase) + _hash(hash_input)[1:length]


def is_cuid(value: object, min_length: int = 2, max_length: int = _BIG_LENGTH) -> bool:
    """Return True if ``value`` looks like a CUID (lower-case, starts with a letter)."""
    return (
        isinstance(value, str)
        and min_length <= len(value) <= max_length
        and value[0] in string.ascii_lowercase
        and all(c in _ALPHABET for c in value)
    )
