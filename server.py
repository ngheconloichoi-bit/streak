"""Server render video streak.

POST /job    : Worker gui yeu cau, server tra loi 202 ngay, render xong TU GUI video len Telegram.
POST /render : (du phong) tra thang file mp4.
"""
import hashlib
import os
import threading
from collections import OrderedDict

import cv2
import numpy as np
import requests
from flask import Flask, Response, abort, jsonify, request

import render as R

app = Flask(__name__)
KEY = os.environ.get("STREAK_KEY", "")
TOKEN = os.environ.get("BOT_TOKEN", "")
SEM = threading.Semaphore(1)          # may yeu nen render lan luot tung video
CACHE = OrderedDict()
CACHE_MAX = 40


@app.get("/")
def health():
    return "streak render ok"


def decode_avatar(raw):
    if not raw:
        return None
    arr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB) if arr is not None else None


def get_video(name, days, raw):
    ck = hashlib.sha1(name.encode() + b"|" + str(days).encode() + b"|" + raw).hexdigest()
    if ck in CACHE:
        CACHE.move_to_end(ck)
        return CACHE[ck]
    with SEM:
        path = R.render(name, days, decode_avatar(raw))
    try:
        data = open(path, "rb").read()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    CACHE[ck] = data
    while len(CACHE) > CACHE_MAX:
        CACHE.popitem(last=False)
    return data


def tg(method, **kw):
    return requests.post(f"https://api.telegram.org/bot{TOKEN}/{method}", timeout=90, **kw)


def run_job(name, days, raw, chat_id, reply_to, caption):
    common = {"chat_id": chat_id, "parse_mode": "HTML", "allow_sending_without_reply": "true"}
    if reply_to:
        common["reply_to_message_id"] = reply_to
    try:
        data = get_video(name, days, raw)
        r = tg("sendVideo", data={**common, "caption": caption, "supports_streaming": "true",
                                  "width": "576", "height": "1024", "duration": "10"},
               files={"video": ("streak.mp4", data, "video/mp4")})
        if r.json().get("ok"):
            return
        print("sendVideo failed:", r.text[:300], flush=True)
    except Exception as e:  # noqa: BLE001
        print("job failed:", repr(e), flush=True)
    try:  # render/gui video loi -> van gui tin chu
        tg("sendMessage", data={**common, "text": caption})
    except Exception as e:  # noqa: BLE001
        print("fallback text failed:", repr(e), flush=True)


@app.post("/job")
def job():
    if not KEY or request.headers.get("x-key") != KEY:
        abort(403)
    if not TOKEN:
        return jsonify(ok=False, error="BOT_TOKEN chua duoc cai tren server"), 500
    name = (request.form.get("name") or "user").strip()[:60] or "user"
    try:
        days = max(0, min(int(request.form.get("days", "1")), 99999))
        chat_id = int(request.form["chat_id"])
        reply_to = int(request.form.get("reply_to") or 0)
    except (ValueError, KeyError):
        abort(400)
    caption = (request.form.get("caption") or "")[:1000]
    f = request.files.get("avatar")
    raw = f.read()[:5_000_000] if f else b""
    threading.Thread(target=run_job, args=(name, days, raw, chat_id, reply_to, caption), daemon=True).start()
    return jsonify(ok=True), 202


@app.post("/render")
def render_video():
    if not KEY or request.headers.get("x-key") != KEY:
        abort(403)
    name = (request.form.get("name") or "user").strip()[:60] or "user"
    try:
        days = max(0, min(int(request.form.get("days", "1")), 99999))
    except ValueError:
        abort(400)
    f = request.files.get("avatar")
    raw = f.read()[:5_000_000] if f else b""
    return Response(get_video(name, days, raw), mimetype="video/mp4")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))