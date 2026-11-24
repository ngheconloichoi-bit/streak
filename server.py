"""Server render video streak. Worker goi POST /render, nhan lai file mp4."""
import hashlib
import os
import threading
from collections import OrderedDict

import cv2
import numpy as np
from flask import Flask, Response, abort, request

import render as R

app = Flask(__name__)
KEY = os.environ.get("STREAK_KEY", "")
SEM = threading.Semaphore(2)          # toi da 2 video render cung luc
CACHE = OrderedDict()                 # key -> bytes mp4
CACHE_MAX = 40


@app.get("/")
def health():
    return "streak render ok"


@app.post("/render")
def render_video():
    if not KEY or request.headers.get("x-key") != KEY:
        abort(403)
    name = (request.form.get("name") or "user").strip()[:60] or "user"
    try:
        days = max(0, min(int(request.form.get("days", "1")), 99999))
    except ValueError:
        abort(400)

    avatar = None
    raw = b""
    f = request.files.get("avatar")
    if f:
        raw = f.read()[:5_000_000]
        arr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if arr is not None:
            avatar = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)

    ck = hashlib.sha1(name.encode() + b"|" + str(days).encode() + b"|" + raw).hexdigest()
    if ck in CACHE:
        CACHE.move_to_end(ck)
        return Response(CACHE[ck], mimetype="video/mp4")

    with SEM:
        path = R.render(name, days, avatar)
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
    return Response(data, mimetype="video/mp4")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
