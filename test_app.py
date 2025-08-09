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
from flask_cors import CORS

# Flask应用配置
app = Flask(__name__)
app.secret_key = 'test_secret_key_here'
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

@app.route('/')
def index():
    """主页"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>交易平台测试</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 800px; margin: 0 auto; }
            .header { background: #f0f0f0; padding: 20px; border-radius: 5px; }
            .test-section { margin: 20px 0; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }
            .button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 3px; cursor: pointer; }
            .result { margin-top: 10px; padding: 10px; background: #f8f9fa; border-radius: 3px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 交易平台测试页面</h1>
                <p>这是一个简化的测试版本，用于验证基本功能</p>
            </div>
            
            <div class="test-section">
                <h2>📊 股票价格测试</h2>
                <button class="button" onclick="testStockPrice()">测试股票价格</button>
                <div id="stockResult" class="result"></div>
            </div>
            
            <div class="test-section">
                <h2>📈 历史数据测试</h2>
                <button class="button" onclick="testHistory()">测试历史数据</button>
                <div id="historyResult" class="result"></div>
            </div>
            
            <div class="test-section">
                <h2>🔧 API测试</h2>
                <button class="button" onclick="testAPI()">测试API</button>
                <div id="apiResult" class="result"></div>
            </div>
        </div>
        
        <script>
            async function testStockPrice() {
                const result = document.getElementById('stockResult');
                result.innerHTML = '正在获取股票价格...';
                
                try {
                    const response = await fetch('/api/price?symbol=AAPL');
                    const data = await response.json();
                    result.innerHTML = `<strong>AAPL 价格:</strong> $${data.price}`;
                } catch (error) {
                    result.innerHTML = `错误: ${error.message}`;
                }
            }
            
            async function testHistory() {
                const result = document.getElementById('historyResult');
                result.innerHTML = '正在获取历史数据...';
                
                try {
                    const response = await fetch('/api/history?symbol=AAPL');
                    const data = await response.json();
                    result.innerHTML = `<strong>历史数据:</strong> ${data.data.length} 条记录`;
                } catch (error) {
                    result.innerHTML = `错误: ${error.message}`;
                }
            }
            
            async function testAPI() {
                const result = document.getElementById('apiResult');
                result.innerHTML = '正在测试API...';
                
                try {
                    const response = await fetch('/api/test');
                    const data = await response.json();
                    result.innerHTML = `<strong>API状态:</strong> ${data.message}`;
                } catch (error) {
                    result.innerHTML = `错误: ${error.message}`;
                }
            }
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
    print("🚀 启动测试服务器...")
    print("📱 访问地址: http://localhost:8080")
    print("🔧 这是一个简化的测试版本")
    app.run(debug=True, host='0.0.0.0', port=8080) 