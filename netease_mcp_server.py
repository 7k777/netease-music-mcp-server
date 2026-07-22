"""
网易云音乐 MCP Server — SSE 模式
"""

import json, os, random, base64, urllib.request, urllib.parse, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

MODULUS = "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf6952280fe31fa725cbd44ab65327951c56ef57e4c0b5cb8a19a5e6a6f3e0195f4b8f2e6d6a4f7c4b4e6f5a3e6a4f7c4b4e6f5a3e6a4f7c4b4e6f5a3"
PUB_KEY = "010001"
NONCE = "0CoJUm6Qyw8W8jud"

def aes_encrypt(text, key):
    iv = b"0102030405060708"
    padder = padding.PKCS7(128).padder()
    padded = padder.update(text.encode()) + padder.finalize()
    e = Cipher(algorithms.AES(key.encode()), modes.CBC(iv)).encryptor()
    return base64.b64encode(e.update(padded) + e.finalize()).decode()

def rsa_encrypt(text):
    return format(pow(int.from_bytes(text[::-1].encode(), "big"), int(PUB_KEY, 16), int(MODULUS, 16)), "x")

def encrypt_params(params):
    text = json.dumps(params, separators=(",", ":"))
    k = "".join(random.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(16))
    return {"params": aes_encrypt(aes_encrypt(text, NONCE), k), "encSecKey": rsa_encrypt(k)}

def weapi(ep, data):
    data = data or {}
    data["csrf_token"] = ""
    body = urllib.parse.urlencode(encrypt_params(data)).encode()
    req = urllib.request.Request(f"https://music.163.com/weapi{ep}", data=body, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/", "Content-Type": "application/x-www-form-urlencoded"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())

TOOLS = [
    {"name": "search_songs", "description": "搜索歌曲", "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["keyword"]}},
    {"name": "get_song_detail", "description": "歌曲详情", "inputSchema": {"type": "object", "properties": {"song_id": {"type": "integer"}}, "required": ["song_id"]}},
    {"name": "get_lyric", "description": "获取歌词", "inputSchema": {"type": "object", "properties": {"song_id": {"type": "integer"}}, "required": ["song_id"]}},
    {"name": "get_playlist", "description": "歌单详情", "inputSchema": {"type": "object", "properties": {"playlist_id": {"type": "integer"}, "max_songs": {"type": "integer"}}, "required": ["playlist_id"]}},
    {"name": "search_playlists", "description": "搜索歌单", "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["keyword"]}},
    {"name": "recommend_playlists", "description": "热门歌单", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "search_artist", "description": "搜索歌手", "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}},
]

def do_call(name, args):
    if name == "search_songs":
        kw = args.get("keyword", "")
        lim = min(int(args.get("limit", 20)), 50)
        r = weapi("/search/get", {"s": kw, "type": 1, "limit": lim, "offset": 0})
        ss = r.get("result", {}).get("songs", [])
        t = f'搜索 "{kw}" 结果：'
        for i, s in enumerate(ss[:lim], 1):
            ar = "/".join(a.get("name", "") for a in s.get("artists", s.get("ar", [])))
            al = (s.get("album", s.get("al", {})) or {}).get("name", "")
            d = s.get("duration", s.get("dt", 0))
            t += f"\n{i}. {s.get('name')} - {ar}" + (f" [{al}]" if al else "") + f" ({d//60000}:{(d%60000)//1000:02d}) [ID:{s.get('id')}]"
        return {"content": [{"type": "text", "text": t}]}
    elif name == "get_song_detail":
        sid = args["song_id"]
        r = weapi("/v3/song/detail", {"c": json.dumps([{"id": sid}]), "ids": [sid]})
        ss = r.get("songs", [])
        if not ss:
            return {"content": [{"type": "text", "text": f"未找到"}], "isError": True}
        s = ss[0]
        ar = "/".join(a.get("name", "") for a in s.get("ar", []))
        al = s.get("al", {}).get("name", "")
        d = s.get("dt", 0)
        return {"content": [{"type": "text", "text": f"歌曲：{s.get('name')}\n歌手：{ar}\n专辑：{al}\n时长：{d//60000}:{(d%60000)//1000:02d}\nID：{sid}"}]}
    elif name == "get_lyric":
        r = weapi("/song/lyric", {"id": args["song_id"], "lv": -1, "kv": -1, "tv": -1})
        lyric = (r.get("lrc", {}) or {}).get("lyric", "") or ""
        if not lyric:
            return {"content": [{"type": "text", "text": "暂无歌词"}]}
        pl = []
        for line in lyric.split("\n"):
            c = line
            while "[" in c and "]" in c:
                c = c[c.find("]") + 1:].strip()
            if c:
                pl.append(c)
        return {"content": [{"type": "text", "text": "\n".join(pl) if pl else "暂无歌词"}]}
    elif name == "get_playlist":
        r = weapi("/v6/playlist/detail", {"id": args["playlist_id"], "n": 100, "s": 8})
        pl = r.get("playlist", {}) or {}
        t = f"歌单：{pl.get('name')}\n创建者：{(pl.get('creator', {}) or {}).get('nickname', '')}\n歌曲数：{pl.get('trackCount', 0)}\n播放量：{pl.get('playCount', 0)}"
        tr = pl.get("tracks", [])[:int(args.get("max_songs", 30))]
        if tr:
            t += f"\n\n歌曲列表（前{len(tr)}首）："
            for i, s in enumerate(tr, 1):
                ar = "/".join(a.get("name", "") for a in s.get("ar", []))
                d = s.get("dt", 0)
                t += f"\n{i}. {s.get('name')} - {ar} ({d//60000}:{(d%60000)//1000:02d}) [ID:{s.get('id')}]"
        return {"content": [{"type": "text", "text": t}]}
    elif name == "search_playlists":
        kw = args.get("keyword", "")
        lim = min(int(args.get("limit", 10)), 30)
        r = weapi("/search/get", {"s": kw, "type": 1000, "limit": lim, "offset": 0})
        ps = r.get("result", {}).get("playlists", [])
        t = f'搜索歌单 "{kw}" 结果：'
        for i, p in enumerate(ps, 1):
            t += f"\n{i}. {p.get('name')} - {(p.get('creator', {}) or {}).get('nickname', '')} ({p.get('trackCount', 0)}首) [ID:{p.get('id')}]"
        return {"content": [{"type": "text", "text": t}]}
    elif name == "recommend_playlists":
        r = weapi("/playlist/list", {"cat": "全部", "limit": 10, "offset": 0, "order": "hot"})
        ps = r.get("playlists", [])
        t = "热门歌单推荐："
        for i, p in enumerate(ps, 1):
            t += f"\n{i}. {p.get('name')}（{p.get('trackCount', 0)}首 · {p.get('playCount', 0)}次播放）[ID:{p.get('id')}]"
        return {"content": [{"type": "text", "text": t}]}
    elif name == "search_artist":
        kw = args.get("keyword", "")
        r = weapi("/search/get", {"s": kw, "type": 100, "limit": 10, "offset": 0})
        as_ = r.get("result", {}).get("artists", [])
        if not as_:
            return {"content": [{"type": "text", "text": f'未找到 "{kw}"'}], "isError": True}
        a = as_[0]
        t = f"歌手：{a.get('name')}\nID：{a.get('id')}"
        h = weapi("/artist/top/song", {"id": a.get("id"), "limit": 10, "offset": 0})
        if h.get("code") == 200:
            hs = h.get("songs", [])
            if hs:
                t += "\n\n热门歌曲："
                for i, s in enumerate(hs, 1):
                    t += f"\n{i}. {s.get('name')} [ID:{s.get('id')}]"
        return {"content": [{"type": "text", "text": t}]}
    return {"content": [{"type": "text", "text": f"未知工具"}], "isError": True}


class H(BaseHTTPRequestHandler):
    def _j(self, d, s=200):
        b = json.dumps(d, ensure_ascii=False).encode()
        self.send_response(s)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(f"event: session\ndata: {json.dumps({'session_id': 'netease-mcp-1'})}\n\n".encode())
        self.wfile.write(f"event: endpoint\ndata: /\n\n".encode())
        self.wfile.flush()
        try:
            while True:
                time.sleep(15)
                self.wfile.write(f": heartbeat\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        cl = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(cl) if cl > 0 else b"{}"
        try:
            body = json.loads(raw)
        except:
            return self._j({"jsonrpc": "2.0", "error": {"code": -32700, "message": "无效JSON"}}, 400)

        m = body.get("method", "")
        i = body.get("id")
        p = body.get("params", {}) or {}

        if m == "initialize":
            return self._j({"jsonrpc": "2.0", "id": i, "result": {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}, "serverInfo": {"name": "netease-music-mcp", "version": "1.0.0"}}})
        elif m in ("notifications/initialized", "notifications/cancelled"):
            return self._j({}, 202)
        elif m == "tools/list":
            return self._j({"jsonrpc": "2.0", "id": i, "result": {"tools": TOOLS}})
        elif m == "tools/call":
            try:
                return self._j({"jsonrpc": "2.0", "id": i, "result": do_call(p.get("name", ""), p.get("arguments", {}) or {})})
            except Exception as e:
                return self._j({"jsonrpc": "2.0", "id": i, "error": {"code": -32000, "message": str(e)}})
        else:
            return self._j({"jsonrpc": "2.0", "id": i, "error": {"code": -32601, "message": f"未知: {m}"}})

    def log_message(self, fmt, *a):
        print(f"[MCP] {fmt % a}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    print(f"🎵 网易云 MCP 端口 {port} 共{len(TOOLS)}工具")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.server_close()
