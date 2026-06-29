# 玄学助手 (Metaphysics Assistant)

互动式玄学助手 — 紫微斗数 & 十神·子平命理解盘。

基于 FastAPI + 前端 SPA，支持 DeepSeek / Ollama 双后端，配备 LanceDB 知识库 RAG 检索。

## 功能

- **紫微斗数** — 命盘可视化、十二宫解读、四化分析
- **八字十神·子平法** — 四柱排盘、日主强弱、格局喜忌
- **AI 智能导入** — 粘贴文墨天机等排盘软件文本，自动解析为结构化命盘
- **知识库 RAG** — 基于 LanceDB 的中文命理经典知识检索
- **多模型支持** — DeepSeek API / 本地 Ollama
- **SSE 流式对话** — 逐字输出，体验流畅

## 目录结构

```
ChinaExpe/
├── app/
│   ├── main.py                  # FastAPI 入口
│   ├── api/
│   │   ├── chat_api.py          # 对话 SSE 接口
│   │   ├── charts_api.py        # 命盘 CRUD 接口
│   │   ├── config_api.py        # 配置管理接口
│   │   └── knowledge_api.py     # 知识库接口
│   ├── models/
│   │   ├── chat.py              # 会话/消息模型
│   │   ├── chart.py             # 命盘数据模型
│   │   └── config.py            # 配置模型
│   ├── services/
│   │   ├── agent_service.py     # System prompt & 上下文组装
│   │   ├── llm_service.py       # DeepSeek/Ollama 统一流式接口
│   │   ├── chart_service.py     # 命盘解析 & 前端数据变换
│   │   ├── chart_import_service.py  # AI 智能排盘导入
│   │   ├── skill_loader.py      # 从 SKILL.md 加载技能知识
│   │   └── knowledge_service.py # LanceDB RAG 检索
│   └── static/                  # 前端 SPA (HTML/CSS/JS)
├── data/
│   ├── config.json              # 运行时配置
│   └── sessions/                # 对话会话持久化
├── requirements.txt
├── setup.sh                     # 一键设置脚本
├── start.sh                     # 开发启动脚本
├── xuanxue-apache.conf          # Apache 反向代理配置
└── xuanxue.service              # systemd 服务文件
```

## 依赖

### 必需

| 组件 | 用途 |
|------|------|
| **Python 3.10+** | 运行后端 |
| **DeepSeek API Key** 或 **Ollama** | LLM 推理 |

### 可选

| 组件 | 用途 | 不装的影响 |
|------|------|-----------|
| **Apache2** | 反向代理 + 静态文件服务 | 直接用 uvicorn 对外暴露即可 |
| **Ollama + bge-m3** | LanceDB 知识库向量检索 | RAG 功能降级，不影响基础对话 |
| **LanceDB 知识库** | 命理经典知识检索增强 | `is_available()` 返回 false，静默跳过 |
| **命盘数据目录** | 已有命盘的 JSON 文件 | 只能通过 AI 导入或手动创建 |

## 快速开始

### 1. 安装 Python 依赖

```bash
cd /path/to/ChinaExpe
pip install -r requirements.txt
```

### 2. 配置 LLM 后端

#### 方案 A：使用 DeepSeek（推荐，零运维）

创建 `data/config.json`：

```json
{
  "provider": "deepseek",
  "deepseek_api_key": "sk-your-api-key",
  "deepseek_base_url": "https://api.deepseek.com",
  "default_model": "deepseek-chat"
}
```

#### 方案 B：使用本地 Ollama

确保 Ollama 已运行并拉取了模型：

```bash
ollama pull qwen2.5:14b    # 或其他中文模型
```

创建 `data/config.json`：

```json
{
  "provider": "ollama",
  "ollama_host": "http://127.0.0.1",
  "ollama_port": 11434,
  "default_model": "qwen2.5:14b"
}
```

### 3. 配置数据目录（硬编码路径）

⚠️ **重要**：以下路径当前为硬编码，部署前请确认或修改。

| 文件 | 路径 | 说明 |
|------|------|------|
| `skill_loader.py:8` | `/Volumes/Storage/OpenClaw-Space/skills` | 技能 SKILL.md 目录 |
| `chart_service.py:6` | `/Volumes/Storage/OpenClaw-Space/命盘` | 命盘 JSON 数据目录 |
| `chart_import_service.py:16-18` | 同上 | AI 导入的 schema & 示例 |
| `knowledge_service.py:8` | `~/.openclaw/memory/lancedb` | LanceDB 知识库路径 |
| `config_api.py:14` | `data/config.json` | 相对于项目根目录 |

> **最简单的迁移方式**：将这些硬编码路径替换为相对于项目根目录的路径，或通过环境变量配置。详见下方 [路径迁移指南](#路径迁移指南)。

### 4. 启动

**开发模式**（带热重载）：

```bash
bash start.sh
# 监听 http://127.0.0.1:8765
```

**生产模式**（无热重载）：

```bash
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

### 5. 访问

浏览器打开 `http://127.0.0.1:8765`，在设置页面配置 API 后端即可开始对话。

## 生产部署

### Apache 反向代理（可选）

如果需要在公网提供服务，建议 uvicorn 只监听 localhost，前面挂 Apache：

```bash
# 1. 复制配置
sudo cp xuanxue-apache.conf /etc/apache2/sites-available/xuanxue.conf

# 2. 启用模块和站点
sudo a2enmod proxy proxy_http
sudo a2ensite xuanxue.conf
sudo systemctl reload apache2
```

Apache 配置默认监听 **1248** 端口，反代到 `127.0.0.1:8765`。

### systemd 开机自启

```bash
# 1. 安装服务（先按需修改 xuanxue.service 中的路径）
sudo cp xuanxue.service /etc/systemd/system/xuanxue.service
sudo systemctl daemon-reload

# 2. 启动 & 设置开机自启
sudo systemctl start xuanxue
sudo systemctl enable xuanxue

# 3. 查看状态
sudo systemctl status xuanxue

# 4. 查看日志
journalctl -u xuanxue -f
```

服务配置要点：

```ini
[Service]
User=你的用户名
WorkingDirectory=/path/to/ChinaExpe
ExecStart=python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8765
Restart=always          # 崩溃自动重启
RestartSec=5            # 等 5 秒再重启

[Install]
WantedBy=multi-user.target  # 开机自启
```

### 防火墙

如果用 Apache 对外暴露，需要开放对应端口：

```bash
sudo nft add rule inet filter input tcp dport 1248 accept
```

## 路径迁移指南

当前项目中存在一些 macOS 开发环境的硬编码路径。迁移到其他机器时，需要修改以下位置：

### 最小改动方案

创建符号链接，避免修改代码：

```bash
# 技能目录
ln -s /your/actual/skills/path /Volumes/Storage/OpenClaw-Space/skills

# 命盘数据目录
ln -s /your/actual/charts/path /Volumes/Storage/OpenClaw-Space/命盘
```

### 代码修改方案

搜索以下路径并替换为你的实际路径：

```bash
grep -rn "OpenClaw-Space" app/
grep -rn "/Volumes/Storage" app/
```

涉及文件：

| 文件 | 行 | 路径 |
|------|-----|------|
| `app/services/skill_loader.py` | 8 | `SKILLS_PATH` |
| `app/services/chart_service.py` | 6 | `CHART_BASE` |
| `app/services/chart_import_service.py` | 16-18 | `SCHEMA_PATH`, `EXAMPLES_PATH`, `SKILLS_PATH` |
| `app/services/knowledge_service.py` | 8 | `LANCE_DB_PATH` |
| `app/main.py` | 19 | `data_dir` |

## 技能系统

技能文件位于 `SKILLS_PATH` 指向的目录，采用 SKILL.md 格式：

```
skills/
├── ziwei-doushu/         # 紫微斗数
│   ├── SKILL.md
│   └── references/
│       ├── calculation.md
│       ├── stars.md
│       ├── sihua.md
│       └── patterns.md
├── bazi-master/          # 八字大师
│   ├── SKILL.md
│   └── references/
│       └── tiangan-dizhi.md
├── bazi-classical/       # 八字经典
│   ├── SKILL.md
│   └── references/
│       ├── wuxing-tables.md
│       ├── shichen-table.md
│       └── dayun-rules.md
└── ziping-zhengliu/      # 子平正解
    ├── SKILL.md
    └── docs/
        └── yuanhai_ziping.md
```

技能加载时会：
1. 优先提取 `解释边界`、`核心规则`、`回应风格` 段落（确保客观中立的分析风格）
2. 加载 SKILL.md 正文（去重后的方法论知识）
3. 按需加载参考文件（星曜表、四化表等）

## 知识库（可选）

RAG 知识库使用 LanceDB 存储，需要：

1. 安装 Ollama 并拉取嵌入模型：
   ```bash
   ollama pull bge-m3
   ```

2. 确保 LanceDB 数据库存在于 `~/.openclaw/memory/lancedb`，表名为 `ziwei_knowledge`

如果知识库不可用，系统会自动降级，不影响基础对话功能。

## API 路由

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/config` | GET/PUT | 获取/更新 LLM 配置 |
| `/api/config/models` | GET | 列出可用模型 |
| `/api/config/test` | POST | 测试 API 连接 |
| `/api/chats` | GET/POST | 列出/创建会话 |
| `/api/chats/{id}` | GET/DELETE | 获取/删除会话 |
| `/api/chats/{id}/messages` | POST | 发送消息（SSE 流式） |
| `/api/chats/{id}/messages/{mid}` | DELETE | 删除消息 |
| `/api/people` | GET/POST | 列出/创建人物 |
| `/api/people/{name}` | DELETE | 删除人物及命盘 |
| `/api/people/{name}/{type}` | GET/DELETE | 获取/删除命盘 (ziwei/shishen) |
| `/api/people/{name}/meta` | PUT | 更新人物显示名 |
| `/api/people/{name}/import` | POST | AI 智能导入命盘 |
| `/api/knowledge` | GET | 查询知识库 |

## 技术栈

- **后端**: FastAPI + uvicorn (Python)
- **前端**: 原生 JavaScript SPA，无框架
- **LLM**: DeepSeek API / Ollama (OpenAI 兼容接口)
- **向量数据库**: LanceDB
- **嵌入模型**: bge-m3 (via Ollama)
- **反向代理**: Apache2 (可选)

## License

MIT
