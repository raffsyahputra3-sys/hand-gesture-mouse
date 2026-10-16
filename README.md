# Hand Gesture Mouse Controller

Kendalikan pointer laptop tanpa mouse fisik — cukup pakai tangan + webcam laptop. Gratis, tanpa hardware tambahan.

## Fitur
- Gerakkan pointer: jempol nempel jari tengah + telunjuk sebagai pointer (jempol lepas = kursor diam)
- Klik kiri: cubit jempol + jari manis
- Double click: tahan cubit manis 0.6 detik (buat buka aplikasi/folder)
- Klik kanan: cubit jempol + kelingking
- Scroll: cubit jempol + manis 2x lalu tahan cubitan ke-2, usap tangan ke atas/bawah
- Voice typing offline Bahasa Indonesia: angkat telunjuk + tengah + manis bersamaan,
  tempelkan jempol ke kelingking untuk on/off. Selagi on, omongan diketik otomatis
  di aplikasi yang sedang fokus (klik dulu kolom teksnya). Model suara (~150MB)
  diunduh otomatis sekali saja saat pertama dinyalakan (butuh internet sekali itu).
- Preview real-time (skeleton tangan, area aktif, status gesture, FPS)
- Keluar dengan tekan `q`

Terasa halus seperti touchpad:
- Smoothing adaptif (One Euro filter) — halus saat gerak pelan, responsif saat cepat
- Dead zone anti-getar, jadi pointer benar-benar diam saat tangan diam
- Ambang cubit dinormalisasi ke ukuran tangan, jadi klik tetap akurat walau tangan maju/mundur dari kamera
- Histeresis klik: harus benar-benar lepas sebelum bisa klik lagi, tidak ada klik dobel liar
- Klik hanya sah kalau jari yang dicubit benar-benar menjulur, jadi jempol yang bersandar di jari menggulung tidak terbaca sebagai klik
- Cubitan harus bertahan 3 frame, jadi noise landmark sekejap tidak jadi klik
- Pointer dibekukan selama cubitan ditahan, supaya klik tidak meleset
- Deteksi jari berdiri diukur dari jangkauan ke pergelangan, bukan "ujung di atas sendi", jadi pointer tidak mati saat tangan dimiringkan atau telunjuk menunjuk ke depan
- Kamera dibaca di thread terpisah, selalu frame terbaru (tanpa ini pointer terasa tertinggal)
- Jalur cepat Windows: kursor digerakkan via `ctypes`, prioritas proses dinaikkan ke High

## Syarat
- Python 3.10+
- Webcam built-in (720p)
- OS: Windows 10/11, macOS 12+, Ubuntu 20.04+
- RAM 4GB+, CPU dual-core

## Setup (≤ 10 menit)

```bash
# 1. Clone / download folder ini
# 2. (Opsional) bikin virtual env
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

# 3. Install dependency
pip install -r requirements.txt

# 4. Jalankan
python hand_mouse.py
```

**Windows:** cukup klik 2x `JALANKAN.bat` — tidak perlu buka terminal.

> Penting: versi mediapipe di-pin ke `0.10.21`. Mediapipe 1.x sudah membuang
> modul `mp.solutions`, jadi script ini tidak jalan di sana. Download pertama
> kali agak besar (~115MB termasuk jaxlib), sabar kalau koneksi lambat.

Kalau di Linux butuh tambahan (untuk pyautogui / mouse control):
```bash
sudo apt install python3-tk python3-dev scrot
```

## Cara Pakai

1. Duduk 30–80 cm dari kamera, cahaya ruangan normal.
2. Buka `python hand_mouse.py`, muncul window "Hand Gesture Mouse".
3. Gesture:

| Gesture | Aksi |
|---------|------|
| Jempol nempel jari tengah + telunjuk gerak | Pointer |
| Jempol lepas dari jari tengah | Kursor diam (sengaja) |
| Cubit jempol + jari manis (rapat) | Klik kiri |
| Tahan cubit manis 0.6 detik | Double click (buka aplikasi) |
| Cubit jempol + kelingking | Klik kanan |
| Cubit manis 2x + tahan, usap atas | Scroll up |
| Cubit manis 2x + tahan, usap bawah | Scroll down |
| 3 jari naik + jempol nempel kelingking | Voice typing on/off |
| Tekan `q` | Keluar |

4. Kotak biru di preview = area aktif. Tangan di dalam kotak biar pointer capai seluruh layar.

## Konfigurasi

Semua di atas file `hand_mouse.py`:

```python
CAMERA_RESOLUTION = (480, 360)
TARGET_FPS = 30           # webcam laptop umumnya mentok 30
MODEL_COMPLEXITY = 0    # 0 = lite (tercepat), 1 = lebih akurat tapi lebih berat
ACTIVE_WIDTH = 0.40     # lebar kotak aktif sebagai fraksi lebar frame

FILTER_MIN_CUTOFF = 0.35 # naikkan kalau pointer terasa ketinggalan/ngeframe
FILTER_BETA = 0.06      # naikkan kalau terasa ngambang/lambat saat gerak cepat
FILTER_D_CUTOFF = 0.5
DEAD_ZONE_PX = 0.5      # kecilkan kalau pointer patah-patah/steppy

PINCH_ON = 0.45         # rasio cubit untuk memicu (mode gampang-nempel)
PINCH_OFF = 0.65        # rasio untuk dianggap lepas
PINCH_FRAMES = 3        # cubitan harus bertahan sekian frame
MIN_REACH_MANIS = 0.70  # ambang ulur jari manis (klik kiri)
MIN_REACH_TENGAH_AKTIF = 0.75 # ambang ulur tengah (gerbang pointer)
MIN_REACH_KELINGKING = 0.70   # ambang ulur kelingking (klik kanan)
FINGER_EXTENDED = 1.00  # ambang telunjuk dianggap menunjuk (pointer)
CLICK_COOLDOWN = 0.35   # detik minimum antar klik
```

Tips:
- Pointer mati padahal telunjuk masih menunjuk? Turunkan `FINGER_EXTENDED` ke 0.9.
- Pointer jalan padahal tangan cuma santai/menggenggam? Naikkan `FINGER_EXTENDED` ke 1.2.
- Tangan harus bergerak terlalu jauh? Turunkan `ACTIVE_WIDTH` ke 0.30 (gain jadi ~6.7x).
- Pointer terlalu sensitif / susah presisi? Naikkan `ACTIVE_WIDTH` ke 0.50–0.55.
- Pointer goyang saat tangan diam? Turunkan `FILTER_MIN_CUTOFF` ke 0.15, atau naikkan `DEAD_ZONE_PX` ke 1.5.
- Pointer terasa lambat/ngeframe? Naikkan `FILTER_MIN_CUTOFF` ke 0.5 dan `FILTER_BETA` ke 0.1.
- Susah cubit? Naikkan `PINCH_ON` ke 0.55.
- Masih klik sendiri? Turunkan `PINCH_ON` ke 0.3, naikkan `PINCH_FRAMES` ke 3–4.
- Klik sering dobel? Lebarkan jarak `PINCH_ON` ↔ `PINCH_OFF`, atau naikkan `CLICK_COOLDOWN`.

Angka `cubit mns.. tgh.. klk..` di preview adalah rasio mentahnya. Kalau klik masih
meleset, lihat angka itu saat gesture yang bermasalah: `PINCH_ON` harus di bawah
nilai saat tangan santai, dan di atas nilai saat benar-benar mencubit.

> Catatan soal klik kiri/kanan: jari manis & kelingking lebih pendek dan saat
> dicubit menekuk lebih dalam, jadi ambangnya (`MIN_REACH_MANIS`,
> `MIN_REACH_KELINGKING` 0.70) memang longgar. Kalau klik terasa rewel, cubit
> dengan jari agak menjulur ke depan (jangan ditekuk penuh ke telapak).
- Mau akurasi lebih tinggi dan rela kehilangan FPS? Set `MODEL_COMPLEXITY = 1`.

Angka filter di atas hasil sweep parameter, bukan kira-kira: pointer diam total
saat tangan diam, dan telat ~30 ms saat tangan bergerak cepat.

> `ACTIVE_WIDTH` dan angka filter saling terkait. Kotak yang lebih kecil berarti
> gain lebih tinggi, dan gain ikut mengalikan noise landmark — jadi kalau
> `ACTIVE_WIDTH` diubah banyak, `FILTER_MIN_CUTOFF` / `DEAD_ZONE_PX` perlu
> disesuaikan lagi, kalau tidak pointer mulai bergetar saat tangan diam.

## Troubleshooting

| Masalah | Solusi |
|---------|--------|
| `[ERROR] Webcam tidak terdeteksi` | Tutup Zoom/Meet, cek privacy kamera OS, coba `cv2.VideoCapture(1)` |
| Tangan tidak terdeteksi | Perbaiki cahaya, jarak 30–80 cm, background polos |
| Pointer berhenti saat telunjuk ditekuk / tangan dimiringkan | Turunkan `FINGER_EXTENDED` (misal 1.05) |
| Pointer beku terus setelah klik | Jauhkan jempol dari jari manis. Kalau masih, naikkan `PINCH_OFF` |
| Tangan harus bergerak jauh untuk lintas layar | Kecilkan `ACTIVE_WIDTH` (misal 0.30) |
| Pointer terlalu sensitif, susah presisi | Besarkan `ACTIVE_WIDTH` (misal 0.55) |
| Klik spam / double | Naikkan `CLICK_COOLDOWN` ke 0.8–1.0 |
| Klik sendiri padahal cuma menunjuk | Jempol bersandar di jari yang menggulung. Naikkan `MIN_FINGER_REACH` ke 1.05, atau jauhkan jempol dari jari tengah |
| `pip install mediapipe` gagal di Python 3.13 | Pakai Python 3.10–3.11 (paling stabil) |
| `AttributeError: module 'mediapipe' has no attribute 'solutions'` | Mediapipe 1.x. Downgrade: `pip install "mediapipe==0.10.21"` |
| `numpy` error / binary incompatibility | Mediapipe 0.10.x butuh numpy 1.x: `pip install "numpy<2"` |
| Download jaxlib lambat / timeout | `pip install "mediapipe==0.10.21" --timeout 100`, ulangi — wheel yang sudah ke-download di-cache |
| FPS rendah (<20) | Turunkan resolusi ke (480, 360), tutup app berat |
| `pyautogui` error di Linux | `sudo apt install python3-tk python3-dev scrot` |
| Window freeze / hanging | Tekan `q` di window (bukan Ctrl+C di terminal), pastikan `kamera.release()` kepanggil |

## Struktur
```
hand-gesture-mouse/
├── hand_mouse.py      # Main script (single file)
├── JALANKAN.bat       # Launcher Windows (klik 2x)
├── requirements.txt   # Dependencies
└── README.md          # Dokumentasi ini
```

## Roadmap
- v1.1 Drag & drop (cubit tahan)
- v1.2 Media control (play/pause, volume)
- v1.3 Double click
- v1.4 GUI settings
- v2.0 Mode presentasi

Lisensi: MIT (bebas pakai, open-source).
