#!/usr/bin/env python3
"""
电火灶电商数据分析报告生成器 v2
- 京东 + 淘宝双平台数据
- 商品、评价、用户体验全维度分析
- 可视化图表 + HTML报告 + CSV/JSON导出
"""
import sqlite3
import json
import os
import csv
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

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
    'jd_red': '#e94560',
    'tb_orange': '#ff6600',
}


def load_data():
    """从数据库加载所有数据"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM products ORDER BY comment_count DESC")
    products = [dict(r) for r in c.fetchall()]

    c.execute("SELECT * FROM reviews ORDER BY review_date DESC")
    reviews = [dict(r) for r in c.fetchall()]

    c.execute("SELECT * FROM search_log ORDER BY id")
    search_logs = [dict(r) for r in c.fetchall()]

    conn.close()
    return products, reviews, search_logs


def analyze_products(products):
    """分析商品数据"""
    analysis = {}
    analysis['_products'] = products

    # 平台分布
    platforms = {}
    for p in products:
        pf = p.get('platform', 'unknown')
        if pf not in platforms:
            platforms[pf] = {'count': 0, 'prices': [], 'comments': 0, 'brands': set()}
        platforms[pf]['count'] += 1
        if p['price'] > 0:
            platforms[pf]['prices'].append(p['price'])
        platforms[pf]['comments'] += p.get('comment_count', 0) or 0
        if p.get('brand'):
            platforms[pf]['brands'].add(p['brand'])

    for pf in platforms:
        prices = platforms[pf]['prices']
        platforms[pf]['avg_price'] = sum(prices) / len(prices) if prices else 0
        platforms[pf]['min_price'] = min(prices) if prices else 0
        platforms[pf]['max_price'] = max(prices) if prices else 0
        platforms[pf]['brand_count'] = len(platforms[pf]['brands'])
        platforms[pf]['brands'] = list(platforms[pf]['brands'])[:10]

    analysis['platforms'] = platforms

    # 基础统计
    analysis['total'] = len(products)
    analysis['jd_count'] = platforms.get('jd', {}).get('count', 0)
    analysis['tb_count'] = platforms.get('taobao', {}).get('count', 0)
    analysis['with_price'] = len([p for p in products if p['price'] > 0])
    analysis['with_shop'] = len([p for p in products if p.get('shop_name')])
    analysis['with_reviews'] = len([p for p in products if (p.get('comment_count') or 0) > 0])
    analysis['with_brand'] = len([p for p in products if p.get('brand')])

    # 价格统计
    prices = [p['price'] for p in products if p['price'] > 0]
    if prices:
        analysis['price_min'] = min(prices)
        analysis['price_max'] = max(prices)
        analysis['price_avg'] = sum(prices) / len(prices)
        sorted_prices = sorted(prices)
        analysis['price_median'] = sorted_prices[len(sorted_prices) // 2]

    # 价格区间分布
    ranges = [(0, 500), (500, 1000), (1000, 2000), (2000, 3000),
              (3000, 4000), (4000, 5000), (5000, 8000), (8000, 100000)]
    analysis['price_ranges'] = []
    for lo, hi in ranges:
        count = len([p for p in products if lo <= p['price'] < hi])
        label = f'¥{lo}-{hi}' if hi < 100000 else f'¥{lo}+'
        analysis['price_ranges'].append({'range': label, 'count': count, 'lo': lo, 'hi': hi})

    # 品牌分析 - 从数据库实际数据
    brands = {}
    for p in products:
        brand = p.get('brand', '')
        if not brand:
            brand = '其他/无品牌'
        if brand not in brands:
            brands[brand] = {'count': 0, 'prices': [], 'comments': 0, 'platforms': set()}
        brands[brand]['count'] += 1
        if p['price'] > 0:
            brands[brand]['prices'].append(p['price'])
        brands[brand]['comments'] += (p.get('comment_count') or 0)
        if p.get('platform'):
            brands[brand]['platforms'].add(p['platform'])

    for b in brands.values():
        b['avg_price'] = sum(b['prices']) / len(b['prices']) if b['prices'] else 0
        b['platforms'] = list(b['platforms'])

    analysis['brands'] = dict(sorted(brands.items(), key=lambda x: -x[1]['count']))
    analysis['brand_count'] = len([b for b in brands if b != '其他/无品牌'])

    # 店铺分析
    shops = {}
    for p in products:
        shop = p.get('shop_name', '')
        if shop:
            if shop not in shops:
                shops[shop] = {'count': 0, 'prices': [], 'comments': 0, 'platform': p.get('platform', '')}
            shops[shop]['count'] += 1
            if p['price'] > 0:
                shops[shop]['prices'].append(p['price'])
            shops[shop]['comments'] += (p.get('comment_count') or 0)

    for s in shops.values():
        s['avg_price'] = sum(s['prices']) / len(s['prices']) if s['prices'] else 0
    analysis['shops'] = dict(sorted(shops.items(), key=lambda x: -x[1]['count'])[:15])

    # 评价统计
    reviewed = [p for p in products if (p.get('comment_count') or 0) > 0]
    analysis['total_comments'] = sum((p.get('comment_count') or 0) for p in reviewed)
    good_rates = [p['good_rate'] for p in reviewed if (p.get('good_rate') or 0) > 0]
    analysis['avg_good_rate'] = sum(good_rates) / len(good_rates) if good_rates else 0

    # 关键词分析
    keywords = {}
    for p in products:
        title = p.get('title', '')
        for kw in ['3000W', '6000W', '5000W', '3500W', '台式', '嵌入', '双灶', '单灶',
                    '商用', '家用', '明火', '等离子', '新能源', '智能', '猛火', '节能',
                    '大功率', '便携', '户外', '台嵌两用', '凹面', '平凹两用', '不挑锅',
                    '可调温', '定时', '触控', '2000W', '10000W', '7500W', '4000W']:
            if kw in title:
                keywords[kw] = keywords.get(kw, 0) + 1
    analysis['keywords'] = dict(sorted(keywords.items(), key=lambda x: -x[1]))

    return analysis


def analyze_reviews(reviews):
    """分析评价数据"""
    analysis = {
        'total': len(reviews),
        'jd_count': len([r for r in reviews if r.get('platform') == 'jd']),
        'tb_count': len([r for r in reviews if r.get('platform') == 'taobao']),
    }

    # 情感分析（基于score）
    positive = [r for r in reviews if (r.get('score') or 0) >= 4]
    neutral = [r for r in reviews if (r.get('score') or 0) == 3]
    negative = [r for r in reviews if (r.get('score') or 0) > 0 and (r.get('score') or 0) <= 2]

    analysis['positive_count'] = len(positive)
    analysis['neutral_count'] = len(neutral)
    analysis['negative_count'] = len(negative)

    # 关键词提取
    review_keywords = {}
    keyword_map = {
        '火力大': ['火力大', '火很大', '火猛', '火力猛', '大火力', '猛火'],
        '加热快': ['加热快', '升温快', '速度快', '热得快'],
        '安全': ['安全', '放心', '不漏气', '无燃气'],
        '方便': ['方便', '便捷', '简单', '易用', '省心'],
        '口感好': ['口感好', '味道好', '好吃', '锅气', '跟燃气灶一样'],
        '外观好': ['好看', '美观', '颜值', '漂亮', '大气'],
        '性价比': ['性价比', '划算', '实惠', '便宜', '值得'],
        '噪音': ['噪音', '声音大', '吵', '嗡嗡'],
        '价格贵': ['贵', '太贵', '价格高', '不值'],
        '质量好': ['质量好', '做工好', '精致', '结实'],
        '安装': ['安装', '师傅', '上门'],
        '售后': ['售后', '客服', '保修', '换新'],
        '功率高': ['功率大', '大功率', '瓦数'],
        '锅气': ['锅气', '烟火气', '明火'],
        '清洁': ['清洁', '清洗', '好打理', '易清洁'],
    }

    for r in reviews:
        content = r.get('content', '') or ''
        for label, patterns in keyword_map.items():
            for pat in patterns:
                if pat in content:
                    review_keywords[label] = review_keywords.get(label, 0) + 1
                    break

    analysis['keywords'] = dict(sorted(review_keywords.items(), key=lambda x: -x[1]))

    # 按品牌分组评价
    brand_reviews = {}
    for r in reviews:
        brand = r.get('brand', '') or r.get('product_name', '')[:4] or '未知'
        if brand not in brand_reviews:
            brand_reviews[brand] = []
        brand_reviews[brand].append(r)

    analysis['by_brand'] = brand_reviews

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
}


def generate_charts(analysis, review_analysis):
    """生成可视化图表"""
    charts = []

    # 图1: 价格区间分布（双平台对比）
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor(COLORS['bg'])
    ax.set_facecolor(COLORS['card'])

    ranges = [r['range'] for r in analysis['price_ranges']]
    jd_counts = []
    tb_counts = []
    for r in analysis['price_ranges']:
        lo = r['lo']
        hi = r['hi']
        jd_counts.append(len([p for p in analysis['_products'] if p['platform'] == 'jd' and lo <= p['price'] < hi]))
        tb_counts.append(len([p for p in analysis['_products'] if p['platform'] == 'taobao' and lo <= p['price'] < hi]))

    import numpy as np
    x = np.arange(len(ranges))
    width = 0.35
    bars1 = ax.bar(x - width/2, jd_counts, width, color=COLORS['jd_red'], label='京东', edgecolor=COLORS['accent'])
    bars2 = ax.bar(x + width/2, tb_counts, width, color=COLORS['tb_orange'], label='淘宝', edgecolor=COLORS['accent'])

    for bar, count in zip(bars1, jd_counts):
        if count > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3, str(count), ha='center', color=COLORS['text'], fontsize=9)
    for bar, count in zip(bars2, tb_counts):
        if count > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3, str(count), ha='center', color=COLORS['text'], fontsize=9)

    ax.set_title('电火灶价格区间分布（京东 vs 淘宝）', color=COLORS['text'], fontsize=16, pad=15)
    ax.set_xlabel('价格区间', color=COLORS['text'], fontsize=12)
    ax.set_ylabel('商品数量', color=COLORS['text'], fontsize=12)
    ax.set_xticks(x)
    ax.set_xticklabels(ranges, color=COLORS['text'], fontsize=10, rotation=30, ha='right')
    ax.tick_params(colors=COLORS['text'])
    ax.legend(facecolor=COLORS['card'], edgecolor=COLORS['text'], labelcolor=COLORS['text'])
    ax.spines['bottom'].set_color(COLORS['text'])
    ax.spines['left'].set_color(COLORS['text'])
    plt.tight_layout()
    plt.savefig(os.path.join(REPORT_DIR, 'price_distribution.png'), dpi=150, facecolor=COLORS['bg'])
    plt.close()
    charts.append('price_distribution.png')

    # 图2: 品牌商品数量TOP15
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor(COLORS['bg'])
    ax.set_facecolor(COLORS['card'])

    top_brands = list(analysis['brands'].items())[:15]
    brand_names = [b[0] for b in top_brands]
    brand_counts = [b[1]['count'] for b in top_brands]
    brand_colors = [COLORS['red'], COLORS['blue'], COLORS['green'], COLORS['yellow'],
                    COLORS['purple'], COLORS['orange'], '#74b9ff', '#55efc4',
                    '#fab1a0', '#a29bfe', '#fd79a8', '#00cec9', '#e17055', '#0984e3', '#00b894']

    bars = ax.barh(brand_names, brand_counts, color=brand_colors[:len(brand_names)])
    for bar, count in zip(bars, brand_counts):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                str(count), va='center', color=COLORS['text'], fontsize=11)

    ax.set_title('电火灶品牌商品数量TOP15', color=COLORS['text'], fontsize=16, pad=15)
    ax.set_xlabel('商品数量', color=COLORS['text'], fontsize=12)
    ax.tick_params(colors=COLORS['text'])
    ax.spines['bottom'].set_color(COLORS['text'])
    ax.spines['left'].set_color(COLORS['text'])
    plt.tight_layout()
    plt.savefig(os.path.join(REPORT_DIR, 'brand_distribution.png'), dpi=150, facecolor=COLORS['bg'])
    plt.close()
    charts.append('brand_distribution.png')

    # 图3: 评价数TOP10商品
    reviewed = sorted([p for p in analysis['_products'] if (p.get('comment_count') or 0) > 0],
                      key=lambda x: -(x.get('comment_count') or 0))[:10]
    if reviewed:
        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor(COLORS['bg'])
        ax.set_facecolor(COLORS['card'])

        titles = [p['title'][:22] + '...' for p in reviewed]
        comments = [p['comment_count'] for p in reviewed]
        bar_colors = [COLORS['jd_red'] if p['platform'] == 'jd' else COLORS['tb_orange'] for p in reviewed]

        bars = ax.barh(range(len(titles)), comments, color=bar_colors, edgecolor=COLORS['accent'])
        ax.set_yticks(range(len(titles)))
        ax.set_yticklabels(titles, color=COLORS['text'], fontsize=10)
        for i, (bar, count) in enumerate(zip(bars, comments)):
            ax.text(bar.get_width() + 20, bar.get_y() + bar.get_height()/2,
                    f'{count}条', va='center', color=COLORS['text'], fontsize=10)

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

    top_kws = list(analysis['keywords'].items())[:15]
    kw_names = [k[0] for k in top_kws]
    kw_counts = [k[1] for k in top_kws]

    bars = ax.bar(kw_names, kw_counts, color=COLORS['purple'], edgecolor=COLORS['accent'])
    for bar, count in zip(bars, kw_counts):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                str(count), ha='center', color=COLORS['text'], fontsize=10)

    ax.set_title('商品标题关键词频率TOP15', color=COLORS['text'], fontsize=16, pad=15)
    ax.set_xlabel('关键词', color=COLORS['text'], fontsize=12)
    ax.set_ylabel('出现次数', color=COLORS['text'], fontsize=12)
    ax.tick_params(colors=COLORS['text'], labelrotation=45)
    ax.spines['bottom'].set_color(COLORS['text'])
    ax.spines['left'].set_color(COLORS['text'])
    plt.tight_layout()
    plt.savefig(os.path.join(REPORT_DIR, 'keyword_frequency.png'), dpi=150, facecolor=COLORS['bg'])
    plt.close()
    charts.append('keyword_frequency.png')

    # 图6: 评价关键词分析
    if review_analysis['keywords']:
        fig, ax = plt.subplots(figsize=(10, 5))
        fig.patch.set_facecolor(COLORS['bg'])
        ax.set_facecolor(COLORS['card'])

        rw_names = list(review_analysis['keywords'].keys())
        rw_counts = list(review_analysis['keywords'].values())
        rw_colors = [COLORS['green'] if c in ['火力大', '加热快', '安全', '方便', '口感好', '外观好', '性价比', '质量好', '锅气', '功率高', '清洁']
                     else COLORS['red'] for c in rw_names]

        bars = ax.bar(rw_names, rw_counts, color=rw_colors, edgecolor=COLORS['accent'])
        for bar, count in zip(bars, rw_counts):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                    str(count), ha='center', color=COLORS['text'], fontsize=11)

        ax.set_title('用户评价关键词分析', color=COLORS['text'], fontsize=16, pad=15)
        ax.set_xlabel('关键词', color=COLORS['text'], fontsize=12)
        ax.set_ylabel('提及次数', color=COLORS['text'], fontsize=12)
        ax.tick_params(colors=COLORS['text'], labelrotation=45)
        ax.spines['bottom'].set_color(COLORS['text'])
        ax.spines['left'].set_color(COLORS['text'])
        plt.tight_layout()
        plt.savefig(os.path.join(REPORT_DIR, 'review_keywords.png'), dpi=150, facecolor=COLORS['bg'])
        plt.close()
        charts.append('review_keywords.png')

    # 图7: 平台对比
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.patch.set_facecolor(COLORS['bg'])
    for ax in axes:
        ax.set_facecolor(COLORS['card'])

    # 商品数量对比
    platforms = ['京东', '淘宝']
    counts = [analysis['jd_count'], analysis['tb_count']]
    axes[0].bar(platforms, counts, color=[COLORS['jd_red'], COLORS['tb_orange']], edgecolor=COLORS['accent'])
    for i, v in enumerate(counts):
        axes[0].text(i, v + 2, str(v), ha='center', color=COLORS['text'], fontsize=14, fontweight='bold')
    axes[0].set_title('商品数量对比', color=COLORS['text'], fontsize=14)
    axes[0].tick_params(colors=COLORS['text'])

    # 均价对比
    jd_prices = [p['price'] for p in analysis['_products'] if p['platform'] == 'jd' and p['price'] > 0]
    tb_prices = [p['price'] for p in analysis['_products'] if p['platform'] == 'taobao' and p['price'] > 0]
    avg_prices = [sum(jd_prices)/len(jd_prices) if jd_prices else 0,
                  sum(tb_prices)/len(tb_prices) if tb_prices else 0]
    axes[1].bar(platforms, avg_prices, color=[COLORS['jd_red'], COLORS['tb_orange']], edgecolor=COLORS['accent'])
    for i, v in enumerate(avg_prices):
        axes[1].text(i, v + 30, f'¥{v:.0f}', ha='center', color=COLORS['text'], fontsize=14, fontweight='bold')
    axes[1].set_title('平均价格对比', color=COLORS['text'], fontsize=14)
    axes[1].tick_params(colors=COLORS['text'])

    # 品牌数对比
    jd_brands = len(set(p['brand'] for p in analysis['_products'] if p['platform'] == 'jd' and p.get('brand')))
    tb_brands = len(set(p['brand'] for p in analysis['_products'] if p['platform'] == 'taobao' and p.get('brand')))
    axes[2].bar(platforms, [jd_brands, tb_brands], color=[COLORS['jd_red'], COLORS['tb_orange']], edgecolor=COLORS['accent'])
    for i, v in enumerate([jd_brands, tb_brands]):
        axes[2].text(i, v + 0.5, str(v), ha='center', color=COLORS['text'], fontsize=14, fontweight='bold')
    axes[2].set_title('品牌数量对比', color=COLORS['text'], fontsize=14)
    axes[2].tick_params(colors=COLORS['text'])

    for ax in axes:
        ax.spines['bottom'].set_color(COLORS['text'])
        ax.spines['left'].set_color(COLORS['text'])

    plt.tight_layout()
    plt.savefig(os.path.join(REPORT_DIR, 'platform_comparison.png'), dpi=150, facecolor=COLORS['bg'])
    plt.close()
    charts.append('platform_comparison.png')

    return charts


def generate_html_report(analysis, review_analysis, charts, products, reviews):
    """生成HTML报告"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    # 商品表格HTML
    top_products = sorted(products, key=lambda x: -(x.get('comment_count') or 0))[:25]
    product_rows = ""
    for i, p in enumerate(top_products, 1):
        title = p['title'][:40] + '...' if len(p.get('title', '')) > 40 else p.get('title', '')
        platform_badge = '京东' if p['platform'] == 'jd' else '淘宝'
        platform_class = 'jd' if p['platform'] == 'jd' else 'tb'
        product_rows += f"""
        <tr>
            <td>{i}</td>
            <td><span class="badge {platform_class}">{platform_badge}</span></td>
            <td>{title}</td>
            <td>¥{p['price']}</td>
            <td>{p.get('brand', '-')}</td>
            <td>{p.get('shop_name', '-')}</td>
            <td>{p.get('comment_count') or 0}</td>
            <td>{p.get('good_rate') or 0}%</td>
            <td><a href="{p.get('url', '#')}" target="_blank">查看</a></td>
        </tr>"""

    # 品牌分析HTML
    brand_rows = ""
    for brand, info in list(analysis['brands'].items())[:20]:
        platforms = ', '.join(info.get('platforms', []))
        brand_rows += f"""
        <tr>
            <td><strong>{brand}</strong></td>
            <td>{info['count']}</td>
            <td>¥{info['avg_price']:.0f}</td>
            <td>{info['comments']}</td>
            <td>{platforms}</td>
        </tr>"""

    # 评价内容HTML
    review_rows = ""
    for r in reviews[:30]:
        content = (r.get('content', '') or '')[:100]
        if len(r.get('content', '') or '') > 100:
            content += '...'
        score = r.get('score') or 0
        if score >= 4:
            score_badge = '<span class="badge positive">好评</span>'
        elif score == 3:
            score_badge = '<span class="badge neutral">中评</span>'
        elif score > 0:
            score_badge = '<span class="badge negative">差评</span>'
        else:
            score_badge = '<span class="badge neutral">未评分</span>'

        platform = r.get('platform', '')
        pf_badge = f'<span class="badge {"jd" if platform == "jd" else "tb"}">{("京东" if platform == "jd" else "淘宝")}</span>'

        review_rows += f"""
        <tr>
            <td>{pf_badge}</td>
            <td>{score_badge}</td>
            <td>{r.get('nickname', '匿名')}</td>
            <td>{content}</td>
            <td>{r.get('review_date', '-')}</td>
        </tr>"""

    # 优缺点HTML
    pros_html = "".join(f'<li class="pro">{p}</li>' for p in USER_EXPERIENCE_DATA['pros'])
    cons_html = "".join(f'<li class="con">{c}</li>' for c in USER_EXPERIENCE_DATA['cons'])

    # 对比分析HTML
    comparison_html = ""
    for pair, desc in USER_EXPERIENCE_DATA['comparisons'].items():
        comparison_html += f'<div class="comparison-item"><strong>{pair}</strong><p>{desc}</p></div>'

    # 平台对比数据
    jd_data = analysis['platforms'].get('jd', {})
    tb_data = analysis['platforms'].get('taobao', {})

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>电火灶电商数据分析报告（京东+淘宝）</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ background: #0f0f1e; color: #e0e0e0; font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; line-height: 1.6; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        h1 {{ text-align: center; color: #e94560; font-size: 28px; margin: 30px 0 10px; }}
        .subtitle {{ text-align: center; color: #888; font-size: 14px; margin-bottom: 30px; }}
        h2 {{ color: #0984e3; font-size: 22px; margin: 30px 0 15px; border-left: 4px solid #e94560; padding-left: 12px; }}
        h3 {{ color: #fdcb6e; font-size: 18px; margin: 20px 0 10px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: #16213e; border-radius: 12px; padding: 20px; text-align: center; border: 1px solid #0f3460; }}
        .stat-card .value {{ font-size: 28px; font-weight: bold; color: #e94560; }}
        .stat-card .label {{ color: #888; font-size: 13px; margin-top: 5px; }}
        .chart-container {{ background: #1a1a2e; border-radius: 12px; padding: 15px; margin: 20px 0; text-align: center; }}
        .chart-container img {{ max-width: 100%; border-radius: 8px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; background: #16213e; border-radius: 8px; overflow: hidden; }}
        th {{ background: #0f3460; color: #e0e0e0; padding: 12px; text-align: left; font-size: 14px; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #0f3460; font-size: 13px; }}
        tr:hover {{ background: #1a1a3e; }}
        a {{ color: #0984e3; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }}
        .badge.jd {{ background: rgba(233,69,96,0.2); color: #e94560; border: 1px solid #e94560; }}
        .badge.tb {{ background: rgba(255,102,0,0.2); color: #ff6600; border: 1px solid #ff6600; }}
        .badge.positive {{ background: rgba(0,184,148,0.2); color: #00b894; }}
        .badge.negative {{ background: rgba(233,69,96,0.2); color: #e94560; }}
        .badge.neutral {{ background: rgba(253,203,110,0.2); color: #fdcb6e; }}
        .pros-cons {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }}
        .pros-cons > div {{ background: #16213e; border-radius: 12px; padding: 20px; }}
        .pro {{ color: #00b894; margin: 8px 0; padding-left: 20px; position: relative; list-style: none; }}
        .pro::before {{ content: '\\2705'; position: absolute; left: 0; }}
        .con {{ color: #e94560; margin: 8px 0; padding-left: 20px; position: relative; list-style: none; }}
        .con::before {{ content: '\\274C'; position: absolute; left: 0; }}
        .comparison-item {{ background: #16213e; border-radius: 8px; padding: 15px; margin: 10px 0; }}
        .comparison-item strong {{ color: #fdcb6e; }}
        .comparison-item p {{ margin-top: 8px; color: #ccc; }}
        .platform-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }}
        .platform-card {{ background: #16213e; border-radius: 12px; padding: 20px; border: 1px solid #0f3460; }}
        .platform-card h3 {{ margin-top: 0; }}
        .platform-card.jd {{ border-top: 3px solid #e94560; }}
        .platform-card.tb {{ border-top: 3px solid #ff6600; }}
        .footer {{ text-align: center; color: #555; margin: 40px 0 20px; font-size: 13px; }}
        .review-table td:nth-child(4) {{ max-width: 400px; }}
    </style>
</head>
<body>
<div class="container">
    <h1>电火灶电商数据分析报告</h1>
    <p class="subtitle">数据来源：京东商城 + 淘宝商城 | 生成时间：{now} | 采集商品：{analysis['total']}个 | 评价：{review_analysis['total']}条</p>

    <h2>📊 数据概览</h2>
    <div class="stats-grid">
        <div class="stat-card"><div class="value">{analysis['total']}</div><div class="label">总商品数</div></div>
        <div class="stat-card"><div class="value">{analysis['jd_count']}</div><div class="label">京东商品</div></div>
        <div class="stat-card"><div class="value">{analysis['tb_count']}</div><div class="label">淘宝商品</div></div>
        <div class="stat-card"><div class="value">{analysis['with_brand']}</div><div class="label">有品牌信息</div></div>
        <div class="stat-card"><div class="value">{analysis['brand_count']}</div><div class="label">品牌总数</div></div>
        <div class="stat-card"><div class="value">{analysis['with_reviews']}</div><div class="label">有评价数据</div></div>
        <div class="stat-card"><div class="value">{analysis.get('total_comments', 0)}</div><div class="label">总评价数</div></div>
        <div class="stat-card"><div class="value">{review_analysis['total']}</div><div class="label">评价文本</div></div>
        <div class="stat-card"><div class="value">¥{analysis.get('price_avg', 0):.0f}</div><div class="label">平均价格</div></div>
        <div class="stat-card"><div class="value">¥{analysis.get('price_min', 0)}</div><div class="label">最低价格</div></div>
        <div class="stat-card"><div class="value">¥{analysis.get('price_max', 0)}</div><div class="label">最高价格</div></div>
        <div class="stat-card"><div class="value">{analysis.get('avg_good_rate', 0):.1f}%</div><div class="label">平均好评率</div></div>
    </div>

    <h2>🏪 平台对比分析</h2>
    <div class="chart-container"><img src="report/platform_comparison.png" alt="平台对比"></div>

    <div class="platform-grid">
        <div class="platform-card jd">
            <h3 style="color:#e94560;">京东</h3>
            <p><strong>商品数：</strong>{analysis['jd_count']}</p>
            <p><strong>品牌数：</strong>{jd_data.get('brand_count', 0)}</p>
            <p><strong>价格区间：</strong>¥{jd_data.get('min_price', 0):.0f} - ¥{jd_data.get('max_price', 0):.0f}</p>
            <p><strong>平均价格：</strong>¥{jd_data.get('avg_price', 0):.0f}</p>
            <p><strong>总评价数：</strong>{jd_data.get('comments', 0)}</p>
            <p><strong>主要品牌：</strong>{', '.join(jd_data.get('brands', [])[:8])}</p>
        </div>
        <div class="platform-card tb">
            <h3 style="color:#ff6600;">淘宝</h3>
            <p><strong>商品数：</strong>{analysis['tb_count']}</p>
            <p><strong>品牌数：</strong>{tb_data.get('brand_count', 0)}</p>
            <p><strong>价格区间：</strong>¥{tb_data.get('min_price', 0):.0f} - ¥{tb_data.get('max_price', 0):.0f}</p>
            <p><strong>平均价格：</strong>¥{tb_data.get('avg_price', 0):.0f}</p>
            <p><strong>总评价数：</strong>{tb_data.get('comments', 0)}</p>
            <p><strong>主要品牌：</strong>{', '.join(tb_data.get('brands', [])[:8])}</p>
        </div>
    </div>

    <h2>📈 价格区间分布</h2>
    <div class="chart-container"><img src="report/price_distribution.png" alt="价格分布"></div>

    <h2>🏷️ 品牌分布</h2>
    <div class="chart-container"><img src="report/brand_distribution.png" alt="品牌分布"></div>

    <table>
        <tr><th>品牌</th><th>商品数</th><th>均价</th><th>总评价数</th><th>平台分布</th></tr>
        {brand_rows}
    </table>

    <h2>💬 评价数量TOP10</h2>
    <div class="chart-container"><img src="report/review_top10.png" alt="评价TOP10"></div>

    <table>
        <tr><th>#</th><th>平台</th><th>商品标题</th><th>价格</th><th>品牌</th><th>店铺</th><th>评价数</th><th>好评率</th><th>链接</th></tr>
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

    <h2>📝 用户评价文本（来自数据库）</h2>
    <div class="chart-container"><img src="report/review_keywords.png" alt="评价关键词"></div>

    <table class="review-table">
        <tr><th>平台</th><th>评价</th><th>用户</th><th>内容</th><th>日期</th></tr>
        {review_rows}
    </table>

    <h2>🔑 商品关键词分析</h2>
    <div class="chart-container"><img src="report/keyword_frequency.png" alt="关键词频率"></div>

    <div class="footer">
        <p>数据采集方式：CDP浏览器自动化 + WebSearch聚合</p>
        <p>数据库：SQLite ({analysis['total']}条商品 + {review_analysis['total']}条评价)</p>
        <p>平台：京东({analysis['jd_count']}) + 淘宝({analysis['tb_count']})</p>
        <p>生成时间：{now}</p>
    </div>
</div>
</body>
</html>"""

    report_path = os.path.join(BASE_DIR, "电火灶电商数据分析报告.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    return report_path


def export_csv(products, reviews):
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

    # Reviews CSV
    review_csv_path = os.path.join(DATA_DIR, "reviews_export.csv")
    with open(review_csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            'review_id', 'product_id', 'platform', 'product_name', 'brand',
            'content', 'score', 'nickname', 'review_date', 'variant', 'images'
        ])
        writer.writeheader()
        for r in reviews:
            writer.writerow({k: r.get(k, '') for k in writer.fieldnames})

    return csv_path, review_csv_path


def export_json(analysis, review_analysis):
    """导出完整数据JSON"""
    json_path = os.path.join(DATA_DIR, "analysis_report.json")

    export_data = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'summary': {
            'total_products': analysis['total'],
            'jd_products': analysis['jd_count'],
            'taobao_products': analysis['tb_count'],
            'total_brands': analysis['brand_count'],
            'total_comments': analysis.get('total_comments', 0),
            'total_reviews': review_analysis['total'],
            'avg_price': analysis.get('price_avg', 0),
            'min_price': analysis.get('price_min', 0),
            'max_price': analysis.get('price_max', 0),
            'avg_good_rate': analysis.get('avg_good_rate', 0),
        },
        'platforms': {k: {kk: vv for kk, vv in v.items() if kk != 'brands'} for k, v in analysis['platforms'].items()},
        'brands': {k: {kk: vv for kk, vv in v.items() if kk != 'platforms'} for k, v in analysis['brands'].items()},
        'review_analysis': review_analysis,
        'user_experience': USER_EXPERIENCE_DATA,
        'keywords': analysis['keywords'],
        'price_ranges': analysis['price_ranges'],
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)
    return json_path


def main():
    print("[1/6] 加载数据库...")
    products, reviews, search_logs = load_data()
    print(f"  商品: {len(products)} 评价: {len(reviews)} 搜索日志: {len(search_logs)}")

    print("[2/6] 分析商品数据...")
    analysis = analyze_products(products)
    print(f"  品牌: {analysis['brand_count']} 店铺: {len(analysis['shops'])}")
    print(f"  京东: {analysis['jd_count']} 淘宝: {analysis['tb_count']}")
    print(f"  总评价数: {analysis.get('total_comments', 0)}")

    print("[3/6] 分析评价数据...")
    review_analysis = analyze_reviews(reviews)
    print(f"  评价: {review_analysis['total']} (好评:{review_analysis['positive_count']} 中评:{review_analysis['neutral_count']} 差评:{review_analysis['negative_count']})")

    print("[4/6] 生成图表...")
    charts = generate_charts(analysis, review_analysis)
    print(f"  生成 {len(charts)} 张图表: {charts}")

    print("[5/6] 生成HTML报告...")
    report_path = generate_html_report(analysis, review_analysis, charts, products, reviews)
    print(f"  报告: {report_path}")

    print("[6/6] 导出数据文件...")
    csv_path, review_csv_path = export_csv(products, reviews)
    json_path = export_json(analysis, review_analysis)
    print(f"  CSV: {csv_path}")
    print(f"  Reviews CSV: {review_csv_path}")
    print(f"  JSON: {json_path}")

    print(f"\n{'='*60}")
    print(f"  报告生成完成！")
    print(f"  京东商品: {analysis['jd_count']} | 淘宝商品: {analysis['tb_count']}")
    print(f"  品牌数: {analysis['brand_count']} | 评价文本: {review_analysis['total']}")
    print(f"  图表数: {len(charts)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
