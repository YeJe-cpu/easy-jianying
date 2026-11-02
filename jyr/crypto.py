"""Encrypt / decrypt draft files with the codec inside the local JianYing.

We compile `jyr_crypt.cpp` once per JianYing binary and cache it under
~/.jyr/bin. The heavy lifting happens in the user's own libvideoeditor.dylib.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from .runtime import CONFIG_DIR, Runtime
from .util import JyrError

SOURCE = Path(__file__).with_name("jyr_crypt.cpp")


def _clean_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("DYLD_")}
    env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    return env


BRIDGE_REV = "2"  # bump when jyr_crypt.cpp changes


def bridge_path(rt: Runtime) -> Path:
    return CONFIG_DIR / "bin" / f"jyr_crypt{BRIDGE_REV}-{platform.machine()}-{rt.dylib_sha256[:12]}"


def ensure_bridge(rt: Runtime) -> Path:
    if rt.is_capcut:
        raise JyrError("CapCut drafts are plaintext; jyr never builds a bridge against CapCut's libraries")
    exe = bridge_path(rt)
    if exe.is_file():
        return exe
    clang = shutil.which("clang++") or "/usr/bin/clang++"
    if not Path(clang).exists():
        raise JyrError("clang++ not found; run `xcode-select --install` once")
    frameworks = rt.dylib.parent
    exe.parent.mkdir(parents=True, exist_ok=True)
    cmd = [clang, "-std=c++17", "-O2", "-arch", platform.machine(), str(SOURCE),
           f"-L{frameworks}", "-lvideoeditor", f"-Wl,-rpath,{frameworks}", "-o", str(exe)]
    out = subprocess.run(cmd, capture_output=True, text=True, env=_clean_env())
    if out.returncode != 0:
        raise JyrError("building the codec bridge failed — the library interface may have changed; "
                       f"run `jyr adapt`.\n{out.stderr[-1500:]}")
    return exe


def _run(rt: Runtime, mode: str, pairs: list[tuple[Path, Path]]) -> list[bool]:
    """Run one bridge process over many files; returns per-file success."""
    exe = ensure_bridge(rt)
    results: list[bool] = []
    for i in range(0, len(pairs), 256):
        chunk = pairs[i : i + 256]
        args = [str(exe), mode]
        for src, dst in chunk:
            args += [str(Path(src).resolve()), str(Path(dst).resolve())]
        out = subprocess.run(args, capture_output=True, text=True, env=_clean_env(), cwd=tempfile.gettempdir())
        if out.returncode == 2:
            raise JyrError(f"bridge usage error: {out.stderr.strip()}")
        failed = {line.split(": ", 1)[1].rsplit(" failed", 1)[0]
                  for line in out.stderr.splitlines() if line.startswith("jyr_crypt: ")}
        results += [str(Path(src).resolve()) not in failed for src, _ in chunk]
    return results


def plain_mode(rt: Runtime) -> bool:
    """Versions whose codec we cannot use (11.7+) get plaintext drafts, which JianYing
    opens and re-encrypts itself on first save."""
    return rt.is_capcut or os.environ.get("JYR_CIPHER") == "plain" or rt.profile.get("cipher") == "plain"


def seal(rt: Runtime, data: bytes) -> bytes:
    return data if plain_mode(rt) else encrypt_bytes(rt, data)


def is_plain_json(data: bytes) -> bool:
    return data.lstrip()[:1] in (b"{", b"[")


def decrypt_bytes(rt: Runtime, data: bytes) -> bytes:
    if is_plain_json(data):
        return data
    if rt.is_capcut:
        raise JyrError("this CapCut file is not plaintext JSON — damaged, or from a CapCut that encrypts drafts "
                       "(jyr does not decrypt CapCut files)")
    with tempfile.TemporaryDirectory(prefix="jyr-") as d:
        src, dst = Path(d, "in"), Path(d, "out")
        src.write_bytes(data)
        if not _run(rt, "dec", [(src, dst)])[0]:
            raise JyrError("cannot decrypt this draft with the codec of JianYing " + rt.version +
                           (" — since 11.7 JianYing keeps the draft key inside the running app, so drafts it "
                            "saved can no longer be read from outside" if plain_mode(rt) else
                            " — the file is damaged or from another install"))
        return dst.read_bytes()


def encrypt_bytes(rt: Runtime, data: bytes) -> bytes:
    with tempfile.TemporaryDirectory(prefix="jyr-") as d:
        src, dst = Path(d, "in"), Path(d, "out")
        src.write_bytes(data)
        if not _run(rt, "enc", [(src, dst)])[0]:
            raise JyrError("encrypt failed")
        out = dst.read_bytes()
    # Never hand back something we cannot read again.
    if decrypt_bytes(rt, out) != data:
        raise JyrError("encrypt round-trip check failed; refusing to write")
    return out


def decrypt_many(rt: Runtime, files: list[Path], out_dir: Path) -> dict[Path, Path | None]:
    """Decrypt many files in one process (loading the library once)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[Path, Path | None] = {}
    todo: list[tuple[Path, Path]] = []
    for n, f in enumerate(files):
        dst = out_dir / f"{n}.json"
        raw = Path(f).read_bytes()
        if is_plain_json(raw):
            dst.write_bytes(raw)
            result[f] = dst
        else:
            todo.append((Path(f), dst))
    if rt.is_capcut:
        result.update({src: None for src, _ in todo})
        return result
    for (src, dst), ok in zip(todo, _run(rt, "dec", todo) if todo else []):
        result[src] = dst if ok else None
    return result
