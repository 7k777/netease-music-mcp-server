"""
网易云音乐 API 服务
===================
基于 FastAPI，提供网易云音乐的 HTTP 接口。
内置 API 加密逻辑，无需额外部署后端服务。

使用方法：
  pip install -r requirements.txt
  python netease_mcp_server.py

RikkaHub 配置：
  - 类型: HTTP
  - URL: https://你的域名.onrender.com
"""

import json
import os
import random
import base64

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="网易云音乐 API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 网易云音乐 API 加密工具
# ============================================================

MODULUS = (
    "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7"
    "b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf6952"
    "280fe31fa725cbd44ab65327951c56ef57e4c0b5cb8a19a5e6a6f3e0195"
    "f4b8f2e6d6a4f7c4b4e6f5a3e6a4f7c4b4e6f5a3e6a4f7c4b4e6f5a3"
)
PUB_KEY = "010001"
NONCE = "0CoJUm6Qyw8W8jud"


def aes_encrypt(text: str, key: str) -> str:
    iv = b"0102030405060708"
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(text.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(key.encode("utf-8")), modes.CBC(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded_data) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("utf-8")


def rsa_encrypt(text: str) -> str:
    text_reversed = text[::-1]
    result = pow(
        int.from_bytes(text_reversed.encode("utf-8"), "big"),
        int(PUB_KEY, 16),
        int(MODULUS, 16),
    )
    return format(result, "x")


def get_random_secret_key(size: int = 16) -> str:
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(random.choice(chars) for _ in range(size))


def encrypt_params(params: dict) -> dict:
    text = json.dumps(params, separators=(",", ":"))
    secret_key = get_random_secret_key(16)
    params_1 = aes_encrypt(text, NONCE)
    params_2 = aes_encrypt(params_1, secret_key)
    enc_sec_key = rsa_encrypt(secret_key)
    return {"params": params_2, "encSecKey": enc_sec_key}


# ============================================================
# API 客户端
# ============================================================

class NeteaseAPI:
    BASE_URL = "https://music.163.com"

    def __init__(self):
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://music.163.com/",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=30,
        )

    async def _weapi_request(self, endpoint: str, data: dict = None) -> dict:
        if data is None:
            data = {}
        data["csrf_token"] = ""
        encrypted = encrypt_params(data)
        url = f"{self.BASE_URL}/weapi{endpoint}"
        resp = await self.client.post(url, data=encrypted)
        return resp.json()


api = NeteaseAPI()


# ============================================================
# HTTP 接口
# ============================================================

@app.get("/")
def root():
    return {"status": "ok", "service": "netease-music-api"}


@app.get("/search/songs")
async def search_songs(keyword: str = Query(..., description="搜索关键词"), limit: int = Query(20, description="返回数量")):
    """搜索歌曲"""
    if limit > 50:
        limit = 50
    result = await api._weapi_request("/search/get", {
        "s": keyword, "type": 1, "limit": limit, "offset": 0,
    })
    if result.get("code") != 200:
        return {"error": result.get("message", "未知错误")}
    songs = result.get("result", {}).get("songs", [])
    formatted = []
    for s in songs:
        artists = "/".join(a.get("name", "未知") for a in s.get("artists", s.get("ar", [])))
        album = s.get("album", s.get("al", {}))
        album_name = album.get("name", "") if album else ""
        formatted.append({
            "id": s.get("id"),
            "name": s.get("name"),
            "artists": artists,
            "album": album_name,
            "duration": s.get("duration", s.get("dt", 0)),
        })
    return {"songs": formatted, "total": len(formatted)}


@app.get("/song/{song_id}")
async def song_detail(song_id: int):
    """获取歌曲详情"""
    data = {"c": json.dumps([{"id": song_id}]), "ids": [song_id]}
    result = await api._weapi_request("/v3/song/detail", data)
    if result.get("code") != 200:
        return {"error": result.get("message", "未知错误")}
    songs = result.get("songs", [])
    if not songs:
        return {"error": "未找到歌曲"}
    s = songs[0]
    artists = "/".join(a.get("name", "未知") for a in s.get("ar", []))
    album = s.get("al", {})
    return {
        "id": s.get("id"),
        "name": s.get("name"),
        "artists": artists,
        "album": album.get("name", "未知专辑"),
        "duration": s.get("dt", 0),
        "pic_url": album.get("picUrl", ""),
    }


@app.get("/lyric/{song_id}")
async def lyric(song_id: int):
    """获取歌词"""
    result = await api._weapi_request("/song/lyric", {
        "id": song_id, "lv": -1, "kv": -1, "tv": -1,
    })
    if result.get("code") != 200:
        return {"error": "获取歌词失败"}
    lrc = result.get("lrc", {})
    lyric_text = lrc.get("lyric", "")
    return {"lyric": lyric_text}


@app.get("/playlist/{playlist_id}")
async def playlist_detail(playlist_id: int):
    """获取歌单详情"""
    result = await api._weapi_request("/v6/playlist/detail", {
        "id": playlist_id, "n": 100, "s": 8,
    })
    if result.get("code") != 200:
        return {"error": "获取歌单失败"}
    pl = result.get("playlist", {})
    tracks = pl.get("tracks", [])
    formatted_tracks = []
    for s in tracks:
        artists = "/".join(a.get("name", "未知") for a in s.get("ar", []))
        formatted_tracks.append({
            "id": s.get("id"),
            "name": s.get("name"),
            "artists": artists,
            "duration": s.get("dt", 0),
        })
    return {
        "id": pl.get("id"),
        "name": pl.get("name"),
        "creator": pl.get("creator", {}).get("nickname", "未知"),
        "track_count": pl.get("trackCount", 0),
        "play_count": pl.get("playCount", 0),
        "tracks": formatted_tracks,
    }


@app.get("/search/playlists")
async def search_playlists(keyword: str = Query(..., description="搜索关键词"), limit: int = Query(10, description="返回数量")):
    """搜索歌单"""
    if limit > 30:
        limit = 30
    result = await api._weapi_request("/search/get", {
        "s": keyword, "type": 1000, "limit": limit, "offset": 0,
    })
    if result.get("code") != 200:
        return {"error": result.get("message", "未知错误")}
    playlists = result.get("result", {}).get("playlists", [])
    formatted = [{
        "id": p.get("id"),
        "name": p.get("name"),
        "creator": p.get("creator", {}).get("nickname", "未知"),
        "track_count": p.get("trackCount", 0),
        "play_count": p.get("playCount", 0),
    } for p in playlists]
    return {"playlists": formatted}


@app.get("/recommend/playlists")
async def recommend_playlists():
    """推荐歌单"""
    result = await api._weapi_request("/playlist/list", {
        "cat": "全部", "limit": 10, "offset": 0, "order": "hot",
    })
    if result.get("code") != 200:
        return {"error": "获取失败"}
    playlists = result.get("playlists", [])
    formatted = [{
        "id": p.get("id"),
        "name": p.get("name"),
        "track_count": p.get("trackCount", 0),
        "play_count": p.get("playCount", 0),
    } for p in playlists]
    return {"playlists": formatted}


@app.get("/search/artist")
async def search_artist(keyword: str = Query(..., description="歌手名称")):
    """搜索歌手"""
    result = await api._weapi_request("/search/get", {
        "s": keyword, "type": 100, "limit": 10, "offset": 0,
    })
    if result.get("code") != 200:
        return {"error": result.get("message", "未知错误")}
    artists = result.get("result", {}).get("artists", [])
    if not artists:
        return {"error": f'没有找到歌手 "{keyword}"'
    }
    a = artists[0]
    hot_result = await api._weapi_request("/artist/top/song", {
        "id": a.get("id"), "limit": 10, "offset": 0,
    })
    hot_songs = []
    if hot_result.get("code") == 200:
        for s in hot_result.get("songs", []):
            hot_songs.append({
                "id": s.get("id"),
                "name": s.get("name"),
            })
    return {
        "id": a.get("id"),
        "name": a.get("name"),
        "hot_songs": hot_songs,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"🎵 网易云音乐 API 服务启动", f"端口: {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
