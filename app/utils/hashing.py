import hashlib
import json
from typing import Any


def sha256_hash(data: Any) -> str:
    if isinstance(data, dict | list):
        raw = json.dumps(data, sort_keys=True, default=str)
    else:
        raw = str(data)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
