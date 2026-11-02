"""Find the local JianYing / CapCut install and describe it.

Everything here is read-only. Version knowledge is a small table of what we
observed ourselves; `jyr adapt` extends it for versions we have not seen.

Two apps share one draft format: JianYing (剪映专业版) and CapCut (its
international edition). For CapCut we only read and write the plaintext draft
files — no library of the app is linked or called, and its UI is never driven.
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

CONFIG_DIR = Path(os.environ.get("JYR_HOME", Path.home() / ".jyr"))

# app version -> what that version itself writes as draft_info.new_version.
# Observed from drafts saved by each version on our machines.
# "cipher": "plain" = from 11.7 the draft key lives inside the running app; we write
# plaintext drafts (JianYing encrypts them on first save) and cannot read its drafts.
KNOWN_VERSIONS: dict[str, dict] = {
    "11.7.0": {"timeline_version": "189.0.0", "cipher": "plain",
               "dylib_sha256": "c2c9bc704f4aef03b069838bcaded39cc6b0a5ec72cf9ff7a8ee854bed3391b2"},
    "11.6.0": {"timeline_version": "189.0.0", "dylib_sha256": "a490d9a08b71a2d9af138d24528d3d40d65b37b06911627c53a2915c6cac0754"},
    "11.5.0": {"timeline_version": "187.0.0"},
}
# CapCut drafts are plaintext JSON; the app never encrypts them.
CAPCUT_VERSIONS: dict[str, dict] = {
    "9.4.1": {"timeline_version": "185.0.0", "cipher": "plain"},
}
DRAFT_FORMAT_VERSION = 360000


@dataclass(frozen=True)
class App:
    """One of the editors that read this draft format."""
    key: str             # "jianying" | "capcut"
    label: str
    bundle_id: str
    candidates: tuple
    user_data: Path
    process: str         # exact process name, for "is it running?"
    app_id: int          # draft_info.platform.app_id the app itself writes
    app_source: str      # draft_info.platform.app_source
    known_versions: dict
    preset_category: str  # how the app names its own preset fonts in drafts

    @property
    def draft_root(self) -> Path:
        return self.user_data / "Projects/com.lveditor.draft"


JIANYING = App("jianying", "JianYing 剪映专业版", "com.lemon.lvpro",
               ("/Applications/VideoFusion-macOS.app", "/Applications/JianyingPro.app",
                str(Path.home() / "Applications/VideoFusion-macOS.app")),
               Path.home() / "Movies/JianyingPro/User Data", "VideoFusion-macOS", 3704, "lv",
               KNOWN_VERSIONS, "剪映预设")
CAPCUT = App("capcut", "CapCut", "com.lemon.lvoverseas",
             ("/Applications/CapCut.app", str(Path.home() / "Applications/CapCut.app")),
             Path.home() / "Movies/CapCut/User Data", "CapCut", 359289, "cc",
             CAPCUT_VERSIONS, "CapCut预设")
APPS = {a.key: a for a in (JIANYING, CAPCUT)}
BY_BUNDLE = {a.bundle_id: a for a in APPS.values()}

# Kept for callers that predate CapCut support.
APP_CANDIDATES = list(JIANYING.candidates)
BUNDLE_ID = JIANYING.bundle_id
USER_DATA = JIANYING.user_data


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
    app: App = JIANYING

    @property
    def timeline_version(self) -> str:
        return self.profile.get("timeline_version", "")

    @property
    def known(self) -> bool:
        return bool(self.profile)

    @property
    def is_capcut(self) -> bool:
        return self.app.key == "capcut"

    @property
    def platform(self) -> dict:
        """What the app itself writes as draft_info.platform."""
        return {"os": "mac", "app_id": self.app.app_id, "app_version": self.version,
                "app_source": self.app.app_source}


def _profile_key(version: str, app: App) -> str:
    return version if app is JIANYING else f"{app.key}:{version}"


def _user_profiles() -> dict:
    p = CONFIG_DIR / "profiles.json"
    if p.is_file():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def save_user_profile(version: str, profile: dict, app: App = JIANYING) -> Path:
    data = _user_profiles()
    data[_profile_key(version, app)] = profile
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


def _installed(app: App) -> Path | None:
    for cand in app.candidates:
        p = Path(cand)
        if _bundle_id(p) == app.bundle_id:
            return p
    return None


def _bundle_id(app_path: Path) -> str:
    try:
        with open(Path(app_path) / "Contents/Info.plist", "rb") as f:
            return plistlib.load(f).get("CFBundleIdentifier", "")
    except (OSError, plistlib.InvalidFileException):
        return ""


def choose_app(name: str | None = None) -> tuple[App, Path]:
    """Which editor to target: --app / JYR_TARGET, else the one JYR_APP points at, else
    the only one installed; with both installed, JianYing (as before CapCut support)."""
    name = (name or os.environ.get("JYR_TARGET") or "auto").lower()
    env = os.environ.get("JYR_APP")
    if env:
        app = BY_BUNDLE.get(_bundle_id(Path(env)))
        if app is None:
            raise JyrError(f"JYR_APP={env} is neither JianYing nor CapCut")
        if name != "auto" and name != app.key:
            raise JyrError(f"JYR_APP points at {app.label}, but --app {name} was asked for")
        return app, Path(env)
    if name != "auto":
        if name not in APPS:
            raise JyrError(f"--app must be one of {sorted(APPS)} or auto, got {name!r}")
        app = APPS[name]
        path = _installed(app)
        if path is None:
            raise JyrError(f"{app.label} not found in /Applications; set JYR_APP to the .app path")
        return app, path
    found = [(a, p) for a in (JIANYING, CAPCUT) if (p := _installed(a))]
    if not found:
        raise JyrError("neither JianYing (剪映专业版) nor CapCut found in /Applications; set JYR_APP to the .app path")
    return found[0]


def find_app(app: App = JIANYING) -> Path:
    env = os.environ.get("JYR_APP")
    if env and _bundle_id(Path(env)) == app.bundle_id:
        return Path(env)
    p = _installed(app)
    if p is None:
        raise JyrError(f"{app.label} not found in /Applications; set JYR_APP to the .app path")
    return p


def _version_from_drafts(app: App, version: str, draft_root: Path, limit: int = 60) -> str:
    """Highest timeline schema (new_version) among drafts this exact app version saved.
    Only for apps whose drafts are plaintext (CapCut)."""
    files = sorted(draft_root.glob("*/draft_info.json"), key=lambda p: -p.stat().st_mtime)[:limit]
    found = []
    for f in files:
        try:
            info = json.loads(f.read_bytes())
        except (OSError, ValueError):
            continue
        plat = info.get("last_modified_platform") or {}
        if plat.get("app_version") == version and plat.get("app_source") == app.app_source and info.get("new_version"):
            found.append(info["new_version"])
    if not found:
        return ""
    return max(found, key=lambda v: [int(x) for x in v.split(".") if x.isdigit()])


def detect(app_name: str | None = None) -> Runtime:
    app, path = choose_app(app_name)
    with open(path / "Contents/Info.plist", "rb") as f:
        plist = plistlib.load(f)
    version = plist.get("CFBundleShortVersionString", "")
    build = str(plist.get("CFBundleVersion", ""))
    draft_root = Path(os.environ.get("JYR_DRAFT_ROOT", app.draft_root))
    builtin = {} if os.environ.get("JYR_NO_BUILTIN_PROFILES") else app.known_versions
    profile = dict(builtin.get(version, {}))
    profile.update(_user_profiles().get(_profile_key(version, app), {}))
    dylib = path / "Contents/Frameworks/libvideoeditor.dylib"
    if app is CAPCUT:
        # Never hashed, linked or loaded: CapCut is handled through its plaintext files only.
        sha = ""
        profile["cipher"] = "plain"
        if not profile.get("timeline_version"):
            tv = _version_from_drafts(app, version, draft_root)
            if tv:
                profile.update({"timeline_version": tv, "learned_from": "drafts"})
            else:
                profile = {}
        return Runtime(path, version, build, dylib, sha, draft_root, app.user_data / "Cache", profile, app)
    if not dylib.is_file():
        raise JyrError(f"{path} has no libvideoeditor.dylib; is this really JianYing?")
    sha = sha256_file(dylib)
    if profile.get("dylib_sha256") and profile["dylib_sha256"] != sha:
        # Same version string, different binary: treat as unknown.
        profile = {}
    return Runtime(path, version, build, dylib, sha, draft_root, app.user_data / "Cache", profile, app)


def app_running(app: App | Runtime = JIANYING) -> bool:
    if isinstance(app, Runtime):
        app = app.app
    out = subprocess.run(["pgrep", "-x", app.process], capture_output=True)
    return out.returncode == 0


def jianying_running() -> bool:
    return app_running(JIANYING)


def quit_hint(rt: Runtime) -> str:
    return f"{rt.app.label} is running. Quit it completely (⌘Q) first — it rewrites the index on exit."


def require_known(rt: Runtime) -> None:
    if not rt.known and rt.is_capcut:
        raise JyrError(
            f"CapCut {rt.version} has not been seen yet and no draft it saved was found. Open CapCut, "
            "create a blank project, quit, then run `jyr --app capcut adapt`."
        )
    if not rt.known:
        raise JyrError(
            f"JianYing {rt.version} has not been adapted yet. Run `jyr adapt` "
            "(it checks the codec and learns the draft schema from a draft this version saved)."
        )
