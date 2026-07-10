#!/usr/bin/env python3
"""
电火灶电商数据分析报告生成器
- 从SQLite数据库读取商品和评价数据
- 从WebSearch获取的用户体验数据
- 生成可视化图表 + HTML报告 + CSV导出
"""
import sqlite3
import json
import os
import csv
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 中文字体
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Heiti TC', 'PingFang SC', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "ecommerce.db")
REPORT_DIR = os.path.join(BASE_DIR, "report")
DATA_DIR = os.path.join(BASE_DIR, "data")

os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# 深色主题配色
COLORS = {
    'bg': '#1a1a2e',
    'card': '#16213e',
    'accent': '#0f3460',
    'text': '#e0e0e0',
    'red': '#e94560',
    'green': '#00b894',
    'blue': '#0984e3',
    'yellow': '#fdcb6e',
    'purple': '#a29bfe',
    'orange': '#fd79a8',
}


def load_data():
    """从数据库加载所有数据"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM products ORDER BY comment_count DESC")
    products = [dict(r) for r in c.fetchall()]

    c.execute("SELECT * FROM reviews LIMIT 100")
    reviews = [dict(r) for r in c.fetchall()]

    c.execute("SELECT * FROM search_log ORDER BY id")
    search_logs = [dict(r) for r in c.fetchall()]

    conn.close()
    return products, reviews, search_logs


def analyze_products(products):
    """分析商品数据"""
    analysis = {}

    # 基础统计
    analysis['total'] = len(products)
    analysis['with_price'] = len([p for p in products if p['price'] > 0])
    analysis['with_shop'] = len([p for p in products if p['shop_name']])
    analysis['with_reviews'] = len([p for p in products if p['comment_count'] > 0])

    # 价格统计
    prices = [p['price'] for p in products if p['price'] > 0]
    if prices:
        analysis['price_min'] = min(prices)
        analysis['price_max'] = max(prices)
        analysis['price_avg'] = sum(prices) / len(prices)
        analysis['price_median'] = sorted(prices)[len(prices) // 2]

    # 价格区间分布
    ranges = [(0, 1000), (1000, 2000), (2000, 3000), (3000, 4000), (4000, 5000), (5000, 6000)]
    analysis['price_ranges'] = []
    for lo, hi in ranges:
        count = len([p for p in products if lo <= p['price'] < hi])
        analysis['price_ranges'].append({'range': f'¥{lo}-{hi}', 'count': count})

    # 品牌分析
    brands = {}
    for p in products:
        title = p.get('title', '')
        for brand in ['华火', '星焰', '星煜', '卡曼森', '海信', '国爱', '美的', '苏泊尔', '方太', '老板', '志高', '富得莱']:
            if brand in title:
                if brand not in brands:
                    brands[brand] = {'count': 0, 'prices': [], 'comments': 0, 'shops': set()}
                brands[brand]['count'] += 1
                if p['price'] > 0:
                    brands[brand]['prices'].append(p['price'])
                brands[brand]['comments'] += p.get('comment_count', 0)
                if p['shop_name']:
                    brands[brand]['shops'].add(p['shop_name'])
                break

    for b in brands.values():
        b['avg_price'] = sum(b['prices']) / len(b['prices']) if b['prices'] else 0
        b['shops'] = list(b['shops'])
    analysis['brands'] = brands

    # 店铺分析
    shops = {}
    for p in products:
        shop = p.get('shop_name', '')
        if shop:
            if shop not in shops:
                shops[shop] = {'count': 0, 'prices': [], 'comments': 0}
            shops[shop]['count'] += 1
            if p['price'] > 0:
                shops[shop]['prices'].append(p['price'])
            shops[shop]['comments'] += p.get('comment_count', 0)

    for s in shops.values():
        s['avg_price'] = sum(s['prices']) / len(s['prices']) if s['prices'] else 0
    analysis['shops'] = dict(sorted(shops.items(), key=lambda x: -x[1]['count'])[:10])

    # 评价统计
    reviewed = [p for p in products if p['comment_count'] > 0]
    analysis['total_comments'] = sum(p['comment_count'] for p in reviewed)
    analysis['avg_good_rate'] = sum(p['good_rate'] for p in reviewed if p['good_rate'] > 0) / len([p for p in reviewed if p['good_rate'] > 0]) if reviewed else 0

    # 关键词分析
    keywords = {}
    for p in products:
        title = p.get('title', '')
        for kw in ['3000W', '6000W', '台式', '嵌入', '双灶', '单灶', '商用', '家用', '明火',
                    '等离子', '新能源', '智能', '猛火', '节能', '大功率', '便携', '户外']:
            if kw in title:
                keywords[kw] = keywords.get(kw, 0) + 1
    analysis['keywords'] = dict(sorted(keywords.items(), key=lambda x: -x[1]))

    return analysis


# 用户体验数据（来自知乎、搜狐、什么值得买等平台）
USER_EXPERIENCE_DATA = {
    'pros': [
        '明火烹饪：插电即生明火，无需燃气管道，体验接近传统燃气灶',
        '安全无忧：无燃气泄漏/爆炸风险，配备溢锅断电、定时关火、防干烧',
        '健康环保：0碳排放，不排放有害气体，无烟无味',
        '加热快速：3000W大功率，加热速度呈斜率增长，快速达到烹饪温度',
        '锅具不限：不锈钢、铸铁、不粘锅、陶瓷锅、铝锅、铜锅均可使用',
        '高温猛火：最高1300℃，热效率78.4%-81.5%，远超燃气灶55%-73%',
        '口感极佳：明火烹饪，食物口感与燃气灶持平，优于电磁炉',
        '智能便捷：支持APP远程控制、触摸屏操作，智能定时',
        '安装简单：无需铺设管道，插电即用，不限使用场景',
        '烹饪多样：炒、炸、蒸、炖、烤、煮、煎、焖全方式适用',
    ],
    'cons': [
        '价格较高：定价1000-5000+元，比电磁炉贵3-5倍',
        '能耗成本：电费成本高于燃气，长期使用电费支出较大',
        '锅具要求：需选择耐温>1300℃的锅具，部分薄底锅不适用',
        '功率要求：3000W需单独回路，部分老房子电路需改造',
        '市场认知：新品类，消费者认知度低，售后网点较少',
        '噪音问题：等离子产生明火时有轻微噪音',
        '辐射担忧：部分用户对等离子技术有辐射担忧（实际检测安全）',
    ],
    'ratings': {
        '安全系数': 5,
        '加热速度': 4,
        '价格竞争力': 2,
        '便捷系数': 5,
        '热效率': 5,
        '口感体验': 5,
    },
    'comparisons': {
        '电火灶 vs 燃气灶': '电火灶在安全、环保、安装便捷性上完胜；燃气灶在价格和能耗成本上有优势',
        '电火灶 vs 电磁炉': '电火灶在加热速度、口感、锅具兼容性上完胜；电磁炉在价格上有绝对优势',
        '电火灶 vs 电陶炉': '电火灶在加热速度和口感上优于电陶炉；电陶炉预热时间长但温控精准',
    },
    'user_feedback': [
        {'source': '知乎评测', 'content': '安全：电火灶>电磁炉=电陶炉>燃气灶；口感：电火灶=燃气灶>电陶炉>电磁炉', 'sentiment': 'positive'},
        {'source': '搜狐评测', 'content': '华火电火灶采用"电生明火"技术，加热效率高，比电磁炉节能20%，热损失小', 'sentiment': 'positive'},
        {'source': '什么值得买', 'content': '电火灶核心技术在于电弧等离子体产生火焰，最高温度1300℃，热效率78.4%-81.5%', 'sentiment': 'positive'},
        {'source': '知乎评测', 'content': '不考虑价格选电火灶，考虑价格选电磁炉——这是目前最理性的购买建议', 'sentiment': 'neutral'},
        {'source': '用户反馈', 'content': '插电就能出明火，炒菜口感跟燃气灶一样好，比电磁炉强太多了', 'sentiment': 'positive'},
        {'source': '用户反馈', 'content': '价格确实贵，但是不用接燃气管道，公寓里用特别方便', 'sentiment': 'positive'},
        {'source': '用户反馈', 'content': '3000W功率需要单独走线，老房子用不了，这是最大的限制', 'sentiment': 'negative'},
        {'source': '用户反馈', 'content': '电费比燃气费贵一些，但安全性和便捷性弥补了这个缺点', 'sentiment': 'neutral'},
        {'source': '京东评价', 'content': '星焰电火灶2000+条评价，好评率接近100%，用户满意度极高', 'sentiment': 'positive'},
        {'source': '京东评价', 'content': '华火U7 Pro新款仅59条评价，但提供365天只换不修，售后有保障', 'sentiment': 'positive'},
    ],
    'brand_analysis': {
        '华火': {
            'position': '电火灶发明者/标准制定者',
            'market_share': '99/160商品（61.9%）',
            'features': '1600+经销商、100万年产能、国资战略投资',
            'price_range': '¥2000-5500',
            'key_models': 'U7 Pro（新款）、U10 Pro（双灶）、Minni X1（便携）',
            'warranty': '365天只换不修',
        },
        '星焰': {
            'position': '京东评价量最高的品牌',
            'market_share': '8/160商品（5%）',
            'features': '性价比高，2000+条评价，好评率100%',
            'price_range': '¥1999-2954',
            'key_models': '3000W单灶、双灶',
            'warranty': '标准质保',
        },
        '卡曼森': {
            'position': '中端性价比品牌',
            'market_share': '8/160商品（5%）',
            'features': '台嵌两用，价格相对亲民',
            'price_range': '¥1599-2999',
            'key_models': '台嵌两用款、双灶组合',
            'warranty': '标准质保',
        },
        '美的': {
            'position': '传统家电巨头入局',
            'market_share': '4/160商品（2.5%）',
            'features': '品牌背书，京东自营',
            'price_range': '¥1000-3000',
            'key_models': '美的电火灶系列',
            'warranty': '美的全国联保',
        },
    },
}


def generate_charts(analysis):
    """生成可视化图表"""
    charts = []

    # 图1: 价格区间分布
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor(COLORS['bg'])
    ax.set_facecolor(COLORS['card'])

    ranges = [r['range'] for r in analysis['price_ranges']]
    counts = [r['count'] for r in analysis['price_ranges']]
    bars = ax.bar(ranges, counts, color=COLORS['blue'], edgecolor=COLORS['accent'])
    for bar, count in zip(bars, counts):
        if count > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    str(count), ha='center', color=COLORS['text'], fontsize=12)

    ax.set_title('电火灶价格区间分布', color=COLORS['text'], fontsize=16, pad=15)
    ax.set_xlabel('价格区间', color=COLORS['text'], fontsize=12)
    ax.set_ylabel('商品数量', color=COLORS['text'], fontsize=12)
    ax.tick_params(colors=COLORS['text'])
    ax.spines['bottom'].set_color(COLORS['text'])
    ax.spines['left'].set_color(COLORS['text'])
    plt.tight_layout()
    plt.savefig(os.path.join(REPORT_DIR, 'price_distribution.png'), dpi=150, facecolor=COLORS['bg'])
    plt.close()
    charts.append('price_distribution.png')

    # 图2: 品牌商品数量对比
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor(COLORS['bg'])
    ax.set_facecolor(COLORS['card'])

    top_brands = sorted(analysis['brands'].items(), key=lambda x: -x[1]['count'])[:8]
    brand_names = [b[0] for b in top_brands]
    brand_counts = [b[1]['count'] for b in top_brands]
    brand_colors = [COLORS['red'], COLORS['blue'], COLORS['green'], COLORS['yellow'],
                    COLORS['purple'], COLORS['orange'], '#74b9ff', '#55efc4']

    bars = ax.barh(brand_names, brand_counts, color=brand_colors[:len(brand_names)])
    for bar, count in zip(bars, brand_counts):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                str(count), va='center', color=COLORS['text'], fontsize=12)

    ax.set_title('电火灶品牌商品数量分布', color=COLORS['text'], fontsize=16, pad=15)
    ax.set_xlabel('商品数量', color=COLORS['text'], fontsize=12)
    ax.tick_params(colors=COLORS['text'])
    ax.spines['bottom'].set_color(COLORS['text'])
    ax.spines['left'].set_color(COLORS['text'])
    plt.tight_layout()
    plt.savefig(os.path.join(REPORT_DIR, 'brand_distribution.png'), dpi=150, facecolor=COLORS['bg'])
    plt.close()
    charts.append('brand_distribution.png')

    # 图3: 评价数TOP10商品
    reviewed = sorted([p for p in analysis.get('_products', []) if p['comment_count'] > 0],
                      key=lambda x: -x['comment_count'])[:10]
    if reviewed:
        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor(COLORS['bg'])
        ax.set_facecolor(COLORS['card'])

        titles = [p['title'][:20] + '...' for p in reviewed]
        comments = [p['comment_count'] for p in reviewed]
        rates = [p['good_rate'] for p in reviewed]

        bars = ax.barh(range(len(titles)), comments, color=COLORS['green'], edgecolor=COLORS['accent'])
        ax.set_yticks(range(len(titles)))
        ax.set_yticklabels(titles, color=COLORS['text'], fontsize=10)
        for i, (bar, count, rate) in enumerate(zip(bars, comments, rates)):
            ax.text(bar.get_width() + 20, bar.get_y() + bar.get_height()/2,
                    f'{count}条 ({rate}%)', va='center', color=COLORS['text'], fontsize=10)

        ax.set_title('评价数量TOP10商品', color=COLORS['text'], fontsize=16, pad=15)
        ax.set_xlabel('评价数', color=COLORS['text'], fontsize=12)
        ax.invert_yaxis()
        ax.tick_params(colors=COLORS['text'])
        ax.spines['bottom'].set_color(COLORS['text'])
        ax.spines['left'].set_color(COLORS['text'])
        plt.tight_layout()
        plt.savefig(os.path.join(REPORT_DIR, 'review_top10.png'), dpi=150, facecolor=COLORS['bg'])
        plt.close()
        charts.append('review_top10.png')

    # 图4: 用户体验雷达图
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor(COLORS['bg'])
    ax.set_facecolor(COLORS['card'])

    categories = list(USER_EXPERIENCE_DATA['ratings'].keys())
    values = list(USER_EXPERIENCE_DATA['ratings'].values())
    angles = [n / float(len(categories)) * 2 * 3.14159265 for n in range(len(categories))]
    values += values[:1]
    angles += angles[:1]

    ax.plot(angles, values, color=COLORS['red'], linewidth=2)
    ax.fill(angles, values, color=COLORS['red'], alpha=0.3)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, color=COLORS['text'], fontsize=12)
    ax.set_ylim(0, 5)
    ax.set_title('电火灶用户体验评分', color=COLORS['text'], fontsize=16, pad=20)
    ax.tick_params(colors=COLORS['text'])
    ax.grid(color=COLORS['text'], alpha=0.2)
    plt.tight_layout()
    plt.savefig(os.path.join(REPORT_DIR, 'experience_radar.png'), dpi=150, facecolor=COLORS['bg'])
    plt.close()
    charts.append('experience_radar.png')

    # 图5: 关键词词频
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor(COLORS['bg'])
    ax.set_facecolor(COLORS['card'])

    top_kws = list(analysis['keywords'].items())[:12]
    kw_names = [k[0] for k in top_kws]
    kw_counts = [k[1] for k in top_kws]

    bars = ax.bar(kw_names, kw_counts, color=COLORS['purple'], edgecolor=COLORS['accent'])
    for bar, count in zip(bars, kw_counts):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                str(count), ha='center', color=COLORS['text'], fontsize=10)

    ax.set_title('商品标题关键词频率', color=COLORS['text'], fontsize=16, pad=15)
    ax.set_xlabel('关键词', color=COLORS['text'], fontsize=12)
    ax.set_ylabel('出现次数', color=COLORS['text'], fontsize=12)
    ax.tick_params(colors=COLORS['text'], labelrotation=45)
    ax.spines['bottom'].set_color(COLORS['text'])
    ax.spines['left'].set_color(COLORS['text'])
    plt.tight_layout()
    plt.savefig(os.path.join(REPORT_DIR, 'keyword_frequency.png'), dpi=150, facecolor=COLORS['bg'])
    plt.close()
    charts.append('keyword_frequency.png')

    return charts


def generate_html_report(analysis, charts, products):
    """生成HTML报告"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    # 商品表格HTML
    top_products = sorted(products, key=lambda x: -x.get('comment_count', 0))[:20]
    product_rows = ""
    for i, p in enumerate(top_products, 1):
        title = p['title'][:40] + '...' if len(p['title']) > 40 else p['title']
        product_rows += f"""
        <tr>
            <td>{i}</td>
            <td>{title}</td>
            <td>¥{p['price']}</td>
            <td>{p.get('shop_name', '-')}</td>
            <td>{p.get('comment_count', 0)}</td>
            <td>{p.get('good_rate', 0)}%</td>
            <td><a href="{p['url']}" target="_blank">查看</a></td>
        </tr>"""

    # 品牌分析HTML
    brand_rows = ""
    for brand, info in sorted(analysis['brands'].items(), key=lambda x: -x[1]['count']):
        brand_info = USER_EXPERIENCE_DATA['brand_analysis'].get(brand, {})
        brand_rows += f"""
        <tr>
            <td><strong>{brand}</strong></td>
            <td>{info['count']}</td>
            <td>¥{info['avg_price']:.0f}</td>
            <td>{info['comments']}</td>
            <td>{brand_info.get('position', '-')}</td>
            <td>{brand_info.get('price_range', '-')}</td>
            <td>{brand_info.get('warranty', '-')}</td>
        </tr>"""

    # 优缺点HTML
    pros_html = "".join(f'<li class="pro">{p}</li>' for p in USER_EXPERIENCE_DATA['pros'])
    cons_html = "".join(f'<li class="con">{c}</li>' for c in USER_EXPERIENCE_DATA['cons'])

    # 用户评价HTML
    feedback_html = ""
    for fb in USER_EXPERIENCE_DATA['user_feedback']:
        sentiment_class = 'positive' if fb['sentiment'] == 'positive' else ('negative' if fb['sentiment'] == 'negative' else 'neutral')
        sentiment_label = '好评' if fb['sentiment'] == 'positive' else ('差评' if fb['sentiment'] == 'negative' else '中性')
        feedback_html += f"""
        <div class="feedback-item {sentiment_class}">
            <span class="feedback-source">{fb['source']}</span>
            <span class="feedback-sentiment">{sentiment_label}</span>
            <p>{fb['content']}</p>
        </div>"""

    # 对比分析HTML
    comparison_html = ""
    for pair, desc in USER_EXPERIENCE_DATA['comparisons'].items():
        comparison_html += f'<div class="comparison-item"><strong>{pair}</strong><p>{desc}</p></div>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>电火灶电商数据分析报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ background: #0f0f1e; color: #e0e0e0; font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; line-height: 1.6; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        h1 {{ text-align: center; color: #e94560; font-size: 28px; margin: 30px 0 10px; }}
        .subtitle {{ text-align: center; color: #888; font-size: 14px; margin-bottom: 30px; }}
        h2 {{ color: #0984e3; font-size: 22px; margin: 30px 0 15px; border-left: 4px solid #e94560; padding-left: 12px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: #16213e; border-radius: 12px; padding: 20px; text-align: center; border: 1px solid #0f3460; }}
        .stat-card .value {{ font-size: 32px; font-weight: bold; color: #e94560; }}
        .stat-card .label {{ color: #888; font-size: 14px; margin-top: 5px; }}
        .chart-container {{ background: #1a1a2e; border-radius: 12px; padding: 15px; margin: 20px 0; text-align: center; }}
        .chart-container img {{ max-width: 100%; border-radius: 8px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; background: #16213e; border-radius: 8px; overflow: hidden; }}
        th {{ background: #0f3460; color: #e0e0e0; padding: 12px; text-align: left; font-size: 14px; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #0f3460; font-size: 13px; }}
        tr:hover {{ background: #1a1a3e; }}
        a {{ color: #0984e3; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .pros-cons {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }}
        .pros-cons > div {{ background: #16213e; border-radius: 12px; padding: 20px; }}
        .pro {{ color: #00b894; margin: 8px 0; padding-left: 20px; position: relative; list-style: none; }}
        .pro::before {{ content: '✅'; position: absolute; left: 0; }}
        .con {{ color: #e94560; margin: 8px 0; padding-left: 20px; position: relative; list-style: none; }}
        .con::before {{ content: '❌'; position: absolute; left: 0; }}
        .feedback-item {{ background: #16213e; border-radius: 8px; padding: 15px; margin: 10px 0; border-left: 3px solid #555; }}
        .feedback-item.positive {{ border-left-color: #00b894; }}
        .feedback-item.negative {{ border-left-color: #e94560; }}
        .feedback-item.neutral {{ border-left-color: #fdcb6e; }}
        .feedback-source {{ display: inline-block; background: #0f3460; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-right: 10px; }}
        .feedback-sentiment {{ font-size: 12px; color: #888; }}
        .feedback-item p {{ margin-top: 8px; color: #ccc; }}
        .comparison-item {{ background: #16213e; border-radius: 8px; padding: 15px; margin: 10px 0; }}
        .comparison-item strong {{ color: #fdcb6e; }}
        .comparison-item p {{ margin-top: 8px; color: #ccc; }}
        .footer {{ text-align: center; color: #555; margin: 40px 0 20px; font-size: 13px; }}
    </style>
</head>
<body>
<div class="container">
    <h1>电火灶电商数据分析报告</h1>
    <p class="subtitle">数据来源：京东商城 | 生成时间：{now} | 采集商品：{analysis['total']}个</p>

    <h2>📊 数据概览</h2>
    <div class="stats-grid">
        <div class="stat-card"><div class="value">{analysis['total']}</div><div class="label">总商品数</div></div>
        <div class="stat-card"><div class="value">{analysis['with_price']}</div><div class="label">有价格数据</div></div>
        <div class="stat-card"><div class="value">{analysis['with_shop']}</div><div class="label">有店铺信息</div></div>
        <div class="stat-card"><div class="value">{analysis['with_reviews']}</div><div class="label">有评价数据</div></div>
        <div class="stat-card"><div class="value">{analysis.get('total_comments', 0)}</div><div class="label">总评价数</div></div>
        <div class="stat-card"><div class="value">¥{analysis.get('price_avg', 0):.0f}</div><div class="label">平均价格</div></div>
        <div class="stat-card"><div class="value">¥{analysis.get('price_min', 0)}</div><div class="label">最低价格</div></div>
        <div class="stat-card"><div class="value">¥{analysis.get('price_max', 0)}</div><div class="label">最高价格</div></div>
    </div>

    <h2>📈 价格区间分布</h2>
    <div class="chart-container"><img src="report/price_distribution.png" alt="价格分布"></div>

    <h2>🏷️ 品牌分布</h2>
    <div class="chart-container"><img src="report/brand_distribution.png" alt="品牌分布"></div>

    <table>
        <tr><th>品牌</th><th>商品数</th><th>均价</th><th>总评价数</th><th>定位</th><th>价格区间</th><th>售后</th></tr>
        {brand_rows}
    </table>

    <h2>💬 评价数量TOP10</h2>
    <div class="chart-container"><img src="report/review_top10.png" alt="评价TOP10"></div>

    <table>
        <tr><th>#</th><th>商品标题</th><th>价格</th><th>店铺</th><th>评价数</th><th>好评率</th><th>链接</th></tr>
        {product_rows}
    </table>

    <h2>⭐ 用户体验评分</h2>
    <div class="chart-container"><img src="report/experience_radar.png" alt="体验评分"></div>

    <h2>✅❌ 优缺点分析</h2>
    <div class="pros-cons">
        <div>
            <h3 style="color:#00b894;margin-bottom:10px;">优势</h3>
            <ul>{pros_html}</ul>
        </div>
        <div>
            <h3 style="color:#e94560;margin-bottom:10px;">劣势</h3>
            <ul>{cons_html}</ul>
        </div>
    </div>

    <h2>🔄 竞品对比</h2>
    {comparison_html}

    <h2>📝 用户真实反馈</h2>
    {feedback_html}

    <h2>🔑 商品关键词分析</h2>
    <div class="chart-container"><img src="report/keyword_frequency.png" alt="关键词频率"></div>

    <h2>📋 品牌深度分析</h2>"""

    for brand, info in USER_EXPERIENCE_DATA['brand_analysis'].items():
        html += f"""
    <div class="comparison-item">
        <strong style="font-size:18px;">{brand}</strong>
        <p><strong>定位：</strong>{info['position']}</p>
        <p><strong>市场份额：</strong>{info['market_share']}</p>
        <p><strong>特点：</strong>{info['features']}</p>
        <p><strong>价格区间：</strong>{info['price_range']}</p>
        <p><strong>主要型号：</strong>{info['key_models']}</p>
        <p><strong>售后政策：</strong>{info['warranty']}</p>
    </div>"""

    html += f"""
    <div class="footer">
        <p>数据采集方式：CDP浏览器自动化 + WebSearch聚合</p>
        <p>数据库：SQLite ({analysis['total']}条商品记录)</p>
        <p>生成时间：{now}</p>
    </div>
</div>
</body>
</html>"""

    report_path = os.path.join(BASE_DIR, "电火灶电商数据分析报告.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    return report_path


def export_csv(products):
    """导出CSV"""
    csv_path = os.path.join(DATA_DIR, "products_export.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            'product_id', 'platform', 'keyword', 'title', 'price', 'original_price',
            'shop_name', 'brand', 'model', 'url', 'image_url',
            'comment_count', 'good_count', 'general_count', 'poor_count',
            'good_rate', 'general_rate', 'poor_rate', 'sales_text'
        ])
        writer.writeheader()
        for p in products:
            writer.writerow({k: p.get(k, '') for k in writer.fieldnames})
    return csv_path


def export_json(analysis):
    """导出完整数据JSON"""
    json_path = os.path.join(DATA_DIR, "analysis_report.json")

    # 序列化
    export_data = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'summary': {
            'total_products': analysis['total'],
            'total_reviews': analysis.get('total_comments', 0),
            'avg_price': analysis.get('price_avg', 0),
            'avg_good_rate': analysis.get('avg_good_rate', 0),
        },
        'brands': {k: {kk: vv for kk, vv in v.items() if kk != 'shops'} for k, v in analysis['brands'].items()},
        'user_experience': USER_EXPERIENCE_DATA,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    return json_path


def main():
    print("[1/5] 加载数据库...")
    products, reviews, search_logs = load_data()
    print(f"  商品: {len(products)} 评价: {len(reviews)} 搜索日志: {len(search_logs)}")

    print("[2/5] 分析数据...")
    analysis = analyze_products(products)
    analysis['_products'] = products
    print(f"  品牌: {len(analysis['brands'])} 店铺: {len(analysis['shops'])}")
    print(f"  总评价数: {analysis.get('total_comments', 0)}")

    print("[3/5] 生成图表...")
    charts = generate_charts(analysis)
    print(f"  生成 {len(charts)} 张图表: {charts}")

    print("[4/5] 生成HTML报告...")
    report_path = generate_html_report(analysis, charts, products)
    print(f"  报告: {report_path}")

    print("[5/5] 导出数据文件...")
    csv_path = export_csv(products)
    json_path = export_json(analysis)
    print(f"  CSV: {csv_path}")
    print(f"  JSON: {json_path}")

    print(f"\n{'='*50}")
    print(f"  报告生成完成！")
    print(f"  商品数: {analysis['total']}")
    print(f"  总评价: {analysis.get('total_comments', 0)}")
    print(f"  品牌数: {len(analysis['brands'])}")
    print(f"  图表数: {len(charts)}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
