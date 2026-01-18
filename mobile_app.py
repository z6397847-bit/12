# -*- coding: utf-8 -*-
"""
日内做T信号系统 - Kivy移动端应用 v5.0
完整增强版：动画 + K线图 + 主题切换 + 提醒 + 预警 + KDJ + 导出
"""

import os
os.environ['KIVY_TEXT'] = 'pil'

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.widget import Widget
from kivy.uix.slider import Slider
from kivy.uix.switch import Switch
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.properties import ListProperty, StringProperty, NumericProperty, BooleanProperty
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle, Ellipse
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.core.audio import SoundLoader
from kivy.metrics import dp, sp
from kivy.utils import get_color_from_hex, platform

import threading
import requests
import numpy as np
from datetime import datetime
import csv
import json

# 自适应窗口
Window.minimum_width = 320
Window.minimum_height = 500
Window.size = (420, 750)

# ==================== 中文字体 ====================
FONT = 'Roboto'
for path in ['C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf']:
    if os.path.exists(path):
        try:
            LabelBase.register(name='CFont', fn_regular=path)
            FONT = 'CFont'
            break
        except:
            pass

# ==================== 主题配置 ====================
THEMES = {
    'dark': {
        'bg': '#0f1117', 'card': '#1a1d26', 'card2': '#252a36',
        'text': '#ffffff', 'gray': '#6b7280', 'green': '#22c55e',
        'red': '#ef4444', 'blue': '#3b82f6', 'yellow': '#eab308', 'purple': '#a855f7'
    },
    'light': {
        'bg': '#f3f4f6', 'card': '#ffffff', 'card2': '#e5e7eb',
        'text': '#1f2937', 'gray': '#6b7280', 'green': '#16a34a',
        'red': '#dc2626', 'blue': '#2563eb', 'yellow': '#ca8a04', 'purple': '#9333ea'
    }
}

# 当前主题
class ThemeManager:
    def __init__(self):
        self.current = 'dark'
        self.listeners = []
    
    def get(self, key):
        return THEMES[self.current].get(key, '#ffffff')
    
    def toggle(self):
        self.current = 'light' if self.current == 'dark' else 'dark'
        for fn in self.listeners:
            fn()
    
    def add_listener(self, fn):
        self.listeners.append(fn)

THEME = ThemeManager()

# ==================== 全局数据 ====================
class AppData:
    watchlist = ['600586', '000001', '600519', '000858']
    current = '600586'
    signals = []
    trades = []  # 交易日志
    position = {'hold': 0, 'cost': 0, 'profit': 0}
    stock_cache = {}
    prices_cache = {}
    # 预警设置
    alerts = {}  # {code: {'high': price, 'low': price}}
    # 设置
    sound_enabled = True
    vibrate_enabled = True

DATA = AppData()

# ==================== API ====================
def fetch_quote(code):
    try:
        sym = f"sh{code}" if code.startswith('6') else f"sz{code}"
        r = requests.get(f'http://qt.gtimg.cn/q={sym}', timeout=5)
        r.encoding = 'gbk'
        if 'v_' in r.text:
            p = r.text.split('~')
            if len(p) > 40:
                return {
                    'name': p[1], 'code': code,
                    'price': float(p[3] or 0),
                    'change': float(p[32] or 0),
                    'open': float(p[5] or 0),
                    'high': float(p[33] or 0),
                    'low': float(p[34] or 0),
                    'volume': float(p[6] or 0),
                }
    except:
        pass
    return None

def fetch_prices(code):
    try:
        sym = f"sh{code}" if code.startswith('6') else f"sz{code}"
        r = requests.get(f'http://data.gtimg.cn/flashdata/hushen/minute/{sym}.js', timeout=5)
        prices, volumes = [], []
        for line in r.text.split('\\n\\')[1:]:
            parts = line.strip().split(' ')
            if len(parts) >= 3:
                try:
                    prices.append(float(parts[1]))
                    volumes.append(float(parts[2]))
                except:
                    pass
        return prices, volumes
    except:
        return [], []

# ==================== 技术分析 ====================
def calc_rsi(p, n=14):
    if len(p) < n+1: return 50
    d = np.diff(p[-n-1:])
    return round(100 - 100 / (1 + np.mean(np.maximum(d,0)) / (np.mean(np.maximum(-d,0))+1e-9)), 1)

def calc_macd(p):
    if len(p) < 26: return 0, 0, 0
    def ema(d, n):
        a = 2/(n+1)
        e = [d[0]]
        for i in range(1, len(d)):
            e.append(a*d[i] + (1-a)*e[-1])
        return e
    fast = ema(p, 12)
    slow = ema(p, 26)
    macd = [f-s for f,s in zip(fast, slow)]
    sig = ema(macd, 9)
    return round(macd[-1], 4), round(sig[-1], 4), round(macd[-1]-sig[-1], 4)

def calc_kdj(p, n=9):
    if len(p) < n: return 50, 50, 50
    low_n = min(p[-n:])
    high_n = max(p[-n:])
    if high_n == low_n:
        rsv = 50
    else:
        rsv = (p[-1] - low_n) / (high_n - low_n) * 100
    k = rsv  # 简化计算
    d = k
    j = 3*k - 2*d
    return round(k, 1), round(d, 1), round(j, 1)

def calc_ma(p, n):
    return round(np.mean(p[-n:]), 2) if len(p) >= n else (round(p[-1], 2) if p else 0)

def calc_boll(p, n=20):
    if len(p) < n: return 0, 0, 0
    mid = np.mean(p[-n:])
    std = np.std(p[-n:])
    return round(mid+2*std, 2), round(mid, 2), round(mid-2*std, 2)

def calc_sr(p, n=15):
    if len(p) < n: return (round(min(p),2), round(max(p),2)) if p else (0,0)
    return round(min(p[-n:]), 2), round(max(p[-n:]), 2)

def calc_volume_ratio(v, n=10):
    if len(v) < n+1: return 1.0
    return round(v[-1] / (np.mean(v[-n-1:-1]) + 1e-9), 2)

def detect_pattern(p):
    if len(p) < 15: return "数据不足"
    r = p[-15:]
    mi, ma = np.argmin(r), np.argmax(r)
    s, l, h, c = r[0], r[mi], r[ma], r[-1]
    if 2 < mi < 12 and (s-l)/s > 0.01 and (c-l)/l > 0.008: return "V型反转"
    if 2 < ma < 12 and (h-s)/s > 0.01 and (h-c)/h > 0.008: return "倒V型"
    if (h-l)/l < 0.015: return "箱体震荡"
    return "趋势运行"

def predict_trend(p, ma5, ma10):
    """简单趋势预测"""
    if len(p) < 10: return "数据不足", 0
    current = p[-1]
    if ma5 > ma10 and current > ma5:
        return "上涨趋势", 1
    elif ma5 < ma10 and current < ma5:
        return "下跌趋势", -1
    else:
        return "震荡整理", 0

def calc_score(price, sup, res, rsi, pat, k, vol_ratio):
    s = 0
    if rsi < 30: s += 25
    elif rsi < 40: s += 18
    elif rsi < 50: s += 8
    if res > sup:
        pos = (price - sup) / (res - sup)
        s += 20 if pos <= 0.2 else (12 if pos <= 0.4 else 4)
    if 'V型' in pat: s += 20
    elif '箱体' in pat: s += 8
    if k < 20: s += 15
    elif k < 30: s += 10
    if vol_ratio < 0.7: s += 10
    elif vol_ratio < 1.0: s += 5
    h = datetime.now().hour + datetime.now().minute / 60
    if 9.75 <= h <= 10.5 or 13.5 <= h <= 14.5: s += 10
    return min(s, 100)

# ==================== 提醒功能 ====================
def play_sound():
    if not DATA.sound_enabled:
        return
    try:
        # Windows系统蜂鸣
        if platform == 'win':
            import winsound
            winsound.Beep(1000, 200)
    except:
        pass

def vibrate():
    if not DATA.vibrate_enabled:
        return
    try:
        if platform == 'android':
            from plyer import vibrator
            vibrator.vibrate(0.3)
    except:
        pass

def check_alerts(code, price):
    """检查价格预警"""
    if code not in DATA.alerts:
        return None
    alert = DATA.alerts[code]
    if alert.get('high') and price >= alert['high']:
        return f"突破上限 {alert['high']}"
    if alert.get('low') and price <= alert['low']:
        return f"跌破下限 {alert['low']}"
    return None

# ==================== 导出功能 ====================
def export_signals_csv(filepath='signals_export.csv'):
    try:
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['日期', '时间', '股票', '类型', '价格', '评分'])
            for s in DATA.signals:
                writer.writerow([s.get('date',''), s.get('time',''), s.get('code',''), 
                                s.get('type',''), s.get('price',''), s.get('score','')])
        return True
    except:
        return False

def export_trades_csv(filepath='trades_export.csv'):
    try:
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['时间', '股票', '操作', '价格', '仓位', '盈亏'])
            for t in DATA.trades:
                writer.writerow([t.get('time',''), t.get('code',''), t.get('action',''),
                                t.get('price',''), t.get('ratio',''), t.get('profit','')])
        return True
    except:
        return False

# ==================== UI组件 ====================
class CLabel(Label):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.font_name = FONT
        if 'color' not in kw:
            self.color = get_color_from_hex(THEME.get('text'))

class CButton(Button):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.font_name = FONT
        self.background_normal = ''
        if 'background_color' not in kw:
            self.background_color = get_color_from_hex(THEME.get('blue'))

class Card(BoxLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.padding = dp(8)
        self._draw_bg()
        self.bind(pos=self._draw_bg, size=self._draw_bg)
        THEME.add_listener(self._draw_bg)
    
    def _draw_bg(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*get_color_from_hex(THEME.get('card')))
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])

class InfoBox(BoxLayout):
    def __init__(self, title='', **kw):
        super().__init__(**kw)
        self.orientation = 'vertical'
        self.padding = dp(4)
        self._draw_bg()
        self.bind(pos=self._draw_bg, size=self._draw_bg)
        THEME.add_listener(self._draw_bg)
        
        self.title_lbl = CLabel(text=title, font_size=sp(10), color=get_color_from_hex(THEME.get('gray')))
        self.val = CLabel(text='--', font_size=sp(13), bold=True)
        self.add_widget(self.title_lbl)
        self.add_widget(self.val)
    
    def _draw_bg(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*get_color_from_hex(THEME.get('card2')))
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
    
    def set(self, v, c=None):
        self.val.text = str(v)
        if c: self.val.color = get_color_from_hex(c)

class AnimatedValue(CLabel):
    """带动画的数值Label"""
    target_value = NumericProperty(0)
    
    def __init__(self, fmt='{:.2f}', **kw):
        super().__init__(**kw)
        self.fmt = fmt
        self.current = 0
    
    def animate_to(self, val):
        anim = Animation(target_value=val, duration=0.3, t='out_cubic')
        anim.start(self)
        
    def on_target_value(self, *a):
        self.text = self.fmt.format(self.target_value)

# ==================== K线图组件 ====================
class KLineChart(Widget):
    """K线图和MACD柱状图"""
    data = ListProperty([])  # [(open, high, low, close), ...]
    macd_hist = ListProperty([])
    
    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(data=self._draw, macd_hist=self._draw, size=self._draw, pos=self._draw)
        THEME.add_listener(self._draw)
    
    def _draw(self, *a):
        self.canvas.clear()
        with self.canvas:
            Color(*get_color_from_hex(THEME.get('card2')))
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
        
        if not self.data or len(self.data) < 2:
            return
        
        # K线区域（上70%）
        k_height = self.height * 0.65
        k_y = self.y + self.height * 0.35
        
        # MACD区域（下30%）
        m_height = self.height * 0.30
        m_y = self.y + dp(5)
        
        n = len(self.data)
        bar_width = (self.width - dp(10)) / n * 0.8
        gap = (self.width - dp(10)) / n * 0.2
        
        # 计算K线范围
        all_prices = [p for d in self.data for p in d]
        pmin, pmax = min(all_prices), max(all_prices)
        if pmax == pmin: pmax = pmin + 0.01
        
        with self.canvas:
            # 绘制K线
            for i, (o, h, l, c) in enumerate(self.data):
                x = self.x + dp(5) + i * (bar_width + gap)
                
                # 颜色
                if c >= o:
                    Color(*get_color_from_hex(THEME.get('green')))
                else:
                    Color(*get_color_from_hex(THEME.get('red')))
                
                # 影线
                hy = k_y + (h - pmin) / (pmax - pmin) * k_height
                ly = k_y + (l - pmin) / (pmax - pmin) * k_height
                cx = x + bar_width / 2
                Line(points=[cx, ly, cx, hy], width=1)
                
                # 实体
                oy = k_y + (o - pmin) / (pmax - pmin) * k_height
                cy = k_y + (c - pmin) / (pmax - pmin) * k_height
                body_h = max(abs(cy - oy), dp(1))
                Rectangle(pos=(x, min(oy, cy)), size=(bar_width, body_h))
            
            # 绘制MACD柱状图
            if self.macd_hist:
                hmax = max(abs(h) for h in self.macd_hist) or 1
                mid_y = m_y + m_height / 2
                
                for i, h in enumerate(self.macd_hist[-n:]):
                    x = self.x + dp(5) + i * (bar_width + gap)
                    if h >= 0:
                        Color(*get_color_from_hex(THEME.get('green')))
                    else:
                        Color(*get_color_from_hex(THEME.get('red')))
                    
                    bar_h = abs(h) / hmax * (m_height / 2 - dp(2))
                    by = mid_y if h >= 0 else mid_y - bar_h
                    Rectangle(pos=(x, by), size=(bar_width, bar_h))

# ==================== 分时图组件 ====================
class ChartWidget(Widget):
    prices = ListProperty([])
    volumes = ListProperty([])
    
    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(prices=self._draw, volumes=self._draw, size=self._draw, pos=self._draw)
        THEME.add_listener(self._draw)
    
    def _draw(self, *a):
        self.canvas.clear()
        with self.canvas:
            Color(*get_color_from_hex(THEME.get('card2')))
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
        
        if len(self.prices) < 2:
            return
        
        # 价格区域（上70%）
        p_height = self.height * 0.7
        p_y = self.y + self.height * 0.3
        
        mn, mx = min(self.prices), max(self.prices)
        if mx == mn: mx += 0.01
        
        with self.canvas:
            # 网格
            Color(1,1,1,0.05)
            for i in range(1, 4):
                y = p_y + p_height * i / 4
                Line(points=[self.x+5, y, self.x+self.width-5, y])
            
            # 均价线
            avg = np.mean(self.prices)
            avg_y = p_y + (avg - mn) / (mx - mn) * p_height
            Color(*get_color_from_hex(THEME.get('yellow')), 0.5)
            Line(points=[self.x+5, avg_y, self.x+self.width-5, avg_y], dash_offset=5)
            
            # 价格线
            Color(*get_color_from_hex(THEME.get('blue')))
            pts = []
            for i, p in enumerate(self.prices):
                x = self.x + 5 + (self.width-10)*i/(len(self.prices)-1)
                y = p_y + (p-mn)/(mx-mn)*p_height
                pts.extend([x, y])
            if pts: Line(points=pts, width=1.5)
            
            # 成交量柱状图
            if self.volumes:
                v_height = self.height * 0.25
                v_y = self.y + dp(3)
                vmax = max(self.volumes) or 1
                bar_w = (self.width - 10) / len(self.volumes)
                
                for i, v in enumerate(self.volumes):
                    x = self.x + 5 + i * bar_w
                    h = v / vmax * v_height
                    # 量能颜色
                    if i > 0 and self.prices[i] >= self.prices[i-1]:
                        Color(*get_color_from_hex(THEME.get('green')), 0.6)
                    else:
                        Color(*get_color_from_hex(THEME.get('red')), 0.6)
                    Rectangle(pos=(x, v_y), size=(bar_w*0.8, h))

# ==================== 主页 ====================
class HomePage(BoxLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.orientation = 'vertical'
        self.spacing = dp(2)
        self.padding = 0  # 移除padding
        
        # 添加背景
        with self.canvas.before:
            Color(*get_color_from_hex(THEME.get('bg')))
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)
        
        self._build()
        Clock.schedule_once(lambda dt: self.refresh(), 1)
        THEME.add_listener(self._update_theme)
    
    def _upd_bg(self, *a):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
    
    def _update_theme(self):
        pass
    
    def _build(self):
        # 股票信息
        info = Card(size_hint_y=0.12, orientation='horizontal')
        left = BoxLayout(orientation='vertical', size_hint_x=0.55)
        self.name_lbl = CLabel(text='加载中...', font_size=sp(15), bold=True, halign='left')
        self.name_lbl.bind(size=lambda *a: setattr(self.name_lbl, 'text_size', self.name_lbl.size))
        self.code_lbl = CLabel(text=DATA.current, font_size=sp(10), color=get_color_from_hex(THEME.get('gray')), halign='left')
        self.code_lbl.bind(size=lambda *a: setattr(self.code_lbl, 'text_size', self.code_lbl.size))
        left.add_widget(self.name_lbl)
        left.add_widget(self.code_lbl)
        
        right = BoxLayout(orientation='vertical', size_hint_x=0.45)
        self.price_lbl = AnimatedValue(fmt='{:.2f}', font_size=sp(22), bold=True, halign='right')
        self.price_lbl.bind(size=lambda *a: setattr(self.price_lbl, 'text_size', self.price_lbl.size))
        self.change_lbl = CLabel(text='--', font_size=sp(12), halign='right')
        self.change_lbl.bind(size=lambda *a: setattr(self.change_lbl, 'text_size', self.change_lbl.size))
        right.add_widget(self.price_lbl)
        right.add_widget(self.change_lbl)
        info.add_widget(left)
        info.add_widget(right)
        self.add_widget(info)
        
        # 分时图 + 成交量
        self.chart = ChartWidget(size_hint_y=0.25)
        self.add_widget(self.chart)
        
        # 指标行1
        g1 = GridLayout(cols=4, spacing=dp(3), size_hint_y=0.10)
        self.rsi_box = InfoBox(title='RSI')
        self.macd_box = InfoBox(title='MACD')
        self.k_box = InfoBox(title='K')
        self.d_box = InfoBox(title='D')
        g1.add_widget(self.rsi_box)
        g1.add_widget(self.macd_box)
        g1.add_widget(self.k_box)
        g1.add_widget(self.d_box)
        self.add_widget(g1)
        
        # 指标行2
        g2 = GridLayout(cols=4, spacing=dp(3), size_hint_y=0.10)
        self.sup_box = InfoBox(title='支撑')
        self.res_box = InfoBox(title='压力')
        self.vol_box = InfoBox(title='量比')
        self.ma5_box = InfoBox(title='MA5')
        g2.add_widget(self.sup_box)
        g2.add_widget(self.res_box)
        g2.add_widget(self.vol_box)
        g2.add_widget(self.ma5_box)
        self.add_widget(g2)
        
        # 趋势预测
        trend_card = Card(size_hint_y=0.07, orientation='horizontal')
        self.trend_lbl = CLabel(text='趋势: --', font_size=sp(12))
        self.pattern_lbl = CLabel(text='形态: --', font_size=sp(12))
        trend_card.add_widget(self.trend_lbl)
        trend_card.add_widget(self.pattern_lbl)
        self.add_widget(trend_card)
        
        # 信号卡片
        sig = Card(size_hint_y=0.18, orientation='vertical')
        self.sig_lbl = CLabel(text='等待分析...', font_size=sp(18), bold=True, size_hint_y=0.45)
        pb = BoxLayout(size_hint_y=0.30, padding=[0, dp(2)])
        self.progress = ProgressBar(max=100)
        pb.add_widget(self.progress)
        self.score_lbl = CLabel(text='评分: 0/100', font_size=sp(10), color=get_color_from_hex(THEME.get('gray')), size_hint_y=0.25)
        sig.add_widget(self.sig_lbl)
        sig.add_widget(pb)
        sig.add_widget(self.score_lbl)
        self.add_widget(sig)
        
        # 持仓
        pos = Card(size_hint_y=0.08, orientation='horizontal')
        self.hold_lbl = CLabel(text=f"持仓: {DATA.position['hold']*100:.0f}%", font_size=sp(11))
        self.profit_lbl = CLabel(text=f"盈亏: {DATA.position['profit']:+.2f}%", font_size=sp(11))
        pos.add_widget(self.hold_lbl)
        pos.add_widget(self.profit_lbl)
        self.add_widget(pos)
        
        # 按钮
        btns = BoxLayout(size_hint_y=0.10, spacing=dp(6))
        rb = CButton(text='刷新', font_size=sp(12))
        rb.bind(on_release=lambda x: self.refresh())
        self.mon_btn = CButton(text='监控', font_size=sp(12), background_color=get_color_from_hex(THEME.get('green')))
        self.mon_btn.bind(on_release=lambda x: self.toggle_mon())
        btns.add_widget(rb)
        btns.add_widget(self.mon_btn)
        self.add_widget(btns)
        
        self.monitoring = False
    
    def refresh(self):
        def f():
            q = fetch_quote(DATA.current)
            p, v = fetch_prices(DATA.current)
            if q: DATA.stock_cache[DATA.current] = q
            if p: DATA.prices_cache[DATA.current] = (p, v)
            Clock.schedule_once(lambda dt: self.update(q, p, v), 0)
        threading.Thread(target=f, daemon=True).start()
    
    def update(self, q, p, v):
        if q:
            self.name_lbl.text = q['name']
            self.code_lbl.text = q['code']
            # 动画更新价格
            self.price_lbl.animate_to(q['price'])
            
            c = q['change']
            self.change_lbl.text = f"{'+' if c>=0 else ''}{c:.2f}%"
            col = THEME.get('green') if c>=0 else THEME.get('red')
            self.price_lbl.color = self.change_lbl.color = get_color_from_hex(col)
            
            # 检查预警
            alert_msg = check_alerts(q['code'], q['price'])
            if alert_msg:
                play_sound()
                vibrate()
        
        if p:
            self.chart.prices = p
            self.chart.volumes = v if v else []
            
            rsi = calc_rsi(p)
            macd, sig, hist = calc_macd(p)
            k, d, j = calc_kdj(p)
            ma5 = calc_ma(p, 5)
            sup, res = calc_sr(p)
            vol_r = calc_volume_ratio(v) if v else 1.0
            pat = detect_pattern(p)
            trend, _ = predict_trend(p, ma5, calc_ma(p, 10))
            
            self.rsi_box.set(rsi, THEME.get('green') if rsi<40 else (THEME.get('red') if rsi>60 else THEME.get('text')))
            self.macd_box.set(f"{hist:+.3f}", THEME.get('green') if hist>0 else THEME.get('red'))
            self.k_box.set(k, THEME.get('green') if k<30 else (THEME.get('red') if k>70 else THEME.get('text')))
            self.d_box.set(d)
            self.sup_box.set(sup, THEME.get('green'))
            self.res_box.set(res, THEME.get('red'))
            self.vol_box.set(vol_r, THEME.get('green') if vol_r<0.8 else THEME.get('text'))
            self.ma5_box.set(ma5, THEME.get('yellow'))
            
            self.trend_lbl.text = f"趋势: {trend}"
            self.pattern_lbl.text = f"形态: {pat}"
            
            if q:
                sc = calc_score(q['price'], sup, res, rsi, pat, k, vol_r)
                # 动画更新进度条
                anim = Animation(value=sc, duration=0.3)
                anim.start(self.progress)
                self.score_lbl.text = f"评分: {sc}/100"
                
                if sc >= 70:
                    self.sig_lbl.text = "买入信号!"
                    self.sig_lbl.color = get_color_from_hex(THEME.get('green'))
                    self._record_signal('买入', q['price'], sc)
                    play_sound()
                    vibrate()
                elif sc >= 55:
                    self.sig_lbl.text = "弱买入"
                    self.sig_lbl.color = get_color_from_hex(THEME.get('yellow'))
                elif sc <= 30:
                    self.sig_lbl.text = "观望/卖出"
                    self.sig_lbl.color = get_color_from_hex(THEME.get('red'))
                else:
                    self.sig_lbl.text = "暂无信号"
                    self.sig_lbl.color = get_color_from_hex(THEME.get('gray'))
        
        self.hold_lbl.text = f"持仓: {DATA.position['hold']*100:.0f}%"
        pcolor = THEME.get('green') if DATA.position['profit'] >= 0 else THEME.get('red')
        self.profit_lbl.text = f"盈亏: {DATA.position['profit']:+.2f}%"
        self.profit_lbl.color = get_color_from_hex(pcolor)
    
    def _record_signal(self, typ, price, score):
        now = datetime.now().strftime('%H:%M')
        if DATA.signals and DATA.signals[-1].get('time') == now and DATA.signals[-1].get('code') == DATA.current:
            return
        DATA.signals.append({
            'time': now, 'date': datetime.now().strftime('%m-%d'),
            'code': DATA.current, 'type': typ, 'price': price, 'score': score
        })
        if len(DATA.signals) > 100:
            DATA.signals = DATA.signals[-100:]
    
    def toggle_mon(self):
        self.monitoring = not self.monitoring
        if self.monitoring:
            self.mon_btn.text = '停止'
            self.mon_btn.background_color = get_color_from_hex(THEME.get('red'))
            Clock.schedule_interval(self._mon, 30)
        else:
            self.mon_btn.text = '监控'
            self.mon_btn.background_color = get_color_from_hex(THEME.get('green'))
            Clock.unschedule(self._mon)
    
    def _mon(self, dt):
        self.refresh()


# ==================== 自选股页 ====================
class WatchlistPage(BoxLayout):
    def __init__(self, on_select=None, **kw):
        super().__init__(**kw)
        self.orientation = 'vertical'
        self.padding = dp(6)
        self.spacing = dp(5)
        self.on_select = on_select
        
        hdr = BoxLayout(size_hint_y=None, height=dp(35))
        hdr.add_widget(CLabel(text='自选股', font_size=sp(15), bold=True))
        ab = CButton(text='+添加', size_hint_x=None, width=dp(60), font_size=sp(11))
        ab.bind(on_press=lambda x: self.add_stock())
        hdr.add_widget(ab)
        self.add_widget(hdr)
        
        sv = ScrollView()
        self.list_box = BoxLayout(orientation='vertical', spacing=dp(5), size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter('height'))
        sv.add_widget(self.list_box)
        self.add_widget(sv)
        
        self.cards = {}
        self._build_list()
        # 延迟启动更新，避免初始化时阻塞
        Clock.schedule_once(lambda dt: self.update_list(), 2)
        Clock.schedule_interval(self.update_list, 30)
    
    def _build_list(self):
        self.list_box.clear_widgets()
        self.cards = {}
        for code in DATA.watchlist:
            card = self._make_card(code)
            self.list_box.add_widget(card)
            self.cards[code] = card
    
    def _make_card(self, code):
        # 使用Button作为整个卡片，确保点击可靠
        btn = Button(size_hint_y=None, height=dp(55),
                    background_normal='', background_color=get_color_from_hex(THEME.get('card')))
        btn.code = code
        btn.bind(on_release=lambda x: self._select_stock(x.code))
        
        # 卡片内容（叠加在按钮上）
        content = BoxLayout(orientation='horizontal', padding=dp(8))
        
        left = BoxLayout(orientation='vertical', size_hint_x=0.5)
        name = CLabel(text=code, font_size=sp(13), bold=True, halign='left')
        name.bind(size=lambda *a, n=name: setattr(n, 'text_size', n.size))
        code_lbl = CLabel(text=code, font_size=sp(9), color=get_color_from_hex(THEME.get('gray')), halign='left')
        code_lbl.bind(size=lambda *a, c=code_lbl: setattr(c, 'text_size', c.size))
        left.add_widget(name)
        left.add_widget(code_lbl)
        
        right = BoxLayout(orientation='vertical', size_hint_x=0.5)
        price = CLabel(text='--', font_size=sp(14), bold=True, halign='right')
        price.bind(size=lambda *a, p=price: setattr(p, 'text_size', p.size))
        change = CLabel(text='--', font_size=sp(10), halign='right')
        change.bind(size=lambda *a, c=change: setattr(c, 'text_size', c.size))
        right.add_widget(price)
        right.add_widget(change)
        
        content.add_widget(left)
        content.add_widget(right)
        btn.add_widget(content)
        
        btn.name_lbl = name
        btn.price_lbl = price
        btn.change_lbl = change
        return btn
    
    def _select_stock(self, code):
        print(f"[DEBUG] Selected: {code}")
        DATA.current = code
        if self.on_select:
            self.on_select(code)
    
    def update_list(self, dt=None):
        def f():
            for code in DATA.watchlist:
                q = fetch_quote(code)
                if q: DATA.stock_cache[code] = q
            Clock.schedule_once(lambda dt: self._upd_cards(), 0)
        threading.Thread(target=f, daemon=True).start()
    
    def _upd_cards(self):
        for code, card in self.cards.items():
            q = DATA.stock_cache.get(code)
            if q:
                card.name_lbl.text = q['name']
                card.price_lbl.text = f"{q['price']:.2f}"
                c = q['change']
                card.change_lbl.text = f"{'+' if c>=0 else ''}{c:.2f}%"
                col = THEME.get('green') if c>=0 else THEME.get('red')
                card.price_lbl.color = card.change_lbl.color = get_color_from_hex(col)
    
    def add_stock(self):
        content = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(8))
        content.add_widget(CLabel(text='输入股票代码:', font_size=sp(12), size_hint_y=None, height=dp(25)))
        inp = TextInput(multiline=False, size_hint_y=None, height=dp(35))
        content.add_widget(inp)
        
        def save(btn):
            code = inp.text.strip()
            if code and code not in DATA.watchlist:
                DATA.watchlist.append(code)
                self._build_list()
            popup.dismiss()
        
        sb = CButton(text='添加', size_hint_y=None, height=dp(32))
        sb.bind(on_press=save)
        content.add_widget(sb)
        popup = Popup(title='添加自选', content=content, size_hint=(0.8, 0.28))
        popup.open()


# ==================== 历史信号页 ====================
class HistoryPage(BoxLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.orientation = 'vertical'
        self.padding = dp(6)
        self.spacing = dp(5)
        
        hdr = BoxLayout(size_hint_y=None, height=dp(35))
        hdr.add_widget(CLabel(text='历史信号', font_size=sp(15), bold=True))
        eb = CButton(text='导出', size_hint_x=None, width=dp(55), font_size=sp(11))
        eb.bind(on_press=lambda x: self.export())
        hdr.add_widget(eb)
        self.add_widget(hdr)
        
        sv = ScrollView()
        self.list_box = BoxLayout(orientation='vertical', spacing=dp(3), size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter('height'))
        sv.add_widget(self.list_box)
        self.add_widget(sv)
        
        Clock.schedule_interval(self.update, 5)
    
    def update(self, dt=None):
        self.list_box.clear_widgets()
        if not DATA.signals:
            self.list_box.add_widget(CLabel(text='暂无历史信号', font_size=sp(12), 
                                            color=get_color_from_hex(THEME.get('gray')), size_hint_y=None, height=dp(35)))
            return
        
        for s in reversed(DATA.signals[-40:]):
            row = BoxLayout(size_hint_y=None, height=dp(30), padding=dp(4))
            with row.canvas.before:
                Color(*get_color_from_hex(THEME.get('card')))
                RoundedRectangle(pos=row.pos, size=row.size, radius=[dp(4)])
            
            col = THEME.get('green') if s['type'] == '买入' else THEME.get('red')
            row.add_widget(CLabel(text=s['time'], font_size=sp(10), size_hint_x=0.18))
            row.add_widget(CLabel(text=s['code'], font_size=sp(10), size_hint_x=0.2))
            row.add_widget(CLabel(text=s['type'], font_size=sp(10), color=get_color_from_hex(col), size_hint_x=0.15))
            row.add_widget(CLabel(text=f"{s['price']:.2f}", font_size=sp(10), size_hint_x=0.25))
            row.add_widget(CLabel(text=f"{s['score']}", font_size=sp(10), size_hint_x=0.12))
            self.list_box.add_widget(row)
    
    def export(self):
        if export_signals_csv():
            popup = Popup(title='导出成功', content=CLabel(text='已导出到 signals_export.csv'), size_hint=(0.7, 0.2))
            popup.open()


# ==================== 设置页 ====================
class SettingsPage(BoxLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.orientation = 'vertical'
        self.padding = dp(10)
        self.spacing = dp(8)
        self._build()
    
    def _build(self):
        self.add_widget(CLabel(text='设置', font_size=sp(16), bold=True, size_hint_y=None, height=dp(35)))
        
        # 主题切换
        theme_row = BoxLayout(size_hint_y=None, height=dp(40))
        theme_row.add_widget(CLabel(text='深色主题', font_size=sp(13)))
        self.theme_switch = Switch(active=THEME.current=='dark')
        self.theme_switch.bind(active=self._toggle_theme)
        theme_row.add_widget(self.theme_switch)
        self.add_widget(theme_row)
        
        # 声音提醒
        sound_row = BoxLayout(size_hint_y=None, height=dp(40))
        sound_row.add_widget(CLabel(text='声音提醒', font_size=sp(13)))
        self.sound_switch = Switch(active=DATA.sound_enabled)
        self.sound_switch.bind(active=lambda w, v: setattr(DATA, 'sound_enabled', v))
        sound_row.add_widget(self.sound_switch)
        self.add_widget(sound_row)
        
        # 股票设置
        self.add_widget(CLabel(text='当前股票:', font_size=sp(12), size_hint_y=None, height=dp(22)))
        row = BoxLayout(size_hint_y=None, height=dp(35), spacing=dp(8))
        self.code_inp = TextInput(text=DATA.current, multiline=False)
        sb = CButton(text='切换', size_hint_x=None, width=dp(55), font_size=sp(12))
        sb.bind(on_press=lambda x: self._switch())
        row.add_widget(self.code_inp)
        row.add_widget(sb)
        self.add_widget(row)
        
        # 价格预警
        self.add_widget(CLabel(text='价格预警:', font_size=sp(12), size_hint_y=None, height=dp(22)))
        alert_row = BoxLayout(size_hint_y=None, height=dp(35), spacing=dp(5))
        alert_row.add_widget(CLabel(text='上限', font_size=sp(11), size_hint_x=0.15))
        self.high_inp = TextInput(hint_text='0', multiline=False, size_hint_x=0.3)
        alert_row.add_widget(self.high_inp)
        alert_row.add_widget(CLabel(text='下限', font_size=sp(11), size_hint_x=0.15))
        self.low_inp = TextInput(hint_text='0', multiline=False, size_hint_x=0.3)
        alert_row.add_widget(self.low_inp)
        self.add_widget(alert_row)
        
        set_alert_btn = CButton(text='设置预警', size_hint_y=None, height=dp(32), font_size=sp(12))
        set_alert_btn.bind(on_press=lambda x: self._set_alert())
        self.add_widget(set_alert_btn)
        
        # 模拟交易
        self.add_widget(CLabel(text='模拟交易:', font_size=sp(12), size_hint_y=None, height=dp(22)))
        trade_row = BoxLayout(size_hint_y=None, height=dp(35), spacing=dp(8))
        buy_btn = CButton(text='买入20%', background_color=get_color_from_hex(THEME.get('green')), font_size=sp(12))
        buy_btn.bind(on_press=lambda x: self._sim_buy())
        sell_btn = CButton(text='全部卖出', background_color=get_color_from_hex(THEME.get('red')), font_size=sp(12))
        sell_btn.bind(on_press=lambda x: self._sim_sell())
        trade_row.add_widget(buy_btn)
        trade_row.add_widget(sell_btn)
        self.add_widget(trade_row)
        
        # 导出交易日志
        export_btn = CButton(text='导出交易日志', size_hint_y=None, height=dp(32), font_size=sp(12),
                            background_color=get_color_from_hex(THEME.get('purple')))
        export_btn.bind(on_press=lambda x: self._export_trades())
        self.add_widget(export_btn)
        
        # 悬浮窗模式（电脑测试：按F键也可切换）
        self.add_widget(CLabel(text='悬浮窗模式:', font_size=sp(12), size_hint_y=None, height=dp(22)))
        float_btn = CButton(text='开启悬浮窗 (按F键)', size_hint_y=None, height=dp(35), font_size=sp(12),
                           background_color=get_color_from_hex('#0ea5e9'))
        float_btn.bind(on_press=lambda x: self._toggle_float())
        self.add_widget(float_btn)
        
        # 状态
        self.status_lbl = CLabel(text='', font_size=sp(11), color=get_color_from_hex(THEME.get('gray')), 
                                 size_hint_y=None, height=dp(25))
        self.add_widget(self.status_lbl)
        
        self.add_widget(BoxLayout())
    
    def _toggle_theme(self, w, v):
        THEME.toggle()
        
    def _switch(self):
        code = self.code_inp.text.strip()
        if code:
            DATA.current = code
            self.status_lbl.text = f'已切换: {code}'
    
    def _set_alert(self):
        try:
            high = float(self.high_inp.text) if self.high_inp.text else None
            low = float(self.low_inp.text) if self.low_inp.text else None
            DATA.alerts[DATA.current] = {'high': high, 'low': low}
            self.status_lbl.text = f'预警已设置: 上限={high}, 下限={low}'
        except:
            self.status_lbl.text = '请输入有效数字'
    
    def _sim_buy(self):
        q = DATA.stock_cache.get(DATA.current)
        if q:
            DATA.position['hold'] = min(DATA.position['hold'] + 0.2, 1.0)
            DATA.position['cost'] = q['price']
            DATA.trades.append({
                'time': datetime.now().strftime('%m-%d %H:%M'),
                'code': DATA.current, 'action': '买入',
                'price': q['price'], 'ratio': '20%', 'profit': ''
            })
            self.status_lbl.text = f"买入 {q['price']:.2f}"
    
    def _sim_sell(self):
        if DATA.position['hold'] > 0:
            q = DATA.stock_cache.get(DATA.current)
            if q:
                profit = (q['price'] - DATA.position['cost']) / DATA.position['cost'] * 100
                DATA.position['profit'] += profit
                DATA.trades.append({
                    'time': datetime.now().strftime('%m-%d %H:%M'),
                    'code': DATA.current, 'action': '卖出',
                    'price': q['price'], 'ratio': f'{DATA.position["hold"]*100:.0f}%', 
                    'profit': f'{profit:+.2f}%'
                })
                DATA.position['hold'] = 0
                self.status_lbl.text = f"卖出 盈亏: {profit:+.2f}%"
    
    def _export_trades(self):
        if export_trades_csv():
            self.status_lbl.text = '已导出 trades_export.csv'
    
    def _toggle_float(self):
        """切换悬浮窗模式 - 通过App访问MainApp"""
        app = App.get_running_app()
        if app and hasattr(app, 'main'):
            app.main.toggle_floating_mode()
            self.status_lbl.text = '已切换悬浮窗模式'


# ==================== 悬浮窗模式 ====================
class FloatingWidget(BoxLayout):
    """透明悬浮窗 - 只显示股价和信号"""
    
    def __init__(self, **kw):
        super().__init__(**kw)
        self.orientation = 'vertical'
        self.size_hint = (None, None)
        self.size = (dp(180), dp(100))
        self.padding = dp(8)
        self.spacing = dp(4)
        
        # 透明背景
        self._draw_bg()
        self.bind(pos=self._draw_bg, size=self._draw_bg)
        
        # 股票名称 + 价格
        top = BoxLayout(size_hint_y=0.4)
        self.name_lbl = CLabel(text='--', font_size=sp(12), bold=True, halign='left')
        self.name_lbl.bind(size=lambda *a: setattr(self.name_lbl, 'text_size', self.name_lbl.size))
        self.price_lbl = CLabel(text='--', font_size=sp(16), bold=True, halign='right')
        self.price_lbl.bind(size=lambda *a: setattr(self.price_lbl, 'text_size', self.price_lbl.size))
        top.add_widget(self.name_lbl)
        top.add_widget(self.price_lbl)
        self.add_widget(top)
        
        # 涨跌幅
        self.change_lbl = CLabel(text='--', font_size=sp(11), halign='right', size_hint_y=0.25)
        self.change_lbl.bind(size=lambda *a: setattr(self.change_lbl, 'text_size', self.change_lbl.size))
        self.add_widget(self.change_lbl)
        
        # 信号提示
        self.signal_lbl = CLabel(text='', font_size=sp(13), bold=True, size_hint_y=0.35)
        self.add_widget(self.signal_lbl)
        
        # 可拖拽
        self.dragging = False
        self.drag_offset = (0, 0)
    
    def _draw_bg(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            # 半透明黑色背景
            Color(0, 0, 0, 0.7)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
    
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.dragging = True
            self.drag_offset = (self.x - touch.x, self.y - touch.y)
            return True
        return super().on_touch_down(touch)
    
    def on_touch_move(self, touch):
        if self.dragging:
            self.x = touch.x + self.drag_offset[0]
            self.y = touch.y + self.drag_offset[1]
            return True
        return super().on_touch_move(touch)
    
    def on_touch_up(self, touch):
        self.dragging = False
        return super().on_touch_up(touch)
    
    def update(self, quote, signal_text='', signal_color=None):
        if quote:
            self.name_lbl.text = quote.get('name', '--')[:6]
            self.price_lbl.text = f"{quote['price']:.2f}"
            c = quote.get('change', 0)
            self.change_lbl.text = f"{'+' if c>=0 else ''}{c:.2f}%"
            col = THEME.get('green') if c>=0 else THEME.get('red')
            self.price_lbl.color = self.change_lbl.color = get_color_from_hex(col)
        
        self.signal_lbl.text = signal_text
        if signal_color:
            self.signal_lbl.color = get_color_from_hex(signal_color)


# ==================== 主应用 ====================
from kivy.uix.floatlayout import FloatLayout as FL

class MainApp(FL):
    floating_mode = BooleanProperty(False)
    
    def __init__(self, **kw):
        super().__init__(**kw)
        self._draw_bg()
        self.bind(pos=self._draw_bg, size=self._draw_bg)
        THEME.add_listener(self._draw_bg)
        
        # 主容器（垂直布局）
        main_box = BoxLayout(orientation='vertical', size_hint=(1, 1))
        
        # 内容区域
        self.content = BoxLayout()
        main_box.add_widget(self.content)
        
        # 页面
        self.home = HomePage()
        self.watch = WatchlistPage(on_select=self.on_stock_select)
        self.history = HistoryPage()
        self.settings = SettingsPage()
        self.pages = [self.home, self.watch, self.history, self.settings]
        self.current_page = 0
        
        # 显示首页
        self.content.add_widget(self.home)
        
        # 底部导航栏
        self.nav = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(2))
        with self.nav.canvas.before:
            Color(*get_color_from_hex(THEME.get('card')))
            self.nav_rect = Rectangle(pos=self.nav.pos, size=self.nav.size)
        self.nav.bind(pos=self._update_nav, size=self._update_nav)
        
        self.nav_btns = []
        tabs = [('行情', 0), ('自选', 1), ('信号', 2), ('设置', 3)]
        for text, idx in tabs:
            btn = Button(text=text, font_name=FONT, font_size=sp(14),
                        background_normal='', 
                        background_color=get_color_from_hex(THEME.get('card')))
            btn.bind(on_release=lambda x, i=idx: self.switch_page(i))
            self.nav_btns.append(btn)
            self.nav.add_widget(btn)
        
        main_box.add_widget(self.nav)
        self.add_widget(main_box)
        
        # 悬浮窗（使用FloatLayout叠加，不占用布局空间）
        self.floating = FloatingWidget()
        self.floating.opacity = 0
        self.add_widget(self.floating)
        
        self._highlight_nav(0)
    
    def _update_nav(self, widget, *a):
        self.nav_rect.pos = widget.pos
        self.nav_rect.size = widget.size
    
    def _highlight_nav(self, idx):
        for i, btn in enumerate(self.nav_btns):
            if i == idx:
                btn.color = get_color_from_hex(THEME.get('blue'))
            else:
                btn.color = get_color_from_hex(THEME.get('gray'))
    
    def switch_page(self, idx):
        if idx == self.current_page:
            if idx == 0:
                self.home.refresh()
            return
        self.content.clear_widgets()
        self.content.add_widget(self.pages[idx])
        self.current_page = idx
        self._highlight_nav(idx)
    
    def on_stock_select(self, code):
        """自选股点击回调"""
        print(f"[DEBUG] on_stock_select: {code}")
        DATA.current = code
        self.home.refresh()
        self.switch_page(0)  # 切换到行情页
    
    def _draw_bg(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            if self.floating_mode:
                # 悬浮模式：完全透明背景
                Color(0, 0, 0, 0)
            else:
                Color(*get_color_from_hex(THEME.get('bg')))
            Rectangle(pos=self.pos, size=self.size)
    
    def toggle_floating_mode(self):
        """切换悬浮窗模式"""
        self.floating_mode = not self.floating_mode
        
        if self.floating_mode:
            # 进入悬浮模式 - 隐藏内容和导航栏
            for child in self.children:
                if child != self.floating:
                    child.opacity = 0
                    child.disabled = True
            self.floating.opacity = 1
            self.floating.pos = (Window.width - self.floating.width - dp(10), 
                                 Window.height - self.floating.height - dp(50))
            Clock.schedule_interval(self._floating_update, 15)
        else:
            # 退出悬浮模式
            for child in self.children:
                if child != self.floating:
                    child.opacity = 1
                    child.disabled = False
            self.floating.opacity = 0
            Clock.unschedule(self._floating_update)
        
        self._draw_bg()
    
    def _floating_update(self, dt):
        """悬浮窗数据更新"""
        def f():
            q = fetch_quote(DATA.current)
            if q:
                DATA.stock_cache[DATA.current] = q
                p, v = fetch_prices(DATA.current)
                if p:
                    rsi = calc_rsi(p)
                    sup, res = calc_sr(p)
                    pat = detect_pattern(p)
                    k, _, _ = calc_kdj(p)
                    vol_r = calc_volume_ratio(v) if v else 1.0
                    sc = calc_score(q['price'], sup, res, rsi, pat, k, vol_r)
                    
                    # 判断信号
                    sig_text, sig_color = '', None
                    if sc >= 70:
                        sig_text = '📈 买入信号!'
                        sig_color = THEME.get('green')
                        play_sound()
                    elif sc <= 30:
                        sig_text = '📉 卖出信号'
                        sig_color = THEME.get('red')
                    
                    Clock.schedule_once(lambda dt: self.floating.update(q, sig_text, sig_color), 0)
        
        threading.Thread(target=f, daemon=True).start()


class T0App(App):
    def build(self):
        self.main = MainApp()
        
        # 监听键盘事件（电脑测试用，按F切换悬浮模式）
        Window.bind(on_keyboard=self._on_keyboard)
        
        return self.main
    
    def _on_keyboard(self, window, key, *args):
        # F键切换悬浮模式
        if key == 102:  # 'f'
            self.main.toggle_floating_mode()
            return True
        # ESC退出悬浮模式
        if key == 27:
            if self.main.floating_mode:
                self.main.toggle_floating_mode()
                return True
        return False
    
    def on_pause(self):
        """Android后台暂停时调用"""
        return True  # 返回True允许后台运行
    
    def on_resume(self):
        """Android从后台恢复时调用"""
        pass


if __name__ == '__main__':
    T0App().run()

