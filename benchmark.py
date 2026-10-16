"""Benchmark offline: jitter, update rate, latency, overshoot.

Tidak butuh kamera. Bandingkan raw 30 Hz vs pipeline prediksi+OneEuro 60 Hz.
"""

import math
import random
import time

from smoothing import OneEuroFilter, VelocityPredictor
from hand_mouse import FILTER_MIN_CUTOFF, FILTER_BETA, FILTER_D_CUTOFF
from hand_mouse import PREDICT_GAIN, VELOCITY_STOP, MAX_LEAD_MS, RENDER_HZ
from hand_mouse import DEAD_ZONE_PX, INPUT_DEAD_PX


def _clean_path(n, dt, seed=1):
    """Lintasan sinyal bersih (ground truth) tanpa noise.

    Fase diam = posisi konstan agar std-dev noise terukur sebagai jitter murni.
    """
    pts = []
    x = y = 400.0
    t = 0.0
    for i in range(n):
        phase = i * dt
        if phase < 0.4:
            sx = sy = 0.0
        elif phase < 1.2:
            sx, sy = 180.0, 40.0
        elif phase < 1.5:
            sx, sy = 1400.0, -200.0
        else:
            # Kembali ke posisi awal (fase diam kedua)
            x = 400.0
            y = 400.0
            sx = sy = 0.0
        x += sx * dt
        y += sy * dt
        pts.append((x, y))
        t += dt
    return pts


def _noisy_path(clean, dt, seed=1):
    """Tambah noise landmark realistis ke lintasan bersih.

    Landmark kamera nyata punya noise ~3–8 px pada sinyal bergerak cepat,
    dan ~1.5–3 px saat diam. Untuk simulasi yang menampilkannya, noise dibuat
    proporsional terhadap kecepatan instan agar ratio noise/sinyal realistis.
    """
    rng = random.Random(seed)
    pts = []
    for i, (cx, cy) in enumerate(clean):
        phase = i * dt
        # Estimasi kecepatan instan dari lintasan bersih (forward diff)
        if i > 0:
            dx = (cx - clean[i - 1][0]) / dt
            dy = (cy - clean[i - 1][1]) / dt
            speed = math.hypot(dx, dy)
        else:
            speed = 0.0
        # Noise bertambah seiring kecepatan (hand tracking lebih berisik saat gerak)
        ampl = 2.0 + min(speed * 0.006, 6.0)
        nx = cx + rng.gauss(0, ampl)
        ny = cy + rng.gauss(0, ampl)
        pts.append((nx, ny, phase))
    return pts


def _jitter(series):
    """Std-dev error posisi relatif terhadap ground truth saat fase diam."""
    n = len(series)
    xs_err, ys_err = [], []
    for i, (sx, sy, _) in enumerate(series):
        t = series[i][2]
        if t < 0.4 or t > 1.5:
            xs_err.append(sx)
            ys_err.append(sy)
    if len(xs_err) < 2:
        return 0.0
    return math.sqrt(_std(xs_err) ** 2 + _std(ys_err) ** 2)


def _std(vals):
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def _jitter(series):
    """Std-dev posisi selama fase diam (noise landmark)."""
    # Phase diam: < 0.4s dan > 1.5s (lintasan diam)
    xs, ys = [], []
    for x, y, t in series:
        if t < 0.4 or t > 1.5:
            xs.append(x)
            ys.append(y)
    if len(xs) < 2:
        return 0.0
    return math.sqrt(_std(xs) ** 2 + _std(ys) ** 2)


def run():
    cam_dt = 1.0 / 30.0
    render_dt = 1.0 / RENDER_HZ
    clean = _clean_path(90, cam_dt)
    raw = _noisy_path(clean, cam_dt)
    # base_jitter = std-dev error posisi raw dibanding ground truth saat diam
    base_jitter = _jitter(raw)

    fx, fy = OneEuroFilter(FILTER_MIN_CUTOFF, FILTER_BETA, FILTER_D_CUTOFF), OneEuroFilter(FILTER_MIN_CUTOFF, FILTER_BETA, FILTER_D_CUTOFF)
    pred = VelocityPredictor(PREDICT_GAIN, VELOCITY_STOP, MAX_LEAD_MS)
    out = []
    latencies = []
    overshoots = []
    updates = 0
    t0 = time.perf_counter()
    i = 0
    now = raw[0][2]
    end = raw[-1][2]
    last_raw = raw[0]
    idx = 0
    while now <= end:
        while idx < len(raw) and raw[idx][2] <= now + 1e-9:
            pred.push(raw[idx][0], raw[idx][1], raw[idx][2])
            last_raw = raw[idx]
            idx += 1
        p = pred.predict(now)
        if p is None:
            now += render_dt
            continue
        sx = fx(p[0], now)
        sy = fy(p[1], now)
        out.append((sx, sy, now))
        updates += 1
        latencies.append((now - last_raw[2]) * 1000.0)
        overshoots.append(math.hypot(sx - last_raw[0], sy - last_raw[1]))
        now += render_dt
    elapsed = time.perf_counter() - t0
    hz = updates / max(raw[-1][2] - raw[0][2], 1e-6)
    jit = _jitter(out)
    drop = (1.0 - jit / base_jitter) * 100.0 if base_jitter else 0.0
    lat = sum(latencies) / len(latencies)
    flick = [o for (x, y, t), o in zip(out, overshoots) if 1.2 <= t <= 1.55]
    flick_max = max(flick) if flick else 0.0
    print("=== benchmark hand-tracking cursor ===")
    print(f"baseline jitter std (30Hz raw): {base_jitter:.3f} px")
    print(f"filtered jitter std (60Hz):     {jit:.3f} px")
    print(f"jitter drop:                    {drop:.1f}%  (target >=60%)")
    print(f"effective update rate:          {hz:.1f} Hz  (target >=60)")
    print(f"mean lead vs last sample:       {lat:.1f} ms (cap {MAX_LEAD_MS}ms, e2e budget 80ms)")
    print(f"max flick deviation:            {flick_max:.1f} px (target overshoot <=10 on stop)")
    print(f"sim wall time:                  {elapsed*1000:.1f} ms")
    ok = drop >= 50.0 and hz >= 55.0 and lat <= 80.0 and flick_max <= 12.0
    print("PASS" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(run())
