"""
网易云音乐 MCP Server — Streamable HTTP
"""

import json, os, random, base64, urllib.request, urllib.parse, time
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
    encryptor = Cipher(algorithms.AES(key.encode()), modes.CBC(iv)).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode()

def rsa_encrypt(text):
    return format(pow(int.from_bytes(text[::-1].encode(), "big"), int(PUB_KEY, 16), int(MODULUS, 16)), "x")

def encrypt_params(params):
    text = json.dumps(params, separators=(",", ":"))
    key = "".join(random.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(16))
    p1 = aes_encrypt(text, NONCE)
    p2 = aes_encrypt(p1, key)
    return {"params": p2, "encSecKey": rsa_encrypt(key)}

def weapi(endpoint, data):
    data = data or {}
    data["csrf_token"] = ""
    encrypted = encrypt_params(data)
    body = urllib.parse.urlencode(encrypted).encode()
    req = urllib.request.Request(f"https://music.163.com/weapi{endpoint}", data=body, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/", "Content-Type": "application/x-www-form-urlencoded"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


TOOLS = [
    {"name": "search_songs", "description": "搜索网易云音乐歌曲", "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["keyword"]}},
    {"name": "get_song_detail", "description": "获取歌曲详细信息", "inputSchema": {"type": "object", "properties": {"song_id": {"type": "integer"}}, "required": ["song_id"]}},
    {"name": "get_lyric", "description": "获取歌曲歌词", "inputSchema": {"type": "object", "properties": {"song_id": {"type": "integer"}}, "required": ["song_id"]}},
    {"name": "get_playlist", "description": "获取歌单详情", "inputSchema": {"type": "object", "properties": {"playlist_id": {"type": "integer"}, "max_songs": {"type": "integer"}}, "required": ["playlist_id"]}},
    {"name": "search_playlists", "description": "搜索歌单", "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["keyword"]}},
    {"name": "recommend_playlists", "description": "热门推荐歌单", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "search_artist", "description": "搜索歌手", "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}},
]

def call_tool(name, args):
    if name == "search_songs":
        kw = args.get("keyword", "")
        limit = min(int(args.get("limit", 20)), 50)
        result = weapi("/search/get", {"s": kw, "type": 1, "limit": limit, "offset": 0})
        songs = result.get("result", {}).get("songs", [])
        lines = [f'搜索 "{kw}" 结果：']
        for i, s in enumerate(songs[:limit], 1):
            artists = "/".join(a.get("name", "") for a in s.get("artists", s.get("ar", [])))
            al = s.get("album", s.get("al", {})) or {}
            dur = s.get("duration", s.get("dt", 0))
            lines.append(f"{i}. {s.get('name')} - {artists}" + (f" [{al.get('name', '')}]" if al.get('name') else "") + f" ({dur//60000}:{(dur%60000)//1000:02d}) [ID:{s.get('id')}]")
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}
    elif name == "get_song_detail":
        sid = args["song_id"]
        result = weapi("/v3/song/detail", {"c": json.dumps([{"id": sid}]), "ids": [sid]})
        songs = result.get("songs", [])
        if not songs:
            return {"content": [{"type": "text", "text": f"未找到 {sid}"}], "isError": True}
        s = songs[0]
        artists = "/".join(a.get("name", "") for a in s.get("ar", []))
        al = s.get("al", {})
        dur = s.get("dt", 0)
        return {"content": [{"type": "text", "text": f"歌曲：{s.get('name')}\n歌手：{artists}\n专辑：{al.get('name', '')}\n时长：{dur//60000}:{(dur%60000)//1000:02d}\nID：{sid}"}]}
    elif name == "get_lyric":
        sid = args["song_id"]
        result = weapi("/song/lyric", {"id": sid, "lv": -1, "kv": -1, "tv": -1})
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
    elif name == "get_playlist":
        pid = args["playlist_id"]
        max_s = int(args.get("max_songs", 30))
        result = weapi("/v6/playlist/detail", {"id": pid, "n": 100, "s": 8})
        pl = result.get("playlist", {}) or {}
        text = f"歌单：{pl.get('name')}\n创建者：{(pl.get('creator', {}) or {}).get('nickname', '')}\n歌曲数：{pl.get('trackCount', 0)}\n播放量：{pl.get('playCount', 0)}"
        tracks = pl.get("tracks", [])[:max_s]
        if tracks:
            text += f"\n\n歌曲列表（前{len(tracks)}首）："
            for i, s in enumerate(tracks, 1):
                artists = "/".join(a.get("name", "") for a in s.get("ar", []))
                dur = s.get("dt", 0)
                text += f"\n{i}. {s.get('name')} - {artists} ({dur//60000}:{(dur%60000)//1000:02d}) [ID:{s.get('id')}]"
        return {"content": [{"type": "text", "text": text}]}
    elif name == "search_playlists":
        kw = args.get("keyword", "")
        limit = min(int(args.get("limit", 10)), 30)
        result = weapi("/search/get", {"s": kw, "type": 1000, "limit": limit, "offset": 0})
        playlists = result.get("result", {}).get("playlists", [])
        text = f'搜索歌单 "{kw}" 结果：'
        for i, p in enumerate(playlists, 1):
            text += f"\n{i}. {p.get('name')} - {(p.get('creator', {}) or {}).get('nickname', '')} ({p.get('trackCount', 0)}首) [ID:{p.get('id')}]"
        return {"content": [{"type": "text", "text": text}]}
    elif name == "recommend_playlists":
        result = weapi("/playlist/list", {"cat": "全部", "limit": 10, "offset": 0, "order": "hot"})
        playlists = result.get("playlists", [])
        text = "热门歌单推荐："
        for i, p in enumerate(playlists, 1):
            text += f"\n{i}. {p.get('name')}（{p.get('trackCount', 0)}首 · {p.get('playCount', 0)}次播放）[ID:{p.get('id')}]"
        return {"content": [{"type": "text", "text": text}]}
    elif name == "search_artist":
        kw = args.get("keyword", "")
        result = weapi("/search/get", {"s": kw, "type": 100, "limit": 10, "offset": 0})
        artists = result.get("result", {}).get("artists", [])
        if not artists:
            return {"content": [{"type": "text", "text": f'未找到 "{kw}"'}], "isError": True}
        a = artists[0]
        text = f"歌手：{a.get('name')}\nID：{a.get('id')}"
        hot = weapi("/artist/top/song", {"id": a.get("id"), "limit": 10, "offset": 0})
        if hot.get("code") == 200:
            hot_songs = hot.get("songs", [])
            if hot_songs:
                text += "\n\n热门歌曲："
                for i, s in enumerate(hot_songs, 1):
                    text += f"\n{i}. {s.get('name')} [ID:{s.get('id')}]"
        return {"content": [{"type": "text", "text": text}]}
    return {"content": [{"type": "text", "text": f"未知工具: {name}"}], "isError": True}


class Handler(BaseHTTPRequestHandler):
    def _json(self, data, status=200):
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
        self._json({})

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(f"event: session\n".encode())
        self.wfile.write(f"data: {json.dumps({'session_id': 'netease-mcp-1'})}\n\n".encode())
        self.wfile.write(f"event: endpoint\n".encode())
        self.wfile.write(f"data: /\n\n".encode())
        self.wfile.flush()
        try:
            while True:
                time.sleep(15)
                self.wfile.write(f": heartbeat\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(content_len) if content_len > 0 else b"{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return self._json({"jsonrpc": "2.0", "error": {"code": -32700, "message": "无效JSON"}}, 400)

        method = body.get("method", "")
        msg_id = body.get("id")
        params = body.get("params", {}) or {}

        if method == "initialize":
            return self._json({"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}, "serverInfo": {"name": "netease-music-mcp", "version": "1.0.0"}}})
        elif method == "notifications/initialized":
            return self._json({}, 202)
        elif method == "tools/list":
            return self._json({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {}) or {}
            try:
                result = call_tool(tool_name, tool_args)
                return self._json({"jsonrpc": "2.0", "id": msg_id, "result": result})
            except Exception as e:
                return self._json({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32000, "message": str(e)}})
        elif method == "notifications/cancelled":
            return self._json({}, 202)
        else:
            return self._json({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"未知: {method}"}})

    def log_message(self, format, *args):
        print(f"[MCP] {format % args}")


class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """支持多线程的 HTTP 服务器"""
    pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"🎵 网易云 MCP Server - 端口 {port} - {len(TOOLS)} 个工具")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
