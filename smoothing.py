"""One Euro filter + prediksi kecepatan antar frame inference."""

import math


class OneEuroFilter:
    """Low-pass adaptif: makin cepat gerakannya, makin ringan smoothing-nya."""

    def __init__(self, min_cutoff=0.12, beta=0.08, d_cutoff=0.5):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def reset(self):
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = 0.0

    def __call__(self, x, t):
        if self.x_prev is None:
            self.x_prev, self.t_prev = x, t
            return x
        dt = t - self.t_prev
        if dt <= 0:
            return self.x_prev
        dx = (x - self.x_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self.dx_prev
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1.0 - a) * self.x_prev
        self.x_prev, self.dx_prev, self.t_prev = x_hat, dx_hat, t
        return x_hat


class OutputSmoother:
    """Ease posisi kursor di laju render biar mulus di antara frame kamera.

    Kamera cuma ~30 Hz, tapi kita menggambar/menggerakkan kursor ~60 Hz. Tanpa ini
    kursor "melangkah" tiap frame kamera. Ease eksponensial berbasis waktu (tahan
    terhadap FPS yang naik-turun): makin kecil tau, makin responsif tapi kurang
    mulus. tau <= 1ms = mati (langsung ikut target).
    """

    def __init__(self, tau_ms=28.0):
        self.tau = max(float(tau_ms), 0.0) / 1000.0
        self.reset()

    def reset(self):
        self.x = None
        self.y = None
        self.t = 0.0

    def update(self, tx, ty, t):
        if self.x is None or self.tau <= 0.001:
            self.x, self.y, self.t = tx, ty, t
            return tx, ty
        dt = t - self.t
        self.t = t
        if dt <= 0:
            return self.x, self.y
        a = 1.0 - math.exp(-dt / self.tau)
        self.x += (tx - self.x) * a
        self.y += (ty - self.y) * a
        return self.x, self.y


class VelocityPredictor:
    """Dead-reckoning dari 3 sampel terakhir.

    Prediktor MATI saat tangan berhenti (|v| < stop_px_s). Prediksi hanya aktif
    ketika tangan benar-benar bergerak, jadi noise landmark tidak ikut ikut
    berekstrapolasi saat diam.
    Lead dibatasi max_lead_ms biar prediksi tidak lari jauh dari sampel terakhir.
    """

    def __init__(self, gain=0.45, stop_px_s=8.0, max_lead_ms=25.0):
        self.gain = gain
        self.stop_px_s = stop_px_s
        self.max_lead = max_lead_ms / 1000.0
        self.reset()

    def reset(self):
        self.samples = []
        self.vx = 0.0
        self.vy = 0.0
        self.aktif = False
        self.stop_frames = 0
        self.stop_threshold = 6  # Frame kamera berturut-turut diam baru matikan prediksi

    def push(self, x, y, t):
        self.samples.append((x, y, t))
        if len(self.samples) > 3:
            self.samples.pop(0)
        if len(self.samples) < 2:
            self.vx = self.vy = 0.0
            self.aktif = False
            self.stop_frames = 0
            return
        x0, y0, t0 = self.samples[0]
        x1, y1, t1 = self.samples[-1]
        dt = t1 - t0
        if dt <= 1e-4:
            self.vx = self.vy = 0.0
            self.aktif = False
            self.stop_frames += 1
            return
        vx = (x1 - x0) / dt
        vy = (y1 - y0) / dt
        speed = math.hypot(vx, vy)
        if speed < self.stop_px_s:
            self.stop_frames += 1
            if self.stop_frames >= self.stop_threshold:
                self.vx = self.vy = 0.0
                self.aktif = False
        else:
            self.stop_frames = 0
            self.vx, self.vy = vx, vy
            self.aktif = True

    def predict(self, now):
        if not self.samples:
            return None
        if not self.aktif:
            # Tidak prediksa saat diam: kembalikan posisi terakhir apa adanya.
            x, y, t = self.samples[-1]
            return x, y
        x, y, t = self.samples[-1]
        lead = min(max(now - t, 0.0), self.max_lead)
        return x + self.vx * lead * self.gain, y + self.vy * lead * self.gain
