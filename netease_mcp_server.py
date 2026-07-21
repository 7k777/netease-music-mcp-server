"""
网易云音乐 MCP Server
=====================
基于 Python FastMCP，内置网易云音乐 API 加密逻辑。
可直接运行，在 RikkaHub / Claude Desktop 等支持 MCP 的客户端中配置使用。

使用方法：
  pip install mcp httpx cryptography
  python netease_mcp_server.py

然后在 RikkaHub 的 MCP 配置中添加：
  - 类型: stdio
  - 命令: python /path/to/netease_mcp_server.py
"""

import json
import os
import random
import hashlib
import base64
from typing import Optional
from urllib.parse import quote

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

from mcp.server.fastmcp import FastMCP

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
    """AES-128-CBC 加密，返回 Base64 字符串"""
    iv = b"0102030405060708"
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(text.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(key.encode("utf-8")), modes.CBC(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded_data) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("utf-8")

def rsa_encrypt(text: str) -> str:
    """RSA 加密，返回十六进制字符串"""
    text_reversed = text[::-1]
    result = pow(
        int.from_bytes(text_reversed.encode("utf-8"), "big"),
        int(PUB_KEY, 16),
        int(MODULUS, 16),
    )
    return format(result, "x")

def get_random_secret_key(size: int = 16) -> str:
    """生成随机密钥"""
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(random.choice(chars) for _ in range(size))

def encrypt_params(params: dict) -> dict:
    """对请求参数进行加密，返回 {'params': ..., 'encSecKey': ...}"""
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
    """封装网易云音乐 HTTP 请求"""

    BASE_URL = "https://music.163.com"

    def __init__(self):
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://music.163.com/",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=30,
        )

    async def _weapi_request(self, endpoint: str, data: dict = None) -> dict:
        """发送加密的 POST 请求到 WeAPI 端点"""
        if data is None:
            data = {}
        data["csrf_token"] = ""
        encrypted = encrypt_params(data)
        url = f"{self.BASE_URL}/weapi{endpoint}"
        resp = await self.client.post(url, data=encrypted)
        return resp.json()

    async def search_songs(self, keyword: str, limit: int = 20, offset: int = 0) -> dict:
        """搜索歌曲"""
        data = {"s": keyword, "type": 1, "limit": limit, "offset": offset}
        return await self._weapi_request("/search/get", data)

    async def get_song_detail(self, song_id: int) -> dict:
        """获取歌曲详情"""
        data = {"c": json.dumps([{"id": song_id}]), "ids": [song_id]}
        return await self._weapi_request("/v3/song/detail", data)

    async def get_lyric(self, song_id: int) -> dict:
        """获取歌词"""
        data = {"id": song_id, "lv": -1, "kv": -1, "tv": -1}
        return await self._weapi_request("/song/lyric", data)

    async def get_song_url(self, song_id: int, br: int = 320000) -> dict:
        """获取歌曲播放地址"""
        data = {"ids": [song_id], "level": "standard", "encodeType": "aac", "br": br}
        return await self._weapi_request("/song/enhance/player/url/v1", data)

    async def get_playlist_detail(self, playlist_id: int) -> dict:
        """获取歌单详情"""
        data = {"id": playlist_id, "n": 100, "s": 8}
        return await self._weapi_request("/v6/playlist/detail", data)

    async def get_recommend_playlists(self, limit: int = 10) -> dict:
        """获取推荐歌单"""
        data = {"limit": limit, "offset": 0}
        return await self._weapi_request("/v1/discovery/recommend/resource", data)

    async def get_top_playlists(self, cat: str = "全部", limit: int = 20, offset: int = 0) -> dict:
        """获取热门歌单"""
        data = {"cat": cat, "limit": limit, "offset": offset, "order": "hot"}
        return await self._weapi_request("/playlist/list", data)


# ============================================================
# MCP Server
# ============================================================

mcp = FastMCP("netease-music", description="网易云音乐 MCP 服务 — 搜索歌曲、获取歌词、查看歌单")
api = NeteaseAPI()


def _format_song(item: dict) -> str:
    """格式化单首歌曲信息"""
    artists = "/".join(a.get("name", "未知") for a in item.get("artists", item.get("ar", [])))
    album = ""
    if "album" in item:
        album = item["album"].get("name", "")
    elif "al" in item:
        album = item["al"].get("name", "")
    song_id = item.get("id", "")
    name = item.get("name", "未知")
    duration = item.get("duration", item.get("dt", 0))
    mins = duration // 60000
    secs = (duration % 60000) // 1000
    return f"{name} — {artists}" + (f" [{album}]" if album else "") + f" ({mins}:{secs:02d}) [ID: {song_id}]"


@mcp.tool(
    name="netease_search_songs",
    description="搜索网易云音乐中的歌曲，返回歌曲列表（含 ID、歌手、专辑、时长）",
)
async def search_songs(keyword: str, limit: int = 20) -> str:
    """
    搜索网易云音乐歌曲。
    Args:
        keyword: 搜索关键词（歌曲名、歌手名等）
        limit: 返回结果数量，默认 20，最大 50
    """
    if limit > 50:
        limit = 50
    result = await api.search_songs(keyword, limit=limit)
    if result.get("code") != 200:
        return f"搜索失败：{result.get('message', '未知错误')}"
    songs = result.get("result", {}).get("songs", [])
    if not songs:
        return f'没有找到与 "{keyword}" 相关的歌曲。'
    lines = [f'搜索 "{keyword}" 结果（共 {len(songs)} 首）：']
    for i, song in enumerate(songs, 1):
        lines.append(f"{i}. {_format_song(song)}")
    return "\n".join(lines)


@mcp.tool(
    name="netease_get_song_detail",
    description="获取网易云音乐单首歌曲的详细信息（歌手、专辑、时长等）",
)
async def get_song_detail(song_id: int) -> str:
    """
    获取歌曲详细信息。
    Args:
        song_id: 歌曲 ID
    """
    result = await api.get_song_detail(song_id)
    if result.get("code") != 200:
        return f"获取失败：{result.get('message', '未知错误')}"
    songs = result.get("songs", [])
    if not songs:
        return f"未找到 ID 为 {song_id} 的歌曲。"
    song = songs[0]
    artists = "/".join(a.get("name", "未知") for a in song.get("ar", []))
    album = song.get("al", {})
    album_name = album.get("name", "未知专辑")
    duration = song.get("dt", 0)
    mins = duration // 60000
    secs = (duration % 60000) // 1000
    lines = [
        f"歌曲：{song.get('name', '未知')}",
        f"歌手：{artists}",
        f"专辑：{album_name}",
        f"时长：{mins}:{secs:02d}",
        f"ID：{song_id}",
    ]
    try:
        lyric_result = await api.get_lyric(song_id)
        if lyric_result.get("code") == 200:
            lrc = lyric_result.get("lrc", {})
            if lrc.get("lyric"):
                first_lines = lrc["lyric"].strip().split("\n")[:8]
                lyrics_text = "\n".join(
                    line.split("]", 1)[-1] if "]" in line else line
                    for line in first_lines
                )
                lines.append(f"\n歌词预览：\n{lyrics_text}")
    except Exception:
        pass
    return "\n".join(lines)


@mcp.tool(
    name="netease_get_lyric",
    description="获取网易云音乐歌曲的完整歌词",
)
async def get_lyric(song_id: int) -> str:
    """
    获取歌曲完整歌词。
    Args:
        song_id: 歌曲 ID
    """
    result = await api.get_lyric(song_id)
    if result.get("code") != 200:
        return f"获取歌词失败：{result.get('message', '未知错误')}"
    lrc = result.get("lrc", {})
    lyric_text = lrc.get("lyric", "")
    if not lyric_text:
        return "该歌曲暂无歌词。"
    pure_lines = []
    for line in lyric_text.strip().split("\n"):
        clean = line
        while "[" in clean and "]" in clean:
            start = clean.find("[")
            end = clean.find("]") + 1
            clean = clean[end:].strip()
        if clean:
            pure_lines.append(clean)
    return "\n".join(pure_lines) if pure_lines else "该歌曲暂无歌词。"


@mcp.tool(
    name="netease_get_playlist",
    description="获取网易云音乐歌单的详细信息，包括歌单中的所有歌曲",
)
async def get_playlist(playlist_id: int, max_songs: int = 30) -> str:
    """
    获取歌单详情及歌曲列表。
    Args:
        playlist_id: 歌单 ID
        max_songs: 最多返回的歌曲数量，默认 30
    """
    result = await api.get_playlist_detail(playlist_id)
    if result.get("code") != 200:
        return f"获取歌单失败：{result.get('message', '未知错误')}"
    pl = result.get("playlist", {})
    name = pl.get("name", "未知歌单")
    description = pl.get("description", "") or ""
    track_count = pl.get("trackCount", 0)
    play_count = pl.get("playCount", 0)
    creator = pl.get("creator", {}).get("nickname", "未知")
    lines = [
        f"歌单：{name}",
        f"创建者：{creator}",
        f"歌曲数：{track_count}",
        f"播放量：{play_count}",
    ]
    if description:
        lines.append(f"简介：{description[:200]}")
    tracks = pl.get("tracks", [])[:max_songs]
    if tracks:
        lines.append(f"\n歌曲列表（前 {len(tracks)} 首）：")
        for i, song in enumerate(tracks, 1):
            lines.append(f"{i}. {_format_song(song)}")
    else:
        lines.append("歌单暂无歌曲。")
    return "\n".join(lines)


@mcp.tool(
    name="netease_search_playlists",
    description="搜索网易云音乐的歌单，按关键词返回歌单列表",
)
async def search_playlists(keyword: str, limit: int = 10) -> str:
    """
    搜索歌单。
    Args:
        keyword: 搜索关键词
        limit: 返回数量，默认 10，最大 30
    """
    if limit > 30:
        limit = 30
    result = await api._weapi_request("/search/get", {
        "s": keyword, "type": 1000, "limit": limit, "offset": 0,
    })
    if result.get("code") != 200:
        return f"搜索失败：{result.get('message', '未知错误')}"
    playlists = result.get("result", {}).get("playlists", [])
    if not playlists:
        return f'没有找到与 "{keyword}" 相关的歌单。'
    lines = [f'搜索歌单 "{keyword}" 结果：']
    for i, pl in enumerate(playlists, 1):
        name = pl.get("name", "未知")
        pl_id = pl.get("id", "")
        track_count = pl.get("trackCount", 0)
        creator = pl.get("creator", {}).get("nickname", "未知")
        lines.append(f"{i}. {name} — {creator}（{track_count}首）[ID: {pl_id}]")
    return "\n".join(lines)


@mcp.tool(
    name="netease_recommend_playlists",
    description="获取网易云音乐的热门/推荐歌单",
)
async def recommend_playlists() -> str:
    """获取推荐歌单"""
    hot = await api.get_top_playlists(limit=10)
    if hot.get("code") == 200:
        pls = hot.get("playlists", [])
        lines = ["热门歌单推荐："]
        for i, pl in enumerate(pls, 1):
            name = pl.get("name", "未知")
            pl_id = pl.get("id", "")
            track_count = pl.get("trackCount", 0)
            play_count = pl.get("playCount", 0)
            lines.append(f"{i}. {name}（{track_count}首 · {play_count}次播放）[ID: {pl_id}]")
        return "\n".join(lines)
    return f"获取推荐失败"


@mcp.tool(
    name="netease_search_artist",
    description="搜索网易云音乐歌手，返回歌手信息和热门歌曲",
)
async def search_artist(keyword: str) -> str:
    """
    搜索歌手并返回热门歌曲。
    Args:
        keyword: 歌手名称
    """
    result = await api._weapi_request("/search/get", {
        "s": keyword, "type": 100, "limit": 10, "offset": 0,
    })
    if result.get("code") != 200:
        return f"搜索失败：{result.get('message', '未知错误')}"
    artists = result.get("result", {}).get("artists", [])
    if not artists:
        return f'没有找到歌手 "{keyword}"。'
    artist = artists[0]
    artist_id = artist.get("id", "")
    artist_name = artist.get("name", "未知")
    lines = [f"歌手：{artist_name}", f"ID：{artist_id}"]
    hot_result = await api._weapi_request("/artist/top/song", {
        "id": artist_id, "limit": 10, "offset": 0,
    })
    if hot_result.get("code") == 200:
        hot_songs = hot_result.get("songs", [])
        if hot_songs:
            lines.append("\n热门歌曲：")
            for i, song in enumerate(hot_songs, 1):
                lines.append(f"{i}. {_format_song(song)}")
    return "\n".join(lines)


if __name__ == "__main__":
    print("Starting Netease Music MCP Server...")
    mcp.run(transport="stdio")
