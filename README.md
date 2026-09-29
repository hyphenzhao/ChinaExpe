# 玄学助手 (Metaphysics Assistant) v2

紫微斗数 · 子平八字 的排盘、学习与 AI 解读工作台。

- **自研排盘引擎**（纯 Python，`app/engine/`）：紫微斗数安星、生年四化/自化/飞化、大限·小限·流年·流月·流日·流时；子平八字四柱十神藏干纳音空亡地势自坐神煞、起运大运流年流月流日。口径按**文墨天机默认**（真太阳时、正月初一分年、全书四化表）与**测测**八字口径，用四份文墨天机导出逐宫逐星做黄金测试（`tests/`）。
- **命盘为中心的三栏界面**：左栏人物 + 按人物分组的对话；中栏命盘（四化/三合/飞星图层、点宫位看运限、底部大限→流年→流月→流日→流时条）；右栏 AI 对话（可折叠）。
- **AI 工具化解盘**：AI 通过工具读取引擎输出（`get_chart / get_horoscope / get_fly / get_bazi / get_bazi_timeline`）、检索典籍切片（`search_knowledge`）、**读典籍全文**（`list_classics / search_classics / read_classic`，返回 `路径:行号` 供核对）、提出修改建议（`propose_person_update`，需用户确认）、记备注（`add_note`）。绝不让 AI 自己排盘。解盘讲法与铁律写在 `app/prompts/jiepan.md`，改这个文件就改了网页端 AI 的工作方式。
- **知识库**：紫微麦文章 + 导入的典籍（紫微斗数全书、续道藏本、梁若瑜飞星问答、渊海子平、学习笔记、方法论 skills），本地倒排索引 + LanceDB/bge-m3 向量混合检索。
- **命盘导出**：人物每次保存都会把整张盘写成 `data/exports/<id>.json`（机器读）与 `.md`（人读），供外部 AI 会话直接读取，不必自己排盘。典籍完整原文另存 `data/classics/`，配 `.claude/skills/jiepan` 解盘工作法。

## 目录

```
app/
  engine/            排盘引擎（calendar / ziwei / bazi / wenmo_parser / settings）
  vendor/lunar_python  内置的 6tail lunar-python（农历/节气/干支）
  api/               people_api（人物+命盘）、chat_api（SSE 对话）、config_api、knowledge_api
  services/          person_service（人物档案+引擎缓存）、tools、agent_service、llm_service、
                     local_knowledge、knowledge_service、literature_importer
  static/            index.html + js/v2 + css/v2（原生 JS，无构建）
data/
  people/<id>.json   人物档案（出生信息 + 设置 + 备注）= 唯一数据源
  exports/<id>.json  排盘结果导出（紫微+八字+运限+文字版），保存人物时自动刷新
  exports/<id>.md    同一张盘的文字版；index.json 是人物清单
  classics/          典籍完整原文（按派别分目录，供 AI 会话精读）+ 书单.md
  readings/          解盘记录与验证台账（由解盘会话写入）
  sessions/          对话
  charts/            旧版手工命盘（仅作历史/校验参考，不再读取）
  lancedb/           向量库（build-vectors 生成）
  golden/            私有金样测试（真实导出，含个人生辰，不入库）
knowledge_base/      紫微麦文章 + literature/（导入的典籍片段，带 YAML 头）
tests/               公开测试（虚构生辰）
scripts/             migrate_people.py · build_vectors.py · build_classics.py ·
                     fetch_classics.py · restart_remote.sh · ui_smoke.py · deploy.sh
.claude/skills/jiepan/  解盘会话用的 skill（读导出 JSON + 典籍，禁止自行排盘）
```

## 运行

```bash
pip install -r requirements.txt        # lunar_python 已内置，无需安装
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
# 打开 http://127.0.0.1:8765 ，右上 ⚙️ 配置 DeepSeek/Ollama
```

测试：`pip install -r requirements-dev.txt && pytest tests -q`（公开测试，用虚构生辰：真太阳时、四柱、安星规则、生年四化、大限、流年流日干支、八字十神与大运流年链）。
与文墨天机 / 测测真实导出逐项比对的金样测试含个人生辰，放在 `data/golden/`（不入库），存在时 `scripts/deploy.sh` 会一并运行：`pytest tests data/golden -q`。

界面自检（需 `pip install playwright && playwright install chromium`）：`python scripts/ui_smoke.py http://127.0.0.1:8765`。

## 人物与排盘口径

人物档案字段：`display_name / gender / birth{solar 钟表时间, longitude, use_true_solar_time, hour_override} / settings{ziwei, bazi}`。

可选流派设置（`GET /api/people/meta/schools`）：四化表（全书默认 / 中州派 / 庚干天相忌）、火铃起法、天马年支/月支、年分界（正月初一/立春）、闰月处理、天伤天使、八字起运算法、晚子时日柱。默认全部 = 文墨天机。

校验：设置 → 「与文墨天机导出比对」，粘贴导出文本，逐宫逐星列差异。

## API

| 路径 | 说明 |
|---|---|
| `GET/POST /api/people`，`GET/PUT/DELETE /api/people/{id}` | 人物档案 |
| `POST /api/people/{id}/notes` | 备注 |
| `GET /api/people/{id}/ziwei` | 本命盘（palaces[].stars[]: name/category/brightness/birth_hua/self_hua_out/self_hua_in）+ decadals + fly |
| `GET …/ziwei/horoscope?date=` | 指定日期五级运限 |
| `GET …/ziwei/yearly-list?decadal=i`，`monthly-list?year=`，`daily-list?year=&month=&leap=`，`hourly-list?date=` | 运限条数据 |
| `GET …/ziwei/fly?palace=i` | 宫干飞化 |
| `GET /api/people/{id}/bazi`，`…/bazi/timeline?date=`，`…/bazi/liunian?dayun=i`，`…/bazi/liuyue?year=` | 八字 |
| `POST /api/people/{id}/wenmo-compare` | 与文墨导出比对 |
| `POST /api/people/{id}/export?date=`，`POST /api/people/export-all?date=` | 重写 `data/exports` 导出（运限按 date 或当天） |
| `GET/POST /api/chats`，`PUT /api/chats/{id}`（model/provider/thinking），`POST /api/chats/{id}/messages`（SSE: token/thinking/warning/tool_start/tool_result/done/error） | 对话 |
| `GET/PUT /api/config/library`，`GET /api/config/catalog` | 模型库与对话页选择器数据（含能力、是否需跳板） |
| `PUT /api/config/proxy` | 只改跳板设置并立即生效（`PUT /api/config` 不会动跳板） |
| `POST /api/knowledge/import-literature`，`build-index`，`build-vectors`，`GET status`，`POST query` | 知识库 |

## 部署（NAS）

代码目录即 SMB 共享目录，改完直接：

```bash
bash scripts/deploy.sh                    # pytest → JS 语法检查 → 重启 NAS 服务 → 开机启动核验 → 生产端 UI 自检
bash scripts/restart_remote.sh            # 只重启：kill uvicorn，systemd 自动拉起，健康检查
ssh haifeng@192.168.50.6 'cd /Volumes/Storage/Workspace/ChinaExpe && python3 scripts/build_vectors.py'   # 需要本机 Ollama bge-m3
```

Apache `:1248` 反代到 `127.0.0.1:8765`（`xuanxue-apache.conf`），systemd 单元见 `xuanxue.service`。

开机启动：`xuanxue.service` 已 `enabled`（`multi-user.target`，`Restart=always`），`apache2`、`ollama` 也已 enabled，`deploy.sh` 每次部署都会打印核验结果。如需修改单元文件（需要 sudo，普通账号做不了）：

```bash
sudo cp xuanxue.service /etc/systemd/system/xuanxue.service
sudo systemctl daemon-reload && sudo systemctl enable --now xuanxue
```

手机端：≤700px 自动进入紧凑盘（盘头折叠条 + 12 宫精简 + 点宫位弹出底部详情），顶栏「🔍 放大」切换为可横滚/双指缩放的完整盘；运限条默认折叠成一行摘要；支持添加到主屏幕（PWA manifest，无 Service Worker）。

## 给外部 AI 会话用的命盘与典籍

```bash
python scripts/build_classics.py      # 把 knowledge_base/literature 的切片拼回整本书
python scripts/fetch_classics.py      # 下载公有领域子平古籍（算准网），已存在的跳过
curl -X POST http://192.168.50.6:1248/api/people/export-all   # 按今天重算运限并导出
```

`data/exports/<id>.json` 的结构：`person`（出生与备注）、`ziwei`（十二宫星曜、生年四化、
`self_hua_out` 离心自化、`self_hua_in` 向心自化、`fly` 十二宫飞化、`decadals`）、
`ziwei_horoscope_now`（五级运限）、`ziwei_yearly_list` / `ziwei_monthly_list`、
`bazi`、`bazi_timeline_now`、`text`（同内容的中文文字版）。运限以导出时刻为准，换日期请调接口。

解盘会话在本目录开 Claude Code，使用 `.claude/skills/jiepan`：只读导出 JSON，禁止自行排盘，
引用典籍必须给文件与行号，结论写入 `data/readings/`。

## 代码分析：格局、身强弱与喜用、人生喜事、反推时辰

全部由代码计算，不接 AI；需要主观判断的部分（破格程度、事件解读、时辰结论）才交给 AI。

| 模块 | 内容 | 口径与局限 |
|---|---|---|
| `engine/bazi/analysis.py` + `tables.py` | 身强身弱（同类占比、得令得地得势、从强从弱门槛）、十神占比、格局候选（子平真诠取格次序 + 相对百分比，另列从格/专旺/化气）、喜忌用神排序（从格→扶抑→调候→通关→病药） | 藏干 60/30/10 权重 + 月令系数；测测等 App 算法未公开，数值不会逐位一致；各层加分为本系统口径 |
| `engine/ziwei/patterns.py` + `view.py` | 约 50 个吉格、14 个凶格的成格方向，附命宫三方四正与夹宫的煞忌空陷事实 | 按全书与中州/三合通行口径；文墨天机未公开清单；不判破格 |
| `engine/ziwei/events.py` + `engine/bazi/events.py` | 结婚、发财、高升、搬迁、添丁、高中逐年打分：流年 1.0、大限 0.6、本命 0.3，叠宫 ×1.5，八字流年十神加减不超过三成；未来 20 年取最强 5 年，往年强年另列；按流月挑农历月份 | 权重为本系统口径，只比较同一人不同年份的相对强弱 |
| `engine/timeshift.py` | 把真太阳时挪到目标时辰中点再反算钟表时间；一天 13 位（早子…亥、晚子），跨日连续 | 不用 `hour_override`，八字与紫微一起变 |
| `services/rectify_service.py` | 代码定义的问卷；候选时辰（大致时段前后各 2 个，或全天 13 位加前一天晚子）按经历打分：有年份的经历权重 3，离异与父母变故 2，头胎男女 1，兄弟姐妹 0.5 | 文字描述不打分，交给 AI；经历少于两条时置信度低 |

对话欢迎区（选中人物、空对话时）给出「紫微斗数格局分析」「十神格局分析」两张卡、【人生喜事】六宫格卡和「引导式反推」入口。
点卡片时前端发送 `action`，服务端把对应的代码结果与任务说明附在这条消息后交给 AI（会话里只存短问题）。
紫微页与八字页顶部有「◀日 ◀时 … 时▶ 日▶」步进器，预览相邻的盘，「应用到此人」才写回出生时间。

| 路径 | 说明 |
|---|---|
| `GET /api/people/{id}/analysis` | 格局、子平分析、人生喜事一次返回 |
| `GET /api/people/{id}/events?event=` | 人生喜事（可只看一类） |
| `GET /api/people/{id}/preview?days=&slots=` | 相邻日期/时辰的紫微与八字，不落盘 |
| `GET /api/people/meta/rectify-questions`，`GET/PUT /api/people/{id}/facts`，`POST /api/people/{id}/rectify` | 反推时辰问卷、经历、候选评分 |

AI 新工具：`get_ziwei_patterns`、`get_bazi_analysis`、`get_life_events`、`get_chart_variant`、`get_rectify_candidates`、`save_life_facts`。
解盘技能 `app/prompts/jiepan.md` 新增「破格评估」「人生喜事解读」「反推时辰」三节。

## 模型库与对话页切换

设置 → 模型库里跨提供商勾选多个模型，圆点标出默认；对话页输入框上方可为**当前会话**切换模型与思考档位，
选择写回 `data/sessions/<id>.json`。能力由 `app/services/model_registry.py` 按模型 id 推断：
`deepseek-reasoner` 不下发工具，Claude 与 GPT-5 系可调思考档位，其余默认不发思考参数。
思考档位翻译为 Anthropic 的 `thinking.budget_tokens` 或 OpenAI 的 `reasoning_effort`，
被接口拒绝时自动去掉参数重试一次。Anthropic 扩展思考下，`tool_use` 前的思考块会原样回传。

跳板设置与模型配置分开保存：`PUT /api/config` 永远不碰隧道，改跳板请用「应用跳板设置」。
（此前两者同用一个保存按钮，页面上没勾选的复选框会把正在用的隧道悄悄停掉。）

## 海外 API 跳板

DeepSeek 与 Ollama 直连。NAS 直连 `api.openai.com` 不通、`api.anthropic.com` 返回 403，所以这两家可以走跳板机 `45.77.19.55`：应用以普通用户身份开一条 `ssh -N -D 127.0.0.1:1080`，把 SOCKS5 交给 httpx 用。跳板机上不装任何东西、不改 sshd、不碰 sing-box，只是多一条 SSH 会话。

一次性授权（在跳板机上执行，不需要给本机 sudo）：

```bash
ssh root@45.77.19.55 'bash -s' < scripts/jumphost_authorize.sh
```

脚本只往 `~/.ssh/authorized_keys` 追加 NAS 的公钥，并用 `restrict,port-forwarding,command="/bin/false"` 限制这把钥匙只能做端口转发。之后在 设置 → 海外 API 跳板 勾选「启用跳板」，选择哪些提供商走跳板，按「启动隧道」「测试可达性」。开关、自动启动、SOCKS 地址、跳板机账号都存在 `data/config.json`。

| 路径 | 说明 |
|---|---|
| `GET /api/config/proxy` | 隧道状态（是否监听、由谁启动、哪些提供商走跳板） |
| `POST /api/config/proxy/start`，`/stop` | 启停隧道（只管本服务自己起的那条） |
| `POST /api/config/proxy/test` | 经隧道访问 OpenAI / Anthropic，401/403 也算连通 |

SOCKS 需要 `httpx[socks]`，已列入 requirements。

## 典籍来源

`literature_importer.py` 从 OpenClaw-Space（`OPENCLAW_SPACE` 环境变量或 `/Volumes/Storage/OpenClaw-Space`）读取：紫微斗数全书章节、紫微典籍（续道藏本、梁若瑜飞星问答）、子平读书笔记（渊海子平全文与笔记）、Notepad 教程，以及本仓库 `skills/` 的方法论文档；切成 ≤2600 字片段写入 `knowledge_base/literature/`。

## License

MIT（内置 lunar-python：MIT）
