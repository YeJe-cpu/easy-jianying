"""卡点: find the beat of a music track and cut footage on it.

Pure numpy: decode with ffmpeg, spectral-flux onset envelope, tempo from
autocorrelation, then dynamic-programming beat tracking (after D. Ellis,
"Beat Tracking by Dynamic Programming", 2007).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from ..media import probe
from ..util import JyrError

SR = 22050
HOP = 512


def _decode(path: str) -> np.ndarray:
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True)
    if out.returncode != 0:
        raise JyrError(f"ffmpeg cannot decode {path}")
    return np.frombuffer(out.stdout, dtype=np.float32)


N_FFT = 2048


def onset_envelope(y: np.ndarray) -> np.ndarray:
    n_fft = N_FFT
    if len(y) < n_fft:
        raise JyrError("audio too short for beat detection")
    frames = np.lib.stride_tricks.sliding_window_view(y, n_fft)[::HOP] * np.hanning(n_fft)
    mag = np.log1p(np.abs(np.fft.rfft(frames, axis=1)) * 10)
    flux = np.maximum(0.0, np.diff(mag, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    flux -= np.convolve(flux, np.ones(16) / 16, mode="same")  # remove slow trend
    flux = np.maximum(flux, 0)
    return flux / (flux.std() + 1e-9)


def tempo(env: np.ndarray, lo: float = 60, hi: float = 180) -> float:
    fps = SR / HOP
    ac = np.correlate(env, env, mode="full")[len(env) - 1 :]
    lags = np.arange(len(ac))
    bpm = 60 * fps / np.maximum(lags, 1)
    # prefer tempos around 120 BPM (log-gaussian weighting, as in Ellis)
    weight = np.exp(-0.5 * (np.log2(np.maximum(bpm, 1) / 120) / 0.9) ** 2)
    ok = (bpm >= lo) & (bpm <= hi)
    score = np.where(ok, ac * weight, 0)
    return float(bpm[int(np.argmax(score))])


def track(env: np.ndarray, bpm: float, tightness: float = 100) -> np.ndarray:
    fps = SR / HOP
    period = 60 * fps / bpm
    n = len(env)
    score = env.copy()
    back = np.full(n, -1)
    lo, hi = int(round(period / 2)), int(round(period * 2))
    window = np.arange(-hi, -lo + 1)
    penalty = -tightness * np.log(-window / period) ** 2
    for i in range(hi, n):
        cand = score[i + window] + penalty
        j = int(np.argmax(cand))
        score[i] = env[i] + cand[j]
        back[i] = i + window[j]
    i = int(np.argmax(score[-int(period):])) + n - int(period)
    beats = []
    while i >= 0:
        beats.append(i)
        i = back[i]
    # frame i covers samples [i*HOP, i*HOP + N_FFT); report its centre
    return np.array(beats[::-1]) / fps + (N_FFT / 2) / SR


def snap_to_transients(y: np.ndarray, times: np.ndarray, before: float = 0.05, after: float = 0.05) -> np.ndarray:
    """Spectral frames are ~46 ms wide; move each beat onto the sharpest energy rise
    near it (5 ms resolution)."""
    win = int(SR * 0.005)
    n = len(y) // win
    rms = np.sqrt((y[: n * win].reshape(n, win) ** 2).mean(axis=1) + 1e-12)
    rise = np.diff(np.log(rms + 1e-6), prepend=0)
    step = win / SR
    out = []
    for t in times:
        a, b = max(0, int((t - before) / step)), min(n, int((t + after) / step) + 1)
        out.append((a + int(np.argmax(rise[a:b]))) * step if b > a else t)
    return np.array(out)


def detect(path: str) -> dict:
    y = _decode(path)
    env = onset_envelope(y)
    bpm = tempo(env)
    times = snap_to_transients(y, track(env, bpm))
    return {"bpm": round(bpm, 1), "beats": [round(float(t), 3) for t in times if t > 0.05]}


def beat_plan(music: str, clips: list[str], every: int = 1, start_beat: int = 0, max_len: float | None = None,
              canvas: str | dict = "9:16", fit: str = "fill", name: str = "卡点") -> tuple[dict, dict]:
    """Cut `clips` (cycled) on every `every`-th beat of `music`."""
    if not clips:
        raise JyrError("no clips to cut on the beat")
    info = detect(music)
    beats = info["beats"][start_beat::every]
    if max_len:
        beats = [b for b in beats if b - beats[0] <= max_len]
    if len(beats) < 2:
        raise JyrError("not enough beats found")
    t0 = beats[0]
    marks = [b - t0 for b in beats]
    vclips, offsets = [], {}
    for i, (a, b) in enumerate(zip(marks, marks[1:])):
        src = clips[i % len(clips)]
        m = probe(src)
        dur = round(b - a, 3)
        clip = {"src": src, "duration": dur}
        if m.kind == "video":
            used = offsets.get(src, 0.0)
            if used + dur > m.duration_us / 1e6:
                used = 0.0
            clip["in"] = round(used, 3)
            offsets[src] = used + dur
        clip["volume"] = 0
        vclips.append(clip)
    total = round(marks[-1], 3)
    plan = {"name": name, "canvas": canvas,
            "tracks": [{"type": "video", "name": "卡点", "clips": vclips},
                       {"type": "audio", "name": "音乐", "clips": [{"src": music, "in": round(t0, 3), "duration": total,
                                                                  "beats": marks, "fade": {"out": min(1.0, total / 4)}}]}]}
    return plan, {"bpm": info["bpm"], "beats_used": len(marks), "duration_s": total}
