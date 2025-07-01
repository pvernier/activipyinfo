import random
import string


def create_unique_id() -> str:
    """"""
    prefix = "".join(random.choices(string.ascii_lowercase, k=1))
    chain = "".join(random.choices(string.ascii_lowercase + string.digits, k=15))

    unique_id = prefix + chain
    return unique_id
