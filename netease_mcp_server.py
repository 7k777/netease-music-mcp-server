"""
网易云音乐 MCP Server — Streamable HTTP 模式
=============================================
实现 MCP Streamable HTTP 传输协议，兼容 RikkaHub。

RikkaHub 配置：
  传输类型: Streamable HTTP
  服务器地址: https://netease-music-mcp-server.onrender.com/
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

# ============================================================
# 网易云音乐 API 加密
# ============================================================

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
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/", "Content-Type": "application/x-www-form-urlencoded"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


class NeteaseMusicMCP:
    """网易云音乐 MCP 工具"""

    SERVER_INFO = {
        "name": "netease-music-mcp",
        "version": "1.0.0",
    }

    CAPABILITIES = {
        "tools": {},
        "prompts": {},
        "resources": {},
    }

    TOOLS = [
        {
            "name": "search_songs",
            "description": "搜索网易云音乐歌曲，返回歌曲列表",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                    "limit": {"type": "integer", "description": "返回数量", "default": 20},
                },
                "required": ["keyword"],
            },
        },
        {
            "name": "get_song_detail",
            "description": "获取歌曲详细信息",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "song_id": {"type": "integer", "description": "歌曲ID"},
                },
                "required": ["song_id"],
            },
        },
        {
            "name": "get_lyric",
            "description": "获取歌曲歌词",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "song_id": {"type": "integer", "description": "歌曲ID"},
                },
                "required": ["song_id"],
            },
        },
        {
            "name": "get_playlist",
            "description": "获取歌单详情和歌曲列表",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "playlist_id": {"type": "integer", "description": "歌单ID"},
                    "max_songs": {"type": "integer", "description": "最多返回歌曲数", "default": 30},
                },
                "required": ["playlist_id"],
            },
        },
        {
            "name": "search_playlists",
            "description": "搜索歌单",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                    "limit": {"type": "integer", "description": "返回数量", "default": 10},
                },
                "required": ["keyword"],
            },
        },
        {
            "name": "recommend_playlists",
            "description": "获取热门推荐歌单",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "search_artist",
            "description": "搜索歌手信息及热门歌曲",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "歌手名称"},
                },
                "required": ["keyword"],
            },
        },
    ]

    async def call_tool(self, name, args):
        if name == "search_songs":
            return await self._search_songs(args.get("keyword", ""), args.get("limit", 20))
        elif name == "get_song_detail":
            return await self._get_song_detail(args["song_id"])
        elif name == "get_lyric":
            return await self._get_lyric(args["song_id"])
        elif name == "get_playlist":
            return await self._get_playlist(args["playlist_id"], args.get("max_songs", 30))
        elif name == "search_playlists":
            return await self._search_playlists(args.get("keyword", ""), args.get("limit", 10))
        elif name == "recommend_playlists":
            return await self._recommend_playlists()
        elif name == "search_artist":
            return await self._search_artist(args.get("keyword", ""))
        else:
            raise ValueError(f"未知工具: {name}")

    async def _search_songs(self, keyword, limit=20):
        if limit > 50:
            limit = 50
        result = weapi_request("/search/get", {"s": keyword, "type": 1, "limit": limit, "offset": 0})
        songs = result.get("result", {}).get("songs", [])
        lines = [f'搜索 "{keyword}" 结果：']
        for i, s in enumerate(songs[:limit], 1):
            artists = "/".join(a.get("name", "") for a in s.get("artists", s.get("ar", [])))
            al = s.get("album", s.get("al", {})) or {}
            album_name = al.get("name", "")
            dur = s.get("duration", s.get("dt", 0))
            mins, secs = dur // 60000, (dur % 60000) // 1000
            lines.append(f"{i}. {s.get('name')} - {artists}" + (f" [{album_name}]" if album_name else "") + f" ({mins}:{secs:02d}) [ID:{s.get('id')}]")
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    async def _get_song_detail(self, song_id):
        result = weapi_request("/v3/song/detail", {"c": json.dumps([{"id": song_id}]), "ids": [song_id]})
        songs = result.get("songs", [])
        if not songs:
            return {"content": [{"type": "text", "text": f"未找到 ID 为 {song_id} 的歌曲"}], "isError": True}
        s = songs[0]
        artists = "/".join(a.get("name", "") for a in s.get("ar", []))
        al = s.get("al", {})
        dur = s.get("dt", 0)
        mins, secs = dur // 60000, (dur % 60000) // 1000
        text = f"歌曲：{s.get('name')}\n歌手：{artists}\n专辑：{al.get('name', '')}\n时长：{mins}:{secs:02d}\nID：{song_id}"
        return {"content": [{"type": "text", "text": text}]}

    async def _get_lyric(self, song_id):
        result = weapi_request("/song/lyric", {"id": song_id, "lv": -1, "kv": -1, "tv": -1})
        lyric = (result.get("lrc", {}) or {}).get("lyric", "") or ""
        if not lyric:
            return {"content": [{"type": "text", "text": "暂无歌词"}]}
        pure = []
        for line in lyric.split("\n"):
            clean = line
            while "[" in clean and "]" in clean:
                clean = clean[clean.find("]") + 1:].strip()
            if clean:
                pure.append(clean)
        return {"content": [{"type": "text", "text": "\n".join(pure) if pure else "暂无歌词"}]}

    async def _get_playlist(self, playlist_id, max_songs=30):
        result = weapi_request("/v6/playlist/detail", {"id": playlist_id, "n": 100, "s": 8})
        pl = result.get("playlist", {}) or {}
        name = pl.get("name", "未知歌单")
        creator = (pl.get("creator", {}) or {}).get("nickname", "未知")
        track_count = pl.get("trackCount", 0)
        play_count = pl.get("playCount", 0)
        text = f"歌单：{name}\n创建者：{creator}\n歌曲数：{track_count}\n播放量：{play_count}"
        tracks = pl.get("tracks", [])[:max_songs]
        if tracks:
            text += f"\n\n歌曲列表（前{len(tracks)}首）："
            for i, s in enumerate(tracks, 1):
                artists = "/".join(a.get("name", "") for a in s.get("ar", []))
                dur = s.get("dt", 0)
                mins, secs = dur // 60000, (dur % 60000) // 1000
                text += f"\n{i}. {s.get('name')} - {artists} ({mins}:{secs:02d}) [ID:{s.get('id')}]"
        return {"content": [{"type": "text", "text": text}]}

    async def _search_playlists(self, keyword, limit=10):
        if limit > 30:
            limit = 30
        result = weapi_request("/search/get", {"s": keyword, "type": 1000, "limit": limit, "offset": 0})
        playlists = result.get("result", {}).get("playlists", [])
        text = f'搜索歌单 "{keyword}" 结果：'
        for i, p in enumerate(playlists, 1):
            text += f"\n{i}. {p.get('name')} - {(p.get('creator', {}) or {}).get('nickname', '')} ({p.get('trackCount', 0)}首) [ID:{p.get('id')}]"
        return {"content": [{"type": "text", "text": text}]}

    async def _recommend_playlists(self):
        result = weapi_request("/playlist/list", {"cat": "全部", "limit": 10, "offset": 0, "order": "hot"})
        playlists = result.get("playlists", [])
        text = "热门歌单推荐："
        for i, p in enumerate(playlists, 1):
            text += f"\n{i}. {p.get('name')}（{p.get('trackCount', 0)}首 · {p.get('playCount', 0)}次播放）[ID:{p.get('id')}]"
        return {"content": [{"type": "text", "text": text}]}

    async def _search_artist(self, keyword):
        result = weapi_request("/search/get", {"s": keyword, "type": 100, "limit": 10, "offset": 0})
        artists = result.get("result", {}).get("artists", [])
        if not artists:
            return {"content": [{"type": "text", "text": f'未找到歌手 "{keyword}"'}], "isError": True}
        a = artists[0]
        text = f"歌手：{a.get('name')}\nID：{a.get('id')}"
        hot = weapi_request("/artist/top/song", {"id": a.get("id"), "limit": 10, "offset": 0})
        hot_songs = hot.get("songs", []) if hot.get("code") == 200 else []
        if hot_songs:
            text += "\n\n热门歌曲："
            for i, s in enumerate(hot_songs, 1):
                text += f"\n{i}. {s.get('name')} [ID:{s.get('id')}]"
        return {"content": [{"type": "text", "text": text}]}


mcp = NeteaseMusicMCP()


# ============================================================
# MCP Streamable HTTP 处理器
# ============================================================

class MCPHandler(BaseHTTPRequestHandler):
    """处理 MCP Streamable HTTP 请求"""

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json({})

    def do_GET(self):
        if self.path == "/" or self.path == "/health":
            return self._send_json({"status": "ok", "service": "netease-music-mcp"})
        self._send_json({"error": "not found"}, 404)

    async def _handle_mcp_request(self, body):
        """处理 MCP JSON-RPC 请求"""
        method = body.get("method", "")
        msg_id = body.get("id")
        params = body.get("params", {}) or {}

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {
                        "tools": {},
                    },
                    "serverInfo": mcp.SERVER_INFO,
                },
            }

        elif method == "notifications/initialized":
            return None  # 无响应

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": mcp.TOOLS,
                },
            }

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {}) or {}
            try:
                result = await mcp.call_tool(tool_name, tool_args)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": result,
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32000, "message": str(e)},
                }

        elif method == "notifications/cancelled":
            return None

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"未知方法: {method}"},
        }

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            return self._send_json({"jsonrpc": "2.0", "error": {"code": -32700, "message": "无效的 JSON"}}, 400)

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            response = loop.run_until_complete(self._handle_mcp_request(body))
        finally:
            loop.close()

        if response is not None:
            self._send_json(response)
        else:
            self._send_json({}, 202)

    def log_message(self, format, *args):
        print(f"[MCP] {format % args}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), MCPHandler)
    print(f"🎵 网易云音乐 MCP Server")
    print(f"   端口: {port}")
    print(f"   传输: Streamable HTTP")
    print(f"   工具: {len(mcp.TOOLS)} 个")
    for t in mcp.TOOLS:
        print(f"     - {t['name']}: {t['description']}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
