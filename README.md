# 网易云音乐 MCP Server

基于 Python FastMCP 构建的网易云音乐 MCP 服务，内置 API 加密逻辑，无需额外部署后端服务。

支持 **SSE** 模式，适用于 RikkaHub 等只支持 HTTP/SSE 的 MCP 客户端。

## 功能

| 工具 | 说明 |
|---|---|
| `netease_search_songs` | 搜索歌曲（关键词找歌） |
| `netease_get_song_detail` | 获取歌曲详情（歌手、专辑、歌词预览） |
| `netease_get_lyric` | 获取完整歌词 |
| `netease_get_playlist` | 查看歌单里的歌曲列表 |
| `netease_search_playlists` | 搜索歌单 |
| `netease_recommend_playlists` | 热门歌单推荐 |
| `netease_search_artist` | 搜索歌手+热门歌曲 |

## 快速开始

### 1. 安装依赖

```bash
pip install mcp httpx cryptography
```

### 2. 启动服务

```bash
# SSE 模式（默认，适用于 RikkaHub）
python netease_mcp_server.py

# 自定义端口
python netease_mcp_server.py --port 8888

# 如果要用 stdio 模式（适用于 Claude Desktop 等）
python netease_mcp_server.py --transport stdio
```

启动后服务监听在 `http://0.0.0.0:8000`

### 3. RikkaHub 配置

在 RikkaHub 的 MCP 配置中添加：

- **类型**: SSE
- **URL**: `http://<你的电脑IP>:8000/mcp`

如果是在本机运行，填 `http://localhost:8000/mcp`

## 技术说明

- 使用网易云音乐 WeAPI 加密协议（AES-128-CBC + RSA）
- 无需登录即可搜索、获取歌词和歌单
- 所有请求直接从你的电脑发出，不经过第三方服务器
