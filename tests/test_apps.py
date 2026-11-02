"""App / file / resource tests: fake app bundles and draft folders, no JianYing or CapCut needed.

Checks that drafts are plain JSON files with each app's own platform / timeline
schema, that only plain JSON is ever read, and that paid resources are flagged
and kept out of the built-in packs.

run: python3 -m unittest discover -s tests
"""

import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jyr import adapt, catalog, files, home, plan as planmod, reader, runtime, writer
from jyr.catalog import Catalog
from jyr.util import JyrError

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="jyr-capcut-test-"))


def fake_app(name: str, bundle_id: str, version: str) -> Path:
    app = TMP / "apps" / name
    (app / "Contents").mkdir(parents=True, exist_ok=True)
    with open(app / "Contents/Info.plist", "wb") as f:
        plistlib.dump({"CFBundleIdentifier": bundle_id, "CFBundleShortVersionString": version,
                       "CFBundleVersion": version}, f)
    return app


def saved_draft(root: Path, name: str, version: str, new_version: str, key_value: dict | None = None,
                materials: dict | None = None) -> Path:
    d = root / name
    d.mkdir(parents=True)
    plat = {"os": "mac", "app_id": 359289, "app_version": version, "app_source": "cc"}
    info = {"id": "T-" + name, "version": 360000, "new_version": new_version, "tracks": [],
            "materials": materials or {}, "platform": plat, "last_modified_platform": plat}
    (d / "draft_info.json").write_text(json.dumps(info, ensure_ascii=False))
    (d / "key_value.json").write_text(json.dumps(key_value or {}, ensure_ascii=False))
    return d


def kv(rid: str, vip: str, category: str = "trans") -> dict:
    return {rid: {"materialId": rid, "is_vip": vip, "materialCategory": category,
                  "materialSubcategory": "transition_effect"}}


def setUpModule():
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=4",
                    "-f", "lavfi", "-i", "sine=duration=4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(TMP / "a.mp4")], check=True)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def capcut_rt(draft_root: Path, version: str = "9.4.1", profile: dict | None = None) -> runtime.Runtime:
    app = fake_app(f"CapCut-{version}.app", "com.lemon.lvoverseas", version)
    return runtime.Runtime(app, version, version, draft_root, draft_root,
                           {"timeline_version": "185.0.0"} if profile is None else profile, runtime.CAPCUT)


def jianying_rt(draft_root: Path) -> runtime.Runtime:
    app = fake_app("VideoFusion-macOS.app", "com.lemon.lvpro", "11.7.0")
    return runtime.Runtime(app, "11.7.0", "11.7.0", draft_root, draft_root, {"timeline_version": "189.0.0"})


class ChooseAppTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for k in ("JYR_APP", "JYR_TARGET", "JYR_DRAFT_ROOT", "JYR_HOME"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.env.stop()

    def test_jyr_app_bundle_id_decides_and_conflicting_target_is_refused(self):
        os.environ["JYR_APP"] = str(fake_app("CapCut.app", "com.lemon.lvoverseas", "9.4.1"))
        app, _ = runtime.choose_app()
        self.assertIs(app, runtime.CAPCUT)
        with self.assertRaisesRegex(JyrError, "points at CapCut"):
            runtime.choose_app("jianying")
        os.environ["JYR_APP"] = str(fake_app("Other.app", "com.example.other", "1.0"))
        with self.assertRaisesRegex(JyrError, "neither"):
            runtime.choose_app()

    def test_only_one_installed_is_picked_both_installed_defaults_to_jianying(self):
        cc = fake_app("CapCut.app", "com.lemon.lvoverseas", "9.4.1")
        jy = fake_app("VideoFusion-macOS.app", "com.lemon.lvpro", "11.7.0")
        only_cc = mock.patch.object(runtime, "_installed", lambda a: cc if a is runtime.CAPCUT else None)
        with only_cc:
            self.assertIs(runtime.choose_app()[0], runtime.CAPCUT)
            with self.assertRaisesRegex(JyrError, "not found"):
                runtime.choose_app("jianying")
        both = mock.patch.object(runtime, "_installed", lambda a: cc if a is runtime.CAPCUT else jy)
        with both:
            self.assertIs(runtime.choose_app()[0], runtime.JIANYING)
            os.environ["JYR_TARGET"] = "capcut"
            self.assertIs(runtime.choose_app()[0], runtime.CAPCUT)

    def test_capcut_detect_learns_unknown_versions_from_its_drafts(self):
        root = TMP / "detect-root"
        saved_draft(root, "a", "9.9.0", "186.0.0")
        saved_draft(root, "b", "9.9.0", "185.5.0")
        saved_draft(root, "old", "9.4.1", "190.0.0")  # another version's schema must not count
        os.environ.update({"JYR_APP": str(fake_app("CapCut-9.9.app", "com.lemon.lvoverseas", "9.9.0")),
                           "JYR_DRAFT_ROOT": str(root), "JYR_HOME": str(TMP / "home")})
        with mock.patch.object(runtime, "CONFIG_DIR", TMP / "home"):
            rt = runtime.detect()
        self.assertTrue(rt.is_capcut)
        self.assertEqual(rt.timeline_version, "186.0.0")
        self.assertEqual(rt.platform["app_source"], "cc")
        self.assertEqual(rt.platform["app_id"], 359289)

    def test_unknown_capcut_without_samples_asks_for_one(self):
        rt = capcut_rt(TMP / "empty-root", "9.9.1", profile={})
        with self.assertRaisesRegex(JyrError, "blank project"):
            runtime.require_known(rt)


class CapCutDraftTests(unittest.TestCase):
    def test_build_writes_plaintext_capcut_draft_and_reads_it_back(self):
        root = TMP / "build-root"
        root.mkdir()
        rt = capcut_rt(root)
        cat = Catalog({"entries": [{"kind": "transition", "name": "叠化", "resource_id": "1", "path": "/x",
                                    "available": True, "seen": 1, "vip": False, "template": {"name": "叠化"}}]})
        p = {"name": "cc", "tracks": [{"type": "video", "clips": [
            {"src": str(TMP / "a.mp4"), "duration": 2, "transition": "叠化"}, {"src": str(TMP / "a.mp4"), "duration": 2}]},
            {"type": "subtitle", "clips": [{"text": "你好 CapCut", "duration": 2}]}]}
        d = planmod.Compiler(rt, cat).compile(p)
        out = writer.write(rt, d, TMP / "build-out")
        raw = (out / "draft_info.json").read_bytes()
        self.assertTrue(files.is_plain_json(raw))
        info = json.loads(raw)
        self.assertEqual(info["new_version"], "185.0.0")
        self.assertEqual(info["platform"], rt.platform)
        self.assertEqual(json.loads((out / ".jyr.json").read_text())["app"], "capcut")
        self.assertEqual(writer.read_info(rt, out)["id"], info["id"])
        r = reader.inspect(rt, out)
        self.assertEqual(r["timeline_version"], "185.0.0")
        self.assertIn("你好 CapCut", reader.srt_text(rt, out))

    def test_jianying_drafts_are_plain_json_and_its_own_saves_are_not_read(self):
        rt = jianying_rt(TMP / "jy-root")
        d = planmod.Compiler(rt, Catalog({"entries": []})).compile(
            {"name": "jy", "tracks": [{"type": "video", "clips": [{"src": str(TMP / "a.mp4"), "duration": 1}]}]})
        out = writer.write(rt, d, TMP / "jy-out")
        for f in ("draft_info.json", "draft_meta_info.json", f"Timelines/{d.id}/draft_info.json"):
            self.assertTrue(files.is_plain_json((out / f).read_bytes()), f)
        info = json.loads((out / "draft_info.json").read_bytes())
        self.assertEqual((info["platform"]["app_id"], info["platform"]["app_source"], info["new_version"]),
                         (3704, "lv", "189.0.0"))
        (out / "draft_info.json").write_bytes(b"\x00\x01saved by the app")
        with self.assertRaisesRegex(JyrError, "does not read"):
            reader.inspect(rt, out)
        with self.assertRaisesRegex(JyrError, "not plain JSON"):
            files.read_json(capcut_rt(TMP / "x"), out / "draft_info.json")

    def test_adapt_unknown_jianying_assumes_newest_known_schema(self):
        os.environ.pop("JYR_TARGET", None)
        rt = runtime.Runtime(Path("/x.app"), "12.0.0", "12.0.0", TMP, TMP, {})
        with mock.patch.object(runtime, "detect", return_value=rt), \
             mock.patch.object(runtime, "CONFIG_DIR", TMP / "adapt-home"):
            rep = adapt.adapt()
            saved = json.loads((TMP / "adapt-home/profiles.json").read_text())
        self.assertEqual(rep["timeline_version"], "189.0.0")
        self.assertTrue(saved["12.0.0"]["assumed"])

    def test_publish_registers_on_capcut_home_and_refuses_a_jianying_build(self):
        root = TMP / "home-root"
        root.mkdir()
        (root / "root_meta_info.json").write_text(json.dumps({"all_draft_store": [], "draft_ids": 0,
                                                              "root_path": str(root)}))
        rt = capcut_rt(root)
        d = planmod.Compiler(rt, Catalog({"entries": []})).compile(
            {"name": "主页测试", "tracks": [{"type": "video", "clips": [{"src": str(TMP / "a.mp4"), "duration": 1}]}]})
        built = writer.write(rt, d, TMP / "home-built")
        with mock.patch.object(home, "app_running", return_value=False), \
             mock.patch.object(home, "CONFIG_DIR", TMP / "home-cfg"):
            res = home.publish(rt, built, "主页测试")
            idx = json.loads((root / "root_meta_info.json").read_text())
            self.assertEqual(idx["all_draft_store"][0]["draft_fold_path"], res["folder"])
            self.assertTrue(Path(res["index_backup"]).name.startswith("capcut-"))
            meta = writer.read_meta(rt, Path(res["folder"]))
            self.assertEqual(meta["draft_root_path"], str(root))
            j = json.loads((built / ".jyr.json").read_text())
            j["app"] = "jianying"
            (built / ".jyr.json").write_text(json.dumps(j))
            with self.assertRaisesRegex(JyrError, "built for jianying"):
                home.publish(rt, built, "错推")
        with mock.patch.object(home, "app_running", return_value=True):
            with self.assertRaisesRegex(JyrError, "CapCut is running"):
                home.publish(rt, built, "x")


class CapCutResourceTests(unittest.TestCase):
    def test_vip_flags_from_key_value(self):
        flags = catalog.vip_flags({**kv("1", "0"), **kv("2", "1"),
                                   "local": {"materialId": "3", "is_vip": "1", "materialSubcategory": "local"},
                                   "x": "not a dict"})
        self.assertEqual(flags, {"1": False, "2": True})

    def test_scan_tags_free_pro_unknown_and_pack_keeps_only_free(self):
        root = TMP / "scan-root"
        tr = lambda rid, name: {"id": rid + "x", "resource_id": rid, "effect_id": rid, "name": name,
                                "path": "/nope", "type": "transition", "duration": 466666}
        saved_draft(root, "d1", "9.4.1", "185.0.0", {**kv("11", "0"), **kv("22", "1")},
                    {"transitions": [tr("11", "叠化"), tr("22", "高级转场"), tr("33", "没记录")]})
        saved_draft(root, "d2", "9.4.1", "185.0.0", kv("11", "1"), {"transitions": [tr("11", "叠化")]})
        saved_draft(root, "d3", "9.4.1", "185.0.0", kv("44", "0"), {"transitions": [tr("44", "闪白")]})
        rt = capcut_rt(root)
        with mock.patch.object(catalog, "CONFIG_DIR", TMP / "scan-home"), \
             mock.patch.object(catalog, "_local_fonts", return_value=[
                 {"kind": "font", "name": "zh-hans", "resource_id": "", "path": "/Applications/CapCut.app/Contents/"
                  "Resources/Font/SystemFont/zh-hans.ttf", "category": "内置字体", "template": {}, "seen": 0}]):
            cat = catalog.scan(rt)
            path = catalog.catalog_path(rt)
        self.assertEqual(path.name, "catalog-capcut.json")
        vip = {e["name"]: e["vip"] for e in cat["entries"]}
        # Pro anywhere wins over free elsewhere; no record stays unknown; bundled fonts are free.
        self.assertEqual(vip, {"叠化": True, "高级转场": True, "没记录": None, "闪白": False, "zh-hans": False})
        out = TMP / "pack.json"
        subprocess.run([sys.executable, str(ROOT / "tools/build_resource_pack.py"), "--app", "capcut",
                        "--out", str(out), str(path)], check=True, capture_output=True)
        pack = json.loads(out.read_text())
        self.assertEqual(pack["app"], "capcut")
        self.assertEqual(sorted(c["name"] for c in pack["cards"]), ["zh-hans", "闪白"])
        self.assertTrue(all(c.get("vip") is False for c in pack["cards"]))
        self.assertEqual(next(c for c in pack["cards"] if c["name"] == "zh-hans")["path"],
                         "@app/Contents/Resources/Font/SystemFont/zh-hans.ttf")

    def test_paid_resource_warns_and_auto_skips_it(self):
        e = lambda name, vip, seen: {"kind": "transition", "name": name, "resource_id": name, "path": "/x",
                                     "available": True, "seen": seen, "vip": vip, "template": {"name": name}}
        cat = Catalog({"entries": [e("高级", True, 99), e("叠化", False, 1)]})
        rt = capcut_rt(TMP / "w")
        clips = lambda tr: {"tracks": [{"type": "video", "clips": [
            {"src": str(TMP / "a.mp4"), "duration": 2, "transition": tr}, {"src": str(TMP / "a.mp4"), "duration": 2}]}]}
        comp = planmod.Compiler(rt, cat)
        d = comp.compile(clips("auto"))
        self.assertEqual(d.materials["transitions"][0]["name"], "叠化")
        self.assertEqual(comp.warnings, [])
        comp = planmod.Compiler(rt, cat)
        comp.compile(clips("高级"))
        self.assertTrue(any("paid" in w for w in comp.warnings))

    def test_shipped_packs_are_free_only_and_private_data_free(self):
        for name in ("resources.json", "resources.capcut.json"):
            blob = (ROOT / "jyr/data" / name).read_text("utf-8")
            self.assertNotIn("/Users/", blob)
            cards = json.loads(blob)["cards"]
            self.assertTrue(cards, name)
            self.assertTrue(all(c.get("vip") is False for c in cards), name)

    def test_example_plans_build_from_free_builtin_resources_only(self):
        media = TMP / "examples/media"
        subprocess.run(["bash", str(ROOT / "tools/make_fixtures.sh"), str(media)], check=True, capture_output=True)
        for plan_name, rt in (("showcase.plan.json", jianying_rt(TMP)), ("capcut.plan.json", capcut_rt(TMP))):
            shutil.copy(ROOT / "examples" / plan_name, TMP / "examples" / plan_name)
            with mock.patch.object(catalog, "CONFIG_DIR", TMP / "no-home"), \
                 mock.patch.object(catalog, "CATALOG_PATH", TMP / "no-home/catalog.json"):
                comp = planmod.Compiler(rt, base_dir=TMP / "examples")
                comp.compile(planmod.load(TMP / "examples" / plan_name))
            self.assertEqual(comp.warnings, [], plan_name)

    def test_old_unflagged_scan_is_ignored(self):
        home_dir = TMP / "legacy-home"
        home_dir.mkdir()
        (home_dir / "catalog.json").write_text(json.dumps({"app_version": "11.6.0", "entries": [
            {"kind": "transition", "name": "旧会员转场", "resource_id": "9", "path": "/x", "seen": 50, "template": {}}]}))
        with mock.patch.object(catalog, "CATALOG_PATH", home_dir / "catalog.json"):
            names = [e["name"] for e in Catalog(rt=jianying_rt(TMP)).list("transition")]
        self.assertNotIn("旧会员转场", names)
        self.assertIn("叠化", names)

    def test_jianying_pack_build_drops_paid_and_unrecorded(self):
        kvroot = TMP / "kv"
        (kvroot / "d").mkdir(parents=True)
        (kvroot / "d/key_value.json").write_text(json.dumps({**kv("1", "0"), **kv("2", "1")}))
        card = lambda rid, kind="transition", path="": {"kind": kind, "name": "n" + rid, "resource_id": rid,
                                                        "path": path, "template": {}, "rank": 1}
        src = TMP / "pack-src.json"
        src.write_text(json.dumps({"cards": [card("1"), card("2"), card("3"),
                                             card("", "font", "@app/Contents/Resources/Font/zh-hans.ttf")]}))
        out = TMP / "jy-pack.json"
        subprocess.run([sys.executable, str(ROOT / "tools/build_resource_pack.py"), "--key-values", str(kvroot),
                        "--out", str(out), str(src)], check=True, capture_output=True)
        self.assertEqual(sorted(c["name"] for c in json.loads(out.read_text())["cards"]), ["n", "n1"])


if __name__ == "__main__":
    unittest.main()
