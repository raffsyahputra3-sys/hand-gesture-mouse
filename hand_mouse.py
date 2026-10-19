"""
Hand Gesture Mouse Controller v1.1
Mengendalikan pointer laptop tanpa mouse fisik, hanya dengan gerakan tangan via webcam.

Cara pakai:
    python hand_mouse.py      (atau klik 2x JALANKAN.bat)

Kontrol:
    - Jempol nempel tengah + telunjuk sebagai pointer -> Gerakkan pointer
    - (jempol lepas dari tengah = kursor diam)
    - Cubit jempol + jari manis         -> Klik kiri
    - Tahan cubit manis 0.6 dtk         -> Double click (buka aplikasi)
    - Cubit jempol + kelingking         -> Klik kanan
    - Cubit jempol + telunjuk + usap    -> Scroll (atas/bawah, pointer beku)
    - Telunjuk+tengah+manis naik + jempol nempel kelingking -> Voice typing on/off
    - Tekan 'q' di preview window       -> Keluar
"""

import ctypes
import math
import os
import sys
import threading
import time

import cv2
import mediapipe as mp
import pyautogui

from smoothing import OneEuroFilter, OutputSmoother, VelocityPredictor


# ================= FR-08: Konfigurasi =================
CAMERA_RESOLUTION = (480, 360)  # Diturunkan dari 640x480: MediaPipe ~2x lebih cepat, delay hilang
TARGET_FPS = 30                 # Webcam laptop umumnya mentok 30; minta 60 malah bikin driver ngos-ngosan
MODEL_COMPLEXITY = 0            # 0 = model lite (paling cepat), 1 = lebih akurat
# MediaPipe diproses pada gambar kecil ini (landmark ternormalisasi 0-1,
# jadi koordinat tetap dipetakan ke frame penuh). 320x240 ~3x lebih cepat
# dari 480x360 dan penurun akurasinya kecil untuk jarak 30-80cm.
PROCESS_WIDTH = 320
PROCESS_HEIGHT = 240
DRAW_SKELETON = True            # True = gambar skeleton (bantu lihat gesture); False = hemat CPU
OVERLAY_ENABLED = True          # Lingkaran neon ngikutin kursor Windows (sementara, hilang saat program mati)
OVERLAY_SIZE = 110              # Diameter lingkaran overlay (px layar) — besar biar gampang kelihatan
OVERLAY_HZ = 60
RENDER_HZ = 60
PREDICT_GAIN = 0.45
VELOCITY_STOP = 60.0
MAX_LEAD_MS = 25.0
# Ease output di laju render biar gerak kursor mulus di antara frame kamera.
# Naikkan kalau masih terasa patah-patah; turunkan (atau 0) kalau terasa lambat.
GLIDE_MS = 28.0
SCROLL_ACCEL = 1.8
SCROLL_MOMENTUM = 0.82
SCROLL_MAX_NOTCH = 8

# Lebar kotak aktif sebagai fraksi lebar frame. Makin kecil, makin sedikit
# tangan perlu bergerak untuk menjangkau seluruh layar (tapi gain besar ikut
# menguatkan noise landmark -> kursor gerak sendiri). 0.30 = gain ~6.7x,
# smoothing + dead-zone di bawah ikut diperkuat buat ngimbangin.
ACTIVE_WIDTH = 0.30

# Smoothing adaptif (One Euro filter): pelan = halus, cepat = responsif.
# Setelan stabil (kursor diam saat tangan diam): cutoff rendah + dead-zone
# sedang. Beta tetap lumayan biar gerak cepat tidak ketinggalan.
FILTER_MIN_CUTOFF = 0.12        # Turunkan kalau kursor masih gerak sendiri saat diam
FILTER_BETA = 0.08              # Naikkan kalau terasa lambat/ngambang saat gerak cepat
FILTER_D_CUTOFF = 0.5
DEAD_ZONE_PX = 2.0              # Gerakan output di bawah ini diabaikan (anti shiver/drift)
INPUT_DEAD_PX = 2.5             # Gerakan ujung telunjuk (px frame) di bawah ini = tangan diam,
                                # pointer tidak di-update sama sekali (rem utama anti drift)

# Cubitan dinormalisasi ke ukuran tangan, jadi tahan terhadap jarak ke kamera
# (setelan seimbang: cubit normal ke-detect, tangan santai tidak nembak sendiri)
PINCH_ON = 0.30                 # Rasio cubit untuk memicu (naikkan kalau susah nempel)
PINCH_OFF = 0.50                # Rasio untuk dianggap lepas (histeresis anti chatter)
PINCH_FRAMES = 3                # Frame kamera berturut-turut (bukan loop) sebelum klik sah
PINCH_MARGIN = 0.03             # Selisih rasio minimum biar satu jari dinyatakan pemenang
PINCH_ON_KIRI = 0.42            # Khusus manis (klik kiri): longgar, jarinya pendek & susah rapat
PINCH_OFF_KIRI = 0.62
# Kelingking lebih pendek dari manis dan menekuk lebih dalam saat dicubit jempol,
# jadi ambangnya WAJIB lebih longgar dari manis -- bukan lebih ketat. Nilai lama
# (on 0.35) bikin klik kanan nyaris tidak pernah sah.
PINCH_ON_KANAN = 0.45           # Khusus kelingking (klik kanan): longgar
PINCH_OFF_KANAN = 0.65
# Scroll: cubit jempol+telunjuk lalu usap vertikal. Telunjuk panjang jadi cubit
# gampang rapat; ambang bisa sedang.
PINCH_ON_SCROLL = 0.38
PINCH_OFF_SCROLL = 0.55
SCROLL_DBL_WINDOW = 0.9         # (tak terpakai lagi; disimpan agar config lama tetap kebaca)
SCROLL_TAHAN_MIN = 0.18         # (tak terpakai lagi; disimpan agar config lama tetap kebaca)
SCROLL_GAIN = 28.0              # Notch scroll untuk usapan setinggi 1 frame penuh
MIN_FINGER_REACH = 0.95         # Ujung jari harus >= sejauh ini x jarak pangkalnya
# Jari manis lebih pendek dan mencubitnya menekuk lebih dalam daripada jari
# tengah, jadi ambangnya harus lebih longgar atau klik sah ikut terblokir.
MIN_REACH_MANIS = 0.70
# Gerbang pointer (jempol+tengah) menekuk jari tengah, jadi ambangnya
# sedikit dilonggarkan biar cubit normal tetap dianggap sah.
MIN_REACH_TENGAH_AKTIF = 0.85
# Kelingking pendek seperti manis DAN menekuk lebih dalam saat dicubit, jadi
# ambang terulurnya harus lebih longgar lagi -- kalau tidak, cubitan kelingking
# yang sah ikut terblokir dan klik kanan tidak pernah terdeteksi.
MIN_REACH_KELINGKING = 0.60

# Ambang jari dianggap berdiri/terulur. Diukur sebagai rasio jangkauan dari
# pergelangan, bukan "ujung di atas sendi": perbandingan vertikal gagal begitu
# tangan dimiringkan atau telunjuk menunjuk ke depan, dan pointer ikut mati.
FINGER_EXTENDED = 1.10
CLICK_COOLDOWN = 0.35           # Detik minimum antar klik

# Voice typing offline Bahasa Indonesia: telunjuk+tengah+manis terangkat
# bersamaan + jempol nempel kelingking = toggle on/off.
VOICE_ENABLED = True
VOICE_MODEL = "base"            # tiny=cepat tapi kasar, base=seimbang, small=akurat tapi berat
VOICE_PINCH_MAX = 0.40          # Rasio jempol-kelingking di bawah ini = dianggap nempel
VOICE_FRAMES = 5                # Pose harus ditahan sekian frame kamera biar toggle sah
MANIS_NAIK = 1.00               # Ambang ulur manis dianggap terangkat (jari pendek)


def load_config():
    """Muat config.yaml kalau ada. Gagal diam-diam, konstanta file tetap dipakai."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    if not os.path.isfile(path):
        return {}
    try:
        import yaml
    except ImportError:
        return _parse_simple_yaml(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return _parse_simple_yaml(path)


def _parse_simple_yaml(path):
    """Parser mini: hanya key skalar + list angka. Tanpa dependency PyYAML."""
    root = {}
    section = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.split("#", 1)[0].rstrip()
                if not line.strip():
                    continue
                if not line.startswith(" ") and line.endswith(":"):
                    section = line[:-1].strip()
                    root[section] = {}
                    continue
                if section is None or ":" not in line:
                    continue
                key, val = line.split(":", 1)
                root[section][key.strip()] = _yaml_val(val.strip())
    except OSError:
        return {}
    return root


def _yaml_val(text):
    if text.startswith("[") and text.endswith("]"):
        parts = [p.strip() for p in text[1:-1].split(",") if p.strip()]
        out = []
        for p in parts:
            out.append(_yaml_val(p))
        return out
    low = text.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text.strip("\"'")


def apply_config(cfg):
    """Timpa konstanta modul dari config. Gesture API tidak berubah."""
    g = globals()
    mapping = {
        ("camera", "target_fps"): "TARGET_FPS",
        ("camera", "process_width"): "PROCESS_WIDTH",
        ("camera", "process_height"): "PROCESS_HEIGHT",
        ("camera", "model_complexity"): "MODEL_COMPLEXITY",
        ("pointer", "active_width"): "ACTIVE_WIDTH",
        ("pointer", "filter_min_cutoff"): "FILTER_MIN_CUTOFF",
        ("pointer", "filter_beta"): "FILTER_BETA",
        ("pointer", "filter_d_cutoff"): "FILTER_D_CUTOFF",
        ("pointer", "dead_zone_px"): "DEAD_ZONE_PX",
        ("pointer", "input_dead_px"): "INPUT_DEAD_PX",
        ("pointer", "render_hz"): "RENDER_HZ",
        ("pointer", "predict_gain"): "PREDICT_GAIN",
        ("pointer", "velocity_stop"): "VELOCITY_STOP",
        ("pointer", "max_lead_ms"): "MAX_LEAD_MS",
        ("pointer", "glide_ms"): "GLIDE_MS",
        ("scroll", "dbl_window"): "SCROLL_DBL_WINDOW",
        ("scroll", "tahan_min"): "SCROLL_TAHAN_MIN",
        ("scroll", "gain"): "SCROLL_GAIN",
        ("scroll", "accel"): "SCROLL_ACCEL",
        ("scroll", "momentum"): "SCROLL_MOMENTUM",
        ("scroll", "max_notch"): "SCROLL_MAX_NOTCH",
        ("overlay", "enabled"): "OVERLAY_ENABLED",
        ("overlay", "size"): "OVERLAY_SIZE",
        ("overlay", "hz"): "OVERLAY_HZ",
        ("voice", "enabled"): "VOICE_ENABLED",
        ("voice", "model"): "VOICE_MODEL",
    }
    for (sec, key), name in mapping.items():
        block = cfg.get(sec)
        if isinstance(block, dict) and key in block and block[key] is not None:
            g[name] = block[key]
    cam = cfg.get("camera") if isinstance(cfg.get("camera"), dict) else {}
    res = cam.get("resolution")
    if isinstance(res, (list, tuple)) and len(res) == 2:
        g["CAMERA_RESOLUTION"] = (int(res[0]), int(res[1]))


class DetektorKlik:
    """Satu tombol: nempel -> tahan PINCH_FRAMES -> klik sekali -> wajib lepas dulu.

    Ambang bisa beda per jari: manis yang pendek butuh ambang lebih longgar
    daripada tengah/kelingking.
    """

    def __init__(self, ambang_on=None, ambang_off=None):
        self.ambang_on = PINCH_ON if ambang_on is None else ambang_on
        self.ambang_off = PINCH_OFF if ambang_off is None else ambang_off
        self.reset()

    def reset(self):
        self.ditahan = False
        self.frames = 0

    def update(self, cubit, jari_terulur):
        """True tepat sekali, pada frame saat cubitan sah baru terdeteksi."""
        if self.ditahan:
            # Histeresis: harus lewat ambang_off dulu, bukan cuma ambang_on.
            # Jari yang tidak terulur juga melepas latch: jempol yang bersandar
            # di jari menggulung jaraknya tetap di bawah ambang_off, jadi tanpa
            # syarat ini latch tidak pernah lepas dan pointer beku permanen.
            if cubit > self.ambang_off or not jari_terulur:
                self.ditahan = False
            self.frames = 0
            return False

        if cubit < self.ambang_on and jari_terulur:
            self.frames += 1
        else:
            self.frames = 0

        if self.frames >= PINCH_FRAMES:
            self.ditahan = True
            self.frames = 0
            return True
        return False


class Mouse:
    """Kontrol kursor. Di Windows pakai ctypes karena pyautogui jauh lebih lambat."""

    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_WHEEL = 0x0800
    WHEEL_DELTA = 120

    def __init__(self):
        self.native = sys.platform == "win32"
        if self.native:
            self.user32 = ctypes.windll.user32
            # Tanpa ini SetCursorPos salah posisi di layar yang display scaling-nya bukan 100%
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                self.user32.SetProcessDPIAware()
        else:
            pyautogui.PAUSE = 0

    def size(self):
        if self.native:
            return self.user32.GetSystemMetrics(0), self.user32.GetSystemMetrics(1)
        return pyautogui.size()

    def move(self, x, y):
        if self.native:
            self.user32.SetCursorPos(int(x), int(y))
        else:
            pyautogui.moveTo(int(x), int(y))

    def click_left(self):
        if self.native:
            self.user32.mouse_event(self.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            self.user32.mouse_event(self.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        else:
            pyautogui.click()

    def click_right(self):
        if self.native:
            self.user32.mouse_event(self.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            self.user32.mouse_event(self.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
        else:
            pyautogui.rightClick()

    def double_click(self):
        """Klik kiri 2x cepat (buat buka aplikasi/folder)."""
        if self.native:
            self.click_left()
            time.sleep(0.05)
            self.click_left()
        else:
            pyautogui.doubleClick()

    def scroll(self, notches):
        """Scroll vertikal. Positif = ke atas, negatif = ke bawah."""
        if notches == 0:
            return
        if self.native:
            self.user32.mouse_event(
                self.MOUSEEVENTF_WHEEL, 0, 0, int(notches) * self.WHEEL_DELTA, 0)
        else:
            pyautogui.scroll(int(notches))


class CursorOverlay:
    """Lingkaran neon yang nempel ngikutin kursor Windows.

    Sementara saja (hilang saat program mati, setting Windows tidak diubah).
    Warna berubah sesuai gesture biar gampang ke-detect:
    cyan=pointer, hijau=klik kiri, magenta=klik kanan, oranye=scroll, merah=tahan.
    Window-nya click-through jadi tidak menghalangi klik.
    """

    def __init__(self, size=OVERLAY_SIZE):
        self.size = size
        self.enabled = False
        self._last_update = 0.0
        self._last_color = ""
        self._vx = 0.0
        self._vy = 0.0
        if not OVERLAY_ENABLED or sys.platform != "win32":
            return
        try:
            import tkinter as tk
            self._tk = tk
            self.root = tk.Tk()
            self.root.withdraw()
            self.win = tk.Toplevel(self.root)
            self.win.overrideredirect(True)
            self.win.attributes("-topmost", True)
            # Hitam jadi transparan, sisanya yang digambar jadi terlihat
            self.win.attributes("-transparentcolor", "black")
            self.win.config(bg="black")
            self.canvas = tk.Canvas(
                self.win, width=size, height=size,
                bg="black", highlightthickness=0, bd=0)
            self.canvas.pack()
            # Click-through: klik tembus ke window di bawahnya
            try:
                hwnd = self.win.winfo_id()
                user32 = ctypes.windll.user32
                GWL_EXSTYLE = -20
                WS_EX_LAYERED = 0x80000
                WS_EX_TRANSPARENT = 0x20
                WS_EX_NOACTIVATE = 0x08000000
                ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(
                    hwnd, GWL_EXSTYLE,
                    ex | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
            except (AttributeError, OSError):
                pass
            self._user32 = ctypes.windll.user32

            class _POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            self._POINT = _POINT
            self.enabled = True
        except Exception:
            self.enabled = False

    def _color_for(self, status):
        s = status or ""
        if "VOICE" in s or "MIC" in s:
            return "#BF00FF"  # ungu (voice typing)
        if "KLIK KANAN" in s:
            return "#FF00FF"  # magenta
        if "DOUBLE" in s or "KLIK KIRI" in s:
            return "#39FF14"  # hijau neon
        if "SCROLL" in s:
            return "#FFA500"  # oranye
        if "TAHAN" in s or "COOLDOWN" in s:
            return "#FF3131"  # merah
        if "NO HAND" in s or "TEMPEL" in s:
            return "#9E9E9E"  # abu (standby)
        return "#00FFFF"      # cyan (pointer)

    def update(self, status="", vx=0.0, vy=0.0):
        if not self.enabled:
            return
        sekarang = time.perf_counter()
        hz = OVERLAY_HZ if OVERLAY_HZ > 1 else 60
        if sekarang - self._last_update < 1.0 / hz:
            return
        self._last_update = sekarang
        self._vx, self._vy = vx, vy
        try:
            pt = self._POINT()
            if not self._user32.GetCursorPos(ctypes.byref(pt)):
                return
            warna = self._color_for(status)
            s = self.size
            self.win.geometry(f"{s}x{s}+{pt.x - s // 2}+{pt.y - s // 2}")
            self.canvas.delete("all")
            c = s // 2
            # Glow 2 lapis biar kebaca di layar terang
            self.canvas.create_oval(4, 4, s - 4, s - 4, outline=warna, width=10)
            self.canvas.create_oval(14, 14, s - 14, s - 14, outline="white", width=3)
            self.canvas.create_oval(22, 22, s - 22, s - 22, outline=warna, width=2)
            self.canvas.create_oval(c - 5, c - 5, c + 5, c + 5, fill="white", outline=warna, width=2)
            arm = 16
            self.canvas.create_line(c, 8, c, 8 + arm, fill="white", width=3)
            self.canvas.create_line(c, s - 8 - arm, c, s - 8, fill="white", width=3)
            self.canvas.create_line(8, c, 8 + arm, c, fill="white", width=3)
            self.canvas.create_line(s - 8 - arm, c, s - 8, c, fill="white", width=3)
            speed = math.hypot(vx, vy)
            if speed > 80:
                scale = min(28.0 / speed, 0.04)
                self.canvas.create_line(
                    c, c, c + vx * scale, c + vy * scale,
                    fill=warna, width=4, arrow=self._tk.LAST)
            label = (status or "")[:16]
            if label:
                self.canvas.create_text(
                    c, s - 12, text=label, fill="white",
                    font=("Segoe UI", 8, "bold"))
            self.root.update_idletasks()
            self.root.update()
        except Exception:
            # Kalau tkinter error di tengah jalan, matikan diam-diam
            try:
                self.enabled = False
            except Exception:
                pass

    def close(self):
        if not self.enabled:
            return
        try:
            self.win.destroy()
            self.root.destroy()
        except Exception:
            pass
        self.enabled = False


class VoiceTyping:
    """Voice typing Bahasa Indonesia offline (Whisper faster-whisper).

    Toggle dengan gesture: telunjuk+tengah+manis terangkat + jempol nempel
    kelingking. Selagi ON, omongan diketik otomatis di aplikasi yang sedang
    fokus (via paste Ctrl+V). Jalan di thread sendiri biar pointer tidak macet.
    Model (~150MB) diunduh otomatis sekali saja saat pertama dinyalakan.
    1 kalimat = bicara, jeda ~1 detik, teks langsung ketik sendiri.
    """

    def __init__(self):
        self.active = False
        self.message = ""
        self.message_until = 0.0
        self._thread = None
        self._stop = threading.Event()

    def _say(self, msg, detik=2.5):
        self.message = msg
        self.message_until = time.perf_counter() + detik

    def toggle(self):
        if self.active:
            self.stop()
            self._say("VOICE OFF")
        else:
            self.active = True
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            self._say("VOICE ON - bicara B.Indonesia...")

    def stop(self):
        self.active = False
        self._stop.set()

    def _run(self):
        import numpy as np
        try:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                self._say("VOICE ERR: pip install faster-whisper", 5.0)
                self.active = False
                return
            try:
                import sounddevice as sd
            except (ImportError, OSError):
                self._say("MIC ERR: pip install sounddevice", 5.0)
                self.active = False
                return
            self._say(f"LOAD MODEL {VOICE_MODEL}...", 30.0)
            try:
                model = WhisperModel(VOICE_MODEL, device="cpu",
                                     compute_type="int8")
            except Exception as e:
                self._say(f"MODEL GAGAL: {e}", 6.0)
                self.active = False
                return
            try:
                stream = sd.RawInputStream(samplerate=16000, blocksize=1600,
                                           dtype="int16", channels=1)
                in_rate = 16000
            except Exception:
                # Ada mic yang tidak support 16kHz: pakai rate asli + resample.
                try:
                    in_rate = int(sd.query_devices(kind="input")
                                  ["default_samplerate"])
                    n = int(1600 * in_rate / 16000)
                    stream = sd.RawInputStream(samplerate=in_rate,
                                               blocksize=n, dtype="int16",
                                               channels=1)
                except Exception as e:
                    self._say(f"MIC ERR: {e}", 5.0)
                    self.active = False
                    return
            with stream:
                self._say("MIC ON - bicara...")
                # Kalibrasi noise 0.5 detik biar ambangngikutin ruangan
                noise = []
                for _ in range(5):
                    data, _ov = stream.read(1600 if in_rate == 16000 else n)
                    x = np.frombuffer(bytes(data), dtype=np.int16).astype(
                        np.float32)
                    if in_rate != 16000:
                        idx = np.linspace(0, len(x) - 1, 1600)
                        x = np.interp(idx, np.arange(len(x)), x).astype(
                            np.float32)
                    noise.append(float(np.sqrt(np.mean(x * x))))
                    if self._stop.is_set():
                        return
                ambang = min(max(np.mean(noise) * 4.0, 300.0), 2000.0)
                buf, suara, sepi = [], 0, 0
                while not self._stop.is_set():
                    data, _ov = stream.read(1600 if in_rate == 16000 else n)
                    x = np.frombuffer(bytes(data), dtype=np.int16).astype(
                        np.float32)
                    if in_rate != 16000:
                        idx = np.linspace(0, len(x) - 1, 1600)
                        x = np.interp(idx, np.arange(len(x)), x).astype(
                            np.float32)
                    rms = float(np.sqrt(np.mean(x * x)))
                    buf.append(x)
                    if rms > ambang:
                        suara += 1
                        sepi = 0
                    else:
                        sepi += 1
                    # Bicara >=0.5 dtk lalu sepi 1 dtk (atau kepanjangan 15 dtk)
                    # = 1 kalimat selesai, transcribe.
                    if (suara >= 5 and sepi >= 10) or len(buf) >= 150:
                        audio = np.concatenate(buf) / 32768.0
                        buf, suara, sepi = [], 0, 0
                        if len(audio) >= 8000:
                            try:
                                seg, _info = model.transcribe(
                                    audio, language="id", beam_size=5,
                                    condition_on_previous_text=False)
                                teks = "".join(s.text for s in seg).strip()
                            except Exception:
                                teks = ""
                            if len(teks) >= 2:
                                self._ketik(teks + " ")
        except Exception as e:
            self._say(f"VOICE ERR: {e}", 5.0)
            self.active = False

    def _ketik(self, teks):
        """Ketik via clipboard + Ctrl+V (aman untuk huruf Indonesia)."""
        try:
            import pyperclip
            import pyautogui
            pyperclip.copy(teks)
            time.sleep(0.05)
            pyautogui.hotkey("ctrl", "v")
            print(f"[VOICE] {teks.strip()}")
        except Exception as e:
            self._say(f"KETIK ERR: {e}", 4.0)


class CameraStream:
    """Baca kamera di thread terpisah dan simpan hanya frame terbaru.

    Loop utama lebih lambat dari kamera, jadi tanpa ini kita memproses frame basi
    dari buffer driver dan pointer terasa tertinggal dari tangan.
    """

    def __init__(self, cap, index=0, backend_nama=""):
        self.cap = cap
        self.index = index
        self.backend_nama = backend_nama
        self._frame = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    @staticmethod
    def _konfigurasi(cap, resolution, fps):
        """Terapkan setelan ringan (resolusi, FPS, buffer, MJPG, autofocus)."""
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
        cap.set(cv2.CAP_PROP_FPS, fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        # MJPG jauh lebih ringan untuk USB webcam dibanding YUY2 mentah,
        # jadi frame sampai lebih cepat dan loop tidak kelaparan.
        try:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        except (AttributeError, cv2.error):
            pass
        # Kunci autofocus: lensa yang hunting maju-mundur bikin seluruh gambar
        # (dan landmark) berenang -> kursor drift padahal tangan diam.
        # Diabaikan diam-diam kalau webcam tidak mendukung (kebanyakan fixed-focus).
        try:
            cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        except (AttributeError, cv2.error):
            pass

    def is_opened(self):
        return self.cap is not None and self.cap.isOpened()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        while self._running:
            sukses, frame = self.cap.read()
            if not sukses:
                time.sleep(0.005)
                continue
            with self._lock:
                self._frame = frame

    def read(self):
        """Frame terbaru, atau None kalau kamera belum mengirim apa pun."""
        with self._lock:
            return self._frame

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self.cap is not None:
            self.cap.release()


def _daftar_backend():
    """Backend video yang dicoba, diurut sesuai OS (yang paling cocok dulu)."""
    if sys.platform == "win32":
        return [(cv2.CAP_DSHOW, "DSHOW"), (cv2.CAP_MSMF, "MSMF"),
                (cv2.CAP_ANY, "ANY")]
    if sys.platform == "darwin":
        return [(cv2.CAP_AVFOUNDATION, "AVFOUNDATION"), (cv2.CAP_ANY, "ANY")]
    return [(cv2.CAP_V4L2, "V4L2"), (cv2.CAP_ANY, "ANY")]


def buka_kamera_auto(resolution=CAMERA_RESOLUTION, fps=TARGET_FPS, max_index=4):
    """Cari kamera yang beneran kirim frame, lintas index x backend.

    Beda device beda index/backend yang jalan, dan isOpened()=True saja tidak
    cukup (sebagian driver "terbuka" tapi gagal baca). Jadi tiap kandidat
    diverifikasi dengan membaca frame sungguhan. Kembalikan CameraStream siap
    pakai, atau None kalau tidak ada yang berhasil.
    """
    for index in range(max_index + 1):
        for backend, nama in _daftar_backend():
            try:
                cap = cv2.VideoCapture(index, backend)
            except cv2.error:
                continue
            if not cap.isOpened():
                cap.release()
                continue
            CameraStream._konfigurasi(cap, resolution, fps)
            # Beri driver beberapa kali coba: frame pertama sering telat datang.
            terbaca = False
            for _ in range(8):
                sukses, frame = cap.read()
                if sukses and frame is not None:
                    terbaca = True
                    break
                time.sleep(0.05)
            if terbaca:
                print(f"[KAMERA] Terdeteksi di index {index} (backend {nama}).")
                return CameraStream(cap, index=index, backend_nama=nama)
            cap.release()
    return None


def set_high_performance():
    """Naikkan prioritas proses dan resolusi timer (Windows)."""
    if sys.platform != "win32":
        return False
    kernel32 = ctypes.windll.kernel32
    # HANDLE itu 64-bit; tanpa restype/argtypes ctypes memotongnya jadi 32-bit
    # dan SetPriorityClass gagal tanpa suara.
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint]

    HIGH_PRIORITY_CLASS = 0x00000080
    ok = bool(kernel32.SetPriorityClass(
        kernel32.GetCurrentProcess(), HIGH_PRIORITY_CLASS))
    ctypes.windll.winmm.timeBeginPeriod(1)
    return ok


def hitung_jarak_px(titik_a, titik_b):
    """Jarak Euclidean 2 titik dalam pixel."""
    return math.hypot(titik_a[0] - titik_b[0], titik_a[1] - titik_b[1])


def jari_menjangkau(pos_tip, pos_mcp, pos_pergelangan, ambang=MIN_FINGER_REACH):
    """True kalau jari menjulur ke depan, bukan terlipat kembali ke arah telapak.

    Diukur dari pergelangan supaya tahan rotasi tangan. Dipakai untuk menolak
    jempol yang kebetulan bersandar di jari menggulung: jaraknya nol, tapi ujung
    jarinya ada di belakang ruas pangkal, jadi bukan cubitan sungguhan.
    """
    jangkauan_mcp = hitung_jarak_px(pos_mcp, pos_pergelangan)
    if jangkauan_mcp <= 0:
        return False
    return hitung_jarak_px(pos_tip, pos_pergelangan) / jangkauan_mcp > ambang


def cek_gesture_voice(telunjuk_naik, tengah_naik, manis_naik, cubit_kanan):
    """True kalau telunjuk+tengah+manis terangkat dan jempol nempel kelingking."""
    return bool(telunjuk_naik and tengah_naik and manis_naik
                and cubit_kanan < VOICE_PINCH_MAX)


def clamp(nilai, batas_bawah, batas_atas):
    """Batasi nilai agar tidak keluar dari rentang [bawah, atas]."""
    return max(batas_bawah, min(nilai, batas_atas))


def hitung_area_aktif(lebar_frame, tinggi_frame, lebar_layar, tinggi_layar):
    """Kotak aktif di tengah frame, aspek rasionya dicocokkan ke layar.

    Dicocokkan supaya gain X dan Y sama; kalau tidak, gerak horizontal dan
    vertikal terasa beda kepekaannya. Balikkan (x0, y0, lebar, tinggi).
    """
    lebar = lebar_frame * ACTIVE_WIDTH
    tinggi = lebar * tinggi_layar / lebar_layar

    # Jangan sampai kotaknya lebih tinggi dari frame
    if tinggi > tinggi_frame:
        tinggi = float(tinggi_frame)
        lebar = tinggi * lebar_layar / tinggi_layar

    return ((lebar_frame - lebar) / 2.0, (tinggi_frame - tinggi) / 2.0,
            lebar, tinggi)


def petakan_ke_layar(ix, iy, area, lebar_layar, tinggi_layar):
    """Konversi koordinat frame kamera ke koordinat layar.

    `area` = (x0, y0, lebar, tinggi) dari hitung_area_aktif. Tangan tidak perlu
    mentok ke tepi kamera untuk menjangkau tepi layar.
    """
    x0, y0, lebar_aktif, tinggi_aktif = area

    nx = clamp(ix, x0, x0 + lebar_aktif)
    ny = clamp(iy, y0, y0 + tinggi_aktif)

    screen_x = (nx - x0) / lebar_aktif * lebar_layar
    screen_y = (ny - y0) / tinggi_aktif * tinggi_layar
    return screen_x, screen_y


def main():
    """Buka kamera, deteksi tangan, kirim aksi mouse."""
    apply_config(load_config())
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0  # Default 0.1s per panggilan: cukup untuk mencekik FPS
    cv2.setUseOptimized(True)
    set_high_performance()

    mouse = Mouse()
    lebar_layar, tinggi_layar = mouse.size()
    overlay = CursorOverlay()
    voice = VoiceTyping()

    mp_hands = mp.solutions.hands
    mp_drawing = mp.solutions.drawing_utils

    # FR-01: hanya 1 tangan, confidence >= 0.7
    hands = mp_hands.Hands(
        max_num_hands=1,
        model_complexity=MODEL_COMPLEXITY,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5,
    )

    # FR-07: cari kamera otomatis (index + backend apa pun yang jalan di device ini)
    print("[KAMERA] Mencari webcam...")
    kamera = buka_kamera_auto(CAMERA_RESOLUTION, TARGET_FPS)
    if kamera is None:
        print("[ERROR] Webcam tidak terdeteksi di index/backend mana pun!")
        print("  - Pastikan webcam tidak dipakai aplikasi lain (Zoom/Meet/Camera).")
        print("  - Cek izin kamera OS: Settings > Privacy > Camera (izinkan desktop app).")
        print("  - Cek proteksi webcam antivirus (McAfee/AVG): izinkan Python/app ini.")
        print("  - Webcam USB: coba cabut-colok; atau restart kalau driver nyangkut.")
        hands.close()
        return 1
    kamera.start()

    filter_x = OneEuroFilter(FILTER_MIN_CUTOFF, FILTER_BETA, FILTER_D_CUTOFF)
    filter_y = OneEuroFilter(FILTER_MIN_CUTOFF, FILTER_BETA, FILTER_D_CUTOFF)
    prediktor = VelocityPredictor(PREDICT_GAIN, VELOCITY_STOP, MAX_LEAD_MS)
    glide = OutputSmoother(GLIDE_MS)
    last_x = last_y = None
    pointer_hidup = False
    render_berikut = 0.0
    cursor_hz = 0.0
    cursor_moves = 0
    t_cursor = time.perf_counter()
    pos_telunjuk_lama = None  # Posisi telunjuk frame kamera sebelumnya (rem drift)
    det_kiri = DetektorKlik(ambang_on=PINCH_ON_KIRI, ambang_off=PINCH_OFF_KIRI)
    det_kanan = DetektorKlik(ambang_on=PINCH_ON_KANAN, ambang_off=PINCH_OFF_KANAN)
    det_scroll = DetektorKlik(ambang_on=PINCH_ON_SCROLL, ambang_off=PINCH_OFF_SCROLL)
    det_aktif = DetektorKlik()
    klik_terakhir = 0.0
    waktu_klik_kiri = 0.0   # Kapan klik kiri terakhir sah (buat timer double-click)
    double_sudah = False    # Sudah nembak double-click di tahan kali ini atau belum
    scroll_anchor_y = None  # Posisi Y pergelangan sebagai acuan usapan scroll
    scroll_acc_f = 0.0      # Akumulasi fraksi notch (biar usapan pelan tetap jalan)
    scroll_vel = 0.0        # Momentum notch/detik, lanjut sebentar setelah usapan berhenti
    voice_frames = 0        # Pose voice sudah ditahan berapa frame kamera
    voice_armed = True      # True = toggle boleh nembak lagi (wajib lepas dulu)
    area = None  # Dihitung saat frame pertama, perlu ukuran frame asli
    tangan_terakhir = 0.0
    fps = 0.0
    t_prev = time.perf_counter()
    frame_sebelumnya = None
    hasil_sebelumnya = None

    print(f"Hand Gesture Mouse jalan ({lebar_layar}x{tinggi_layar}). "
          "Tekan 'q' di window untuk keluar.")

    try:
        while True:
            frame = kamera.read()
            if frame is None:
                time.sleep(0.005)
                continue

            sekarang = time.perf_counter()
            dt = sekarang - t_prev
            t_prev = sekarang
            if dt > 0:
                fps += (1.0 / dt - fps) * 0.1

            # Mirror effect biar gerakan terasa natural
            frame = cv2.flip(frame, 1)
            tinggi_frame, lebar_frame = frame.shape[:2]

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_rgb.flags.writeable = False  # Hindari copy di dalam mediapipe
            # Frame kamera belum ganti (kamera 30fps, loop bisa 90fps+):
            # pakai hasil terakhir, jangan bebani MediaPipe dengan gambar sama.
            # Ini sumber delay + ngeframe kemarin.
            frame_baru = frame is not frame_sebelumnya
            frame_sebelumnya = frame
            if frame_baru or hasil_sebelumnya is None:
                # Proses versi kecilnya saja (lihat PROCESS_WIDTH/HEIGHT):
                # landmark ternormalisasi jadi tetap akurat di frame penuh.
                frame_kecil = cv2.resize(frame_rgb, (PROCESS_WIDTH, PROCESS_HEIGHT),
                                         interpolation=cv2.INTER_LINEAR)
                hasil = hands.process(frame_kecil)
                hasil_sebelumnya = hasil
            else:
                hasil = hasil_sebelumnya

            status = "NO HAND"
            info = ""

            if area is None:
                area = hitung_area_aktif(lebar_frame, tinggi_frame,
                                         lebar_layar, tinggi_layar)
                ax, ay, aw, ah = area
                print(f"Area aktif {aw:.0f}x{ah:.0f}px dari frame "
                      f"{lebar_frame}x{tinggi_frame} -> gain {lebar_layar / aw:.1f}x")

            ax, ay, aw, ah = area
            # Kotak area aktif (FR-06)
            cv2.rectangle(frame, (int(ax), int(ay)),
                          (int(ax + aw), int(ay + ah)), (255, 0, 0), 2)

            if hasil.multi_hand_landmarks:
                tangan_terakhir = sekarang
                # Edge case: ambil tangan pertama saja
                tangan = hasil.multi_hand_landmarks[0]
                landmarks = tangan.landmark

                # Skeleton dimatikan default (lihat DRAW_SKELETON): menggambar
                # 21 titik + koneksi tiap frame itu mahal, titik telunjuk cukup.
                if DRAW_SKELETON:
                    mp_drawing.draw_landmarks(frame, tangan, mp_hands.HAND_CONNECTIONS)

                def ke_px(idx):
                    lm = landmarks[idx]
                    return (int(lm.x * lebar_frame), int(lm.y * tinggi_frame))

                pos_pergelangan = ke_px(0)
                pos_jempol = ke_px(4)
                pos_telunjuk = ke_px(8)
                pos_tengah = ke_px(12)
                pos_manis = ke_px(16)
                pos_kelingking = ke_px(20)
                pos_telunjuk_mcp = ke_px(5)
                pos_tengah_mcp = ke_px(9)
                pos_manis_mcp = ke_px(13)
                pos_kelingking_mcp = ke_px(17)

                # Tandai ujung telunjuk (FR-06)
                cv2.circle(frame, pos_telunjuk, 8, (0, 255, 0), cv2.FILLED)

                telunjuk_naik = jari_menjangkau(
                    pos_telunjuk, pos_telunjuk_mcp, pos_pergelangan,
                    FINGER_EXTENDED)
                tengah_naik = jari_menjangkau(
                    pos_tengah, pos_tengah_mcp, pos_pergelangan,
                    FINGER_EXTENDED)
                manis_naik = jari_menjangkau(
                    pos_manis, pos_manis_mcp, pos_pergelangan, MANIS_NAIK)

                # Ukuran tangan jadi pembagi: ambang cubit ikut menyesuaikan
                # saat tangan maju/mundur dari kamera
                ukuran_tangan = max(
                    hitung_jarak_px(pos_pergelangan, pos_tengah_mcp), 1.0)
                cubit_telunjuk = hitung_jarak_px(pos_jempol, pos_telunjuk) / ukuran_tangan
                cubit_kiri = hitung_jarak_px(pos_jempol, pos_manis) / ukuran_tangan
                cubit_aktif = hitung_jarak_px(pos_jempol, pos_tengah) / ukuran_tangan
                cubit_kanan = hitung_jarak_px(pos_jempol, pos_kelingking) / ukuran_tangan

                manis_terbuka = jari_menjangkau(
                    pos_manis, pos_manis_mcp, pos_pergelangan, MIN_REACH_MANIS)
                tengah_terbuka = jari_menjangkau(
                    pos_tengah, pos_tengah_mcp, pos_pergelangan,
                    MIN_REACH_TENGAH_AKTIF)
                kelingking_terbuka = jari_menjangkau(
                    pos_kelingking, pos_kelingking_mcp, pos_pergelangan,
                    MIN_REACH_KELINGKING)

                # Pose voice typing mentah (tanpa debounce): 3 jari naik +
                # jempol nempel kelingking. Dipakai juga buat menahan klik
                # kanan: pose ini memang nempelin jempol+kelingking, jadi tanpa
                # gerbang ini tiap nyalain voice ikut nembak klik kanan.
                voice_pose = cek_gesture_voice(
                    telunjuk_naik, tengah_naik, manis_naik, cubit_kanan)

                # Pemenang cubit: yang paling dekat ke jempol dengan margin.
                # Tanpa ini, jari manis yang nekuk saat pointer (jempol+tengah)
                # jaraknya ikut kecil lalu nembak klik kiri liar.
                # Harus dihitung SEBELUM detektor di-update (dipakai di bawah).
                # Telunjuk (scroll) ikut jadi peserta biar satu cubitan = satu
                # pemenang: scroll tidak nembak saat klik, klik tidak nembak saat scroll.
                kiri_menang = (cubit_kiri + PINCH_MARGIN < cubit_aktif
                               and cubit_kiri + PINCH_MARGIN < cubit_kanan
                               and cubit_kiri + PINCH_MARGIN < cubit_telunjuk)
                kanan_menang = (cubit_kanan + PINCH_MARGIN < cubit_aktif
                                and cubit_kanan + PINCH_MARGIN < cubit_kiri
                                and cubit_kanan + PINCH_MARGIN < cubit_telunjuk)
                telunjuk_menang = (cubit_telunjuk + PINCH_MARGIN < cubit_aktif
                                   and cubit_telunjuk + PINCH_MARGIN < cubit_kiri
                                   and cubit_telunjuk + PINCH_MARGIN < cubit_kanan)

                # Detektor di-update hanya saat frame kamera baru (bukan tiap loop):
                # frame duplikat pakai data identik, jadi kalau ikut dihitung,
                # PINCH_FRAMES habis dalam 33ms oleh 1 frame noise = klik liar.
                # Syarat menang ikut jadi gerbang: cubitan yang bukan pemenang
                # dianggap lepas (lihat update(): not jari_terulur melepas latch),
                # jadi latch tidak nyangkut dan klik liar saat pointer tertahan.
                # det_aktif bukan tombol klik: return-nya diabaikan, yang dipakai
                # cuma flag ditahan-nya sebagai gerbang pointer.
                if frame_baru:
                    klik_kiri = det_kiri.update(cubit_kiri, manis_terbuka and kiri_menang)
                    det_aktif.update(cubit_aktif, tengah_terbuka)
                    klik_kanan = det_kanan.update(
                        cubit_kanan,
                        kelingking_terbuka and kanan_menang and not voice_pose)
                    # Scroll pakai latch "ditahan"-nya (bukan klik sekali). Telunjuk
                    # menekuk saat dicubit, jadi gerbangnya telunjuk_menang -- bukan
                    # syarat terulur (yang justru menolak cubitan sah).
                    det_scroll.update(cubit_telunjuk, telunjuk_menang)
                else:
                    klik_kiri = False
                    klik_kanan = False

                # Toggle voice typing: pose ditahan VOICE_FRAMES baru sah,
                # wajib lepas dulu sebelum bisa toggle lagi.
                if VOICE_ENABLED and frame_baru:
                    if voice_pose:
                        voice_frames += 1
                    else:
                        voice_frames = 0
                        voice_armed = True
                    if voice_frames >= VOICE_FRAMES and voice_armed:
                        voice_armed = False
                        voice_frames = 0
                        voice.toggle()

                pemenang = ('S' if telunjuk_menang else
                            ('K' if kiri_menang else
                             ('N' if kanan_menang else '-')))
                # Angka mentah buat kalibrasi: lihat nilainya saat klik/scroll sendiri
                info = (f"tlj{cubit_telunjuk:.2f} mns{cubit_kiri:.2f} "
                        f"tgh{cubit_aktif:.2f} klk{cubit_kanan:.2f}"
                        f"  ulur {'Y' if manis_terbuka else 'n'}"
                        f"{'Y' if tengah_terbuka else 'n'}"
                        f"{'Y' if kelingking_terbuka else 'n'}"
                        f"  menang:{pemenang}")

                # Prioritas gesture: klik > scroll > pointer (gerbang jempol+tengah) > standby
                if not det_kiri.ditahan:
                    # Cubitan dilepas: reset jatah double-click tahan berikutnya
                    double_sudah = False
                if not det_scroll.ditahan and scroll_anchor_y is not None:
                    # Cubit jempol+telunjuk dilepas: bersihkan acuan & momentum scroll
                    scroll_anchor_y = None
                    scroll_acc_f = 0.0
                    scroll_vel = 0.0
                if klik_kiri:
                    # Klik kiri: cubit jempol + jari manis. (Scroll sekarang gestur
                    # terpisah jempol+telunjuk, jadi di sini murni klik/double-click.)
                    if sekarang - klik_terakhir > CLICK_COOLDOWN:
                        mouse.click_left()
                        klik_terakhir = sekarang
                        waktu_klik_kiri = sekarang
                        status = "KLIK KIRI!"
                    else:
                        status = "COOLDOWN..."
                elif klik_kanan:
                    # Klik kanan: cubit jempol + kelingking
                    if sekarang - klik_terakhir > CLICK_COOLDOWN:
                        mouse.click_right()
                        klik_terakhir = sekarang
                        status = "KLIK KANAN!"
                    else:
                        status = "COOLDOWN..."
                elif det_scroll.ditahan:
                    # Scroll: cubit jempol+telunjuk ditahan, lalu usap tangan
                    # vertikal. Gerak dibaca dari pergelangan (posisi tangan
                    # keseluruhan). Pointer sengaja dibekukan selama scroll.
                    wy = pos_pergelangan[1]
                    if scroll_anchor_y is None:
                        scroll_anchor_y = wy
                        status = "SCROLL"
                    elif frame_baru:
                        # Sumbu Y gambar ke bawah: usap ke atas = dy positif.
                        dy = scroll_anchor_y - wy
                        scroll_anchor_y = wy
                        # Kecepatan dinormalisasi ke tinggi frame / detik.
                        speed = (dy / max(tinggi_frame, 1)) / max(dt, 1e-3)
                        boosted = speed * (1.0 + SCROLL_ACCEL * min(abs(speed), 4.0))
                        scroll_vel = (
                            SCROLL_MOMENTUM * scroll_vel
                            + (1.0 - SCROLL_MOMENTUM) * boosted * SCROLL_GAIN)
                    if scroll_anchor_y is not None:
                        scroll_acc_f += scroll_vel * max(dt, 0.0)
                        notch = int(scroll_acc_f)
                        notch = max(-SCROLL_MAX_NOTCH, min(SCROLL_MAX_NOTCH, notch))
                        if notch != 0:
                            mouse.scroll(notch)
                            scroll_acc_f -= notch
                            status = ("SCROLL UP" if notch > 0 else "SCROLL DOWN")
                        else:
                            status = "SCROLL"
                        # Rem pelan kalau tangan sudah diam, biar tidak nyangkut.
                        if frame_baru and abs(scroll_vel) < 0.4:
                            scroll_vel *= 0.5
                elif det_kiri.ditahan or det_kanan.ditahan:
                    # Pointer dibekukan selama cubitan klik ditahan, biar klik tidak meleset.
                    # Cubit kiri DITAHAN 0.6 dtk = double click (buat buka aplikasi).
                    if (det_kiri.ditahan and not double_sudah
                            and sekarang - waktu_klik_kiri > 0.6):
                        mouse.double_click()
                        double_sudah = True
                        status = "DOUBLE KLIK!"
                    else:
                        status = "TAHAN"
                elif det_aktif.ditahan:
                    # Gerbang pointer: jempol nempel tengah, telunjuk jadi pointer.
                    # Jempol lepas = det_aktif lepas = kursor diam.
                    if telunjuk_naik:
                        # Rem drift: diukur di koordinat frame (sebelum gain),
                        # jadi goyangan noise 1px tidak jadi 5px di layar.
                        if frame_baru:
                            if pos_telunjuk_lama is None:
                                geser = 999.0
                            else:
                                geser = hitung_jarak_px(pos_telunjuk, pos_telunjuk_lama)
                            pos_telunjuk_lama = pos_telunjuk
                        else:
                            geser = 0.0
                        if frame_baru and geser >= INPUT_DEAD_PX:
                            target_x, target_y = petakan_ke_layar(
                                pos_telunjuk[0], pos_telunjuk[1],
                                area, lebar_layar, tinggi_layar,
                            )
                            prediktor.push(target_x, target_y, sekarang)
                            pointer_hidup = True
                        elif frame_baru and geser < INPUT_DEAD_PX:
                            prediktor.vx = prediktor.vy = 0.0
                        if not pointer_hidup:
                            status = "POINTER (diam)"
                        elif sekarang >= render_berikut:
                            render_berikut = sekarang + 1.0 / max(RENDER_HZ, 1)
                            pred = prediktor.predict(sekarang)
                            if pred is None:
                                status = "POINTER (diam)"
                            else:
                                sx = filter_x(pred[0], sekarang)
                                sy = filter_y(pred[1], sekarang)
                                # Ease akhir di laju render: mulus antar frame kamera.
                                sx, sy = glide.update(sx, sy, sekarang)
                                if (last_x is None
                                        or abs(sx - last_x) > DEAD_ZONE_PX
                                        or abs(sy - last_y) > DEAD_ZONE_PX):
                                    mouse.move(sx, sy)
                                    cursor_moves += 1
                                    last_x, last_y = sx, sy
                                status = "POINTER"
                        else:
                            status = "POINTER"
                    else:
                        pointer_hidup = False
                        status = "AKTIF (angkat telunjuk)"
                else:
                    # Jempol tidak nempel ke tengah: kursor sengaja diam
                    status = "TEMPEL JEMPOL+TENGAN"
            elif sekarang - tangan_terakhir > 0.3:
                # Tangan hilang cukup lama: jangan menggeret pointer dari posisi lama
                filter_x.reset()
                filter_y.reset()
                prediktor.reset()
                glide.reset()
                pointer_hidup = False
                last_x = last_y = None
                pos_telunjuk_lama = None
                scroll_anchor_y = None
                scroll_acc_f = 0.0
                scroll_vel = 0.0
                det_kiri.reset()
                det_kanan.reset()
                det_scroll.reset()
                det_aktif.reset()

            # Pesan voice (toggle on/off, download model, error): tampil sesaat.
            if sekarang < voice.message_until:
                status = voice.message

            # Label status gesture (FR-06)
            cv2.putText(frame, status, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            if voice.active:
                cv2.putText(frame, "MIC ON", (lebar_frame - 130, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            if sekarang - t_cursor >= 1.0:
                cursor_hz = cursor_moves / (sekarang - t_cursor)
                cursor_moves = 0
                t_cursor = sekarang
            cv2.putText(frame, f"{fps:4.1f} FPS  cur {cursor_hz:4.0f}Hz",
                        (lebar_frame - 230, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
            cv2.putText(frame, info, (10, tinggi_frame - 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            cv2.putText(frame, "Tekan 'q' untuk keluar", (10, tinggi_frame - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

            cv2.imshow("Hand Gesture Mouse", frame)
            overlay.update(status, prediktor.vx, prediktor.vy)

            # FR-07: tekan 'q' untuk keluar bersih
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        try:
            overlay.close()
        except Exception:
            pass
        voice.stop()
        kamera.stop()
        cv2.destroyAllWindows()
        hands.close()
        if sys.platform == "win32":
            ctypes.windll.winmm.timeEndPeriod(1)

    print("Program berhenti. Kamera di-release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
