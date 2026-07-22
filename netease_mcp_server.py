"""
网易云音乐 API 服务
===================
用 Python 标准库 http.server 实现，仅依赖 cryptography。

RikkaHub 配置：
  类型: HTTP
  URL: https://你的域名.onrender.com

接口：
  GET /search/songs?keyword=xxx
  GET /song/123
  GET /lyric/123
  GET /playlist/123
  GET /search/playlists?keyword=xxx
  GET /recommend/playlists
  GET /search/artist?keyword=xxx
"""

import json
import os
import random
import base64
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

MODULUS = "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf6952280fe31fa725cbd44ab65327951c56ef57e4c0b5cb8a19a5e6a6f3e0195f4b8f2e6d6a4f7c4b4e6f5a3e6a4f7c4b4e6f5a3e6a4f7c4b4e6f5a3"
PUB_KEY = "010001"
NONCE = "0CoJUm6Qyw8W8jud"


def aes_encrypt(text, key):
    iv = b"0102030405060708"
    padder = padding.PKCS7(128).padder()
    padded = padder.update(text.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(key.encode()), modes.CBC(iv))
    encrypted = cipher.encryptor().update(padded) + cipher.encryptor().finalize()
    return base64.b64encode(encrypted).decode()


def rsa_encrypt(text):
    text_reversed = text[::-1]
    result = pow(int.from_bytes(text_reversed.encode(), "big"), int(PUB_KEY, 16), int(MODULUS, 16))
    return format(result, "x")


def encrypt_params(params):
    text = json.dumps(params, separators=(",", ":"))
    key = "".join(random.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(16))
    p1 = aes_encrypt(text, NONCE)
    p2 = aes_encrypt(p1, key)
    return {"params": p2, "encSecKey": rsa_encrypt(key)}


def weapi_request(endpoint, data):
    data = data or {}
    data["csrf_token"] = ""
    encrypted = encrypt_params(data)
    body = urllib.parse.urlencode(encrypted).encode()
    req = urllib.request.Request(
        f"https://music.163.com/weapi{endpoint}",
        data=body,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://music.163.com/",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def json_response(handler, data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def error_response(handler, msg, status=400):
    json_response(handler, {"error": msg}, status)


def parse_query(path):
    if "?" not in path:
        return {}, path
    path, qs = path.split("?", 1)
    params = urllib.parse.parse_qs(qs)
    return {k: v[0] for k, v in params.items()}, path


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        params, path = parse_query(self.path)
        try:
            self.route(params, path)
        except Exception as e:
            json_response(self, {"error": str(e)}, 500)

    def route(self, params, path):
        if path == "/" or path == "/health":
            return json_response(self, {"status": "ok"})

        if path == "/search/songs":
            kw = params.get("keyword", "")
            if not kw:
                return error_response(self, "缺少 keyword 参数")
            limit = min(int(params.get("limit", 20)), 50)
            result = weapi_request("/search/get", {"s": kw, "type": 1, "limit": limit, "offset": 0})
            if result.get("code") != 200:
                return json_response(self, {"songs": []})
            songs = result.get("result", {}).get("songs", [])
            fmt = []
            for s in songs:
                artists = "/".join(a.get("name", "") for a in s.get("artists", s.get("ar", [])))
                al = s.get("album", s.get("al", {})) or {}
                fmt.append({"id": s.get("id"), "name": s.get("name"), "artists": artists, "album": al.get("name", ""), "duration": s.get("duration", s.get("dt", 0))})
            return json_response(self, {"songs": fmt})

        if path.startswith("/song/"):
            try:
                sid = int(path.split("/")[-1])
            except ValueError:
                return error_response(self, "无效的歌曲ID")
            result = weapi_request("/v3/song/detail", {"c": json.dumps([{"id": sid}]), "ids": [sid]})
            songs = result.get("songs", [])
            if not songs:
                return error_response(self, "未找到歌曲", 404)
            s = songs[0]
            artists = "/".join(a.get("name", "") for a in s.get("ar", []))
            al = s.get("al", {})
            return json_response(self, {"id": s.get("id"), "name": s.get("name"), "artists": artists, "album": al.get("name", ""), "duration": s.get("dt", 0), "pic_url": al.get("picUrl", "")})

        if path.startswith("/lyric/"):
            try:
                sid = int(path.split("/")[-1])
            except ValueError:
                return error_response(self, "无效的歌曲ID")
            result = weapi_request("/song/lyric", {"id": sid, "lv": -1, "kv": -1, "tv": -1})
            lyric = (result.get("lrc", {}) or {}).get("lyric", "") or ""
            return json_response(self, {"lyric": lyric})

        if path.startswith("/playlist/"):
            try:
                pid = int(path.split("/")[-1])
            except ValueError:
                return error_response(self, "无效的歌单ID")
            result = weapi_request("/v6/playlist/detail", {"id": pid, "n": 100, "s": 8})
            pl = result.get("playlist", {}) or {}
            tracks = pl.get("tracks", [])
            fmt_tracks = []
            for s in tracks:
                artists = "/".join(a.get("name", "") for a in s.get("ar", []))
                fmt_tracks.append({"id": s.get("id"), "name": s.get("name"), "artists": artists, "duration": s.get("dt", 0)})
            return json_response(self, {"id": pl.get("id"), "name": pl.get("name"), "creator": (pl.get("creator", {}) or {}).get("nickname", ""), "track_count": pl.get("trackCount", 0), "play_count": pl.get("playCount", 0), "tracks": fmt_tracks})

        if path == "/search/playlists":
            kw = params.get("keyword", "")
            if not kw:
                return error_response(self, "缺少 keyword 参数")
            limit = min(int(params.get("limit", 10)), 30)
            result = weapi_request("/search/get", {"s": kw, "type": 1000, "limit": limit, "offset": 0})
            playlists = result.get("result", {}).get("playlists", [])
            fmt = []
            for p in playlists:
                fmt.append({"id": p.get("id"), "name": p.get("name"), "creator": (p.get("creator", {}) or {}).get("nickname", ""), "track_count": p.get("trackCount", 0), "play_count": p.get("playCount", 0)})
            return json_response(self, {"playlists": fmt})

        if path == "/recommend/playlists":
            result = weapi_request("/playlist/list", {"cat": "全部", "limit": 10, "offset": 0, "order": "hot"})
            playlists = result.get("playlists", [])
            fmt = []
            for p in playlists:
                fmt.append({"id": p.get("id"), "name": p.get("name"), "track_count": p.get("trackCount", 0), "play_count": p.get("playCount", 0)})
            return json_response(self, {"playlists": fmt})

        if path == "/search/artist":
            kw = params.get("keyword", "")
            if not kw:
                return error_response(self, "缺少 keyword 参数")
            result = weapi_request("/search/get", {"s": kw, "type": 100, "limit": 10, "offset": 0})
            artists = result.get("result", {}).get("artists", [])
            if not artists:
                return error_response(self, "未找到歌手", 404)
            a = artists[0]
            hot = weapi_request("/artist/top/song", {"id": a.get("id"), "limit": 10, "offset": 0})
            hot_songs = [{"id": s.get("id"), "name": s.get("name")} for s in (hot.get("songs") or [])]
            return json_response(self, {"id": a.get("id"), "name": a.get("name"), "hot_songs": hot_songs})

        return error_response(self, "未知路径", 404)

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"🎵 网易云音乐 API 服务启动 - 端口: {port}")
    print(f"   接口: /search/songs, /song/<id>, /lyric/<id>, /playlist/<id>, /search/playlists, /recommend/playlists, /search/artist")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
