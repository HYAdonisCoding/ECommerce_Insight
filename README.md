# ECommerce_Insight — 电火灶电商数据分析

> 京东 + 淘宝双平台电火灶（电焰灶/电燃灶）商品数据采集、评价分析与可视化报告

## 项目概述

本项目通过 **Chrome DevTools Protocol (CDP)** 自动化采集京东、淘宝两大电商平台的电火灶商品数据，包括商品标题、价格、品牌、店铺、评价数量、好评率及用户评价文本，存储于 SQLite 数据库，并生成包含 7 张可视化图表的 HTML 分析报告。

## 数据采集成果

| 维度 | 京东 | 淘宝 | 合计 |
|------|------|------|------|
| 商品数 | 160 | 192 | **352** |
| 评价文本 | 62 | 50 | **112** |
| 品牌数 | — | — | **40** |
| 价格区间 | ¥580–¥5,577 | ¥25–¥9,026 | — |
| 平均价格 | ¥2,767 | ¥1,214 | — |
| 搜索关键词 | 6 | 6 | 12 组 |

**TOP 5 品牌**：华火 (148)、好太太 (12)、美的 (10)、星焰 (10)、卡曼森 (9)

## 搜索关键词

```
电火灶 | 电焰灶 | 电燃灶 | 电火灶 商用 | 电火灶 家用 | 电火灶 双灶
```

每个关键词采集 3 页搜索结果，去重后入库。

## 项目结构

```
ECommerce_Insight/
├── cdp_browser.py            # CDP 浏览器客户端（核心模块）
├── db_init.py                # 数据库初始化（建表）
├── jd_spider_v5.py           # 京东商品采集（搜索页 React DOM 适配）
├── jd_review_boost.py         # 京东评价采集（CDP 逐页访问 + DOM 提取）
├── taobao_spider_v4.py       # 淘宝商品采集（登录 + React DOM 适配）
├── save_taobao_webdata.py    # WebSearch 补充淘宝商品数据
├── save_taobao_reviews.py    # WebSearch 补充淘宝评价数据
├── save_extra_reviews.py     # WebSearch 补充用户体验数据
├── clean_data.py             # 数据清洗（价格修复 / 销量解析 / 品牌提取）
├── generate_report.py        # 报告生成器（图表 + HTML + CSV + JSON）
├── data/
│   ├── ecommerce.db          # SQLite 数据库
│   ├── products_export.csv   # 商品数据导出
│   ├── reviews_export.csv    # 评价数据导出
│   └── analysis_report.json  # 分析结果 JSON
├── report/                   # 可视化图表
│   ├── price_distribution.png
│   ├── brand_distribution.png
│   ├── platform_comparison.png
│   ├── review_top10.png
│   ├── review_keywords.png
│   ├── keyword_frequency.png
│   └── experience_radar.png
└── 电火灶电商数据分析报告.html   # 最终 HTML 报告
```

## 技术架构

### 浏览器自动化 — CDP 直连

不依赖 Selenium / Playwright / DrissionPage，直接通过 **WebSocket 连接 Chrome DevTools Protocol**，兼容所有 Chrome 版本：

```
Chrome (--remote-debugging-port=9222)
    ↕ HTTP /json 获取 tab 列表
    ↕ WebSocket 发送 CDP 指令
Python (cdp_browser.py)
    ├── Page.navigate         页面导航
    ├── Runtime.evaluate      执行 JS 提取数据
    ├── Network.setBlockedURLs 屏蔽图片/视频/字体（加速加载）
    └── Page.captureScreenshot 截图调试
```

**资源屏蔽策略**：屏蔽 `*.jpg`、`*.png`、`*.mp4`、`*.woff2` 等 24 种资源模式，页面加载速度提升 3–5 倍。

### 京东采集策略

京东搜索页为 React 应用，CSS class 名经 hash 混淆（如 `_card_1n6pm_83`）。采集流程：

1. 导航到 `search.jd.com/Search?keyword=电火灶&page=1`
2. 滚动页面触发懒加载
3. 通过 `Runtime.evaluate` 执行 JS 提取商品卡片 DOM 数据
4. 逐个访问商品详情页，提取评价摘要和评价文本

### 淘宝采集策略

淘宝搜索页同为 React 应用，商品卡片 class 为 `doubleCard--gO3Bz6bu` 格式。采集流程：

1. 先导航到 `login.taobao.com`，等待用户手动登录
2. 登录成功后搜索关键词
3. 通过 `div[class*="doubleCard--"]` 定位商品卡片
4. 正则提取价格（`¥\s*(\d+(?:\.\d{1,2})?)`）和销量（`(\d+\+?\s*人付款)`）

### 数据清洗

淘宝采集存在价格与销量数字合并的问题（如 `¥2429` + `100+人付款` 拼接为 `2429100`），`clean_data.py` 处理：

- **价格拆分**：根据 sales_text 中的销量数字反推真实价格
- **销量解析**：从 `XX+人付款` 格式提取 comment_count
- **品牌提取**：从标题中匹配 52 个已知品牌关键词

## 数据库结构

### products 表

| 字段 | 类型 | 说明 |
|------|------|------|
| product_id | TEXT | 平台商品 ID（唯一） |
| platform | TEXT | `jd` / `taobao` |
| keyword | TEXT | 搜索关键词 |
| title | TEXT | 商品标题 |
| price | REAL | 商品价格 |
| original_price | REAL | 原价 |
| shop_name | TEXT | 店铺名称 |
| brand | TEXT | 品牌 |
| model | TEXT | 型号 |
| url | TEXT | 商品链接 |
| image_url | TEXT | 主图链接 |
| comment_count | INTEGER | 评价总数 |
| good_count | INTEGER | 好评数 |
| general_count | INTEGER | 中评数 |
| poor_count | INTEGER | 差评数 |
| good_rate | REAL | 好评率 (%) |
| sales_text | TEXT | 销量文本（如 "100+人付款"） |

### reviews 表

| 字段 | 类型 | 说明 |
|------|------|------|
| product_id | TEXT | 关联商品 ID |
| platform | TEXT | `jd` / `taobao` |
| content | TEXT | 评价内容 |
| score | INTEGER | 评分 (1–5) |
| nickname | TEXT | 用户昵称 |
| review_date | TEXT | 评价日期 |
| variant | TEXT | 商品规格 |

### review_tags / user_experience / search_log

分别存储评价标签、用户体验数据和搜索日志。

## 快速开始

### 环境要求

- Python 3.10+
- Chrome 浏览器（支持 remote debugging）
- macOS / Linux

### 安装依赖

```bash
pip install websocket-client requests matplotlib
```

### 运行流程

```bash
# 1. 初始化数据库
python db_init.py

# 2. 启动 Chrome（远程调试模式）
# macOS:
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 --remote-allow-origins=* --no-sandbox

# 3. 采集京东商品（端口 9222）
python jd_spider_v5.py

# 4. 采集京东评价
python jd_review_boost.py

# 5. 采集淘宝商品（需另一个 Chrome 实例，端口 9223）
python taobao_spider_v4.py

# 6. 数据清洗
python clean_data.py

# 7. 生成报告
python generate_report.py
```

> 淘宝采集需要手动登录，脚本会等待登录成功后自动继续。

### 并行采集

可同时启动两个 Chrome 实例（端口 9222 / 9223），京东和淘宝并行采集：

```bash
# 终端 1 — 京东
python jd_spider_v5.py &

# 终端 2 — 淘宝
python taobao_spider_v4.py &
```

## 报告内容

最终生成的 `电火灶电商数据分析报告.html` 包含：

1. **数据概览** — 12 项核心指标卡片
2. **平台对比** — 京东 vs 淘宝商品数 / 均价 / 品牌数三维度对比
3. **价格分布** — 双平台价格区间柱状图
4. **品牌分析** — TOP 15 品牌排行 + 均价 + 平台分布
5. **评价 TOP10** — 评价数最多的商品排行
6. **用户体验** — 6 维度雷达图（安全 / 加热速度 / 性价比 / 便捷 / 热效率 / 口感）
7. **优缺点分析** — 10 项优势 + 7 项劣势
8. **竞品对比** — 电火灶 vs 燃气灶 / 电磁炉 / 电陶炉
9. **评价文本** — 100 条真实用户评价表格
10. **关键词分析** — 标题词频 + 评价关键词

## 技术栈

| 组件 | 技术 |
|------|------|
| 浏览器自动化 | Chrome DevTools Protocol (WebSocket) |
| 数据存储 | SQLite 3 |
| 数据清洗 | Python (re, sqlite3) |
| 可视化 | Matplotlib |
| 报告 | HTML + CSS (暗色主题) |
| 数据导出 | CSV + JSON |

## 注意事项

- 京东评价 API (`productCommentSummaries.action`) 在非浏览器上下文调用会返回"系统繁忙"，必须通过 CDP 在浏览器环境中执行
- 淘宝搜索页结构可能随版本更新变化，需定期检查 DOM 选择器
- 采集频率建议每页间隔 2–3 秒，避免触发反爬机制
- 价格与销量合并是淘宝 DOM 的已知问题，`clean_data.py` 提供自动修复

## License

MIT
