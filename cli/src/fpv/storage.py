from __future__ import annotations
from typing import Tuple, Optional
from pathlib import Path
import hashlib, os, shutil, time, httpx
from .config import PhotoNestConfig
import datetime
import datetime as _dt
from datetime import timezone

UA = "PhotoNest/0.1 (fpv)"

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def atomic_move(src: Path, dst: Path) -> None:
    ensure_dir(dst.parent)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    shutil.move(str(src), str(tmp))
    os.replace(str(tmp), str(dst))

def sha256_of(path: Path, chunk: int = 1024*1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def download_to_tmp(url: str, tmp_dir: Path, timeout: float = 60.0) -> Tuple[Path, int, str]:
    ensure_dir(tmp_dir)
    name = f"dl_{int(time.time()*1000)}_{os.getpid()}"
    tmp_path = tmp_dir / name
    headers = {"User-Agent": UA}
    with httpx.stream("GET", url, headers=headers, timeout=timeout) as r:
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        with tmp_path.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
        size = tmp_path.stat().st_size
    return tmp_path, size, ctype

def decide_relpath(shot_at_utc: Optional[datetime.datetime], src: str, hash_hex: str, ext: str) -> str:
    dt = shot_at_utc or _dt.datetime.now(timezone.utc)
    y, m, d = dt.year, dt.month, dt.day
    hash8 = hash_hex[:8]
    fname = f"{dt.strftime('%Y%m%d_%H%M%S')}_{src}_{hash8}.{ext}"
    return f"{y:04d}/{m:02d}/{d:02d}/{fname}"
