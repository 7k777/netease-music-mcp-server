# 网易云音乐 MCP Server

基于 Python FastMCP 构建的网易云音乐 MCP 服务，内置 API 加密逻辑，无需额外部署后端服务。

## 功能

- 搜索歌曲（`netease_search_songs`）
- 获取歌曲详情（`netease_get_song_detail`）
- 获取歌词（`netease_get_lyric`）
- 查看歌单（`netease_get_playlist`）
- 搜索歌单（`netease_search_playlists`）
- 热门歌单推荐（`netease_recommend_playlists`）
- 搜索歌手（`netease_search_artist`）

## 快速开始

```bash
# 1. 安装依赖
pip install mcp httpx cryptography

# 2. 启动服务
python netease_mcp_server.py
```

## RikkaHub 配置

在 RikkaHub 的 MCP 配置中添加：

```json
{
  "mcpServers": {
    "netease-music": {
      "command": "python",
      "args": ["/path/to/netease_mcp_server.py"]
    }
  }
}
```

或者直接在 RikkaHub MCP 配置界面选择 `stdio` 类型，填入命令：
```
python /path/to/netease_mcp_server.py
```

## 技术说明

- 使用网易云音乐 WeAPI 加密协议（AES-128-CBC + RSA）
- 无需登录即可搜索、获取歌词和歌单
- 歌曲播放地址需要有效的 Cookie（登录态），未登录时可能返回空
