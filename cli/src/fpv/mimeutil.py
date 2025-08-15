from __future__ import annotations

def ext_from_filename(name: str) -> str:
    import os
    base, ext = os.path.splitext(name)
    return (ext or "").lower().lstrip(".")

def ext_from_mime(mime: str) -> str:
    mime = (mime or "").lower()
    if mime.startswith("image/jpeg"): return "jpg"
    if mime.startswith("image/png"): return "png"
    if mime.startswith("image/webp"): return "webp"
    if mime.startswith("image/heic") or mime.startswith("image/heif"): return "heic"
    if mime.startswith("video/mp4"): return "mp4"
    if mime.startswith("video/quicktime"): return "mov"
    if mime.startswith("video/x-msvideo"): return "avi"
    return ""

def is_video_mime(mime: str) -> bool:
    return (mime or "").lower().startswith("video/")
