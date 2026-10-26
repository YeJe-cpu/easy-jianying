"""Find the local JianYing install and describe it.

Everything here is read-only. Version knowledge is a small table of what we
observed ourselves; `jyr adapt` extends it for versions we have not seen.
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .util import JyrError

APP_CANDIDATES = [
    "/Applications/VideoFusion-macOS.app",
    "/Applications/JianyingPro.app",
    str(Path.home() / "Applications/VideoFusion-macOS.app"),
]
BUNDLE_ID = "com.lemon.lvpro"
USER_DATA = Path.home() / "Movies/JianyingPro/User Data"
CONFIG_DIR = Path(os.environ.get("JYR_HOME", Path.home() / ".jyr"))

# app version -> what that version itself writes as draft_info.new_version.
# Observed from drafts saved by each version on our machines.
KNOWN_VERSIONS: dict[str, dict] = {
    "11.6.0": {"timeline_version": "189.0.0", "dylib_sha256": "a490d9a08b71a2d9af138d24528d3d40d65b37b06911627c53a2915c6cac0754"},
    "11.5.0": {"timeline_version": "187.0.0"},
}
DRAFT_FORMAT_VERSION = 360000


@dataclass
class Runtime:
    app_path: Path
    version: str
    build: str
    dylib: Path
    dylib_sha256: str
    draft_root: Path
    cache_root: Path
    profile: dict = field(default_factory=dict)

    @property
    def timeline_version(self) -> str:
        return self.profile.get("timeline_version", "")

    @property
    def known(self) -> bool:
        return bool(self.profile)


def _user_profiles() -> dict:
    p = CONFIG_DIR / "profiles.json"
    if p.is_file():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def save_user_profile(version: str, profile: dict) -> Path:
    data = _user_profiles()
    data[version] = profile
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    p = CONFIG_DIR / "profiles.json"
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return p


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_app() -> Path:
    env = os.environ.get("JYR_APP")
    for cand in ([env] if env else []) + APP_CANDIDATES:
        p = Path(cand)
        if (p / "Contents/Frameworks/libvideoeditor.dylib").is_file():
            return p
    raise JyrError("JianYing desktop (剪映专业版) not found in /Applications; set JYR_APP to the .app path")


def detect() -> Runtime:
    app = find_app()
    with open(app / "Contents/Info.plist", "rb") as f:
        plist = plistlib.load(f)
    if plist.get("CFBundleIdentifier") != BUNDLE_ID:
        raise JyrError(f"{app} is not JianYing ({plist.get('CFBundleIdentifier')})")
    version = plist.get("CFBundleShortVersionString", "")
    dylib = app / "Contents/Frameworks/libvideoeditor.dylib"
    sha = sha256_file(dylib)
    draft_root = Path(os.environ.get("JYR_DRAFT_ROOT", USER_DATA / "Projects/com.lveditor.draft"))
    profile = dict(KNOWN_VERSIONS.get(version, {}))
    profile.update(_user_profiles().get(version, {}))
    if profile.get("dylib_sha256") and profile["dylib_sha256"] != sha:
        # Same version string, different binary: treat as unknown.
        profile = {}
    return Runtime(app, version, str(plist.get("CFBundleVersion", "")), dylib, sha, draft_root, USER_DATA / "Cache", profile)


def jianying_running() -> bool:
    out = subprocess.run(["pgrep", "-x", "VideoFusion-macOS"], capture_output=True)
    return out.returncode == 0


def require_known(rt: Runtime) -> None:
    if not rt.known:
        raise JyrError(
            f"JianYing {rt.version} has not been adapted yet. Run `jyr adapt` "
            "(it checks the codec and learns the draft schema from a draft this version saved)."
        )
