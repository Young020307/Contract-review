import os

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BACKEND_DIR, "uploads")
DOC_UPLOAD_DIR = os.path.join(BACKEND_DIR, "temp")


def resolve_path(file_path: str) -> str:
    """Resolve a stored file path to an absolute path.

    Handles both legacy absolute paths and relative paths (uploads/...).
    Normalises platform-specific separators so databases created on one OS
    work when cloned and run on another.
    """
    if os.path.isabs(file_path):
        return file_path
    normalised = file_path.replace("\\", os.sep).replace("/", os.sep)
    return os.path.join(BACKEND_DIR, normalised)


def decode_filename(name: str) -> str:
    """Fix filenames sent with incorrect encoding by the HTTP client.

    Some clients (curl, certain browsers) send non-ASCII filenames as raw
    bytes without proper RFC 5987 encoding. FastAPI/Starlette interprets
    these bytes as latin-1 characters, producing garbled text.
    """
    try:
        raw = name.encode("latin-1")
    except UnicodeEncodeError:
        return name
    for enc in ("gbk", "utf-8"):
        try:
            decoded = raw.decode(enc)
            if decoded != name:
                return decoded
        except UnicodeDecodeError:
            continue
    return name
