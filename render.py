"""Render video "streak" cho /diemdanh.

Lay video mau (template.mp4), thay:
  - avatar trai  = assets/right.png (anh co dinh)
  - avatar phai  = avatar nguoi diem danh (hoac chu cai dau neu khong co anh)
  - @ten         = @username
  - so ngay      = so ngay diem danh lien tuc
Am thanh giu nguyen tu video mau.
"""
import json
import os
import subprocess
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "assets")
W, H = 576, 1024

TRACK = json.load(open(os.path.join(A, "track.json")))
RIGHT_IMG = cv2.cvtColor(cv2.imread(os.path.join(A, "right.png")), cv2.COLOR_BGR2RGB)

BG_NAME = (246, 238, 211)      # nen be (RGB) o vung ten
CLOUD = (239, 235, 221)        # mau may (RGB) o vung so
YELLOW = (255, 208, 56)        # mau chu so (RGB)
INNER_R = 48.4                 # ban kinh trong cua vong den quanh avatar

# vung ten @Shinn trong video mau (x0, y0, x1, y1)
NAME_BOX = (28, 186, 560, 252)
NAME_X, NAME_CAP_TOP = 37, 194   # goc trai-tren cua chu "@Shinn"
NAME_MAX_W = 520
# vung so "3" va tam nhan "tuc" can giu lai
NUM_BOX = (200, 676, 372, 880)
LABEL_KEEP = (176, 686, 244, 730)
NUM_CX, NUM_CY, NUM_H = 306, 806, 138


def square_crop(img):
    h, w = img.shape[:2]
    s = min(h, w)
    y0 = max(0, int((h - s) * 0.3))
    x0 = (w - s) // 2
    return img[y0:y0 + s, x0:x0 + s]


def letter_avatar(name, size=256):
    """Avatar du phong khi nguoi dung khong co anh dai dien."""
    palette = [(239, 108, 108), (242, 153, 74), (86, 180, 120), (86, 156, 214), (155, 114, 207), (230, 110, 170)]
    seed = sum(ord(c) for c in (name or "?"))
    img = Image.new("RGB", (size, size), palette[seed % len(palette)])
    ch = (name or "?").strip().lstrip("@")[:1].upper() or "?"
    f = ImageFont.truetype(os.path.join(A, "Inter-Bold.otf"), int(size * 0.5))
    d = ImageDraw.Draw(img)
    d.text((size / 2, size / 2), ch, font=f, fill=(255, 255, 255), anchor="mm")
    return np.array(img)


def prep_avatar(img_rgb):
    d = int(round(INNER_R * 2)) + 8
    return cv2.resize(square_crop(img_rgb), (d, d), interpolation=cv2.INTER_AREA)


def paste_disk(frame, av, cx, cy):
    """Dan avatar hinh tron (khu rang cua) vao frame tai tam (cx, cy) co phan thap phan."""
    d = av.shape[0]
    half = d / 2.0
    x0 = int(np.floor(cx - half)) - 1
    y0 = int(np.floor(cy - half)) - 1
    size = d + 3
    # dich avatar theo phan thap phan bang warpAffine
    M = np.float32([[1, 0, (cx - half) - x0], [0, 1, (cy - half) - y0]])
    canvas = cv2.warpAffine(av, M, (size, size), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_REPLICATE)
    yy, xx = np.mgrid[0:size, 0:size]
    dist = np.hypot(xx + x0 - cx, yy + y0 - cy)
    alpha = np.clip(INNER_R - dist + 0.5, 0, 1)[..., None]
    roi = frame[y0:y0 + size, x0:x0 + size]
    if roi.shape[:2] != (size, size):
        return
    roi[:] = (canvas * alpha + roi * (1 - alpha)).astype(np.uint8)


def build_static_layers(username, days):
    """Ve chu @ten va so ngay len mot lop trong suot, dung chung cho moi frame."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # ---- @ten ----
    text = username.strip()
    if not text.startswith("@"):
        text = "@" + text
    size = 54
    while size > 22:
        f = ImageFont.truetype(os.path.join(A, "Inter-Bold.otf"), size)
        if d.textlength(text, font=f) <= NAME_MAX_W:
            break
        size -= 2
    # can theo dinh chu: chu @ Shinn cao ~47px, dat baseline cho thang hang voi video mau
    d.text((NAME_X, NAME_CAP_TOP + 46), text, font=f, fill=(0, 0, 0, 255), anchor="ls")

    # ---- so ngay ----
    s = str(int(days))
    nf = ImageFont.truetype(os.path.join(A, "Inter-Black.otf"), 220)
    bbox = d.textbbox((0, 0), s, font=nf, stroke_width=0)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    scale = NUM_H / th
    max_w = 240
    if tw * scale > max_w:
        scale = max_w / tw
    fs = max(40, int(220 * scale))
    nf = ImageFont.truetype(os.path.join(A, "Inter-Black.otf"), fs)
    stroke = max(5, int(fs * 0.04))
    cy = NUM_CY
    d.text((NUM_CX, cy), s, font=nf, fill=YELLOW + (255,), anchor="mm",
           stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    layer = np.array(layer)
    return layer[..., :3], layer[..., 3:4].astype(np.float32) / 255.0


def render(username, days, avatar_rgb=None, out_path=None):
    """Tra ve duong dan file mp4 da render."""
    # trai = anh co dinh (assets/right.png), phai = avatar nguoi go /diemdanh
    left = prep_avatar(RIGHT_IMG)
    right = prep_avatar(avatar_rgb if avatar_rgb is not None else letter_avatar(username))
    txt_rgb, txt_a = build_static_layers(username, days)

    out_path = out_path or tempfile.mktemp(suffix=".mp4")
    tpl = os.path.join(A, "template.mp4")

    dec = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", tpl, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE)
    tmp_video = out_path + ".v.mp4"
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", "30", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp_video],
        stdin=subprocess.PIPE)

    n = 0
    fsz = W * H * 3
    # che vung ten + vung so (tru tam nhan "tuc") bang mau nen
    cover = np.zeros((H, W), np.uint8)
    x0, y0, x1, y1 = NAME_BOX
    cover[y0:y1, x0:x1] = 1
    base_mask_num = None
    while True:
        buf = dec.stdout.read(fsz)
        if len(buf) < fsz:
            break
        fr = np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy()
        if n == 0:
            # tao mask so tu frame dau: pixel vang + vien den xung quanh, bo phan tam nhan
            hsv = cv2.cvtColor(fr, cv2.COLOR_RGB2HSV)
            yel = ((hsv[..., 0] > 15) & (hsv[..., 0] < 32) & (hsv[..., 1] > 130) & (hsv[..., 2] > 190)).astype(np.uint8)
            yel[:NUM_BOX[1], :] = 0
            yel[NUM_BOX[3]:, :] = 0
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))
            k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            m = cv2.dilate(yel, k)
            # trong khung nhan "tuc": chi xoa phan vang, giu nguyen chu trang tren nen den
            lx0, ly0, lx1, ly1 = LABEL_KEEP
            m[ly0:ly1, lx0:lx1] = cv2.dilate(yel, k2)[ly0:ly1, lx0:lx1]
            base_mask_num = m.astype(bool)
            name_bg = tuple(int(v) for v in np.median(fr[190:250, 560:572].reshape(-1, 3), axis=0))
            cloud_bg = tuple(int(v) for v in np.median(fr[760:780, 130:150].reshape(-1, 3), axis=0))
            name_mask = cover.astype(bool)
        fr[name_mask] = name_bg
        fr[base_mask_num] = cloud_bg
        # lop chu moi
        fr = (txt_rgb * txt_a + fr * (1 - txt_a)).astype(np.uint8)
        # avatar
        tr = TRACK[min(n, len(TRACK) - 1)]
        paste_disk(fr, left, tr["L"][0], tr["L"][1])
        paste_disk(fr, right, tr["R"][0], tr["R"][1])
        enc.stdin.write(fr.tobytes())
        n += 1
    enc.stdin.close()
    enc.wait()
    dec.wait()

    # ghep am thanh goc
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", tmp_video, "-i", tpl, "-map", "0:v", "-map", "1:a?",
         "-c:v", "copy", "-c:a", "copy", "-shortest", out_path], check=True)
    os.remove(tmp_video)
    return out_path


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "huycoi"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    print(render(name, days, out_path=os.path.join(HERE, "sample.mp4")))
