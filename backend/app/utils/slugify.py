import uuid
import re


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")

    if not text:
        return uuid.uuid4().hex[:8]

    return text
