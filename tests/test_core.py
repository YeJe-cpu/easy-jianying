"""Fast tests: no JianYing needed (media via ffmpeg fixtures, resources via a fake catalog).

run: python3 -m unittest discover -s tests
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from jyr import plan as planmod
from jyr.catalog import Catalog
from jyr.draft import Draft
from jyr.recipes import batch, beats, roughcut, subtitles
from jyr.runtime import Runtime
from jyr.srt import parse_srt, to_srt
from jyr.util import JyrError

TMP = Path(tempfile.mkdtemp(prefix="jyr-test-"))


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def setUpModule():
    ff("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=6", "-f", "lavfi", "-i",
       "sine=frequency=440:duration=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
       str(TMP / "a.mp4"))
    ff("-f", "lavfi", "-i", "color=c=red:size=64x64", "-frames:v", "1", str(TMP / "p.png"))
    ff("-f", "lavfi", "-i", "testsrc2=size=64x64:rate=10:duration=1", str(TMP / "g.gif"))
    ff("-f", "lavfi", "-i", "sine=duration=3", "-i", str(TMP / "p.png"), "-map", "0", "-map", "1",
       "-c:a", "libmp3lame", "-c:v", "mjpeg", "-disposition:v", "attached_pic", str(TMP / "cover.mp3"))


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def fake_catalog():
    def e(kind, name, **kw):
        return {"kind": kind, "name": name, "resource_id": str(abs(hash(name)) % 10**18), "path": "/x",
                "available": True, "seen": kw.pop("seen", 1), "template": {"name": name, "path": "/x"}, **kw}
    return Catalog({"entries": [
        e("transition", "叠化", default_duration_us=500000, seen=2), e("transition", "推近", seen=9),
        e("mask", "圆形", shape="circle"), e("animation", "渐显", slot="in", target="text"),
        e("effect", "模糊"), e("font", "某体", roles={"title": 3}),
    ]})


RT = Runtime(Path("/Applications/x.app"), "11.6.0", "11.6.0", Path("/x"), "0" * 64, Path("/tmp"), Path("/tmp"),
             {"timeline_version": "189.0.0"})


def compile_(p):
    return planmod.Compiler(RT, fake_catalog()).compile(p)


class PlanTests(unittest.TestCase):
    def test_sequential_clips_follow_each_other_on_frame_grid(self):
        d = compile_({"canvas": "9:16", "tracks": [{"type": "video", "clips": [
            {"src": str(TMP / "a.mp4"), "duration": 1.01}, {"src": str(TMP / "a.mp4"), "in": 2, "duration": 2}]}]})
        a, b = d.tracks[0].segments
        end_a = a["target_timerange"].get("start", 0) + a["target_timerange"]["duration"]
        self.assertEqual(end_a, b["target_timerange"]["start"])
        self.assertEqual(end_a, int(round(end_a * 30 / 1e6) * 1e6 / 30))  # on the 30 fps grid

    def test_one_material_per_segment_and_fade_copied_onto_material(self):
        d = compile_({"tracks": [{"type": "video", "clips": [
            {"src": str(TMP / "a.mp4"), "duration": 1, "fade": {"out": 0.5}}, {"src": str(TMP / "a.mp4"), "duration": 1}]}]})
        vids = d.materials["videos"]
        self.assertEqual(len(vids), 2)
        self.assertEqual(vids[0]["audio_fade"]["fade_out_duration"], 500000)
        self.assertEqual(len(d.local_media), 1)

    def test_transition_snaps_to_even_frames_and_not_on_last_clip(self):
        d = compile_({"tracks": [{"type": "video", "clips": [
            {"src": str(TMP / "a.mp4"), "duration": 2, "transition": "叠化"}, {"src": str(TMP / "a.mp4"), "duration": 2}]}]})
        self.assertEqual(d.materials["transitions"][0]["duration"], 466666)
        with self.assertRaises(JyrError):
            compile_({"tracks": [{"type": "video", "clips": [{"src": str(TMP / "a.mp4"), "duration": 1, "transition": "叠化"}]}]})

    def test_source_overrun_is_reported(self):
        with self.assertRaisesRegex(JyrError, "needs"):
            compile_({"tracks": [{"type": "video", "clips": [{"src": str(TMP / "a.mp4"), "in": 5, "duration": 3}]}]})

    def test_stills_and_gif(self):
        d = compile_({"tracks": [{"type": "video", "clips": [{"src": str(TMP / "p.png"), "duration": 30},
                                                              {"src": str(TMP / "g.gif"), "duration": 30}]}]})
        self.assertEqual([m["type"] for m in d.materials["videos"]], ["photo", "gif"])

    def test_mp3_with_cover_art_is_audio(self):
        # Regression (2026-10-30): an embedded album cover made a song look like a video,
        # which left JianYing's preview black.
        d = compile_({"tracks": [{"type": "video", "clips": [{"src": str(TMP / "a.mp4"), "duration": 2}]},
                                 {"type": "audio", "clips": [{"src": str(TMP / "cover.mp3"), "duration": 2}]}]})
        self.assertEqual(len(d.materials["audios"]), 1)
        self.assertEqual(len(d.materials["videos"]), 1)
        # a video file used for its sound on an audio track is an audio material too
        d = compile_({"tracks": [{"type": "video", "clips": [{"src": str(TMP / "p.png"), "duration": 2}]},
                                 {"type": "audio", "clips": [{"src": str(TMP / "a.mp4"), "duration": 2}]}]})
        self.assertEqual([m["type"] for m in d.materials["audios"]], ["extract_music"])

    def test_keyframes_validation(self):
        with self.assertRaises(JyrError):
            compile_({"tracks": [{"type": "video", "clips": [{"src": str(TMP / "a.mp4"), "duration": 1,
                                                                "keyframes": {"x": [[0.5, 0], [0.2, 1]]}}]}]})
        d = compile_({"tracks": [{"type": "video", "clips": [{"src": str(TMP / "a.mp4"), "duration": 2,
                                                              "keyframes": {"scale": [[0, 1], [2, 1.2]]}}]}]})
        props = [k["property_type"] for k in d.tracks[0].segments[0]["common_keyframes"]]
        self.assertEqual(props, ["KFTypeScaleX", "KFTypeScaleY"])

    def test_auto_resources_pick_most_used(self):
        d = compile_({"tracks": [{"type": "video", "clips": [
            {"src": str(TMP / "a.mp4"), "duration": 2, "transition": "auto"}, {"src": str(TMP / "a.mp4"), "duration": 2}]}]})
        self.assertEqual(d.materials["transitions"][0]["name"], "推近")

    def test_subtitle_track_flag_and_unknown_resource_message(self):
        d = compile_({"tracks": [{"type": "subtitle", "clips": [{"text": "你好", "duration": 1}]}]})
        self.assertEqual(d.tracks[0].flag, 1)
        self.assertEqual(d.materials["texts"][0]["type"], "subtitle")
        with self.assertRaisesRegex(JyrError, "Available"):
            compile_({"tracks": [{"type": "effect", "clips": [{"name": "不存在", "duration": 1}]}]})


class RecipeTests(unittest.TestCase):
    def test_srt_roundtrip(self):
        cues = [(500000, 2000000, "第一句"), (2000000, 3500000, "第二句")]
        self.assertEqual(parse_srt(to_srt(cues)), cues)

    def test_subtitle_cues_break_on_punctuation_and_length(self):
        words = [{"start": i * 0.3, "end": i * 0.3 + 0.25, "text": t} for i, t in enumerate(
            ["今天", "我们", "聊聊", "剪映，", "这个", "工具", "真的", "非常", "非常", "好用。"])]
        cues = subtitles.cues_from_words(words, max_chars=8)
        self.assertTrue(all(len(c["text"]) <= 8 for c in cues))
        self.assertEqual(cues[0]["text"], "今天我们聊聊剪映")

    def test_roughcut_drops_fillers_stutters_false_starts_and_pauses(self):
        w = lambda s, e, t: {"start": s, "end": e, "text": t}
        words = [w(0, .3, "我想"), w(.3, .5, "说。"),            # false start
                 w(1.0, 1.3, "我想"), w(1.3, 1.6, "说的是"), w(1.6, 1.8, "嗯"), w(1.8, 2.0, "这个"),
                 w(2.0, 2.2, "这个"), w(2.2, 2.6, "工具。"),
                 w(4.0, 4.4, "很好用。")]                       # after a 1.4 s silence
        an = roughcut.analyze(words)
        reasons = sorted(d["reason"] for d in an["drops"])
        self.assertEqual(reasons, ["false-start", "filler", "repeat"])
        ranges = roughcut.keep_ranges(an)
        self.assertEqual(len(ranges), 2)  # the long pause splits the take
        kept = "".join(x["text"] for _, _, ws in ranges for x in ws)
        self.assertEqual(kept, "我想说的是这个工具。很好用。")

    def test_batch_fill_keeps_types(self):
        tpl = {"name": "{{t}}", "tracks": [{"type": "text", "clips": [{"text": "第{{n}}期 {{t}}", "duration": "{{d}}"}]}]}
        p = batch.expand(tpl, [{"t": "A", "n": "1", "d": "2.5"}])[0]
        self.assertEqual(p["tracks"][0]["clips"][0], {"text": "第1期 A", "duration": 2.5})
        with self.assertRaises(JyrError):
            batch.expand(tpl, [{"t": "A"}])

    def test_beats_on_click_track(self):
        f = TMP / "click.wav"
        ff("-f", "lavfi", "-i", "aevalsrc='if(lt(mod(t,0.5),0.03),sin(2*PI*1000*t),0)':s=22050:d=12", str(f))
        r = beats.detect(str(f))
        self.assertAlmostEqual(r["bpm"], 120, delta=2.5)
        err = max(abs(t - round(t / 0.5) * 0.5) for t in r["beats"])
        self.assertLess(err, 0.02)


class DraftJsonTests(unittest.TestCase):
    def test_to_json_shape(self):
        d = Draft("x", 1080, 1920, 30)
        t = d.add_track("text")
        d.add_text(t, "hi", 0, 1_000_000, stroke_color="#000000")
        j = d.to_json()
        self.assertEqual(j["new_version"], "189.0.0")
        self.assertEqual(j["canvas_config"]["width"], 1080)
        c = json.loads(j["materials"]["texts"][0]["content"])
        self.assertEqual(c["text"], "hi")
        self.assertIn("strokes", c["styles"][0])


if __name__ == "__main__":
    unittest.main()
