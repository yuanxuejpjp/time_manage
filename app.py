"""
大科技AI股票筛选器 & 监控列表
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime
import os

# ==================== AI 营收占比字典 ====================
AI_REVENUE_PCT = {
    'NVDA': 40.0,
    'MSFT': 35.0,
    'GOOGL': 30.0,
    'AMZN': 25.0,
    'META': 20.0,
    'AAPL': 15.0
}

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="大科技股筛选器",
    page_icon="📈",
    layout="wide",
)

# ==================== 默认配置 ====================
DEFAULT_WATCHLIST = ['NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'AAPL']

# ==================== RSI 缓存 ====================
RSI_CACHE = {}  # 缓存 RSI 值，避免重复计算

# ==================== Session State ====================
# 文件存储路径
WATCHLIST_FILE = 'watchlist.txt'

def load_watchlist_from_file():
    """从文件加载监控列表"""
    try:
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return content.split(',')
        return DEFAULT_WATCHLIST.copy()
    except:
        return DEFAULT_WATCHLIST.copy()

def save_watchlist_to_file(watchlist):
    """保存监控列表到文件"""
    try:
        with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
            f.write(','.join(watchlist))
    except Exception as e:
        st.warning(f"保存失败: {e}")

# 不在启动时自动设置默认值，让用户自己初始化
if 'watchlist' not in st.session_state:
    # 从文件加载，如果文件不存在则用空列表
    st.session_state.watchlist = load_watchlist_from_file()
elif not isinstance(st.session_state.watchlist, list):
    st.session_state.watchlist = list(st.session_state.watchlist)

def save_watchlist(watchlist):
    """保存监控列表到 session_state 和文件"""
    st.session_state.watchlist = watchlist.copy()
    save_watchlist_to_file(watchlist)

def init_default_watchlist():
    """初始化默认监控列表（只调用一次）"""
    if 'watchlist_initialized' not in st.session_state:
        st.session_state.watchlist_initialized = True
        if not st.session_state.watchlist:  # 只在列表为空时才设置默认值
            st.session_state.watchlist = DEFAULT_WATCHLIST.copy()
            save_watchlist_to_file(DEFAULT_WATCHLIST.copy())

if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = None

# ==================== 宏观指标获取 ====================

def get_fear_and_greed_index():
    """获取 CNN 恐惧贪婪指数"""
    try:
        # 添加浏览器头部，避免被 CNN 阻止
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.cnn.com/',
        }

        response = requests.get(
            'https://production.dataviz.cnn.io/index/fearandgreed/graphdata',
            headers=headers,
            timeout=10
        )
        data = response.json()
        # 尝试多种数据结构格式
        score = None
        if 'fear_and_greed' in data:
            score = data['fear_and_greed'].get('score')
        elif 'score' in data:
            score = data['score']
        elif 'data' in data and len(data['data']) > 0:
            score = data['data'][0].get('score')
        if score is None:
            score = 50  # 默认值
        return score
    except Exception as e:
        st.warning(f"获取恐惧贪婪指数失败: {e}")
        return None

def get_sp500_index():
    """获取 S&P 500 指数"""
    try:
        sp500 = yf.Ticker('^GSPC')
        info = sp500.info
        current = info.get('currentPrice') or info.get('regularMarketPrice')
        prev_close = info.get('previousClose')
        # 计算日增长率
        growth = None
        if current and prev_close:
            growth = ((current - prev_close) / prev_close) * 100
        return current, growth
    except Exception as e:
        st.warning(f"获取 S&P 500 指数失败: {e}")
        return None, None

def get_nasdaq_index():
    """获取纳斯达克指数"""
    try:
        nasdaq = yf.Ticker('^IXIC')
        info = nasdaq.info
        current = info.get('currentPrice') or info.get('regularMarketPrice')
        prev_close = info.get('previousClose')
        # 计算日增长率
        growth = None
        if current and prev_close:
            growth = ((current - prev_close) / prev_close) * 100
        return current, growth
    except Exception as e:
        st.warning(f"获取纳斯达克指数失败: {e}")
        return None, None

def interpret_fear_greed(score):
    """解读恐惧贪婪指数"""
    if score < 25:
        return "极度恐惧", "🔴"
    elif score < 45:
        return "恐惧", "🟠"
    elif score <= 55:
        return "中性", "⚪"
    elif score <= 75:
        return "贪婪", "🟢"
    else:
        return "极度贪婪", "🟢"

# ==================== RSI 计算 ====================

def calculate_rsi(ticker_symbol, period=14):
    """计算 RSI 指标"""
    # 检查缓存
    if ticker_symbol in RSI_CACHE:
        return RSI_CACHE[ticker_symbol]

    try:
        ticker = yf.Ticker(ticker_symbol)
        # 获取足够的历史数据（至少 period + 1 天）
        hist = ticker.history(period="1mo")
        if hist.empty or len(hist) < period + 1:
            return None

        closes = hist['Close'].values

        # 计算价格变化
        deltas = closes[1:] - closes[:-1]

        # 分离上涨和下跌
        gains = deltas.copy()
        losses = deltas.copy()
        gains[gains < 0] = 0
        losses[losses > 0] = 0
        losses = -losses

        # 计算平均涨跌幅（使用 Wilder 平滑方法）
        avg_gain = gains[:period].mean()
        avg_loss = losses[:period].mean()

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            rsi = 100  # 没有下跌，RSI 为 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        rsi_value = round(rsi, 1)
        # 缓存结果
        RSI_CACHE[ticker_symbol] = rsi_value
        return rsi_value
    except Exception as e:
        # 静默失败，返回 None
        return None

# ==================== 数据获取 ====================

def get_stock_data(ticker_symbol):
    """获取股票数据"""
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info

        # 计算 FCF Yield
        market_cap = info.get('marketCap')
        free_cash_flow = info.get('freeCashflow')
        if market_cap and market_cap > 0:
            fcf_yield = (free_cash_flow / market_cap * 100) if free_cash_flow else 0
        else:
            fcf_yield = 0

        # 计算净现金
        total_cash = info.get('totalCash') or 0
        total_debt = info.get('totalDebt') or 0
        net_cash = total_cash - total_debt

        # ROE 转换为百分比
        roe = info.get('returnOnEquity')
        if roe is not None:
            roe = roe * 100

        # 机构持股转换为百分比
        inst_holding = info.get('heldPercentInstitutions')
        if inst_holding is not None:
            inst_holding = inst_holding * 100

        # 计算 PEG = Forward PE / EPS增长率(百分比)
        forward_pe = info.get('forwardPE')
        # Yahoo 的 earningsQuarterlyGrowth/earningsGrowth 可能是小数或百分比格式
        eps_growth_raw = info.get('earningsQuarterlyGrowth') or info.get('earningsGrowth')
        peg_ratio = info.get('pegRatio')  # 先用 Yahoo 的值作为默认

        # 如果 Yahoo 有 PEG，直接使用；否则自己计算
        if peg_ratio is None and forward_pe is not None and eps_growth_raw is not None:
            # 判断 eps_growth 是小数(<1)还是百分比(>=1)，统一转换为百分比
            if abs(eps_growth_raw) < 1:
                eps_growth_pct = eps_growth_raw * 100  # 小数转百分比，如 0.15 -> 15
            else:
                eps_growth_pct = eps_growth_raw  # 已经是百分比
            if eps_growth_pct > 0:
                peg_ratio = forward_pe / eps_growth_pct

        # 获取 RSI 值
        rsi = calculate_rsi(ticker_symbol)

        return {
            'ticker': ticker_symbol,
            'current_price': info.get('currentPrice') or info.get('regularMarketPrice'),
            'forward_pe': forward_pe,
            'peg_ratio': peg_ratio,
            'debt_to_equity': info.get('debtToEquity'),
            'total_revenue': info.get('totalRevenue'),
            'revenue_growth': info.get('revenueGrowth'),
            'eps_growth': eps_growth_raw,
            'free_cash_flow': free_cash_flow,
            'fcf_yield': fcf_yield,
            'net_cash': net_cash,
            'beta': info.get('beta'),  # Beta值
            'rsi': rsi,  # RSI指标
            'roe': roe,
            'institutional_holdings': inst_holding,
            'recommendation': info.get('averageRecommendation'),
            'ai_revenue_pct': AI_REVENUE_PCT.get(ticker_symbol, 0),
        }
    except Exception as e:
        st.warning(f"获取 {ticker_symbol} 数据失败: {e}")
        return None

def fetch_all_stocks(watchlist):
    """批量获取所有股票数据"""
    stock_data = {}
    for ticker in watchlist:
        data = get_stock_data(ticker)
        if data:
            stock_data[ticker] = data
    return stock_data

# ==================== 筛选逻辑函数 ====================

def check_step1(data):
    """1. Forward PEG ≤ 1.2 (如果 PEG 不可用则跳过此步骤)"""
    peg = data.get('peg_ratio')
    # 如果 PEG 数据不可用，跳过此检查（返回 True）
    if peg is None:
        return True
    return peg <= 1.2

def check_step2(data):
    """2. 债务权益比率 < 50%"""
    d_e = data.get('debt_to_equity')
    return d_e is not None and d_e < 50

def check_step3(data):
    """3. TTM 营收 ≥ 500亿美元"""
    revenue = data.get('total_revenue')
    return revenue is not None and revenue >= 50e9

def check_step4(data):
    """4. Forward PE ≤ 25 且 营收增长 ≥ 15%"""
    pe = data.get('forward_pe')
    growth = data.get('revenue_growth')
    pe_ok = pe is not None and pe <= 25
    growth_ok = growth is not None and growth >= 0.15
    return pe_ok and growth_ok

def check_step5(data):
    """5. EPS增长率 >= 20% (越高越好)"""
    eps = data.get('eps_growth')
    if eps is not None:
        eps_pct = eps * 100
        return eps_pct >= 20
    return False

def check_step6(data):
    """6. FCF为正 且 FCF Yield ≥ 2.5%"""
    fcf = data.get('free_cash_flow')
    yield_val = data.get('fcf_yield')
    fcf_ok = fcf is not None and fcf > 0
    yield_ok = yield_val is not None and yield_val >= 2.5
    return fcf_ok and yield_ok

def check_step7(data):
    """7. 净现金 > 0"""
    net_cash = data.get('net_cash')
    return net_cash is not None and net_cash > 0

def calculate_bonus_points(data):
    """计算加分项"""
    points = 0
    details = []

    # 加分1: Forward PE < 22 (PEG 数据不可用，仅使用 PE 判断)
    pe = data.get('forward_pe')
    if pe is not None and pe < 22:
        points += 1
        details.append(f"估值优(PE<{pe:.1f})")

    # 加分2: AI营收占比 ≥ 30%
    ai_pct = data.get('ai_revenue_pct', 0)
    if ai_pct >= 30:
        points += 1
        details.append(f"AI业务强({ai_pct}%)")

    # 加分3: ROE ≥ 25%
    roe = data.get('roe')
    if roe is not None and roe >= 25:
        points += 1
        details.append(f"高ROE({roe:.1f}%)")

    # 加分4: 机构持股 > 70% 且 推荐 ≤ 2.0
    inst = data.get('institutional_holdings')
    rec = data.get('recommendation')
    if inst is not None and inst > 70 and rec is not None and rec <= 2.0:
        points += 1
        details.append(f"机构看好({inst:.1f}%)")

    return points, details

def run_screening(data):
    """运行所有筛选步骤"""
    steps = {
        'step1': check_step1(data),
        'step2': check_step2(data),
        'step3': check_step3(data),
        'step4': check_step4(data),
        'step5': check_step5(data),
        'step6': check_step6(data),
        'step7': check_step7(data),
    }

    passed_count = sum(1 for v in steps.values() if v)
    bonus_points, bonus_details = calculate_bonus_points(data)

    # 确定状态和颜色
    if passed_count == 7:
        status = "强烈推荐"
        color = "#90EE90"
    elif passed_count >= 5:
        status = "观察中"
        color = "#FFFF99"
    else:
        status = "不推荐"
        color = "#FFFFFF"

    return {
        'steps': steps,
        'passed_count': passed_count,
        'bonus_points': bonus_points,
        'bonus_details': bonus_details,
        'status': status,
        'color': color
    }

# ==================== 格式化函数 ====================

def format_value(value, decimals=2, default="N/A"):
    """格式化数值"""
    if value is None:
        return default
    try:
        return f"{round(value, decimals)}"
    except:
        return default

def format_price(value):
    """格式化价格"""
    if value is None:
        return "N/A"
    return f"${value:.2f}"

def format_revenue(value_in_billions):
    """格式化营收（十亿美元）"""
    if value_in_billions is None:
        return "N/A"
    return f"${value_in_billions/1e9:.1f}B"

def format_percent(value, decimals=1):
    """格式化百分比"""
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}%"

def format_net_cash(value):
    """格式化净现金"""
    if value is None:
        return "N/A"
    abs_value = abs(value)
    if abs_value >= 1e9:
        return f"${value/1e9:.1f}B"
    elif abs_value >= 1e6:
        return f"${value/1e6:.1f}M"
    else:
        return f"${value:.0f}"

# ==================== 表格创建 ====================

def create_watchlist_dataframe(stock_data):
    """创建监控列表表格"""
    rows = []

    for ticker, data in stock_data.items():
        screening = run_screening(data)
        steps = screening['steps']

        row = {
            'Ticker': ticker,
            '价格': format_price(data.get('current_price')),
            'Forward PE': format_value(data.get('forward_pe')),
            'PEG': format_value(data.get('peg_ratio'), decimals=2),
            '债务权益比': format_value(data.get('debt_to_equity'), decimals=1),
            'TTM营收': format_revenue(data.get('total_revenue')),
            'EPS增长': format_percent((data.get('eps_growth') or 0) * 100),
            'FCF Yield': format_percent(data.get('fcf_yield')),
            '净现金': format_net_cash(data.get('net_cash')),
            'Beta': format_value(data.get('beta'), decimals=2),
            'RSI': format_value(data.get('rsi'), decimals=1),
            '通过步数': f"{screening['passed_count']}/7",
            '加分项': f"+{screening['bonus_points']}",
            '状态': screening['status'],
            '_color': screening['color'],  # 内部字段，用于颜色编码
            '_passed_count': screening['passed_count'],  # 用于排序
            '_bonus_points': screening['bonus_points'],  # 用于排序
            '_screening': screening,  # 保存完整筛选结果
            '_data': data,  # 保存完整数据
            # 保存每列是否通过的条件（用于红色高亮）
            '_fail_peg': not steps['step1'],  # PEG 在 step1
            '_fail_forward_pe': not steps['step4'],  # Forward PE 在 step4
            '_fail_debt_equity': not steps['step2'],  # 债务权益比在 step2
            '_fail_revenue': not steps['step3'],  # TTM营收在 step3
            '_fail_eps_growth': not steps['step5'],  # EPS增长在 step5
            '_fail_fcf_yield': not steps['step6'],  # FCF Yield在 step6
            '_fail_net_cash': not steps['step7'],  # 净现金在 step7
            # RSI 颜色标记
            '_rsi_value': data.get('rsi'),  # 保存原始 RSI 值用于颜色判断
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    # 按照推荐程度排序：通过步数多的在前，通过步数相同时加分项多的在前
    df = df.sort_values(by=['_passed_count', '_bonus_points'], ascending=False)
    return df


# ==================== 详细信息展开 ====================

def show_stock_details(ticker, data, screening):
    """显示股票详细信息"""
    with st.expander(f"📊 {ticker} 详细筛选结果"):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### 筛选标准")
            steps = screening['steps']
            step_names = [
                ("Forward PEG ≤ 1.2", 'peg_ratio', format_value(data.get('peg_ratio')) if data.get('peg_ratio') else "N/A (跳过)"),
                ("债务权益比 < 50%", 'debt_to_equity', format_value(data.get('debt_to_equity'), decimals=1) + '%'),
                ("TTM营收 ≥ 500亿美元", 'total_revenue', format_revenue(data.get('total_revenue'))),
                ("Forward PE ≤ 25 且营收增长 ≥ 15%", 'forward_pe',
                 f"PE:{format_value(data.get('forward_pe'))} 增长:{format_percent(data.get('revenue_growth')*100)}"),
                ("EPS增长率 >= 20% (越高越好)", 'eps_growth', format_percent((data.get('eps_growth') or 0) * 100)),
                ("FCF为正且 Yield ≥ 2.5%", 'fcf_yield', format_percent(data.get('fcf_yield'))),
                ("净现金 > 0", 'net_cash', f"${data.get('net_cash', 0)/1e9:.1f}B"),
            ]

            for i, (name, key, val) in enumerate(step_names, 1):
                if steps[f'step{i}']:
                    st.markdown(f"✅ **{name}**: {val}")
                else:
                    st.markdown(f"❌ **{name}**: {val}")

        with col2:
            st.markdown("### 加分项详情")
            if screening['bonus_details']:
                for detail in screening['bonus_details']:
                    st.markdown(f"⭐ +1 {detail}")
            else:
                st.info("无加分项")

            st.markdown("### 其他关键指标")
            st.markdown(f"**ROE**: {format_percent(data.get('roe'))}")
            st.markdown(f"**机构持股**: {format_percent(data.get('institutional_holdings'))}")
            st.markdown(f"**Beta**: {format_value(data.get('beta'), decimals=2)} (波动性指标)")
            rec = data.get('recommendation')
            st.markdown(f"**分析师评分**: {format_value(rec)} (1=买入, 5=卖出)")
            st.markdown(f"**AI营收占比**: {data.get('ai_revenue_pct', 0)}%")
# ==================== 侧边栏 ====================

def render_sidebar():
    """渲染侧边栏"""
    st.sidebar.title("⚙️ 设置")

    # 初始化默认监控列表（如果是第一次使用）
    if not st.session_state.watchlist:
        st.sidebar.info("监控列表为空，点击下方按钮初始化默认列表")
        if st.sidebar.button("🔄 初始化默认列表"):
            init_default_watchlist()
            st.rerun()

    st.sidebar.markdown("---")

    # 添加新股票
    st.sidebar.subheader("添加股票")
    new_ticker = st.sidebar.text_input(
        "股票代码",
        placeholder="例如: TSLA"
    ).strip().upper()

    if st.sidebar.button("➕ 添加到监控列表"):
        if new_ticker:
            if new_ticker not in st.session_state.watchlist:
                # 创建新列表并保存
                new_list = st.session_state.watchlist.copy()
                new_list.append(new_ticker)
                save_watchlist(new_list)
                st.sidebar.success(f"已添加 {new_ticker}")
            else:
                st.sidebar.warning(f"{new_ticker} 已在列表中")

    st.sidebar.markdown("---")

    # 当前监控列表
    st.sidebar.subheader(f"当前监控列表 ({len(st.session_state.watchlist)})")

    if st.session_state.watchlist:
        st.sidebar.write(", ".join(st.session_state.watchlist))

        stocks_to_remove = st.sidebar.multiselect(
            "选择要移除的股票",
            st.session_state.watchlist
        )

        if stocks_to_remove and st.sidebar.button("🗑️ 移除选中"):
            if stocks_to_remove:
                # 创建新列表并保存
                new_list = [s for s in st.session_state.watchlist if s not in stocks_to_remove]
                save_watchlist(new_list)
                st.sidebar.success("已移除")

    st.sidebar.markdown("---")

    # 刷新数据
    if st.sidebar.button("🔄 刷新所有数据"):
        st.session_state.last_refresh = datetime.now()
        st.rerun()

    # 显示最后刷新时间
    if st.session_state.last_refresh:
        st.sidebar.caption(
            f"最后刷新: {st.session_state.last_refresh.strftime('%H:%M:%S')}"
        )

# ==================== 主函数 ====================

def main():
    """主函数"""

    # 自定义 CSS - 移动端优化 + 美化
    st.markdown(
        """
        <style>
        /* 全局字体和背景 */
        .main {
            font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }

        /* 移动端优化 */
        @media (max-width: 768px) {
            /* 表格水平滚动 */
            .main .block-container {
                padding-left: 1rem !important;
                padding-right: 1rem !important;
            }
            /* 减小表格字体 */
            .dataframe {
                font-size: 0.7rem !important;
            }
            .dataframe td, .dataframe th {
                padding: 0.4rem 0.3rem !important;
            }
            /* 减小标题字体 */
            h1 {
                font-size: 1.5rem !important;
            }
            h2 {
                font-size: 1.2rem !important;
            }
            h3 {
                font-size: 1rem !important;
            }
            /* 卡片内边距 */
            .css-1d391kg {
                padding: 0.5rem !important;
            }
            /* 指标卡片 */
            .css-1vbd788 {
                padding: 0.75rem 0.5rem !important;
            }
            /* Metric 标签字体 */
            .metric-label {
                font-size: 0.8rem !important;
            }
            .metric-value {
                font-size: 1.2rem !important;
            }
        }
        @media (max-width: 480px) {
            /* 超小屏幕优化 */
            .dataframe {
                font-size: 0.65rem !important;
            }
            .dataframe td, .dataframe th {
                padding: 0.3rem 0.2rem !important;
            }
        }

        /* 美化指标卡片 */
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 1rem;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }

        /* 美化表格 */
        .stDataFrame {
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .stDataFrame table {
            width: 100%;
        }
        .stDataFrame th {
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            color: white;
            font-weight: 600;
            text-align: center;
        }
        .stDataFrame td {
            text-align: center;
        }

        /* 标题渐变 */
        .title-gradient {
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        /* 按钮美化 */
        .stButton > button {
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            padding: 0.5rem 1.5rem;
            font-weight: 600;
            transition: all 0.3s;
        }
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }

        /* 输入框美化 */
        .stTextInput > div > div > input {
            border-radius: 8px;
            border: 2px solid #e0e0e0;
        }
        .stTextInput > div > div > input:focus {
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        /* Tab 美化 */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 8px 8px 0 0;
            padding: 10px 20px;
            font-weight: 600;
        }

        /* 侧边栏美化 */
        .css-1d391kg {
            background: linear-gradient(180deg, #f8f9ff 0%, #ffffff 100%);
        }

        /* Expander 美化 */
        .streamlit-expanderHeader {
            background: linear-gradient(90deg, #f0f4ff 0%, #ffffff 100%);
            border-radius: 8px;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # 渲染侧边栏
    render_sidebar()

    # 页面标题
    st.markdown('<h1 class="title-gradient">🤖 大科技股筛选器</h1>', unsafe_allow_html=True)
    st.markdown("**基于彼得·林奇风格优化的7步筛选法，专门针对大科技AI公司**")

    # 当前日期
    today = datetime.now().strftime('%Y年%m月%d日 %A')
    st.markdown(
        f'<p style="text-align: center; color: #999; font-size: 0.9rem;">📅 {today}</p>',
        unsafe_allow_html=True
    )

    # 名言卡片
    st.markdown(
        """
        <div style="
            text-align: center;
            padding: 1.5rem 1rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 16px;
            margin: 1.5rem 0;
            box-shadow: 0 8px 24px rgba(102, 126, 234, 0.25);
        ">
            <p style="
                color: white;
                font-size: clamp(1rem, 3vw, 1.3rem);
                font-weight: 600;
                margin: 0;
                letter-spacing: 0.5px;
            ">
                💎 投资是个等待的游戏 💎
            </p>
            <p style="
                color: rgba(255,255,255,0.8);
                font-size: clamp(0.75rem, 2vw, 0.9rem);
                margin: 0.5rem 0 0 0;
            ">
                — 彼得·林奇
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ==================== 第一部分：宏观指标区 ====================
    st.markdown("---")
    st.markdown("### 📊 市场概览")

    # 使用容器包裹宏观指标，添加卡片样式
    with st.container():
        col1, col2, col3 = st.columns(3)

        with col1:
            fg_score = get_fear_and_greed_index()
            if fg_score is not None:
                fg_text, fg_emoji = interpret_fear_greed(fg_score)
                st.metric(
                    label=f"CNN 恐惧贪婪指数 {fg_emoji}",
                    value=f"{fg_score}",
                    delta=fg_text
                )
                st.caption(f"<25 极度恐惧 | 25-45 恐惧 | 45-55 中性 | 55-75 贪婪 | >75 极度贪婪")

        with col2:
            sp500_value, sp500_growth = get_sp500_index()
            if sp500_value is not None:
                delta_str = f"{sp500_growth:+.2f}%" if sp500_growth is not None else None
                st.metric(
                    label="S&P 500 指数",
                    value=f"{sp500_value:.2f}",
                    delta=delta_str
                )

        with col3:
            nasdaq_value, nasdaq_growth = get_nasdaq_index()
            if nasdaq_value is not None:
                delta_str = f"{nasdaq_growth:+.2f}%" if nasdaq_growth is not None else None
                st.metric(
                    label="纳斯达克指数 (NASDAQ)",
                    value=f"{nasdaq_value:.2f}",
                    delta=delta_str
                )

    # ==================== 第二部分：标签页 ====================
    st.markdown("---")

    # 获取所有股票数据（在标签页外获取一次，避免重复请求）
    stock_data = fetch_all_stocks(st.session_state.watchlist)

    tab1, tab2 = st.tabs(["📈 监控列表", "📋 筛选指标说明"])

    # 标签页1：监控列表
    with tab1:
        st.subheader("监控列表")

        if not stock_data:
            st.info("监控列表为空或数据获取失败")
        else:
            # 创建表格
            df = create_watchlist_dataframe(stock_data)

            # 删除内部列用于显示
            display_columns = [col for col in df.columns if not col.startswith('_')]
            display_df = df[display_columns].copy()

            # 为状态列添加颜色样式
            def highlight_status_col(s):
                """高亮状态列"""
                return ['background-color: #90EE90' if v == "强烈推荐" else
                        'background-color: #FFFF99' if v == "观察中" else ''
                        for v in s]

            # 为 RSI 列添加颜色（<30 绿色超卖，>70 红色超买）
            def highlight_rsi_col(s, orig_df):
                """高亮 RSI 列"""
                styles = []
                for idx, val in enumerate(s):
                    orig_row = orig_df.iloc[idx]
                    rsi_val = orig_row.get('_rsi_value')
                    if rsi_val is None:
                        styles.append('')
                    elif rsi_val < 30:
                        styles.append('background-color: #90EE90')  # 绿色 - 超卖
                    elif rsi_val > 70:
                        styles.append('background-color: #FFCCCC')  # 红色 - 超买
                    else:
                        styles.append('')
                return styles

            # 为失败列添加红色 - 闭包捕获 original_df
            def make_highlight_func(col_name, orig_df):
                """创建高亮函数工厂"""
                def highlight_func(s):
                    """高亮失败的列"""
                    styles = []
                    for idx, val in enumerate(s):
                        orig_row = orig_df.iloc[idx]
                        should_red = False

                        if col_name == 'PEG' and orig_row.get('_fail_peg', False):
                            should_red = True
                        elif col_name == 'Forward PE' and orig_row.get('_fail_forward_pe', False):
                            should_red = True
                        elif col_name == '债务权益比' and orig_row.get('_fail_debt_equity', False):
                            should_red = True
                        elif col_name == 'TTM营收' and orig_row.get('_fail_revenue', False):
                            should_red = True
                        elif col_name == 'EPS增长' and orig_row.get('_fail_eps_growth', False):
                            should_red = True
                        elif col_name == 'FCF Yield' and orig_row.get('_fail_fcf_yield', False):
                            should_red = True
                        elif col_name == '净现金' and orig_row.get('_fail_net_cash', False):
                            should_red = True

                        styles.append('background-color: #FFCCCC' if should_red else '')
                    return styles
                return highlight_func

            # 应用样式
            styled_df = display_df.style
            styled_df.apply(highlight_status_col, subset=['状态'])
            styled_df.apply(highlight_rsi_col, orig_df=df, subset=['RSI'])
            styled_df.apply(make_highlight_func('PEG', df), subset=['PEG'])
            styled_df.apply(make_highlight_func('Forward PE', df), subset=['Forward PE'])
            styled_df.apply(make_highlight_func('债务权益比', df), subset=['债务权益比'])
            styled_df.apply(make_highlight_func('TTM营收', df), subset=['TTM营收'])
            styled_df.apply(make_highlight_func('EPS增长', df), subset=['EPS增长'])
            styled_df.apply(make_highlight_func('FCF Yield', df), subset=['FCF Yield'])
            styled_df.apply(make_highlight_func('净现金', df), subset=['净现金'])

            st.dataframe(styled_df, use_container_width=True, hide_index=True)

            # 显示每只股票的详细信息
            st.markdown("---")
            st.subheader("📊 详细筛选结果")

            for ticker, data in stock_data.items():
                screening = run_screening(data)
                show_stock_details(ticker, data, screening)

    # 标签页2：筛选指标说明
    with tab2:
        st.markdown("### 📋 筛选指标说明")

        st.markdown("""
        #### 指标含义解释

        | 表格列名 | 含义 | 筛选标准 |
        |----------|------|----------|
        | **价格** | 股票当前市场价格 | - |
        | **Forward PE** | 未来市盈率 = 当前股价 ÷ 预期每股收益。衡量投资者为公司未来收益支付的价格，数值越低估值越便宜。 | ≤ 25 |
        | **债务权益比** | 总负债 ÷ 股东权益。衡量公司财务杠杆水平，反映公司依赖债务融资的程度。数值越高风险越大。 | < 50% |
        | **TTM营收** | 过去12个月总营收。衡量公司业务规模和市场地位。 | ≥ $500B |
        | **EPS增长** | 每股收益年增长率。衡量公司盈利能力的增长速度，EPS增长通常推动股价上涨。 | ≥ 20% |
        | **FCF Yield** | 自由现金流收益率 = 自由现金流 ÷ 市值。衡量公司产生现金回报股东的能力，比PE更能反映真实盈利质量。 | ≥ 2.5% |
        | **净现金** | 现金减去总债务。净现金为正表示公司现金多于债务，财务实力雄厚。 | > 0 |
        | **Beta** | 衡量股票相对整个市场的波动性。Beta > 1 表示波动比市场大，Beta < 1 表示波动比市场小。 | - |

        #### 7步筛选法详解 (彼得·林奇风格)

        1. **Forward PEG ≤ 1.2**: PEG = Forward PE ÷ EPS增长率，综合考虑估值和成长性。PEG < 1 表示被低估，PEG = 1 合理估值，PEG > 1 被高估 (数据不可用时跳过)
        2. **债务权益比 < 50%**: 财务健康，债务负担较轻
        3. **TTM营收 ≥ $500亿**: 大型成熟公司，业务稳定
        4. **Forward PE ≤ 25 且营收增长 ≥ 15%**: 估值合理且业务在扩张
        5. **EPS增长率 ≥ 20%**: 盈利增长强劲，越高越好
        6. **FCF为正且 Yield ≥ 2.5%**: 产生真金白银的现金流
        7. **净现金 > 0**: 现金多于债务，财务实力雄厚

        #### 加分项 (0-4分)

        - **估值优**: Forward PE < 22 (低估值)
        - **AI业务强**: AI营收占比 ≥ 30%
        - **高ROE**: 净资产收益率 ≥ 25%
        - **机构看好**: 机构持股 > 70% 且分析师推荐 ≤ 2.0

        #### 状态颜色说明

        - 🟢 **绿色 (强烈推荐)**: 通过全部 7 步筛选
        - 🟡 **黄色 (观察中)**: 通过至少 5 步但未全部通过
        - ⚪ **白色**: 通过少于 5 步，不推荐

        #### 单元格颜色说明

        - 🔴 **红色背景**: 该指标不满足筛选条件
        """)

    # 页脚
    st.markdown("---")
    st.markdown(
        """
        <div style="
            text-align: center;
            padding: 1.5rem;
            background: linear-gradient(90deg, #f8f9ff 0%, #fff5f5 100%);
            border-radius: 12px;
            margin-top: 2rem;
        ">
            <p style="color: #666; font-size: 0.9rem; margin: 0;">
                📊 数据来源: Yahoo Finance (yfinance) | CNN Fear & Greed Index
            </p>
            <p style="color: #999; font-size: 0.8rem; margin: 0.5rem 0 0 0;">
                最后更新: {}
            </p>
        </div>
        """.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
