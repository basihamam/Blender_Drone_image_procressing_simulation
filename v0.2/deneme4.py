"""
DRONE CANLI GÖRÜNTÜ İZLEYİCİ  v12 hehehehheheheheh ALEXANDER JOJO
=====================================
Düzeltmeler:
  1. Ayarlar paneli çift flip sorunu giderildi (draw() kendi flip'ini yapar,
     settings açıkken tek flip kullanılır).
  2. CANLI mod (4 tuşu) kaldırıldı — live_fetch ayarlardan açılır/kapanır.
     Modlar: 1=HIZLI  2=NORMAL  3=KESİN
  3. Spiral mantığı tamamen yeniden yazıldı:
     - Spiral uçarken renk görürse → DUR, konumu kaydet
     - Önce görülen / en yakın renge git, yükü bırak
     - Kaydettiğin spiral noktasına geri dön, spirale devam et
     - İkinci rengi de görürse → oraya git, yükü bırak, eve dön
"""

import socket, base64, json, time, io, math, threading, sys, os
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

try:
    import pygame
except Exception as e:
    print(f"pygame yuklenemedi: {e}")
    sys.exit(1)

# ─────────────────────────────────────────
# SABİT PARAMETRELER
# ─────────────────────────────────────────
BLENDER_HOST = "127.0.0.1"
BLENDER_PORT = 9999

RED_L1  = np.array([0,   50, 50]);   RED_U1  = np.array([15,  255, 255])
RED_L2  = np.array([160, 50, 50]);   RED_U2  = np.array([180, 255, 255])
BLUE_L  = np.array([90,  50, 50]);   BLUE_U  = np.array([140, 255, 255])
MIN_AREA = 100

REFRESH_INTERVAL = 0.1
MANUAL_STEP      = 0.3
DRONE_HEIGHT     = 5.0
DROP_HEIGHT      = 1.5
DROP_WAIT        = 2.0

THRESH_FAST    = 18
THRESH_NORMAL  = 38
THRESH_PRECISE = 60

MARKER_HALF     = 14
CORNER_LEN      = 18
SERVO_LOOP_WAIT = 0.18

SCENE_W = 35.0
SCENE_H = 26.0

SPIRAL_START_X    = 0.0
SPIRAL_START_Y    = 0.0
SPIRAL_CENTER_X   = 14.0
SPIRAL_CENTER_Y   = -2.0
SPIRAL_TURNS      = 5
SPIRAL_PTS_PER    = 24
SPIRAL_MOVE_WAIT  = 0.15
SPIRAL_FLY_SPEED  = 0.12
SPIRAL_FLY_DELAY  = 0.03
SPIRAL_SCAN_EVERY = 3

DESCENT_STEP  = 0.30
DESCENT_DELAY = 0.06

# Planlama ekranı dünya sınırları (spiral alanını kapsayacak şekilde)
# Harita moduna girilmeden önceki varsayılan (fallback) dünya sınırları.
# Gerçek sınırlar ENTER_MAP ile Blender'daki Sketchfab_model collection'ından okunur.
PLAN_WORLD_X0_DEFAULT, PLAN_WORLD_X1_DEFAULT = -10.0, 10.0
PLAN_WORLD_Y0_DEFAULT, PLAN_WORLD_Y1_DEFAULT = -10.0, 10.0

WP_ACTIONS = ["none", "hover", "photo", "scan"]
WP_ACTION_LABELS = {"none": "Gec", "hover": "Bekle", "photo": "Foto", "scan": "Tara"}
WP_ACTION_COLORS = {"none": (150,150,170), "hover": (230,200,60),
                     "photo": (60,210,120), "scan": (60,220,200)}

PANEL_W  = 640
PANEL_H  = 480
GAP      = 6
LEFT_W   = 240   # sol dikey panel (üst yazılar)
RIGHT_W  = 260   # sag dikey panel (alt yazılar)
WIN_W    = LEFT_W + RIGHT_W + PANEL_W*2 + GAP*4
WIN_H    = PANEL_H*2 + GAP*3

SETTINGS_W = 320

# ─────────────────────────────────────────
# RENKLER
# ─────────────────────────────────────────
C_BG       = (10,  12,  18)
C_PANEL_BG = (18,  22,  32)
C_BORDER   = (40,  50,  70)
C_TEXT     = (200, 210, 230)
C_DIM      = (90,  100, 120)
C_RED      = (230, 60,  60)
C_BLUE     = (60,  130, 230)
C_GREEN    = (60,  210, 120)
C_YELLOW   = (230, 200, 60)
C_ORANGE   = (230, 140, 40)
C_WHITE    = (255, 255, 255)
C_CYAN     = (60,  220, 200)
C_PURPLE   = (170, 80,  230)

# CANLI mod kaldırıldı — sadece 3 mod
MODE_COLORS = {
    "fast":    (60,  210, 120),
    "normal":  (230, 200, 60),
    "precise": (230, 60,  60),
}
MODE_LABELS = {
    "fast":    "HIZLI",
    "normal":  "NORMAL",
    "precise": "KESIN",
}
MODE_THRESH = {
    "fast":    THRESH_FAST,
    "normal":  THRESH_NORMAL,
    "precise": THRESH_PRECISE,
}
ORDER_LABELS = {
    "red_first":  "R-once",
    "blue_first": "B-once",
    "auto":       "Otomatik",
}
LABEL_COLORS = {
    "Orijinal Goruntu": (160, 170, 190),
    "Kirmizi Mask":     C_RED,
    "Mavi Mask":        C_BLUE,
    "Tespit Sonucu":    C_GREEN,
}

# ─────────────────────────────────────────
# AYARLAR
# ─────────────────────────────────────────
class Settings:
    def __init__(self):
        self.safe_border_enabled  = True
        self.slow_descent_enabled = True
        self.live_fetch_enabled   = True   # Sürekli görüntü yenileme (ayarlardan)
        self.show_masks           = True
        self.show_hud             = True
        self.fullscreen           = False
        self.safe_border_px  = 60
        self.descent_step    = DESCENT_STEP
        self.descent_delay   = DESCENT_DELAY

    def toggle(self, key):
        setattr(self, key, not getattr(self, key))

    def adjust(self, key, delta):
        val = getattr(self, key)
        if key == "safe_border_px":
            val = max(10, min(200, int(val + delta)))
        elif key == "descent_step":
            val = round(max(0.02, min(1.0, val + delta * 0.01)), 2)
        elif key == "descent_delay":
            val = round(max(0.01, min(0.5,  val + delta * 0.01)), 2)
        setattr(self, key, val)


# ─────────────────────────────────────────
# FONT
# ─────────────────────────────────────────
pygame.init()

_FONT_CANDIDATES = [
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_FONT_PATH = None
_FONT_IS_DEFAULT = True
for _fp in _FONT_CANDIDATES:
    if os.path.isfile(_fp):
        try:
            ImageFont.truetype(_fp, 12)
            _FONT_PATH = _fp
            _FONT_IS_DEFAULT = False
            break
        except Exception:
            pass

_text_cache: dict = {}
_CACHE_MAX = 512

def pil_render_text(text, size=14, color=(255, 255, 255)):
    key = (text, size, color)
    if key in _text_cache:
        return _text_cache[key]
    font = (ImageFont.truetype(_FONT_PATH, size)
            if not _FONT_IS_DEFAULT and _FONT_PATH else ImageFont.load_default())
    tmp  = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = tmp.textbbox((0, 0), text, font=font)
    w = max(bbox[2] - bbox[0] + 4, 1)
    h = max(bbox[3] - bbox[1] + 4, 1)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((2 - bbox[0], 2 - bbox[1]), text, fill=color, font=font)
    surf = pygame.image.frombuffer(img.tobytes(), img.size, img.mode).convert_alpha()
    if len(_text_cache) >= _CACHE_MAX:
        for k in list(_text_cache)[:_CACHE_MAX // 2]:
            del _text_cache[k]
    _text_cache[key] = surf
    return surf

def draw_text(screen, text, pos, size=14, color=C_TEXT, shadow=True):
    if shadow:
        screen.blit(pil_render_text(text, size, (0, 0, 0)), (pos[0]+1, pos[1]+1))
    screen.blit(pil_render_text(text, size, color), pos)


# ─────────────────────────────────────────
# BLENDER
# ─────────────────────────────────────────
def send_command(cmd, timeout=90.0):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((BLENDER_HOST, BLENDER_PORT))
            s.sendall(f"{cmd}\n".encode())
            buf = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
                if buf.endswith(b"\n"):
                    break
        return buf.decode().strip()
    except ConnectionRefusedError:
        return "ERROR:connection_refused"
    except Exception as e:
        return f"ERROR:{e}"

def ping():
    return send_command("PING", timeout=5.0) == "PONG"

def get_image():
    resp = send_command("GET_IMAGE", timeout=120)
    if resp.startswith("IMAGE:"):
        img_bytes = base64.b64decode(resp[6:])
        pil = Image.open(io.BytesIO(img_bytes))
        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    return None

def get_position():
    resp = send_command("GET_POSITION")
    if resp.startswith("POSITION:"):
        return json.loads(resp[9:])
    return {"x": 0.0, "y": 0.0, "z": DRONE_HEIGHT}

def move_to(x, y, z=DRONE_HEIGHT):
    return send_command(f"MOVE_DRONE:{x:.4f},{y:.4f},{z:.4f}") == "OK"


# ── HARİTA (Sketchfab_model collection'ından otomatik sınır + ortografik cekim) ──
def enter_map():
    """Kamerayı harita moduna al, collection sınırlarını oku. Bounds dict ya da None."""
    resp = send_command("ENTER_MAP", timeout=30.0)
    if resp.startswith("BOUNDS:"):
        try:
            return json.loads(resp[7:])
        except Exception:
            return None
    return None

def capture_map(scale_mult=1.0, offset_x=0.0, offset_y=0.0):
    """Verilen zoom/pan ile ortografik harita görüntüsü çeker. BGR numpy döner ya da None."""
    resp = send_command(f"CAPTURE_MAP:{scale_mult:.4f},{offset_x:.4f},{offset_y:.4f}",
                        timeout=120.0)
    if resp.startswith("IMAGE:"):
        img_bytes = base64.b64decode(resp[6:])
        pil = Image.open(io.BytesIO(img_bytes))
        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    return None

def exit_map():
    """Kamerayı harita moduna girmeden önceki haline geri döndürür."""
    return send_command("EXIT_MAP", timeout=15.0) == "OK"


# ─────────────────────────────────────────
# SPIRAL ÜRET
# ─────────────────────────────────────────
def make_inward_spiral(sx, sy, cx, cy, turns, pts):
    dx, dy = sx - cx, sy - cy
    r0 = math.sqrt(dx*dx + dy*dy)
    a0 = math.atan2(dy, dx)
    total = turns * pts
    result = []
    for i in range(total):
        t = i / max(total - 1, 1)
        r = r0 * (1 - t)
        a = a0 - 2 * math.pi * turns * t
        result.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return result


# ─────────────────────────────────────────
# GÖRÜNTÜ İŞLEME
# ─────────────────────────────────────────
def detect_colors(bgr):
    h, w = bgr.shape[:2]
    cx, cy = w // 2, h // 2
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    kernel = np.ones((5, 5), np.uint8)
    mr1 = cv2.inRange(hsv, RED_L1, RED_U1)
    mr2 = cv2.inRange(hsv, RED_L2, RED_U2)
    mask_r = cv2.morphologyEx(cv2.bitwise_or(mr1, mr2), cv2.MORPH_OPEN, kernel)
    mask_b = cv2.morphologyEx(cv2.inRange(hsv, BLUE_L, BLUE_U), cv2.MORPH_OPEN, kernel)
    dets = {}
    for color, mask in [("red", mask_r), ("blue", mask_b)]:
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if cnts:
            big = max(cnts, key=cv2.contourArea)
            area = cv2.contourArea(big)
            if area > MIN_AREA:
                M = cv2.moments(big)
                if M["m00"] > 0:
                    px_ = int(M["m10"] / M["m00"])
                    py_ = int(M["m01"] / M["m00"])
                    ddx, ddy = px_ - cx, py_ - cy
                    dets[color] = {
                        "px": px_, "py": py_, "dx": ddx, "dy": ddy,
                        "dist_px": math.sqrt(ddx*ddx + ddy*ddy),
                        "area": area,
                        "bx": (px_ / w - 0.5) * SCENE_W,
                        "by": (0.5 - py_ / h) * SCENE_H,
                    }
    return dets, w, h


def corner_rect_cv(img, cx, cy, half, color, thickness=1, cl=18):
    x1, y1, x2, y2 = cx-half, cy-half, cx+half, cy+half
    segs = [
        ((x1,y1),(x1+cl,y1)), ((x1,y1),(x1,y1+cl)),
        ((x2,y1),(x2-cl,y1)), ((x2,y1),(x2,y1+cl)),
        ((x1,y2),(x1+cl,y2)), ((x1,y2),(x1,y2-cl)),
        ((x2,y2),(x2-cl,y2)), ((x2,y2),(x2,y2-cl)),
    ]
    for p1, p2 in segs:
        cv2.line(img, p1, p2, color, thickness)


def process_frame(bgr, active_mode="normal", settings=None):
    if settings is None:
        settings = Settings()
    dets, w, h = detect_colors(bgr)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    kernel = np.ones((5, 5), np.uint8)
    mr1 = cv2.inRange(hsv, RED_L1, RED_U1)
    mr2 = cv2.inRange(hsv, RED_L2, RED_U2)
    mask_r = cv2.morphologyEx(cv2.bitwise_or(mr1, mr2), cv2.MORPH_OPEN, kernel)
    mask_b = cv2.morphologyEx(cv2.inRange(hsv, BLUE_L, BLUE_U), cv2.MORPH_OPEN, kernel)

    panel_orig = cv2.resize(bgr, (PANEL_W, PANEL_H))
    rv = np.zeros_like(bgr); rv[mask_r > 0] = [0, 60, 200]
    panel_red  = cv2.resize(rv, (PANEL_W, PANEL_H))
    bv = np.zeros_like(bgr); bv[mask_b > 0] = [200, 60, 0]
    panel_blue = cv2.resize(bv, (PANEL_W, PANEL_H))

    result = bgr.copy()
    overlay = result.copy()
    overlay[mask_r > 0] = [0, 40, 180]
    overlay[mask_b > 0] = [180, 40, 0]
    cv2.addWeighted(overlay, 0.35, result, 0.65, 0, result)

    cx, cy = w // 2, h // 2

    if settings.safe_border_enabled:
        b = settings.safe_border_px
        cv2.rectangle(result, (b, b), (w-b, h-b), (0, 180, 255), 1)
        cl2 = 20
        for (bx_, by_) in [(b,b),(w-b,b),(b,h-b),(w-b,h-b)]:
            dx_ = 1 if bx_ == b else -1
            dy_ = 1 if by_ == b else -1
            cv2.line(result, (bx_, by_), (bx_+dx_*cl2, by_), (0, 200, 255), 2)
            cv2.line(result, (bx_, by_), (bx_, by_+dy_*cl2), (0, 200, 255), 2)

    corner_rect_cv(result, cx, cy, THRESH_PRECISE, (60, 60, 200), 1, CORNER_LEN)
    corner_rect_cv(result, cx, cy, THRESH_NORMAL,  (0, 200, 230), 1, CORNER_LEN)
    corner_rect_cv(result, cx, cy, THRESH_FAST,    (40, 200, 40), 1, CORNER_LEN)

    act_thresh = MODE_THRESH.get(active_mode, THRESH_NORMAL)
    act_col = {"fast":(40,210,40),"normal":(0,210,230),"precise":(40,40,230)}.get(
        active_mode, (200,200,200))
    corner_rect_cv(result, cx, cy, act_thresh, act_col, 2, CORNER_LEN+4)

    cv2.line(result, (cx-12, cy), (cx+12, cy), (220, 220, 220), 1)
    cv2.line(result, (cx, cy-12), (cx, cy+12), (220, 220, 220), 1)
    cv2.circle(result, (cx, cy), 3, (220, 220, 220), -1)

    for color, info in dets.items():
        px_, py_ = info["px"], info["py"]
        dx_, dy_ = info["dx"], info["dy"]
        bgr_col = (0, 60, 220) if color == "red" else (220, 60, 0)
        hs = MARKER_HALF
        cv2.rectangle(result, (px_-hs, py_-hs), (px_+hs, py_+hs), bgr_col, -1)
        cv2.rectangle(result, (px_-hs-2, py_-hs-2), (px_+hs+2, py_+hs+2), (255,255,255), 2)
        cv2.line(result, (px_-22, py_), (px_+22, py_), (255,255,255), 1)
        cv2.line(result, (px_, py_-22), (px_, py_+22), (255,255,255), 1)
        cv2.line(result, (cx, cy), (px_, py_), bgr_col, 1)
        lbl = "KIRMIZI" if color == "red" else "MAVI"
        cv2.putText(result, lbl, (px_+hs+4, py_-6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, bgr_col, 1, cv2.LINE_AA)
        cv2.putText(result, f"dx={dx_:+d} dy={dy_:+d}", (px_+hs+4, py_+12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (160,220,160), 1, cv2.LINE_AA)

    panel_result = cv2.resize(result, (PANEL_W, PANEL_H))
    stats = {
        "red_px":  cv2.countNonZero(mask_r),
        "blue_px": cv2.countNonZero(mask_b),
        "img_w": w, "img_h": h,
    }
    return panel_orig, panel_red, panel_blue, panel_result, dets, stats


def bgr_to_surface(bgr):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return pygame.surfarray.make_surface(rgb.transpose(1, 0, 2))


# ─────────────────────────────────────────
# GÖREV  –  YENİDEN YAZILMIŞ SPİRAL
# ─────────────────────────────────────────
class Waypoint:
    """Kullanıcının plan ekranında tıklayarak eklediği konum noktası."""
    def __init__(self, x, y, z=None, action="none"):
        self.x = x
        self.y = y
        self.z = z if z is not None else DRONE_HEIGHT
        self.action = action  # "none" | "hover" | "photo" | "scan"

    def as_tuple(self):
        return (self.x, self.y, self.z, self.action)


class MissionRunner:
    def __init__(self, log_fn, frame_push_fn, settings_ref):
        self.log        = log_fn
        self.push_frame = frame_push_fn
        self.cfg        = settings_ref
        self.running    = False
        self.stop_evt   = threading.Event()
        self.payloads   = {"red": True, "blue": True}
        self.drone_pos  = {"x": 0.0, "y": 0.0, "z": DRONE_HEIGHT}
        self.current_offset = {}
        self.spiral_path = []
        self.spiral_idx  = 0
        self.mode        = "normal"
        self.color_order = "red_first"
        self.mission_type = "spiral"   # "spiral" | "waypoints"
        self.waypoints     = []        # Waypoint listesi (planlama ekranından)
        self.wp_idx        = 0

    def start(self, mode="normal", color_order="red_first",
             mission_type="spiral", waypoints=None):
        if self.running:
            self.log("Gorev zaten calisiyor!"); return
        self.stop_evt.clear()
        self.payloads      = {"red": True, "blue": True}
        self.mode          = mode
        self.color_order   = color_order
        self.mission_type  = mission_type
        self.waypoints     = waypoints or []
        self.wp_idx        = 0
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.stop_evt.set()

    def _world_pos_of(self, color, dets, drone_x, drone_y):
        """Kamerada görülen rengin dünya koordinatını tahmin et."""
        if color in dets:
            return drone_x + dets[color]["bx"], drone_y + dets[color]["by"]
        return drone_x, drone_y

    # ── smooth yatay uçuş ───────────────────────────────────────
    def _fly_to(self, tx, ty, height=DRONE_HEIGHT):
        pos = get_position()
        cx, cy = pos.get("x", 0.0), pos.get("y", 0.0)
        while not self.stop_evt.is_set():
            ddx, ddy = tx - cx, ty - cy
            dist = math.sqrt(ddx*ddx + ddy*ddy)
            if dist < SPIRAL_FLY_SPEED:
                move_to(tx, ty, height)
                self.drone_pos = {"x": tx, "y": ty, "z": height}
                return True
            sx = (ddx/dist) * SPIRAL_FLY_SPEED
            sy = (ddy/dist) * SPIRAL_FLY_SPEED
            cx += sx; cy += sy
            move_to(cx, cy, height)
            self.drone_pos = {"x": cx, "y": cy, "z": height}
            time.sleep(SPIRAL_FLY_DELAY)
        return False

    # ── alçalma ────────────────────────────────────────────────
    def _descend_slow(self, tx, ty, color, target_z):
        pos = get_position()
        cur_z = pos.get("z", DRONE_HEIGHT)
        self.log(f"  Inis: {cur_z:.2f}→{target_z:.2f}")
        while cur_z > target_z + 0.01 and not self.stop_evt.is_set():
            cur_z = max(target_z, cur_z - self.cfg.descent_step)
            move_to(tx, ty, cur_z)
            self.drone_pos = {"x": tx, "y": ty, "z": cur_z}
            time.sleep(self.cfg.descent_delay)
        move_to(tx, ty, target_z)
        self.drone_pos = {"x": tx, "y": ty, "z": target_z}
        return tx, ty

        # ── merkezleme ──────────────────────────────────────────────
    def _center_on(self, color, label, thresh_px, height,
                   step_scale=0.08, max_step=0.25, stable_need=3, max_iter=200):
        self.log(f"  Merkezleniyor: {label} esik=±{thresh_px}px")
        time.sleep(1.0)
        no_det = 0; stable = 0
        for step in range(max_iter):
            if self.stop_evt.is_set(): return False
            bgr = get_image()
            if bgr is None: time.sleep(0.3); continue
            self.push_frame(bgr)
            dets, _, _ = detect_colors(bgr)
            if color not in dets:
                no_det += 1; stable = 0
                if no_det >= 8:
                    self.log(f"  {label} kayboldu"); return False
                time.sleep(0.3); continue
            no_det = 0
            info = dets[color]
            dx_, dy_, dist_ = info["dx"], info["dy"], info["dist_px"]
            self.current_offset[color] = {"dx": dx_, "dy": dy_, "dist_px": dist_}
            in_box = (abs(dx_) < thresh_px and abs(dy_) < thresh_px)
            if step % 4 == 0:
                self.log(f"  [{step}] dx={dx_:+d} dy={dy_:+d} {'OK' if in_box else '--'}")
            if in_box:
                stable += 1
                if stable >= stable_need:
                    pf = get_position()
                    self.log(f"  Merkez OK ({pf.get('x',0):.2f},{pf.get('y',0):.2f})")
                    self.current_offset.pop(color, None)
                    return True
            else:
                stable = 0
                sy_ = max(-max_step, min(max_step, dx_ * step_scale))
                sx_ = max(-max_step, min(max_step, dy_ * step_scale))
                pos = get_position(); self.drone_pos = pos
                move_to(pos["x"] - sx_, pos["y"] - sy_, height)
            time.sleep(SERVO_LOOP_WAIT)
        self.log(f"  Maks iter ({label})")
        return False

    # ── yük bırak ───────────────────────────────────────────────
    def _drop(self, color):
        self.log(f"  Servo: {color.upper()} bırakılıyor...")
        for i in range(5):
            self.log(f"    %{(i+1)*20}")
            time.sleep(DROP_WAIT / 5)
        self.payloads[color] = False
        self.log(f"  {color.upper()} bırakıldı!")

    # ── bir renge git, bırak, geri dön ──────────────────────────
    def _deliver(self, color, label, resume_x, resume_y):
        """
        Verilen rengin üstüne git, merkezle, alçal, bırak.
        Sonra resume_x/resume_y noktasına geri dön.
        """
        self.log(f"=== TESLİMAT: {label} ===")
        # Merkezle
        thresh = MODE_THRESH.get(self.mode, THRESH_NORMAL)
        scale  = {"fast":0.10,"normal":0.08,"precise":0.07}.get(self.mode, 0.08)
        mstep  = {"fast":0.30,"normal":0.25,"precise":0.20}.get(self.mode, 0.25)
        stable = {"fast":2,   "normal":3,   "precise":3  }.get(self.mode, 3)

        ok = self._center_on(color, label, thresh, DRONE_HEIGHT,
                             step_scale=scale, max_step=mstep, stable_need=stable)
        if not ok:
            self.log(f"  {label} merkez saglanamadi, atlanıyor.")
            return False

        pos = get_position(); tx, ty = pos["x"], pos["y"]

        if self.mode == "precise":
            mid_h = (DRONE_HEIGHT + DROP_HEIGHT) / 2.0
            self.log(f"  Orta yuksege inis ({mid_h:.1f})...")
            tx, ty = self._descend_slow(tx, ty, color, mid_h)
            self._center_on(color, label, THRESH_NORMAL, mid_h,
                            step_scale=0.05, max_step=0.08, stable_need=3, max_iter=120)
            pos = get_position(); tx, ty = pos["x"], pos["y"]

        self.log(f"  Alcaga inis ({DROP_HEIGHT:.1f})...")
        tx, ty = self._descend_slow(tx, ty, color, DROP_HEIGHT)

        if self.mode in ("normal", "precise"):
            self._center_on(color, label, THRESH_FAST, DROP_HEIGHT,
                            step_scale=0.02, max_step=0.05, stable_need=2, max_iter=40)
            pos = get_position(); tx, ty = pos["x"], pos["y"]

        self._drop(color)

        # Yüksekliğe çık
        self.log(f"  Yukseliyor...")
        move_to(tx, ty, DRONE_HEIGHT)
        self.drone_pos = {"x": tx, "y": ty, "z": DRONE_HEIGHT}
        time.sleep(0.5)

        # Kaydettiğimiz spiral noktasına geri dön
        self.log(f"  Spiral noktasina donuyor ({resume_x:.1f},{resume_y:.1f})...")
        self._fly_to(resume_x, resume_y)
        return True

    # ── ANA SPİRAL ARAMA (tek geçişte her şeyi halleder) ────────
    def _spiral_mission(self):
        """
        Spiral çizerken:
          - Renk görünce → SPİRAL DUR, konumu kaydet
          - O renge git, teslim et, kaydettiğin noktaya dön, devam et
          - İkinci rengi de görürse aynısını yap
          - İkisi aynı anda görünürse: en yakını önce, diğerini cache'le
        """
        pts = make_inward_spiral(SPIRAL_START_X, SPIRAL_START_Y,
                                 SPIRAL_CENTER_X, SPIRAL_CENTER_Y,
                                 SPIRAL_TURNS, SPIRAL_PTS_PER)
        self.spiral_path = pts
        total = len(pts)

        # Hangi renkler teslim edilmedi?
        remaining = set()
        if self.color_order == "blue_first":
            remaining = {"blue", "red"}
        else:
            remaining = {"red", "blue"}   # auto ve red_first için aynı başlangıç

        # Henüz cache'lenmemiş ama görülen renkler:
        # cache = {color: (dünya_x, dünya_y, spiral_resume_x, spiral_resume_y, spiral_idx)}
        cache = {}

        self.log("Spiral basliyor...")
        self._fly_to(SPIRAL_START_X, SPIRAL_START_Y)

        i = 0
        while i < total and not self.stop_evt.is_set():
            if not remaining:
                break   # Tüm renkler teslim edildi

            tx, ty = pts[i]
            self.spiral_idx = i

            if i % 8 == 0:
                self.log(f"  Spiral [{i+1}/{total}] %{(i+1)/total*100:.0f}")

            # Bu noktaya doğru uçarken tara
            pos = get_position()
            cx_, cy_ = pos.get("x", 0.0), pos.get("y", 0.0)
            step = 0
            found_now = None   # Bu adımda yeni bulunan (first, second?) veya None

            while not self.stop_evt.is_set():
                ddx, ddy = tx - cx_, ty - cy_
                dist_ = math.sqrt(ddx*ddx + ddy*ddy)
                if dist_ < SPIRAL_FLY_SPEED:
                    cx_, cy_ = tx, ty
                    move_to(cx_, cy_, DRONE_HEIGHT)
                    self.drone_pos = {"x": cx_, "y": cy_, "z": DRONE_HEIGHT}
                    break
                sx_ = (ddx/dist_) * SPIRAL_FLY_SPEED
                sy_ = (ddy/dist_) * SPIRAL_FLY_SPEED
                cx_ += sx_; cy_ += sy_
                move_to(cx_, cy_, DRONE_HEIGHT)
                self.drone_pos = {"x": cx_, "y": cy_, "z": DRONE_HEIGHT}
                time.sleep(SPIRAL_FLY_DELAY)

                if step % SPIRAL_SCAN_EVERY == 0:
                    bgr = get_image()
                    if bgr is not None:
                        self.push_frame(bgr)
                        dets, _, _ = detect_colors(bgr)
                        found_now = self._check_and_cache(
                            dets, cx_, cy_, i, remaining, cache)
                        if found_now:
                            break   # Renk bulundu, spiral dur
                step += 1

            if found_now:
                # Spiral durduruldu — şu anki noktayı resume noktası yap
                resume_x, resume_y = cx_, cy_
                resume_i = i  # Buradan devam edeceğiz

                # Önce hangi renge gidilecek?
                deliver_order = self._decide_order(found_now, cache)

                for color in deliver_order:
                    if color not in remaining:
                        continue
                    if self.stop_evt.is_set():
                        break
                    label = "Kirmizi" if color == "red" else "Mavi"
                    wx, wy, rx, ry, _ = cache.pop(color)
                    self.log(f"  -> {label} konumuna gidiliyor ({wx:.1f},{wy:.1f})")
                    self._fly_to(wx, wy)
                    ok = self._deliver(color, label, resume_x, resume_y)
                    if ok:
                        remaining.discard(color)

                    # Teslim sonrası diğer renk hâlâ biliniyorsa devam
                    # (eğer ikisi aynı anda bulunduysa döngü onu da halleder)

                # Resume noktasından spirale devam
                i = resume_i
                # (while döngüsü i'yi artıracak)
            else:
                # Noktaya vardık, tarama yap
                bgr = get_image()
                if bgr is not None:
                    self.push_frame(bgr)
                    dets, _, _ = detect_colors(bgr)
                    found_now = self._check_and_cache(
                        dets, tx, ty, i, remaining, cache)
                    if found_now:
                        resume_x, resume_y = tx, ty
                        resume_i = i
                        deliver_order = self._decide_order(found_now, cache)
                        for color in deliver_order:
                            if color not in remaining:
                                continue
                            if self.stop_evt.is_set():
                                break
                            label = "Kirmizi" if color == "red" else "Mavi"
                            wx, wy, rx, ry, _ = cache.pop(color)
                            self.log(f"  -> {label} konumuna gidiliyor ({wx:.1f},{wy:.1f})")
                            self._fly_to(wx, wy)
                            ok = self._deliver(color, label, resume_x, resume_y)
                            if ok:
                                remaining.discard(color)
                        i = resume_i

                time.sleep(SPIRAL_MOVE_WAIT)

            i += 1

        if remaining:
            self.log(f"Spiral bitti, bulunamayan: {remaining}")
        else:
            self.log("Tum renkler teslim edildi!")

    def _check_and_cache(self, dets, drone_x, drone_y, spiral_i, remaining, cache):
        newly_found = []
        for color in list(remaining):
            if color in dets and color not in cache:
                # Dünya koordinatı hesaplamak YERİNE,
                # drone’un şu anki konumunu hedef olarak sakla.
                cache[color] = (drone_x, drone_y, drone_x, drone_y, spiral_i)
                label = "Kirmizi" if color == "red" else "Mavi"
                self.log(f"  {label} bulundu ve cache'lendi (drone konumu {drone_x:.1f},{drone_y:.1f})")
                newly_found.append(color)
        return newly_found if newly_found else None

    def _decide_order(self, found_colors, cache):
        """
        Hangi renk önce teslim edilecek?
        - color_order red_first/blue_first: ona göre sırala
        - auto: hangisi kameraya daha yakınsa (dist_px küçük olan)
        """
        if len(found_colors) == 1:
            return found_colors

        if self.color_order == "red_first":
            return ["red", "blue"]
        elif self.color_order == "blue_first":
            return ["blue", "red"]
        else:  # auto: hangisi drone'a dünya koordinatında daha yakın
            pos = get_position()
            dx_ = pos.get("x", 0.0)
            dy_ = pos.get("y", 0.0)
            def dist_to(color):
                wx, wy, *_ = cache[color]
                return math.sqrt((wx-dx_)**2 + (wy-dy_)**2)
            return sorted(found_colors, key=dist_to)

    # ─────────────────────────────────────────────────────────────
    def _fly_home(self):
        self.log("Eve donuluyor...")
        self._fly_to(0.0, 0.0)
        self.log("Eve donuldu!")

    # ── KULLANICI TANIMLI ROTA (planlama ekranından) ─────────────
    def _waypoint_mission(self):
        if not self.waypoints:
            self.log("Rota bos! Once planlama ekranindan konum ekle.")
            return
        total = len(self.waypoints)
        self.log(f"Rota basliyor: {total} konum")
        for i, wp in enumerate(self.waypoints):
            if self.stop_evt.is_set():
                break
            self.wp_idx = i
            self.log(f"  -> Konum {i+1}/{total} ({wp.x:.1f},{wp.y:.1f}) [{wp.action}]")
            self._fly_to(wp.x, wp.y, wp.z)
            if wp.action == "hover":
                self.log("  Bekleniyor (hover)...")
                time.sleep(2.0)
            elif wp.action == "photo":
                self.log("  Fotograf cekiliyor...")
                bgr = get_image()
                if bgr is not None:
                    self.push_frame(bgr)
            elif wp.action == "scan":
                self.log("  Taraniyor...")
                bgr = get_image()
                if bgr is not None:
                    self.push_frame(bgr)
                time.sleep(1.0)
        self.wp_idx = total

    def _run(self):
        self.running = True
        if self.mission_type == "waypoints":
            self.log(f"GOREV: Manuel Rota | {len(self.waypoints)} konum")
            self._waypoint_mission()
        else:
            self.log(f"GOREV: {MODE_LABELS[self.mode]} | Sira: {ORDER_LABELS[self.color_order]}")
            self._spiral_mission()
        if not self.stop_evt.is_set():
            self._fly_home()
            self.log("TUM GOREVLER TAMAMLANDI!")
        else:
            self.log("Gorev durduruldu.")
        self.running = False


# ─────────────────────────────────────────
# LIVE FETCHER
# ─────────────────────────────────────────
class LiveFetcher:
    def __init__(self, push_fn):
        self.push   = push_fn
        self.active = False
        self._stop  = threading.Event()

    def start(self):
        if self.active: return
        self._stop.clear()
        self.active = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()
        self.active = False

    def _loop(self):
        while not self._stop.is_set():
            bgr = get_image()
            if bgr is not None:
                self.push(bgr)
            time.sleep(REFRESH_INTERVAL)


# ─────────────────────────────────────────
# ÇİZİM
# ─────────────────────────────────────────
def corner_rect_pg(screen, cx, cy, half, color, thickness=1, cl=18):
    x1, y1, x2, y2 = cx-half, cy-half, cx+half, cy+half
    segs = [
        ((x1,y1),(x1+cl,y1)), ((x1,y1),(x1,y1+cl)),
        ((x2,y1),(x2-cl,y1)), ((x2,y1),(x2,y1+cl)),
        ((x1,y2),(x1+cl,y2)), ((x1,y2),(x1,y2-cl)),
        ((x2,y2),(x2-cl,y2)), ((x2,y2),(x2,y2-cl)),
    ]
    for p1, p2 in segs:
        pygame.draw.line(screen, color, p1, p2, thickness)


def draw_offset_hud(screen, detections, offsets, panel_x, panel_y,
                    img_w, img_h, active_mode):
    cx_p = panel_x + PANEL_W // 2
    cy_p = panel_y + PANEL_H // 2
    sx = PANEL_W / max(img_w, 1)
    sy = PANEL_H / max(img_h, 1)

    pygame.draw.line(screen, (160,160,160), (cx_p-14,cy_p), (cx_p+14,cy_p), 1)
    pygame.draw.line(screen, (160,160,160), (cx_p,cy_p-14), (cx_p,cy_p+14), 1)
    pygame.draw.circle(screen, (160,160,160), (cx_p,cy_p), 3, 1)

    act_thresh = MODE_THRESH.get(active_mode, THRESH_NORMAL)
    for thresh, col, cl in [
        (THRESH_PRECISE, (80,40,40),  12),
        (THRESH_NORMAL,  (80,80,40),  10),
        (THRESH_FAST,    (40,80,40),  8),
    ]:
        r = int(thresh * sx)
        is_act = (thresh == act_thresh)
        draw_col = MODE_COLORS.get(active_mode, col) if is_act else col
        corner_rect_pg(screen, cx_p, cy_p, r, draw_col, 2 if is_act else 1, cl)

    if not detections: return
    for color, info in detections.items():
        tx = panel_x + int(info["px"] * sx)
        ty = panel_y + int(info["py"] * sy)
        col_rgb = C_RED if color == "red" else C_BLUE
        hs = max(6, int(MARKER_HALF * sx))
        pygame.draw.rect(screen, col_rgb, pygame.Rect(tx-hs, ty-hs, hs*2, hs*2), 2)
        pygame.draw.line(screen, col_rgb, (cx_p, cy_p), (tx, ty), 1)
        dx_, dy_ = info["dx"], info["dy"]
        dist = info["dist_px"]
        in_f = (abs(dx_) < THRESH_FAST    and abs(dy_) < THRESH_FAST)
        in_n = (abs(dx_) < THRESH_NORMAL  and abs(dy_) < THRESH_NORMAL)
        in_p = (abs(dx_) < THRESH_PRECISE and abs(dy_) < THRESH_PRECISE)
        if in_f:   txt_col = C_GREEN;  dlbl = "IC KARE"
        elif in_n: txt_col = C_YELLOW; dlbl = "ORTA KARE"
        elif in_p: txt_col = C_ORANGE; dlbl = "DIS KARE"
        else:      txt_col = col_rgb;  dlbl = f"~{dist:.0f}px"
        bx_i = panel_x + PANEL_W - 162
        by_i = panel_y + 30 + list(detections).index(color) * 72
        pygame.draw.rect(screen, (10,12,18), pygame.Rect(bx_i-4,by_i-4,160,68))
        pygame.draw.rect(screen, col_rgb,    pygame.Rect(bx_i-4,by_i-4,160,68), 1)
        draw_text(screen, "KIRMIZI" if color=="red" else "MAVI",
                  (bx_i, by_i), 11, col_rgb, False)
        draw_text(screen, f"dx={dx_:+d}  dy={dy_:+d}", (bx_i, by_i+14), 10, C_TEXT, False)
        draw_text(screen, f"dist={dist:.0f}px",         (bx_i, by_i+27), 10, C_DIM,  False)
        draw_text(screen, dlbl,                          (bx_i, by_i+41), 11, txt_col, False)


def draw_panel(screen, surf, x, y, label, extra="", active=False):
    bc = LABEL_COLORS.get(label, C_BORDER)
    r  = pygame.Rect(x-2, y-2, PANEL_W+4, PANEL_H+4)
    pygame.draw.rect(screen, C_PANEL_BG, r)
    pygame.draw.rect(screen, bc, r, 2 if active else 1)
    screen.blit(surf, (x, y))
    draw_text(screen, label, (x+8, y+8), 13, bc)
    if extra:
        draw_text(screen, extra, (x+8, y+PANEL_H-18), 10, C_DIM)


def draw_header(screen, win_w, win_h, status, frame_no, elapsed, mission_running,
                drone_pos, spiral_pct, active_mode, color_order):
    """SOL dikey panel — üst yazılar. Ekranın tam yüksekliği boyunca uzanır."""
    pygame.draw.rect(screen, (14,18,28), (0, 0, LEFT_W, win_h))
    pygame.draw.line(screen, C_BORDER, (LEFT_W-1, 0), (LEFT_W-1, win_h), 1)

    px = 12
    tc = C_ORANGE if mission_running else C_TEXT
    draw_text(screen, "DRONE v8.1", (px, 10), 16, tc)

    pos_t1 = f"X={drone_pos.get('x',0):.2f}"
    pos_t2 = f"Y={drone_pos.get('y',0):.2f}"
    pos_t3 = f"Z={drone_pos.get('z',0):.2f}"
    draw_text(screen, pos_t1, (px, 36), 11, C_DIM)
    draw_text(screen, pos_t2, (px, 52), 11, C_DIM)
    draw_text(screen, pos_t3, (px, 68), 11, C_DIM)
    if mission_running and spiral_pct > 0:
        draw_text(screen, f"Spiral:{spiral_pct:.0f}%", (px, 84), 11, C_ORANGE)

    draw_text(screen, f"#{frame_no}  {elapsed:.1f}s", (px, 106), 11, C_DIM)
    sc = (C_ORANGE if mission_running else
          C_GREEN  if "OK" in status else
          C_YELLOW if ("Yenileniyor" in status or "Bekleniyor" in status) else C_RED)
    draw_text(screen, status, (px, 122), 12, sc)

    # Mod butonları — dikey olarak alt alta
    by = 150
    bw = LEFT_W - px*2
    for mk, ml, em in [
        ("fast",    "HIZLI",  "1"),
        ("normal",  "NORMAL", "2"),
        ("precise", "KESIN",  "3"),
    ]:
        col = MODE_COLORS[mk]; is_act = (mk == active_mode)
        r = pygame.Rect(px, by, bw, 26)
        pygame.draw.rect(screen, col if is_act else (28,32,42), r, border_radius=4)
        if not is_act:
            pygame.draw.rect(screen, col, r, 1, border_radius=4)
        draw_text(screen, f"[{em}] {ml}", (px+8, by+6), 11,
                  (0,0,0) if is_act else col, False)
        by += 32

    ord_col = {"red_first":C_RED,"blue_first":C_BLUE,"auto":C_PURPLE}.get(color_order, C_TEXT)
    r = pygame.Rect(px, by, bw, 26)
    pygame.draw.rect(screen, (28,32,42), r, border_radius=4)
    pygame.draw.rect(screen, ord_col,    r, 1, border_radius=4)
    draw_text(screen, f"[T] {ORDER_LABELS.get(color_order,'?')}", (px+8, by+6), 11, ord_col, False)
    by += 32

    r = pygame.Rect(px, by, bw, 26)
    pygame.draw.rect(screen, (30,40,60), r, border_radius=4)
    pygame.draw.rect(screen, C_CYAN,     r, 1, border_radius=4)
    draw_text(screen, "[A] AYAR", (px+8, by+6), 11, C_CYAN, False)


def draw_footer(screen, win_w, win_h, detections, stats, mission_log,
                mission_running, payloads, active_mode, color_order):
    """SAG dikey panel — alt yazılar. Ekranın tam yüksekliği boyunca uzanır."""
    x = win_w - RIGHT_W
    pygame.draw.rect(screen, (12,15,22), (x, 0, RIGHT_W, win_h))
    pygame.draw.line(screen, C_BORDER, (x, 0), (x, win_h), 1)

    px = x + 12
    draw_text(screen, f"Kirmizi px: {stats.get('red_px',0)}", (px, 10),  11, C_RED)
    draw_text(screen, f"Mavi px:    {stats.get('blue_px',0)}", (px, 26), 11, C_BLUE)

    desc = {
        "fast":    "HIZLI: yesil kare",
        "normal":  "NORMAL: sari kare",
        "precise": "KESIN: yesil→sari→kirmizi",
    }
    draw_text(screen, desc.get(active_mode, ""), (px, 46), 10,
              MODE_COLORS.get(active_mode, C_TEXT))
    ord_col = {"red_first":C_RED,"blue_first":C_BLUE,"auto":C_PURPLE}.get(color_order, C_TEXT)
    draw_text(screen, f"Sira: {ORDER_LABELS.get(color_order,'?')}", (px, 62), 10, ord_col)

    dy = 84
    if detections:
        for col, info in detections.items():
            dx_, dy_ = info.get("dx",0), info.get("dy",0)
            inf = (abs(dx_) < THRESH_FAST and abs(dy_) < THRESH_FAST)
            lbl1 = f"{'OK' if inf else '-'} {col.upper()} ({info['px']},{info['py']})"
            lbl2 = ('[IC KARE]' if inf else f'dx={dx_:+d} dy={dy_:+d}')
            draw_text(screen, lbl1, (px, dy), 10, C_RED if col=="red" else C_BLUE)
            draw_text(screen, lbl2, (px, dy+14), 10, C_RED if col=="red" else C_BLUE)
            dy += 32
    else:
        draw_text(screen, "Hedef yok", (px, dy), 11, C_YELLOW)
        dy += 20

    dy += 10
    for col, has in payloads.items():
        draw_text(screen, f"{col.upper()}: {'Yuklu' if has else 'Birakildi'}",
                  (px, dy), 11, C_GREEN if has else C_DIM)
        dy += 18

    dy += 10
    draw_text(screen, "LOG:", (px, dy), 10, C_DIM)
    dy += 16
    log_w_chars = max(10, (RIGHT_W - 24) // 7)
    for line in mission_log[-6:]:
        lc = (C_GREEN  if ("TAMAMLANDI" in line or "Merkez" in line or "OK" in line) else
              C_ORANGE if ("birak" in line.lower() or "Servo" in line or "Teslim" in line) else
              C_CYAN   if any(k in line.lower() for k in ["kare","inis","adim","sinir","spiral"]) else
              C_YELLOW if any(k in line for k in ["durduruldu","kayboldu","bulunamadi"]) else
              C_TEXT)
        draw_text(screen, line[:log_w_chars], (px, dy), 10, lc)
        dy += 15

    keys = ("S: durdur\nQ: cik" if mission_running else
            "1-3:mod T:sira\nP:plan M:tip V:harita\n+/-:zoom Yon:kaydir/manuel\nG:baslat S:dur\nSPACE:yenile\nA:ayar Q:cik")
    ky = win_h - 90
    for kline in keys.split("\n"):
        draw_text(screen, kline, (px, ky), 10, C_DIM)
        ky += 15


# ─────────────────────────────────────────
# AYARLAR PANELİ
# ─────────────────────────────────────────
class SettingsPanel:
    def __init__(self, win_w, win_h):
        self.win_w = win_w
        self.win_h = win_h
        self.x     = win_w - RIGHT_W - SETTINGS_W

    def get_panel_rect(self):
        return pygame.Rect(self.x, 0, SETTINGS_W, self.win_h)

    def _row(self, i):
        return 34 + i * 32

    def draw(self, screen, cfg: Settings, click_pos=None):
        """click_pos yalnızca panel içindeki tıklamalar için iletilir."""
        full_req = False
        x = self.x
        pw = SETTINGS_W

        surf = pygame.Surface((pw, self.win_h), pygame.SRCALPHA)
        surf.fill((14, 20, 36, 220))
        screen.blit(surf, (x, 0))
        pygame.draw.rect(screen, C_CYAN,
                         pygame.Rect(x, 0, pw, self.win_h), 1)
        draw_text(screen, "AYARLAR", (x+12, 6), 14, C_CYAN)
        pygame.draw.line(screen, C_BORDER, (x, 26), (x+pw, 26), 1)

        row = 1

        def toggle_row(label, key, value, color=C_TEXT):
            nonlocal row
            y_ = self._row(row)
            col = C_GREEN if value else C_RED
            btn = pygame.Rect(x+pw-54, y_, 50, 22)
            pygame.draw.rect(screen, (20,40,20) if value else (40,20,20), btn, border_radius=4)
            pygame.draw.rect(screen, col, btn, 1, border_radius=4)
            draw_text(screen, "ACIK" if value else "KAPALI", (btn.x+4, btn.y+5), 9, col, False)
            draw_text(screen, label, (x+10, y_+4), 11, color)
            if click_pos and btn.collidepoint(click_pos):
                cfg.toggle(key)
            row += 1

        def num_row(label, key, value, fmt="{:.2f}"):
            nonlocal row
            y_ = self._row(row)
            draw_text(screen, label, (x+10, y_+4), 11, C_TEXT)
            val_str = fmt.format(value) if "{" in fmt else str(value)
            draw_text(screen, val_str, (x+pw-110, y_+4), 11, C_YELLOW)
            btn_m = pygame.Rect(x+pw-54, y_, 22, 22)
            btn_p = pygame.Rect(x+pw-28, y_, 22, 22)
            pygame.draw.rect(screen, (50,30,30), btn_m, border_radius=3)
            pygame.draw.rect(screen, (30,50,30), btn_p, border_radius=3)
            pygame.draw.rect(screen, C_DIM, btn_m, 1, border_radius=3)
            pygame.draw.rect(screen, C_DIM, btn_p, 1, border_radius=3)
            draw_text(screen, "-", (btn_m.x+7, btn_m.y+5), 11, C_RED,   False)
            draw_text(screen, "+", (btn_p.x+6, btn_p.y+5), 11, C_GREEN, False)
            if click_pos:
                if btn_m.collidepoint(click_pos): cfg.adjust(key, -1)
                if btn_p.collidepoint(click_pos): cfg.adjust(key,  1)
            row += 1

        def section(title):
            nonlocal row
            y_ = self._row(row)
            draw_text(screen, title, (x+10, y_+4), 10, C_DIM)
            pygame.draw.line(screen, C_BORDER, (x+10, y_+18), (x+pw-10, y_+18), 1)
            row += 1

        section("-- GOREV --")
        toggle_row("Guvenli Alan Siniri",   "safe_border_enabled",  cfg.safe_border_enabled,  C_CYAN)
        toggle_row("Yavas Alcalma",         "slow_descent_enabled", cfg.slow_descent_enabled, C_GREEN)
        toggle_row("Surekli Goruntu (Live)","live_fetch_enabled",   cfg.live_fetch_enabled,   C_BLUE)

        section("-- GUVENLI ALAN --")
        num_row("Sinir (px)", "safe_border_px", cfg.safe_border_px, "{:d}")

        section("-- ALCALMA HIZI --")
        num_row("Adim Boyu",         "descent_step",  cfg.descent_step,  "{:.2f}")
        num_row("Adim Gecikmesi (s)","descent_delay", cfg.descent_delay, "{:.2f}")

        section("-- GORUNTU --")
        toggle_row("Mask Panelleri", "show_masks", cfg.show_masks, C_TEXT)
        toggle_row("HUD Goster",     "show_hud",   cfg.show_hud,   C_TEXT)

        section("-- PENCERE --")
        y_ = self._row(row)
        fs_col = C_YELLOW if cfg.fullscreen else C_DIM
        btn_fs = pygame.Rect(x+pw-54, y_, 50, 22)
        pygame.draw.rect(screen, (60,50,20) if cfg.fullscreen else (30,30,30),
                         btn_fs, border_radius=4)
        pygame.draw.rect(screen, fs_col, btn_fs, 1, border_radius=4)
        draw_text(screen, "ACIK" if cfg.fullscreen else "KAPALI",
                  (btn_fs.x+4, btn_fs.y+5), 9, fs_col, False)
        draw_text(screen, "Tam Ekran", (x+10, y_+4), 11, C_TEXT)
        if click_pos and btn_fs.collidepoint(click_pos):
            cfg.toggle("fullscreen")
            full_req = True
        row += 1

        return full_req


# ─────────────────────────────────────────
# ANA PENCERE
# ─────────────────────────────────────────
class LiveViewer:
    def __init__(self):
        self.cfg = Settings()
        pygame.display.set_caption("Drone v8.1")
        self.win_w  = WIN_W
        self.win_h  = WIN_H
        self.screen = pygame.display.set_mode((self.win_w, self.win_h))
        self.clock  = pygame.time.Clock()

        self.panels     = None
        self.detections = {}
        self.stats      = {"red_px":0,"blue_px":0,"img_w":640,"img_h":480}
        self.frame_no   = 0
        self.status     = "Bekleniyor..."
        self.last_fetch = 0.0
        self.fetching   = False
        self.should_quit = False
        self.drone_pos   = {"x":0.0,"y":0.0,"z":DRONE_HEIGHT}
        self.active_mode = "normal"
        self.color_order = "red_first"

        # Ayarlar paneli durumu
        self.show_settings = False

        # Planlama modu (kullanıcı tanımlı rota)
        self.planning_mode  = False
        self.waypoints      = []          # Waypoint listesi
        self.mission_type   = "spiral"    # "spiral" | "waypoints"
        self.wp_action_cursor = "none"    # yeni eklenecek waypoint'in aksiyonu

        # Harita modu (Blender'daki Sketchfab_model collection'ından otomatik sınır + ortografik çekim)
        self.map_entered     = False   # ENTER_MAP başarıyla çağrıldı mı (kamera harita modunda mı)
        self.map_bounds      = None    # ENTER_MAP'ten dönen {cx,cy,base_scale,min_x,max_x,min_y,max_y}
        self.map_scale_mult  = 1.0     # [+]/[-] ile değişen zoom çarpanı
        self.map_offset_x    = 0.0     # ok tuşlarıyla değişen kaydırma (dünya birimi)
        self.map_offset_y    = 0.0
        self.plan_bg_bgr      = None   # son çekilen harita görüntüsü (BGR numpy)
        self.plan_bg_capturing = False
        self.plan_bg_status    = ""

        self.mission_log = ["1=Hizli  2=Normal  3=Kesin  T=Sira  A=Ayar  G=Baslat  P=Plan"]
        self._mission        = MissionRunner(self._add_log, self._push_frame, self.cfg)
        self._live_fetcher   = LiveFetcher(self._push_frame)
        self._settings_panel = SettingsPanel(self.win_w, self.win_h)

    def _add_log(self, msg):
        self.mission_log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        print(f"[GOREV] {msg}")

    def _push_frame(self, bgr):
        p_o, p_r, p_b, p_res, dets, stats = process_frame(bgr, self.active_mode, self.cfg)
        self.panels     = (p_o, p_r, p_b, p_res)
        self.detections = dets
        self.stats      = stats
        self.frame_no  += 1
        self.last_fetch = time.time()

    def _fetch_thread(self):
        self.status = "Yenileniyor..."
        bgr = get_image()
        if bgr is None:
            self.status = "HATA: goruntu alinamadi"
            self.fetching = False; return
        self._push_frame(bgr)
        n = len(self.detections)
        self.status = f"OK — {n} hedef" if n else "OK — Hedef yok"
        self.fetching = False

    def start_fetch(self):
        if self.fetching: return
        self.fetching = True
        threading.Thread(target=self._fetch_thread, daemon=True).start()

    def _refresh_pos(self):
        pos = get_position()
        if pos: self.drone_pos = pos

    def _manual_move(self, key):
        pos = get_position()
        x, y, z = pos.get("x",0.0), pos.get("y",0.0), pos.get("z",DRONE_HEIGHT)
        if   key == pygame.K_UP:    y += MANUAL_STEP
        elif key == pygame.K_DOWN:  y -= MANUAL_STEP
        elif key == pygame.K_LEFT:  x -= MANUAL_STEP
        elif key == pygame.K_RIGHT: x += MANUAL_STEP
        else: return
        if move_to(x, y, z):
            self.drone_pos = {"x":x,"y":y,"z":z}
            self._add_log(f"Manuel X={x:.2f} Y={y:.2f}")

    def _apply_fullscreen(self):
        if self.cfg.fullscreen:
            self.screen = pygame.display.set_mode(
                (self.win_w, self.win_h), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode((self.win_w, self.win_h))

    def _settings_btn_rect(self):
        # Sol dikey panelde: px=12, by = 150 + 3*32 (mod) + 32 (sira) = 278
        return pygame.Rect(12, 278, LEFT_W - 24, 26)

    # ── Kamera/Planlama alanı geometrisi (sol ve sag panel arasi) ─
    def _cam_rect(self):
        cam_x0 = LEFT_W + GAP
        cam_x1 = self.win_w - RIGHT_W - GAP
        return pygame.Rect(cam_x0, GAP, cam_x1 - cam_x0, self.win_h - GAP*2)

    # ── Harita moduna giriş: Sketchfab_model sınırlarını oku + ilk çekim ──
    def _enter_map_and_capture(self):
        if self.plan_bg_capturing:
            return
        self.plan_bg_capturing = True
        self.plan_bg_status = "Harita siniri okunuyor..."
        self._add_log("Harita moduna giriliyor, Sketchfab_model sinirlari okunuyor...")
        try:
            bounds = enter_map()
            if bounds is None:
                self._add_log("HATA: harita sinirlari okunamadi "
                              "(sahnede Camera/blue/red/Sun disinda mesh objesi yok mu?)")
                self.plan_bg_capturing = False
                return
            self.map_bounds     = bounds
            self.map_entered    = True
            self.map_scale_mult = 1.0
            self.map_offset_x   = 0.0
            self.map_offset_y   = 0.0
            self._add_log(f"Harita sinirlari OK. Merkez=({bounds['cx']:.2f},{bounds['cy']:.2f}) "
                          f"olcek={bounds['base_scale']:.2f}")
        finally:
            self.plan_bg_capturing = False
        self._do_capture_map()

    # ── Mevcut zoom/pan ile haritayı yeniden çek ──────────────────
    def _do_capture_map(self):
        if not self.map_entered or self.map_bounds is None:
            return
        self.plan_bg_capturing = True
        self.plan_bg_status = "Harita cekiliyor..."
        try:
            bgr = capture_map(self.map_scale_mult, self.map_offset_x, self.map_offset_y)
            if bgr is not None:
                self.plan_bg_bgr = bgr
                self._add_log(f"Harita guncellendi (zoom x{self.map_scale_mult:.2f}, "
                              f"pan={self.map_offset_x:.1f},{self.map_offset_y:.1f})")
            else:
                self._add_log("Harita cekilemedi (goruntu alinamadi)")
        finally:
            self.plan_bg_status = ""
            self.plan_bg_capturing = False

    def _exit_map_mode(self):
        if self.map_entered:
            self._add_log("Kamera harita modundan cikiyor, eski konumuna donuyor...")
            exit_map()
            self.map_entered = False

    def _start_map_enter(self):
        threading.Thread(target=self._enter_map_and_capture, daemon=True).start()

    def _start_map_recapture(self):
        threading.Thread(target=self._do_capture_map, daemon=True).start()

    def _start_map_exit(self):
        threading.Thread(target=self._exit_map_mode, daemon=True).start()

    # ── Su anki zoom/pan'a göre görünen dünya sınırları ───────────
    def _plan_world_bounds(self):
        if self.map_bounds is None:
            return (PLAN_WORLD_X0_DEFAULT, PLAN_WORLD_X1_DEFAULT,
                    PLAN_WORLD_Y0_DEFAULT, PLAN_WORLD_Y1_DEFAULT)
        cx = self.map_bounds["cx"] + self.map_offset_x
        cy = self.map_bounds["cy"] + self.map_offset_y
        ortho_scale = self.map_bounds["base_scale"] * self.map_scale_mult
        half_w = ortho_scale / 2.0
        half_h = (ortho_scale * (PANEL_H / PANEL_W)) / 2.0
        return (cx - half_w, cx + half_w, cy - half_h, cy + half_h)

    # ── Planlama ekranı dünya <-> ekran dönüşümü ──────────────────
    def _plan_world_to_screen(self, wx, wy, rect):
        x0, x1, y0, y1 = self._plan_world_bounds()
        tx = (wx - x0) / max(x1 - x0, 1e-6)
        ty = (wy - y0) / max(y1 - y0, 1e-6)
        sx = rect.x + tx * rect.w
        sy = rect.y + (1 - ty) * rect.h
        return int(sx), int(sy)

    def _plan_screen_to_world(self, sx, sy, rect):
        x0, x1, y0, y1 = self._plan_world_bounds()
        tx = (sx - rect.x) / max(rect.w, 1)
        ty = 1 - (sy - rect.y) / max(rect.h, 1)
        wx = x0 + tx * (x1 - x0)
        wy = y0 + ty * (y1 - y0)
        return wx, wy

    # ── Planlama ekranını çiz ──────────────────────────────────────
    def _draw_planning_canvas(self, rect):
        screen = self.screen

        if self.plan_bg_bgr is not None:
            bg_resized = cv2.resize(self.plan_bg_bgr, (rect.w, rect.h))
            bg_surf = bgr_to_surface(bg_resized)
            screen.blit(bg_surf, (rect.x, rect.y))
            dim = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 70))   # izgara/nokta okunurlugu icin hafif karartma
            screen.blit(dim, (rect.x, rect.y))
            grid_col = (90, 190, 190)
        else:
            pygame.draw.rect(screen, (16, 20, 30), rect)
            grid_col = (30, 38, 52)
        pygame.draw.rect(screen, C_CYAN, rect, 1)

        x0, x1, y0, y1 = self._plan_world_bounds()

        # Izgara (görünen alanı ~8 parçaya bölecek adım büyüklüğü)
        step = max((x1 - x0) / 8.0, 0.5)
        gx = x0
        while gx <= x1:
            sx, _ = self._plan_world_to_screen(gx, 0, rect)
            pygame.draw.line(screen, grid_col, (sx, rect.y), (sx, rect.y + rect.h), 1)
            gx += step
        gy = y0
        while gy <= y1:
            _, sy = self._plan_world_to_screen(0, gy, rect)
            pygame.draw.line(screen, grid_col, (rect.x, sy), (rect.x + rect.w, sy), 1)
            gy += step

        # Merkez eksenler (0,0 = ev / kalkış noktası)
        ox, oy = self._plan_world_to_screen(0, 0, rect)
        pygame.draw.line(screen, C_BORDER, (rect.x, oy), (rect.x + rect.w, oy), 1)
        pygame.draw.line(screen, C_BORDER, (ox, rect.y), (ox, rect.y + rect.h), 1)
        pygame.draw.circle(screen, C_GREEN, (ox, oy), 6, 2)
        draw_text(screen, "EV", (ox + 8, oy - 8), 11, C_GREEN)

        # Su anki drone konumu
        dx, dy = self._plan_world_to_screen(
            self.drone_pos.get("x", 0.0), self.drone_pos.get("y", 0.0), rect)
        pygame.draw.circle(screen, C_ORANGE, (dx, dy), 7, 0)
        pygame.draw.circle(screen, C_WHITE, (dx, dy), 7, 1)
        draw_text(screen, "DRONE", (dx + 10, dy - 6), 11, C_ORANGE)

        # Waypoint'ler ve aralarındaki rota çizgisi
        pts = [self._plan_world_to_screen(wp.x, wp.y, rect) for wp in self.waypoints]
        if len(pts) >= 2:
            pygame.draw.lines(screen, C_CYAN, False, pts, 2)
        for i, (wp, (sx, sy)) in enumerate(zip(self.waypoints, pts)):
            col = WP_ACTION_COLORS.get(wp.action, C_TEXT)
            pygame.draw.circle(screen, col, (sx, sy), 10, 0)
            pygame.draw.circle(screen, C_WHITE, (sx, sy), 10, 2)
            draw_text(screen, str(i+1), (sx-4, sy-7), 11, (0,0,0), False)
            draw_text(screen, WP_ACTION_LABELS.get(wp.action,""), (sx+12, sy-6), 10, col)

        # Ust bilgi çubuğu
        info = (f"Tikla: konum ekle | Sag tik: sil | [K]Aksiyon:{WP_ACTION_LABELS.get(self.wp_action_cursor,'?')} | "
                f"[M]Rota:{'Manuel' if self.mission_type=='waypoints' else 'Spiral'} | "
                f"[+/-]Zoom | [Yon]Kaydir | [V]Yenile | [C]Temizle | [P]Cik")
        draw_text(screen, info, (rect.x + 10, rect.y + 8), 11, C_CYAN)
        draw_text(screen, f"Konum sayisi: {len(self.waypoints)}   "
                          f"Zoom: x{self.map_scale_mult:.2f}   "
                          f"Pan: ({self.map_offset_x:.1f}, {self.map_offset_y:.1f})",
                  (rect.x + 10, rect.y + 26), 11, C_TEXT)

        if self.plan_bg_capturing:
            spin = "◐◓◑◒"[int(time.time()*3) % 4]
            msg = pil_render_text(f"{spin} {self.plan_bg_status}", 16, C_YELLOW)
            screen.blit(msg, msg.get_rect(center=(rect.x + rect.w//2, rect.y + rect.h//2)))
        elif self.plan_bg_bgr is None:
            hint = pil_render_text("[V] tusuyla harita gorunutusu cek", 14, C_DIM)
            screen.blit(hint, hint.get_rect(center=(rect.x + rect.w//2, rect.y + rect.h//2)))

    # ── Tek flip noktası ────────────────────────────────────────
    def _render(self, click_for_settings=None):
        """Tüm ekranı çiz ve BİR KEZ flip yap."""
        self.screen.fill(C_BG)
        elapsed = time.time() - self.last_fetch if self.last_fetch else 0.0
        m = self._mission
        total_pts = len(m.spiral_path)
        spi_pct = (m.spiral_idx / max(total_pts-1, 1) * 100) if (m.running and total_pts>0) else 0.0

        draw_header(self.screen, self.win_w, self.win_h, self.status, self.frame_no, elapsed,
                    m.running, self.drone_pos, spi_pct, self.active_mode, self.color_order)

        # Kamera alanı: sol ve sag paneller arasında, tam yukseklik
        cam_x0 = LEFT_W + GAP
        cam_x1 = self.win_w - RIGHT_W - GAP
        pw = (cam_x1 - cam_x0 - GAP) // 2
        ph = (self.win_h - GAP*3) // 2
        pw = max(pw, 160); ph = max(ph, 120)

        draw_footer(self.screen, self.win_w, self.win_h, self.detections, self.stats,
                    self.mission_log, m.running, m.payloads,
                    self.active_mode, self.color_order)

        if self.planning_mode:
            self._draw_planning_canvas(self._cam_rect())
        elif self.panels:
            surfs   = [bgr_to_surface(cv2.resize(p, (pw, ph))) for p in self.panels]
            labels  = ["Orijinal Goruntu","Kirmizi Mask","Mavi Mask","Tespit Sonucu"]
            extras  = ["", f"Px:{self.stats.get('red_px',0)}",
                       f"Px:{self.stats.get('blue_px',0)}",
                       f"Tespit:{','.join(self.detections.keys()) or 'yok'}"]
            actives = [False, False, False, bool(self.detections)]
            pos_    = [(cam_x0, GAP), (cam_x0+GAP+pw, GAP),
                       (cam_x0, GAP*2+ph), (cam_x0+GAP+pw, GAP*2+ph)]

            for idx, (surf, (px_, py_), lbl, ext, act) in enumerate(
                    zip(surfs, pos_, labels, extras, actives)):
                if not self.cfg.show_masks and idx in (1, 2):
                    pygame.draw.rect(self.screen, C_PANEL_BG,
                                     pygame.Rect(px_-2, py_-2, pw+4, ph+4))
                    draw_text(self.screen, "(mask kapali)", (px_+8, py_+8), 11, C_DIM)
                else:
                    bc = LABEL_COLORS.get(lbl, C_BORDER)
                    r  = pygame.Rect(px_-2, py_-2, pw+4, ph+4)
                    pygame.draw.rect(self.screen, C_PANEL_BG, r)
                    pygame.draw.rect(self.screen, bc, r, 2 if act else 1)
                    self.screen.blit(surf, (px_, py_))
                    draw_text(self.screen, lbl, (px_+8, py_+8), 13, bc)
                    if ext:
                        draw_text(self.screen, ext, (px_+8, py_+ph-18), 10, C_DIM)

            if self.cfg.show_hud:
                draw_offset_hud(self.screen, self.detections, m.current_offset,
                                pos_[0][0], pos_[0][1],
                                self.stats.get("img_w",640), self.stats.get("img_h",480),
                                self.active_mode)
        else:
            spin = "◐◓◑◒"[int(time.time()*3) % 4]
            msg  = pil_render_text("Blender'dan ilk frame bekleniyor...", 16, C_DIM)
            spn  = pil_render_text(spin, 20, C_YELLOW)
            cx_, cy_ = (cam_x0 + cam_x1) // 2, self.win_h // 2
            self.screen.blit(msg, msg.get_rect(center=(cx_, cy_-16)))
            self.screen.blit(spn, spn.get_rect(center=(cx_, cy_+20)))

        # Ayarlar paneli (üstüne çiz, flip'ten önce)
        if self.show_settings:
            full_req = self._settings_panel.draw(
                self.screen, self.cfg, click_for_settings)
            if full_req:
                self._apply_fullscreen()

        # ── Tek flip ──
        pygame.display.flip()

    def run(self):
        print("Drone v8.1 basliyor...")
        self.start_fetch()
        last_auto = time.time()
        last_pos  = time.time()

        while not self.should_quit:
            click_for_settings = None

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.should_quit = True

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    pos_click  = event.pos
                    btn_rect   = self._settings_btn_rect()
                    panel_rect = self._settings_panel.get_panel_rect()

                    if btn_rect.collidepoint(pos_click):
                        # Sadece [A] butonuna tıklanınca toggle
                        self.show_settings = not self.show_settings
                    elif self.show_settings:
                        if panel_rect.collidepoint(pos_click):
                            # Panel içi → ayarı değiştir, panel açık kalsın
                            click_for_settings = pos_click
                        else:
                            # Panel dışı → kapat
                            self.show_settings = False
                    elif self.planning_mode and not self._mission.running:
                        cam_rect = self._cam_rect()
                        if cam_rect.collidepoint(pos_click):
                            wx, wy = self._plan_screen_to_world(
                                pos_click[0], pos_click[1], cam_rect)
                            self.waypoints.append(
                                Waypoint(wx, wy, DRONE_HEIGHT, self.wp_action_cursor))
                            self._add_log(
                                f"Konum {len(self.waypoints)} eklendi "
                                f"({wx:.1f},{wy:.1f}) [{self.wp_action_cursor}]")

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    if self.planning_mode and self.waypoints and not self._mission.running:
                        self.waypoints.pop()
                        self._add_log(f"Son konum silindi ({len(self.waypoints)} kaldi)")

                elif event.type == pygame.KEYDOWN:
                    k = event.key
                    if k in (pygame.K_ESCAPE,):
                        if self.show_settings:
                            self.show_settings = False
                        else:
                            self.should_quit = True
                    elif k == pygame.K_q:
                        self.should_quit = True
                    elif k == pygame.K_a:
                        self.show_settings = not self.show_settings
                    elif k == pygame.K_1 and not self._mission.running:
                        self.active_mode = "fast";    self._add_log("Mod: HIZLI")
                    elif k == pygame.K_2 and not self._mission.running:
                        self.active_mode = "normal";  self._add_log("Mod: NORMAL")
                    elif k == pygame.K_3 and not self._mission.running:
                        self.active_mode = "precise"; self._add_log("Mod: KESIN")
                    elif k == pygame.K_t and not self._mission.running:
                        orders = ["red_first","blue_first","auto"]
                        idx = orders.index(self.color_order)
                        self.color_order = orders[(idx+1) % 3]
                        self._add_log(f"Sira: {ORDER_LABELS[self.color_order]}")
                    elif k == pygame.K_p and not self._mission.running:
                        self.planning_mode = not self.planning_mode
                        self._add_log("Planlama modu ACIK" if self.planning_mode
                                      else "Planlama modu KAPALI")
                        if self.planning_mode:
                            if not self.map_entered and not self.plan_bg_capturing:
                                self._start_map_enter()
                        else:
                            self._start_map_exit()
                    elif k == pygame.K_v and self.planning_mode and not self._mission.running:
                        if self.map_entered:
                            self._start_map_recapture()
                        else:
                            self._start_map_enter()
                    elif (k in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS)
                          and self.planning_mode and self.map_entered
                          and not self.plan_bg_capturing and not self._mission.running):
                        self.map_scale_mult = max(0.15, self.map_scale_mult * 0.8)
                        self._add_log(f"Yakinlastir: x{self.map_scale_mult:.2f}")
                        self._start_map_recapture()
                    elif (k in (pygame.K_MINUS, pygame.K_KP_MINUS)
                          and self.planning_mode and self.map_entered
                          and not self.plan_bg_capturing and not self._mission.running):
                        self.map_scale_mult = min(6.0, self.map_scale_mult * 1.25)
                        self._add_log(f"Uzaklastir: x{self.map_scale_mult:.2f}")
                        self._start_map_recapture()
                    elif k == pygame.K_m and not self._mission.running:
                        self.mission_type = ("waypoints" if self.mission_type == "spiral"
                                              else "spiral")
                        self._add_log(f"Rota tipi: "
                                      f"{'Manuel Rota' if self.mission_type=='waypoints' else 'Spiral Tara'}")
                    elif k == pygame.K_k and self.planning_mode and not self._mission.running:
                        idx = WP_ACTIONS.index(self.wp_action_cursor)
                        self.wp_action_cursor = WP_ACTIONS[(idx+1) % len(WP_ACTIONS)]
                        self._add_log(f"Yeni konum aksiyonu: {WP_ACTION_LABELS[self.wp_action_cursor]}")
                    elif k == pygame.K_c and self.planning_mode and not self._mission.running:
                        self.waypoints = []
                        self._add_log("Rota temizlendi")
                    elif k == pygame.K_SPACE:
                        self.start_fetch(); last_auto = time.time()
                    elif k == pygame.K_g:
                        if not self._mission.running:
                            if self.mission_type == "waypoints" and not self.waypoints:
                                self._add_log("Rota bos! Once P ile plan ekranini ac, tikla.")
                            else:
                                self._add_log(
                                    f"Baslıyor: {'Manuel Rota' if self.mission_type=='waypoints' else MODE_LABELS[self.active_mode]} "
                                    f"| {ORDER_LABELS[self.color_order]}")
                                self.planning_mode = False
                                self._start_map_exit()
                                if self.cfg.live_fetch_enabled:
                                    self._live_fetcher.start()
                                self._mission.start(self.active_mode, self.color_order,
                                                    self.mission_type, list(self.waypoints))
                        else:
                            self._add_log("Gorev aktif (S ile durdur)")
                    elif k == pygame.K_s:
                        if self._mission.running:
                            self._mission.stop()
                            self._live_fetcher.stop()
                            self._add_log("Durdurma istegi")
                        else:
                            self._add_log("Aktif gorev yok.")
                    elif k in (pygame.K_UP, pygame.K_DOWN,
                                pygame.K_LEFT, pygame.K_RIGHT):
                        if self.planning_mode:
                            if self.map_entered and not self._mission.running:
                                x0, x1, y0, y1 = self._plan_world_bounds()
                                pan_step = (x1 - x0) * 0.08
                                if   k == pygame.K_UP:    self.map_offset_y += pan_step
                                elif k == pygame.K_DOWN:  self.map_offset_y -= pan_step
                                elif k == pygame.K_LEFT:  self.map_offset_x -= pan_step
                                elif k == pygame.K_RIGHT: self.map_offset_x += pan_step
                                self._start_map_recapture()
                        elif not self._mission.running:
                            threading.Thread(
                                target=self._manual_move, args=(k,),
                                daemon=True).start()
                        else:
                            self._add_log("Gorev aktifken manuel kapali")

            # Tek noktada render + flip
            self._render(click_for_settings)

            # Görev bitince live fetcher durdur
            if not self._mission.running and self._live_fetcher.active:
                self._live_fetcher.stop()

            # Otomatik yenile (görev yokken)
            if (not self._mission.running and not self.fetching
                    and time.time() - last_auto >= REFRESH_INTERVAL):
                self.start_fetch(); last_auto = time.time()

            # Konum sorgula
            if not self._mission.running and time.time() - last_pos > 1.5:
                threading.Thread(target=self._refresh_pos, daemon=True).start()
                last_pos = time.time()

            if self._mission.running:
                self.drone_pos   = self._mission.drone_pos
                self.active_mode = self._mission.mode

            self.clock.tick(30)

        if self._mission.running:
            self._mission.stop()
        self._live_fetcher.stop()
        if self.map_entered:
            self._exit_map_mode()
        pygame.quit()
        print("Kapatildi.")


if __name__ == "__main__":
    print("DRONE v8.1")
    os.environ.setdefault("SDL_VIDEODRIVER", "x11")
    if not ping():
        print("Blender bulunamadi — test modu")
    else:
        print("Baglanti kuruldu!")
    LiveViewer().run()