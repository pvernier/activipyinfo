import secrets
import string


def create_unique_id() -> str:
    """Create a lower-case alphanumeric client id compatible with API constraints."""
    alphabet = string.ascii_lowercase + string.digits
    prefix = secrets.choice(string.ascii_lowercase)
    chain = "".join(secrets.choice(alphabet) for _ in range(23))

    unique_id = prefix + chain
    return unique_id
