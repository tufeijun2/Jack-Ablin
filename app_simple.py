from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response
import pandas as pd
import yfinance as yf
from datetime import datetime
import pytz
import hashlib
import json
import os
import uuid
import random
import requests
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
from werkzeug.utils import secure_filename

# Flask应用配置
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your_secret_key_here')
CORS(app, supports_credentials=True)

# 加载环境变量
load_dotenv()

# 股票图片映射
STOCK_IMAGES = {
    'AAPL': 'https://logo.clearbit.com/apple.com',
    'MSFT': 'https://logo.clearbit.com/microsoft.com',
    'GOOGL': 'https://logo.clearbit.com/google.com',
    'AMZN': 'https://logo.clearbit.com/amazon.com',
    'META': 'https://logo.clearbit.com/meta.com',
    'TSLA': 'https://logo.clearbit.com/tesla.com',
    'NVDA': 'https://logo.clearbit.com/nvidia.com',
    'JPM': 'https://logo.clearbit.com/jpmorgan.com',
    'V': 'https://logo.clearbit.com/visa.com',
    'WMT': 'https://logo.clearbit.com/walmart.com'
}

# 数据库配置
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'trading_platform'
}

# 数据库连接函数
def get_db_connection():
    try:
        connection = mysql.connector.connect(**db_config)
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def format_datetime(dt_str):
    """将UTC时间字符串转换为美国东部时间并格式化为 DD-MMM-YY 格式"""
    try:
        # 解析UTC时间字符串
        dt = datetime.strptime(dt_str.split('+')[0], '%Y-%m-%d %H:%M:%S.%f')
        # 设置为UTC时区
        dt = pytz.UTC.localize(dt)
        # 转换为美国东部时间
        eastern = pytz.timezone('America/New_York')
        dt = dt.astimezone(eastern)
        # 格式化为 DD-MMM-YY 格式 (Windows 兼容格式)
        day = str(dt.day)  # 不使用 %-d
        return f"{day}-{dt.strftime('%b-%y')}"
    except Exception as e:
        try:
            # 尝试其他格式
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            dt = pytz.UTC.localize(dt)
            eastern = pytz.timezone('America/New_York')
            dt = dt.astimezone(eastern)
            day = str(dt.day)  # 不使用 %-d
            return f"{day}-{dt.strftime('%b-%y')}"
        except:
            return dt_str

def format_date_for_db(dt):
    """将日期格式化为数据库存储格式（UTC）"""
    if isinstance(dt, str):
        try:
            # 尝试解析 DD-MMM-YY 格式
            dt = datetime.strptime(dt, '%d-%b-%y')
        except:
            try:
                # 尝试解析其他格式
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            except:
                return None
    
    # 转换为UTC时间
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    else:
        dt = dt.astimezone(pytz.UTC)
    
    return dt.strftime('%Y-%m-%d %H:%M:%S.%f')

def get_real_time_price(symbol, asset_type=None):
    """获取实时价格"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        current_price = info.get('regularMarketPrice', 0)
        return current_price
    except Exception as e:
        print(f"Error getting price for {symbol}: {e}")
        return 0

def get_historical_data(symbol):
    """获取历史数据"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1mo")
        return hist.to_dict('records')
    except Exception as e:
        print(f"Error getting history for {symbol}: {e}")
        return []

def get_device_fingerprint():
    """获取设备指纹"""
    return str(uuid.uuid4())

def get_next_whatsapp_agent(device_fingerprint):
    """获取下一个WhatsApp代理"""
    # 简化的代理分配逻辑
    agents = [
        {"name": "Agent 1", "phone": "+1234567890"},
        {"name": "Agent 2", "phone": "+0987654321"},
        {"name": "Agent 3", "phone": "+1122334455"}
    ]
    
    # 基于设备指纹选择代理
    hash_value = hash(device_fingerprint) % len(agents)
    return agents[hash_value]

@app.route('/api/get-whatsapp-link', methods=['GET', 'POST'])
def get_whatsapp_link():
    """获取WhatsApp链接"""
    try:
        device_fingerprint = get_device_fingerprint()
        agent = get_next_whatsapp_agent(device_fingerprint)
        
        # 构建WhatsApp链接
        message = "你好！我想了解更多关于交易平台的信息。"
        whatsapp_url = f"https://wa.me/{agent['phone']}?text={requests.utils.quote(message)}"
        
        return jsonify({
            'success': True,
            'whatsapp_url': whatsapp_url,
            'agent': agent,
            'device_fingerprint': device_fingerprint
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/')
def index():
    """主页"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>交易平台</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .card { background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .button { background: #007bff; color: white; padding: 12px 24px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
            .button:hover { background: #0056b3; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
            .stock-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .price { font-size: 24px; font-weight: bold; color: #28a745; }
            .symbol { font-size: 18px; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 交易平台</h1>
                <p>实时股票数据、交易分析和投资策略</p>
            </div>
            
            <div class="grid">
                <div class="card">
                    <h2>📊 实时股票价格</h2>
                    <div id="stockPrices"></div>
                    <button class="button" onclick="loadStockPrices()">刷新价格</button>
                </div>
                
                <div class="card">
                    <h2>💬 WhatsApp 咨询</h2>
                    <p>需要帮助？点击下方按钮联系我们的专业顾问</p>
                    <button class="button" onclick="getWhatsAppLink()">联系顾问</button>
                    <div id="whatsappResult"></div>
                </div>
                
                <div class="card">
                    <h2>📈 热门股票</h2>
                    <div id="popularStocks"></div>
                </div>
            </div>
        </div>
        
        <script>
            const stocks = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'];
            
            async function loadStockPrices() {
                const container = document.getElementById('stockPrices');
                container.innerHTML = '正在加载...';
                
                try {
                    const promises = stocks.map(symbol => 
                        fetch(`/api/price?symbol=${symbol}`).then(r => r.json())
                    );
                    
                    const results = await Promise.all(promises);
                    let html = '';
                    
                    results.forEach(result => {
                        html += `
                            <div class="stock-card">
                                <div class="symbol">${result.symbol}</div>
                                <div class="price">$${result.price}</div>
                            </div>
                        `;
                    });
                    
                    container.innerHTML = html;
                } catch (error) {
                    container.innerHTML = `错误: ${error.message}`;
                }
            }
            
            async function getWhatsAppLink() {
                const result = document.getElementById('whatsappResult');
                result.innerHTML = '正在获取链接...';
                
                try {
                    const response = await fetch('/api/get-whatsapp-link', {
                        method: 'POST'
                    });
                    const data = await response.json();
                    
                    if (data.success) {
                        result.innerHTML = `
                            <p>✅ 链接已生成</p>
                            <a href="${data.whatsapp_url}" target="_blank" class="button">
                                打开 WhatsApp
                            </a>
                        `;
                    } else {
                        result.innerHTML = `错误: ${data.error}`;
                    }
                } catch (error) {
                    result.innerHTML = `错误: ${error.message}`;
                }
            }
            
            // 页面加载时自动加载股票价格
            loadStockPrices();
        </script>
    </body>
    </html>
    """

@app.route('/api/price')
def api_price():
    """股票价格API"""
    symbol = request.args.get('symbol', 'AAPL')
    price = get_real_time_price(symbol)
    return jsonify({'symbol': symbol, 'price': price})

@app.route('/api/history')
def api_history():
    """历史数据API"""
    symbol = request.args.get('symbol', 'AAPL')
    data = get_historical_data(symbol)
    return jsonify({'symbol': symbol, 'data': data})

@app.route('/api/test')
def api_test():
    """测试API"""
    return jsonify({'message': 'API运行正常！', 'status': 'success'})

if __name__ == '__main__':
    print("🚀 启动交易平台服务器...")
    print("📱 访问地址: http://localhost:8080")
    print("🔧 这是一个简化版本，包含核心功能")
    app.run(debug=True, host='0.0.0.0', port=8080) 