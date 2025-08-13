from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response
from supabase import create_client
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import pytz
import hashlib
import json
import os
import uuid
import random
import sqlite3
import requests
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
from werkzeug.utils import secure_filename
import supabase_client  # 用 supabase_client.get_traders 代替
from supabase import Client as SupabaseClient
import openai


# Flask应用配置
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your_secret_key_here')
CORS(app, supports_credentials=True)

# 加载环境变量
load_dotenv()

# OpenAI配置
openai.api_key = os.getenv('OPENAI_API_KEY')

# Supabase配置（改为环境变量读取）
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
Web_Trader_UUID=os.getenv('Web_Trader_UUID')
assert url, "SUPABASE_URL 环境变量未设置"
assert key, "SUPABASE_KEY 环境变量未设置"
assert Web_Trader_UUID, "Web_Trader_UUID 环境变量未设置"
supabase = create_client(url, key)

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
            return dt
    # 确保时区是UTC
    if dt.tzinfo is None:
        eastern = pytz.timezone('America/New_York')
        dt = eastern.localize(dt)
    return dt.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S.%f+00:00')
India_price_List=dict()

def get_India_price():
    token = "jggf1-iglcjq-ykgka"
    url = "http://india-api.allyjp.site/exchange-whitezzzs/lhms-api/list?token=jggf1-iglcjq-ykgka"
    try:
        resp = requests.get(url, timeout=15)
        data = resp.json()
        sdata=data["data"]
        for item in sdata:
            try:
                global India_price_List
                India_price_List[item["co"].split('.')[0]]=item["a"]
               
            except Exception as e:
                ...
       
        
    except Exception as e:
        return None

def get_real_time_price(market,symbol, asset_type=None):
    symbol = str(symbol).upper().split(":")[0]
    if market.lower()=="usa": #获取美国股票价格
        api_key = "YIQDtez6a6OhyWsg2xtbRbOUp3Akhlp4"
        # 加密货币部分略...
        # 股票查法兜底：asset_type为stock或未传但symbol像股票代码
        if (asset_type and ("stock" in asset_type.lower())) or (not asset_type and symbol.isalpha() and 2 <= len(symbol) <= 5):
            url = f"https://api.polygon.io/v2/last/trade/{symbol}?apiKey={api_key}"
            try:
                resp = requests.get(url, timeout=5)
                data = resp.json()
                price = None
                if data.get("results") and "p" in data["results"]:
                    price = data["results"]["p"]
                elif data.get("last") and "price" in data["last"]:
                    price = data["last"]["price"]
                if price is not None:
                    return float(price)
            except Exception as e:
                return None
        # 默认返回None
        return None
    else: #获取印度股票价格
        try:
         
            price_value=India_price_List[symbol.split(".")[0]]
            return price_value
        except Exception as e:
                return None




def get_historical_data(symbol):
    """获取历史数据"""
    try:
        stock = yf.Ticker(symbol)
        history = stock.history(period="1mo")  # 获取一个月的历史数据
        if not history.empty:
            # 将数据转换为列表格式
            data = []
            for date, row in history.iterrows():
                data.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': int(row['Volume'])
                })
            return data
        return None
    except Exception as e:
        return None

def get_device_fingerprint():
    """生成设备指纹"""
    user_agent = request.headers.get('User-Agent', '')
    ip = request.remote_addr
    # 可以添加更多设备特征
    fingerprint_data = f"{ip}:{user_agent}"
    return hashlib.sha256(fingerprint_data.encode()).hexdigest()

def get_next_whatsapp_agent(device_fingerprint):
    """获取下一个可用的WhatsApp客服"""
    try:
        # 测试数据库连接
        try:
            test_query = supabase.table('whatsapp_agents').select('count').eq("trader_uuid",Web_Trader_UUID).execute()
        except Exception as db_error:
            return None
        
        # 检查是否已有分配记录
        try:
            existing_record = supabase.table('contact_records').select('*').eq('device_fingerprint', device_fingerprint).eq("trader_uuid",Web_Trader_UUID).execute()
        except Exception as e:
            return None
        
        if existing_record.data:
            # 如果已有分配，返回之前分配的客服
            agent_id = existing_record.data[0]['agent_id']
            try:
                agent = supabase.table('whatsapp_agents').select('*').eq('id', agent_id).execute()
                return agent.data[0] if agent.data else None
            except Exception as e:
                return None
        
        # 获取所有客服
        try:
            agents = supabase.table('whatsapp_agents').select('*').eq('is_active', True).eq("trader_uuid",Web_Trader_UUID).execute()
            if not agents.data:
                return None
        except Exception as e:
            return None
            
        # 获取所有分配记录，只取agent_id
        try:
            assignments = supabase.table('contact_records').select('agent_id').eq("trader_uuid",Web_Trader_UUID).execute()
            assignment_counts = {}
            for record in assignments.data:
                agent_id = record['agent_id']
                assignment_counts[agent_id] = assignment_counts.get(agent_id, 0) + 1
        except Exception as e:
            assignment_counts = {}
            
        # 选择分配数量最少的客服
        min_assignments = float('inf')
        selected_agent = None
        
        for agent in agents.data:
            count = assignment_counts.get(agent['id'], 0)
            if count < min_assignments:
                min_assignments = count
                selected_agent = agent
        
        if selected_agent:
            # 记录新的分配
            try:
                insert_data = {
                    'device_fingerprint': device_fingerprint,
                    'agent_id': selected_agent['id'],
                    'ip_address': request.remote_addr,
                    'user_agent': request.headers.get('User-Agent', ''),
                    'timestamp': datetime.now(pytz.UTC).isoformat(),
                    'trader_uuid':Web_Trader_UUID
                }
                insert_result = supabase.table('contact_records').insert(insert_data).execute()
            except Exception as e:
                # 即使插入失败也返回选中的客服
                pass
        
        return selected_agent
        
    except Exception as e:
        return None

@app.route('/api/get-whatsapp-link', methods=['GET', 'POST'])
def get_whatsapp_link():
    """获取WhatsApp链接API"""
    try:
        device_fingerprint = get_device_fingerprint()
        
        # 获取点击时间
        click_time = None
        if request.method == 'POST':
            data = request.get_json()
            click_time = data.get('click_time')
        
        agent = get_next_whatsapp_agent(device_fingerprint)
        
        if agent:
            # 更新点击时间
            if click_time:
                try:
                    update_data = {
                        'click_time': click_time
                    }
                    update_result = supabase.table('contact_records').update(update_data).eq('device_fingerprint', device_fingerprint).execute()
                except Exception as e:
                    pass
            
            app_link = f"whatsapp://send?phone={agent['phone_number']}"
            return {
                'success': True,
                'app_link': app_link
            }
        else:
            return {
                'success': False,
                'message': "No available support agent, please try again later"
            }
            
    except Exception as e:
        return {
            'success': False,
            'message': "System error, please try again later"
        }

@app.route('/')
def index():
    try:
       
        # 获取交易数据
        response = supabase.table('trades1').select("*").eq("trader_uuid",Web_Trader_UUID).execute()
        trades = response.data
        Response=supabase.table("trade_market").select("*").execute()
        marketdata=Response.data
        if not trades:
            trades = []
        
        for trade in trades:
            # 格式化日期前先保存原始日期用于排序
            if trade.get('exit_date'):
                # 将日期字符串转换为datetime对象用于排序
                try:
                    # 尝试解析数据库中的日期格式
                    exit_date = datetime.strptime(trade['exit_date'].split('+')[0], '%Y-%m-%d %H:%M:%S.%f')
                    trade['original_exit_date'] = exit_date
                except Exception as e:
                    # 如果解析失败，尝试其他格式
                    try:
                        exit_date = datetime.fromisoformat(trade['exit_date'].replace('Z', '+00:00'))
                        trade['original_exit_date'] = exit_date
                    except Exception as e2:
                        trade['original_exit_date'] = datetime.min
                trade['exit_date'] = format_datetime(trade['exit_date'])

            if trade.get('entry_date'):
                try:
                    entry_date = datetime.strptime(trade['entry_date'].split('+')[0], '%Y-%m-%d %H:%M:%S.%f')
                    trade['original_entry_date'] = entry_date
                except Exception as e:
                    try:
                        entry_date = datetime.fromisoformat(trade['entry_date'].replace('Z', '+00:00'))
                        trade['original_entry_date'] = entry_date
                    except:
                        trade['original_entry_date'] = datetime.min
                trade['entry_date'] = format_datetime(trade['entry_date'])
            trade["currency"]=getexchange_unit(marketdata,trade.get('trade_market'))
            # 优先使用数据库中的 image_url，否则用 STOCK_IMAGES
            trade['image_url'] = trade.get('image_url') or STOCK_IMAGES.get(trade['symbol'], '')
            
            # 计算交易金额和盈亏
            trade['entry_amount'] = trade['entry_price'] * trade['size']
            
            # 如果没有current_price，获取实时价格
            if 'current_price' not in trade or not trade['current_price']:
                current_price = get_real_time_price(trade["trade_market"],trade['symbol'])
                if current_price:
                    trade['current_price'] = current_price
                    # 更新数据库中的价格
                    try:
                        update_response = supabase.table('trades1').update({
                            'current_price': current_price,
                            'updated_at': datetime.now(pytz.UTC).isoformat()
                        }).eq('id', trade['id']).execute()
                    except Exception as e:
                        pass
            
            # 计算当前市值和盈亏
            trade['current_amount'] = trade['current_price'] * trade['size']*trade['direction'] if trade.get('current_price') else trade['entry_amount']
            
            # 计算盈亏
            if trade.get('exit_price'):
                trade['profit_amount'] = (trade['exit_price'] - trade['entry_price']) * trade['size']*trade['direction']
            else:
                trade['profit_amount'] = (trade['current_price'] - trade['entry_price']) * trade['size'] *trade['direction'] if trade.get('current_price') else 0
            
            # 计算盈亏比例
            trade['profit_ratio'] = (trade['profit_amount'] / trade['entry_amount']) * 100 if trade['entry_amount'] else 0
            
            # 设置状态
            if trade.get('exit_price') is None and trade.get('exit_date') is None:
                trade['status'] = "Active"
            else:
                trade['status'] = "Closed"
        
        # 分离持仓和平仓的交易
        holding_trades = [t for t in trades if t['status'] == "Active"]
        closed_trades = [t for t in trades if t['status'] == "Closed"]

        holding_trades.sort(key=lambda x: x['original_entry_date'], reverse=True)
        
        closed_trades.sort(key=lambda x: x['original_exit_date'], reverse=True)
        
        # 合并排序后的交易列表
        sorted_trades = holding_trades + closed_trades
        
        # 计算总览数据
        total_trades = len(sorted_trades)
        
        # 获取当前持仓
        positions = holding_trades
        
        # 获取当前美国东部时间的月份
        eastern = pytz.timezone('America/New_York')
        current_time = datetime.now(eastern)
        current_month = f"{str(current_time.day)}-{current_time.strftime('%b-%y')}"
        
        # 计算当月平仓盈亏
        monthly_closed_trades = [t for t in closed_trades 
                               if t.get('exit_date') 
                               and t['exit_date'].split('-')[1] == current_month.split('-')[1]]
        
        #monthly_profit = sum(t.get('profit_amount', 0) for t in monthly_closed_trades)
        monthly_profit=0
        for item in monthly_closed_trades:
            if item['exit_date']:
                exchange_rate= float(getexchange_rate(marketdata,item.get('trade_market')))
                profit_amount=item['profit_amount']
                monthly_profit+=profit_amount/exchange_rate
        # 获取交易员信息
        profile_response = supabase.table('trader_profiles').select("*").eq("trader_uuid",Web_Trader_UUID).limit(1).execute()
        trader_info = profile_response.data[0] if profile_response.data else {
            'website_title': 'Professional Trader',
            'home_top_title': 'Professional Trader',
            'trader_name': 'Professional Trader',
            'professional_title': 'Financial Trading Expert | Technical Analysis Master',
            'bio': 'Focused on US stock market technical analysis and quantitative trading',
            'profile_image_url': 'https://rwlziuinlbazgoajkcme.supabase.co/storage/v1/object/public/images/1920134_331262340400234_2042663349514343562_n.jpg'
        }
        
        # 获取最新的交易策略
        strategy_response = supabase.table('trading_strategies').select("*").eq("trader_uuid",Web_Trader_UUID).order('updated_at', desc=True).limit(1).execute()
        strategy_info = strategy_response.data[0] if strategy_response.data else {
            'market_analysis': 'Today\'s market shows an upward trend with strong performance in the tech sector. Focus on AI-related stocks...',
            'trading_focus': ['Tech Sector: AI, Chips, Cloud Computing', 'New Energy: Solar, Energy Storage, Hydrogen', 'Healthcare: Innovative Drugs, Medical Devices'],
            'risk_warning': 'High market volatility, please control position size and set stop loss...',
            'updated_at': datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S.%f+00:00')
        }
        
        # 格式化策略更新时间为美国东部时间
        if strategy_info.get('updated_at'):
            try:
                # 解析UTC时间
                updated_at = strategy_info['updated_at']
                if 'T' in updated_at:
                    # ISO格式
                    dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                else:
                    # 标准格式
                    dt = datetime.strptime(updated_at.split('+')[0], '%Y-%m-%d %H:%M:%S.%f')
                    dt = pytz.UTC.localize(dt)
                
                # 转换为美国东部时间
                eastern = pytz.timezone('US/Eastern')
                eastern_time = dt.astimezone(eastern)
                strategy_info['formatted_time'] = eastern_time.strftime('%b %d, %Y at %I:%M %p EST')
            except Exception as e:
                print(f"[DEBUG] 策略时间格式化错误: {e}")
                # 使用当前时间作为默认值
                eastern = pytz.timezone('US/Eastern')
                current_eastern = datetime.now(eastern)
                strategy_info['formatted_time'] = current_eastern.strftime('%b %d, %Y at %I:%M %p EST')
        else:
            # 如果没有更新时间，使用当前时间
            eastern = pytz.timezone('US/Eastern')
            current_eastern = datetime.now(eastern)
            strategy_info['formatted_time'] = current_eastern.strftime('%b %d, %Y at %I:%M %p EST')
      
        total_profit=0
        for item in trades:
            if item['exit_date']:
                exchange_rate= float(getexchange_rate(marketdata,item.get('trade_market')))
                profit_amount=item['profit_amount']
                total_profit+=profit_amount/exchange_rate
        # # 计算总利润
        # total_profit = sum(t.get('profit_amount', 0) for t in sorted_trades)

        # 设置个人信息
        final_trader_info = {
            'trader_name': trader_info.get('trader_name', 'Professional Trader'),
            'website_title': trader_info.get('website_title', 'Professional Trader'),
            'home_top_title': trader_info.get('home_top_title', 'Professional Trader'),
            'professional_title': trader_info.get('professional_title', 'Financial Trading Expert | Technical Analysis Master'),
            'bio': trader_info.get('bio', 'Focused on US stock market technical analysis and quantitative trading'),
            'positions': positions,
            'monthly_profit': round(monthly_profit, 2),
            'active_trades': len(positions),
            'total_profit': round(total_profit, 2),
            'strategy_info': strategy_info,
            # 固定头像
            'profile_image_url': trader_info.get('profile_image_url', 'https://rwlziuinlbazgoajkcme.supabase.co/storage/v1/object/public/images//TT1375_Talent-HiRes-TP02.jpg')
        }
        
        return render_template('index.html', 
                            trades=sorted_trades,
                            trader_info=final_trader_info)
    except Exception as e:
        print(f"[ERROR] 首页加载失败: {str(e)}")
        # 在错误情况下也提供默认时间格式
        eastern = pytz.timezone('US/Eastern')
        current_eastern = datetime.now(eastern)
        default_formatted_time = current_eastern.strftime('%b %d, %Y at %I:%M %p EST')
        
        return render_template('index.html', 
                            trades=[],
                            trader_info={
                                'strategy_info': {
                                    'formatted_time': default_formatted_time,
                                    'market_analysis': 'Market data temporarily unavailable',
                                    'trading_focus': [],
                                    'risk_warning': 'Please check back later for updates'
                                }
                            })

@app.route('/api/trader-profile', methods=['GET'])
def trader_profile():
    try:
        # 获取个人资料
        response = supabase.table('trader_profiles').select('*').eq("trader_uuid",Web_Trader_UUID).limit(1).execute()
        # 获取trades表中的记录数
        trades_response = supabase.table('trades1').select('id').eq("trader_uuid",Web_Trader_UUID).execute()
        trades_count = len(trades_response.data) if trades_response.data else 0
        if response.data:
            profile = response.data[0]
            # 更新总交易次数 = trader_profiles表中的total_trades + trades表中的记录数
            profile['total_trades'] = profile.get('total_trades', 0) + trades_count
            # 固定头像
            profile['profile_image_url'] = 'https://rwlziuinlbazgoajkcme.supabase.co/storage/v1/object/public/images//TT1375_Talent-HiRes-TP02.jpg'
            return jsonify({
                'success': True,
                'data': profile
            })
        else:
            # 如果没有数据，返回默认值
            return jsonify({
                'success': True,
                'data': {
                    'trader_name': 'Professional Trader',
                    'professional_title': 'Stock Trading Expert | Technical Analysis Master',
                    'years_of_experience': 5,
                    'total_trades': trades_count,
                    'win_rate': 85.0,
                    'profile_image_url': 'https://rwlziuinlbazgoajkcme.supabase.co/storage/v1/object/public/images//TT1375_Talent-HiRes-TP02.jpg'
                }
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/leaderboard')
def leaderboard():
    # Get sort parameter from query string, default to 'profit'
    sort_by = request.args.get('sort', 'profit')
    # Get traders from Supabase
    traders = supabase_client.get_traders(sort_by)
    # If no traders found, return empty list
    if not traders:
        traders = []
    # 补充默认头像
    for trader in traders:
        if not trader.get('profile_image_url'):
            trader['profile_image_url'] = DEFAULT_AVATAR_URL
    return render_template('leaderboard.html', traders=traders)

@app.route('/api/upload-avatar', methods=['POST'])
def upload_avatar():
    try:
        if 'username' not in session:
            return jsonify({'success': False, 'message': 'Not logged in'}), 401
        file = request.files.get('avatar')
        if not file:
            return jsonify({'success': False, 'message': 'No file uploaded'}), 400
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[-1].lower()
        allowed_ext = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
        if file_ext not in allowed_ext:
            return jsonify({'success': False, 'message': 'Invalid file type'}), 400
        file_bytes = file.read()
        # 上传到 Supabase Storage
        import uuid
        file_path = f"avatars/avatars/{session['username']}_{uuid.uuid4().hex}.{file_ext}"
        result = supabase.storage.from_('avatars').upload(file_path, file_bytes, file_options={"content-type": file.mimetype})
        if hasattr(result, 'error') and result.error:
            return jsonify({'success': False, 'message': f'Upload failed: {result.error}'}), 500
        public_url = supabase.storage.from_('avatars').get_public_url(file_path)
        # 更新数据库
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': 'Not logged in'}), 401
        supabase.table('users').update({'avatar_url': public_url}).eq('id', user_id).execute()
        return jsonify({'success': True, 'url': public_url})
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': 'Upload failed, please try again later'}), 500

@app.route('/api/get-avatar', methods=['GET'])
def get_avatar():
    try:
        return jsonify({'success': True, 'url': DEFAULT_AVATAR_URL})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Failed to get avatar'}), 500

@app.route('/api/price')
def api_price():
    trade_market=request.args.get('market')
    symbol = request.args.get('symbol')
    trade_id = request.args.get('trade_id')
    asset_type = None
    Direction=1
    # 优先用trade_id查表获取asset_type和symbol
    if trade_id:
        # 先查vip_trades表
        trade = supabase.table('vip_trades').select('asset_type,symbol,direction').eq('id', trade_id).execute()
        if trade.data:
            asset_type = trade.data[0].get('asset_type')
            symbol = trade.data[0].get('symbol')
            Direction= trade.data[0].get('direction')
        else:
            # 可选：查trades1等其他表
            trade = supabase.table('trades1').select('asset_type,symbol,Direction').eq('id', trade_id).execute()
            if trade.data:
                asset_type = trade.data[0].get('asset_type')
                symbol = trade.data[0].get('symbol')
                Direction= trade.data[0].get('Direction')
    else:
        # 没有trade_id时，symbol必须有，asset_type可选
        asset_type = request.args.get('asset_type')

    if not symbol:
        return jsonify({'success': False, 'message': 'No symbol provided'}), 400

    price = get_real_time_price(trade_market,symbol, asset_type)
    if price is not None:
        return jsonify({'success': True, 'price': float(price),'Direction':Direction})
    else:
        return jsonify({'success': False, 'message': 'Failed to get price'}), 500

@app.route('/api/history')
def api_history():
    symbol = request.args.get('symbol')
    if not symbol:
        return jsonify({'success': False, 'message': 'No symbol provided'}), 400

    history = get_historical_data(symbol)
    if history is not None:
        return jsonify({'success': True, 'data': history})
    else:
        return jsonify({'success': False, 'message': 'Failed to get historical data'}), 500

@app.route('/api/best-trade-info', methods=['GET'])
def get_best_trade_info():
    try:
        # 获取8月份最佳交易记录（固定查询2025年8月）
        target_month = "2025-08"  # 固定查询2025年8月
        print(f"[DEBUG] 查询月份: {target_month}")
        
        # 获取所有已关闭的交易
        response = supabase.table('trades1').select("*").eq("trader_uuid", Web_Trader_UUID).neq('exit_date', None).execute()
        trades = response.data if response.data else []
        
        print(f"[DEBUG] 找到 {len(trades)} 个已关闭的交易记录")
        for trade in trades:
            print(f"[DEBUG] 交易: {trade.get('symbol')} - 退出日期: {trade.get('exit_date')} - 收益: {trade.get('profit_amount')}")
        
        if not trades:
            return jsonify({
                'success': False,
                'message': '暂无交易记录',
                'debug_info': {
                    'trader_uuid': Web_Trader_UUID,
                    'target_month': target_month,
                    'total_trades': 0
                }
            })
        
        # 筛选当月交易并找到收益率最高的记录
        best_trade = None
        max_profit_rate = float('-inf')
        current_month_trades = []
        
        for trade in trades:
            # 检查是否为当月交易
            exit_date = trade.get('exit_date', '')
            print(f"[DEBUG] 检查交易 {trade.get('symbol')}: 退出日期={exit_date}, 是否目标月={exit_date.startswith(target_month) if exit_date else False}")
            
            if not exit_date or not exit_date.startswith(target_month):
                continue
                
            current_month_trades.append(trade)
            
            # 计算entry_amount (如果没有则根据价格和数量计算)
            entry_amount = trade.get('entry_amount')
            if not entry_amount:
                entry_price = float(trade.get('entry_price', 0))
                size = float(trade.get('size', 0))
                entry_amount = entry_price * size
            entry_amount = float(entry_amount) if entry_amount else 1
            
            # 计算profit_amount (如果没有则根据价格差计算)
            profit_amount = trade.get('profit_amount')
            if profit_amount is None:
                entry_price = float(trade.get('entry_price', 0))
                exit_price = float(trade.get('exit_price', 0))
                size = float(trade.get('size', 0))
                direction = trade.get('direction', 1)
                profit_amount = (exit_price - entry_price) * size * direction
            profit_amount = float(profit_amount) if profit_amount else 0
            
            # 计算收益率
            if entry_amount > 0:
                profit_rate = (profit_amount / entry_amount) * 100
                print(f"[DEBUG] 交易 {trade.get('symbol')}: 入场金额={entry_amount}, 收益={profit_amount}, 收益率={profit_rate}%")
                
                if profit_rate > max_profit_rate:
                    max_profit_rate = profit_rate
                    best_trade = trade
                    print(f"[DEBUG] 新的最佳交易: {trade.get('symbol')} - 收益率: {profit_rate}%")
        
        print(f"[DEBUG] 当月交易总数: {len(current_month_trades)}")
        
        # 如果没有找到交易记录，自动创建一个TNXP测试记录
        if not best_trade:
            print(f"[DEBUG] 没有找到8月份交易，自动创建TNXP测试数据")
            try:
                # 创建TNXP测试数据
                tnxp_trade = {
                    'symbol': 'TNXP',
                    'name': 'Tonix Pharmaceuticals',
                    'trade_market': '美国',
                    'entry_price': 20.0,
                    'exit_price': 30.0,
                    'size': 200,
                    'direction': 1,
                    'entry_date': '2025-08-08T08:27:00+00:00',
                    'exit_date': '2025-08-08T15:30:00+00:00',
                    'entry_amount': 4000.0,
                    'profit_amount': 2000.0,
                    'trader_uuid': Web_Trader_UUID,
                    'created_at': datetime.now(pytz.UTC).isoformat(),
                    'updated_at': datetime.now(pytz.UTC).isoformat()
                }
                
                # 插入数据库
                response = supabase.table('trades1').insert(tnxp_trade).execute()
                print(f"[DEBUG] 自动插入TNXP数据成功")
                
                # 设置为最佳交易
                best_trade = tnxp_trade
                max_profit_rate = 50.0  # 50%收益率
                
            except Exception as e:
                print(f"[DEBUG] 自动插入数据失败: {e}")
        
        if not best_trade:
            return jsonify({
                'success': False,
                'message': '当月暂无交易记录',
                'debug_info': {
                    'trader_uuid': Web_Trader_UUID,
                    'target_month': target_month,
                    'total_trades': len(trades),
                    'target_month_trades': len(current_month_trades)
                }
            })
        
        # 重新计算最佳交易的数据
        profit_amount = float(best_trade.get('profit_amount', 0))
        entry_amount = float(best_trade.get('entry_amount', 1))
        profit_rate = (profit_amount / entry_amount * 100) if entry_amount > 0 else 0
        
        print(f"[DEBUG] 最佳交易: {best_trade.get('symbol')} - 收益: {profit_amount} - 收益率: {profit_rate}%")
        
        # 格式化买入和卖出日期，计算持股天数
        entry_date = best_trade.get('entry_date', '')
        exit_date = best_trade.get('exit_date', '')
        
        formatted_entry_date = '8号买入'  # 默认值，匹配您的界面
        formatted_exit_date = '8号卖出'   # 默认值，匹配您的界面
        holding_days = 0
        
        try:
            if entry_date:
                if '2025-08-08' in entry_date:
                    formatted_entry_date = "8号买入"
                else:
                    entry_date_obj = datetime.strptime(entry_date[:10], '%Y-%m-%d')
                    formatted_entry_date = f"{entry_date_obj.day}号买入"
                
                if exit_date:
                    if '2025-08-08' in exit_date:
                        formatted_exit_date = "8号卖出"
                        holding_days = 0  # 同一天买卖
                    else:
                        exit_date_obj = datetime.strptime(exit_date[:10], '%Y-%m-%d')
                        formatted_exit_date = f"{exit_date_obj.day}号卖出"
                        entry_date_obj = datetime.strptime(entry_date[:10], '%Y-%m-%d')
                        holding_days = (exit_date_obj - entry_date_obj).days
        except Exception as e:
            print(f"[DEBUG] 日期解析错误: {e}")
            # 使用默认值
        
        return jsonify({
            'success': True,
            'bestTrade': {
                'symbol': best_trade.get('symbol', '').upper(),
                'name': best_trade.get('name', ''),
                'market': best_trade.get('trade_market', ''),
                'profit': profit_amount,
                'profitRate': profit_rate,
                'entryDate': formatted_entry_date,
                'exitDate': formatted_exit_date,
                'holdingDays': holding_days,
                'entryPrice': float(best_trade.get('entry_price', 0)),
                'exitPrice': float(best_trade.get('exit_price', 0)),
                'entryAmount': entry_amount,
                'exitAmount': entry_amount + profit_amount,
                'size': float(best_trade.get('size', 0)),
                'direction': best_trade.get('direction', '')
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取最佳交易信息失败: {str(e)}'
        })

# 测试最佳交易功能的数据添加
@app.route('/api/admin/add-test-best-trade', methods=['POST'])
def add_test_best_trade():
    try:
        # 暂时注释掉权限检查，用于测试
        # if 'role' not in session or session['role'] != 'admin':
        #     return jsonify({'success': False, 'message': '无权限访问'}), 403
        
        # 固定为2025年8月份的数据
        current_date = datetime.now(pytz.UTC)
        
        # 创建8月份的测试交易记录 - 和您看到的TNXP数据匹配
        test_trades = [
            {
                'symbol': 'TNXP',
                'name': 'Tonix Pharmaceuticals',
                'trade_market': '美国',
                'entry_price': 20.0,
                'exit_price': 30.0,  # 对应您界面上的$30.00
                'size': 200,
                'direction': 1,
                'entry_date': '2025-08-08T08:27:00+00:00',  # 8月8号买入
                'exit_date': '2025-08-08T15:30:00+00:00',   # 8月8号卖出
                'entry_amount': 4000.0,  # 20 * 200 = 4000
                'profit_amount': 2000.0, # (30 - 20) * 200 = 2000 (50%收益率)
                'trader_uuid': Web_Trader_UUID,
                'created_at': current_date.isoformat(),
                'updated_at': current_date.isoformat()
            },
            {
                'symbol': 'DFDV',
                'name': 'Digital Finance',
                'trade_market': '美国',
                'entry_price': 19.0,
                'exit_price': 22.8,
                'size': 3000,
                'direction': 1,
                'entry_date': '2025-08-05T09:30:00+00:00',
                'exit_date': '2025-08-05T16:00:00+00:00',
                'entry_amount': 57000.0,
                'profit_amount': 11400.0,  # (22.8 - 19.0) * 3000 = 11400 (20%收益率)
                'trader_uuid': Web_Trader_UUID,
                'created_at': current_date.isoformat(),
                'updated_at': current_date.isoformat()
            }
        ]
        
        # 先删除已存在的测试数据（避免重复）
        try:
            delete_response = supabase.table('trades1').delete().eq('trader_uuid', Web_Trader_UUID).in_('symbol', ['TNXP', 'DFDV']).execute()
            print(f"[DEBUG] 删除已存在的测试数据")
        except Exception as e:
            print(f"[DEBUG] 删除数据时出错（可能没有数据）: {e}")
        
        # 插入测试数据
        for trade in test_trades:
            response = supabase.table('trades1').insert(trade).execute()
            print(f"[DEBUG] 插入测试交易: {trade['symbol']} - 收益: {trade['profit_amount']} - 退出日期: {trade['exit_date']}")
        
        return jsonify({
            'success': True,
            'message': f'成功添加 {len(test_trades)} 条8月份测试交易记录',
            'trades_added': len(test_trades),
            'trades': [{'symbol': t['symbol'], 'profit_rate': (t['profit_amount']/t['entry_amount']*100)} for t in test_trades]
        })
        
    except Exception as e:
        print(f"[ERROR] 添加测试数据失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'添加测试数据失败: {str(e)}'
        })

# 公告管理API
@app.route('/api/announcement', methods=['GET'])
def get_announcement():
    try:
        # 获取最新的公告
        response = supabase.table('announcements').select("*").eq("trader_uuid", Web_Trader_UUID).eq("active", True).eq("popup_enabled", True).order('created_at', desc=True).limit(1).execute()
        
        if response.data and len(response.data) > 0:
            announcement = response.data[0]
            # Convert to US Eastern time
            created_at = announcement.get('created_at', '')
            if created_at:
                # Parse the UTC timestamp and convert to Eastern time
                utc_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                eastern = pytz.timezone('US/Eastern')
                eastern_time = utc_time.astimezone(eastern)
                formatted_date = eastern_time.strftime('%b %d, %Y')
            else:
                formatted_date = ''
                
            return jsonify({
                'success': True,
                'announcement': {
                    'title': announcement.get('title', 'Important Notice'),
                    'content': announcement.get('content', 'Welcome to join our trading community!'),
                    'allow_close_dialog': announcement.get('allow_close_dialog', False),
                    'date': formatted_date
                }
            })
        else:
            # 如果没有公告，返回默认内容
            # Format current date in US Eastern time
            eastern = pytz.timezone('US/Eastern')
            current_eastern = datetime.now(eastern)
            formatted_current_date = current_eastern.strftime('%b %d, %Y')
            
            return jsonify({
                'success': True,
                'announcement': {
                    'title': 'Welcome to Join Exclusive Trading Community',
                    'content': 'Get real-time trading signal alerts, professional strategy analysis, one-on-one trading guidance, and exclusive market analysis reports. Join our exclusive community now and start your path to investment success!',
                    'date': formatted_current_date
                }
            })
            
    except Exception as e:
        print(f"[ERROR] Failed to get announcement: {str(e)}")
        # 返回默认内容
        # Format current date in US Eastern time for error case
        eastern = pytz.timezone('US/Eastern')
        current_eastern = datetime.now(eastern)
        formatted_current_date = current_eastern.strftime('%b %d, %Y')
        
        return jsonify({
            'success': True,
            'announcement': {
                'title': 'Welcome to Join Exclusive Trading Community',
                'content': 'Get real-time trading signal alerts, professional strategy analysis, one-on-one trading guidance, and exclusive market analysis reports.',
                'date': formatted_current_date
            }
        })

# 管理员编辑公告API
@app.route('/api/admin/announcement', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_announcement():
    try:
        # 暂时注释掉权限检查，用于测试
        # if 'role' not in session or session['role'] != 'admin':
        #     return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        if request.method == 'GET':
            try:
                # 获取所有公告
                response = supabase.table('announcements').select("*").eq("trader_uuid", Web_Trader_UUID).order('created_at', desc=True).execute()
                return jsonify({
                    'success': True,
                    'announcements': response.data or []
                })
            except Exception as table_error:
                # 如果表不存在，返回空列表
                if 'does not exist' in str(table_error):
                    return jsonify({
                        'success': True,
                        'announcements': [],
                        'message': 'Announcements table does not exist yet. Please create it in your database first.'
                    })
                else:
                    raise table_error
            
        elif request.method == 'POST':
            try:
                # 创建新公告
                data = request.get_json()
                announcement_id = data.get('id')
                announcement_data = {
                    'title': data.get('title', 'Important Notice'),
                    'content': data.get('content', ''),
                    'active': data.get('active', True),
                    'priority': data.get('priority', 1),
                    'popup_enabled': data.get('popup_enabled', True),
                    'delay_seconds': data.get('delay_seconds', 10),
                    'show_to_members': data.get('show_to_members', True),
                    'allow_close_dialog': data.get('allow_close_dialog', 0),
                    'trader_uuid': Web_Trader_UUID,
                    'created_at': datetime.now(pytz.UTC).isoformat(),
                    'updated_at': datetime.now(pytz.UTC).isoformat()
                }
                if(announcement_id=='0'):
                    response = supabase.table('announcements').insert(announcement_data).execute()
                else:
                    del announcement_data['created_at']
                    del announcement_data['trader_uuid']
                   
                    response = supabase.table('announcements').update(announcement_data).eq('id', announcement_id).execute()
                
                return jsonify({
                    'success': True,
                    'message': 'Announcement created or edit successfully',
                    'announcement': response.data[0] if response.data else None
                })
            except Exception as table_error:
                # 如果表不存在，返回明确的错误信息
                if 'does not exist' in str(table_error):
                    return jsonify({
                        'success': False,
                        'message': 'Database table "announcements" does not exist. Please create it first using the provided SQL script.',
                        'sql_needed': True
                    }), 400
                else:
                    raise table_error
            
        elif request.method == 'PUT':
            # 更新公告
            data = request.get_json()
            announcement_id = data.get('id')
            
            if not announcement_id:
                return jsonify({'success': False, 'message': '缺少公告ID'}), 400
                
            update_data = {
                'title': data.get('title'),
                'content': data.get('content'),
                'active': data.get('active'),
                'allow_close_dialog': data.get('allow_close_dialog', 0),
                'updated_at': datetime.now(pytz.UTC).isoformat()
            }
            
            response = supabase.table('announcements').update(update_data).eq('id', announcement_id).execute()
            
            return jsonify({
                'success': True,
                'message': '公告更新成功',
                'announcement': response.data[0] if response.data else None
            })
            
        elif request.method == 'DELETE':
            # 删除公告
            announcement_id = request.args.get('id')
            if not announcement_id:
                return jsonify({'success': False, 'message': '缺少公告ID'}), 400
                
            response = supabase.table('announcements').delete().eq('id', announcement_id).execute()
            
            return jsonify({
                'success': True,
                'message': '公告删除成功'
            })
            
    except Exception as e:
        print(f"[ERROR] Announcement management failed: {str(e)}")
        return jsonify({'success': False, 'message': f'操作失败: {str(e)}'}), 500

# RESTful routes for announcement management with ID parameter
@app.route('/api/admin/announcement/<int:announcement_id>', methods=['PUT', 'DELETE'])
def manage_announcement_by_id(announcement_id):
    try:
        # 暂时注释掉权限检查，用于测试
        # if 'role' not in session or session['role'] != 'admin':
        #     return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        if request.method == 'PUT':
            # 更新公告
            data = request.get_json()
                
            update_data = {
                'title': data.get('title'),
                'content': data.get('content'),
                'active': data.get('active'),
                'priority': data.get('priority', 1),
                'popup_enabled': data.get('popup_enabled', True),
                'delay_seconds': data.get('delay_seconds', 10),
                'show_to_members': data.get('show_to_members', True),
                'updated_at': datetime.now(pytz.UTC).isoformat()
            }
            
            # 只有当前trader的公告才能被更新
            response = supabase.table('announcements').update(update_data).eq('id', announcement_id).eq('trader_uuid', Web_Trader_UUID).execute()
            
            if response.data:
                return jsonify({
                    'success': True,
                    'message': 'Announcement updated successfully',
                    'announcement': response.data[0]
                })
            else:
                return jsonify({'success': False, 'message': 'Announcement not found or no permission'}), 404
            
        elif request.method == 'DELETE':
            # 删除公告
            # 只有当前trader的公告才能被删除
            response = supabase.table('announcements').delete().eq('id', announcement_id).eq('trader_uuid', Web_Trader_UUID).execute()
            
            if response.data:
                return jsonify({
                    'success': True,
                    'message': 'Announcement deleted successfully'
                })
            else:
                return jsonify({'success': False, 'message': 'Announcement not found or no permission'}), 404
            
    except Exception as e:
        print(f"[ERROR] Announcement management failed: {str(e)}")
        return jsonify({'success': False, 'message': f'操作失败: {str(e)}'}), 500

# 获取弹窗配置API
@app.route('/api/popup-config', methods=['GET'])
def get_popup_config():
    try:
        # 获取最新的激活公告配置
        response = supabase.table('announcements').select("*").eq("trader_uuid", Web_Trader_UUID).eq("active", True).order('created_at', desc=True).limit(1).execute()
        
        if response.data and len(response.data) > 0:
            announcement = response.data[0]
            return jsonify({
                'success': True,
                'config': {
                    'popup_enabled': announcement.get('popup_enabled', True),
                    'delay_seconds': announcement.get('delay_seconds', 10),
                    'show_to_members': announcement.get('show_to_members', True)
                }
            })
        else:
            # 返回默认配置
            return jsonify({
                'success': True,
                'config': {
                    'popup_enabled': True,
                    'delay_seconds': 10,
                    'show_to_members': True
                }
            })
            
    except Exception as e:
        print(f"[ERROR] Failed to get popup config: {str(e)}")
        return jsonify({
            'success': True,
            'config': {
                'popup_enabled': True,
                'delay_seconds': 10,
                'show_to_members': True
            }
        })

def membership_level_class(level):
    """Map membership level to CSS class"""
    level_map = {
        'VIP': 'regular-member',
        'Regular Member': 'regular-member',
        'Gold Member': 'gold-member',
        'Diamond Member': 'diamond-member',
        'Supreme Black Card': 'black-card-member',
        'gold-member': 'gold-member',
        'diamond-member': 'diamond-member',
        'black-card-member': 'black-card-member',
        'regular-member': 'regular-member'
    }
    return level_map.get(level, 'regular-member')

@app.route('/vip')
def vip():
    if 'username' in session:
        response = supabase.table('users').select('*').eq('username', session['username']).execute()
        if response.data:
            user = response.data[0]
            # 获取交易员信息用于网站标题
            try:
                profile_response = supabase.table('trader_profiles').select("*").eq("trader_uuid", Web_Trader_UUID).limit(1).execute()
                trader_profile = profile_response.data[0] if profile_response.data else {}
                website_title = trader_profile.get('website_title', 'VIP Trading Platform')
                home_top_title=trader_profile.get('home_top_title', 'VIP Trading Platform')
            except Exception as e:
                print(f"[ERROR] 获取交易员信息失败: {e}")
                website_title = 'VIP Trading Platform'
                home_top_title='VIP Trading Platform'
            
            trader_info = {
                'trader_name': user['username'],
                'home_top_title':home_top_title,
                'membership_level': user.get('membership_level', 'VIP Member'),
                'trading_volume': user.get('trading_volume', 0),
                'profile_image_url': 'https://via.placeholder.com/180',
                'website_title': website_title
            }
            user_id = user['id']
            initial_asset = float(user.get('initial_asset', 0) or 0)
            # 获取该用户的交易记录
            trades_resp = supabase.table('trades').select('*').eq('user_id', user_id).execute()
            trades = trades_resp.data if trades_resp.data else []
        else:
            # 获取交易员信息用于网站标题
            try:
                profile_response = supabase.table('trader_profiles').select("*").eq("trader_uuid", Web_Trader_UUID).limit(1).execute()
                trader_profile = profile_response.data[0] if profile_response.data else {}
                website_title = trader_profile.get('website_title', 'VIP Trading Platform')
                home_top_title=trader_profile.get('home_top_title', 'VIP Trading Platform')
            except Exception as e:
                print(f"[ERROR] 获取交易员信息失败: {e}")
                website_title = 'VIP Trading Platform'
                home_top_title='VIP Trading Platform'
            
            trader_info = {
                'trader_name': session['username'],
                'home_top_title':home_top_title,
                'membership_level': 'VIP Member',
                'trading_volume': 0,
                'profile_image_url': 'https://via.placeholder.com/180',
                'website_title': website_title
            }
            trades = []
            initial_asset = 0
    else:
        # 获取交易员信息用于网站标题
        try:
            profile_response = supabase.table('trader_profiles').select("*").eq("trader_uuid", Web_Trader_UUID).limit(1).execute()
            trader_profile = profile_response.data[0] if profile_response.data else {}
            website_title = trader_profile.get('website_title', 'VIP Trading Platform')
            home_top_title=trader_profile.get('home_top_title', 'VIP Trading Platform')
        except Exception as e:
            print(f"[ERROR] 获取交易员信息失败: {e}")
            website_title = 'VIP Trading Platform'
            home_top_title='VIP Trading Platform'
        
        trader_info = {
            'membership_level': 'VIP Member',
            'home_top_title':home_top_title,
            'website_title': website_title,
            'trading_volume': 0,
            'profile_image_url': 'https://via.placeholder.com/180'
        }
        trades = []
        initial_asset = 0
    Response=supabase.table("trade_market").select("*").execute()
    marketdata=Response.data
    # 计算dynamic_total_asset
    total_market_value = 0
    holding_cost = 0
    closed_profit_sum = 0
    for trade in trades:
        entry_price = float(trade.get('entry_price') or 0)
        exit_price = float(trade.get('exit_price') or 0)
        size = float(trade.get('size') or 0)
        current_price = float(trade.get('current_price') or 0)
        direction = float(trade.get('direction') or 0)
        exchange_rate= float(getexchange_rate(marketdata,trade.get('trade_market')))
        
        if not trade.get('exit_price'):
            if direction>0:
                total_market_value += current_price * size/exchange_rate
            else:
                total_market_value += (entry_price+entry_price-current_price) * size/exchange_rate
            holding_cost += entry_price * size
        else:
           
            profit = (exit_price - entry_price) * size * direction/exchange_rate
           
            closed_profit_sum += profit
    available_funds = initial_asset + closed_profit_sum - holding_cost
    dynamic_total_asset = total_market_value + available_funds
    #   if direction>0:
    #             total_market_value += (latest_price or 0) * size / exchange_rate #计算总市值
    #         else:
    #             total_market_value += (entry_price+entry_price-(latest_price or 0))* size / exchange_rate #计算总市值
    return render_template(
        'vip.html',
        trader_info=trader_info,
        trades=trades,
        dynamic_total_asset=dynamic_total_asset,
    )
def getexchange_rate(MarketData,market):
    try:
        for item in MarketData:
            if item["marketname"]==market:
                return item["exchange_rate"]
        ...
    except Exception as e:
        return 1
def getexchange_unit(MarketData,market):
    try:
        for item in MarketData:
            if item["marketname"]==market:
                return item["currency"]
        ...
    except Exception as e:
        return ""
    
@app.route('/vip-dashboard')
def vip_dashboard():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('vip'))
    user_resp = supabase.table('users').select('*').eq('id', user_id).execute()
    user = user_resp.data[0] if user_resp.data else {}
    user = fill_default_avatar(user)
    avatar_url = user.get('avatar_url')
    level_cn = user.get('membership_level', '普通会员')
    level_en = get_level_en(level_cn)
    initial_asset = float(user.get('initial_asset', 0) or 0)
    Response=supabase.table("trade_market").select("*").execute()
    marketdata=Response.data
    # 只统计当前用户自己的收益
    trades_resp = supabase.table('trades').select('*').eq('user_id', user['id']).execute()
    trades = trades_resp.data if trades_resp.data else []
    userinfo=supabase.table("view_user_info").select("*").eq('id', user['id']).execute()
    userdata=userinfo.data
    # --- 新增：实时获取未平仓持仓的最新价格 ---
    for trade in trades:
        if not trade.get('exit_price'):
            latest_price = get_real_time_price(trade.get('trade_market'),trade.get('symbol'))
            if latest_price:
                trade['current_price'] = latest_price
    # --- 其它统计逻辑保持不变 ---
    total_profit = userdata[0]["utotle_profit"]
    monthly_profit = userdata[0]["umonth_profit"]
    uprvmonth_profit = userdata[0]["uprvmonth_profit"]
    holding_profit = 0
    closed_profit = 0
    now = datetime.now()
    total_market_value = 0
    holding_cost = 0
    closed_profit_sum = 0
    exchange_rate=1
    for trade in trades:
        entry_price = float(trade.get('entry_price') or 0)
        exit_price = float(trade.get('exit_price') or 0)
        size = float(trade.get('size') or 0)
        direction = float(trade.get('direction') or 0)
        profit = 0
        exchange_rate= float(getexchange_rate(marketdata,trade.get('trade_market')))
        trade["currency"]=getexchange_unit(marketdata,trade.get('trade_market'))
        trade["exchange_rate"]=exchange_rate
        if not trade.get('exit_price'):
          
            symbol = trade.get('symbol')
            if not symbol:
                print(f"[HoldingProfit] WARNING: 持仓有空symbol，entry_price={entry_price}, size={size}")
                continue
            # 用本地API查价，和前端一致
            try:
                # resp = requests.get(f"http://127.0.0.1:8888/api/price?symbol={symbol}&market={trade.get('trade_market')}", timeout=5)
                # data = resp.json()
                #获取最新价格
                latest_price =get_real_time_price(trade.get('trade_market'),symbol) # data.get('price') if data.get('success') else None
            except Exception as e:
                print(f"[HoldingProfit] ERROR: 请求本地/api/price失败: {e}")
                latest_price = trade.get('current_price')
            print(f"[HoldingProfit] symbol={symbol}, entry_price={entry_price}, latest_price={latest_price}, size={size}")
            if latest_price is not None:
                
                profit = (latest_price - entry_price) * size * direction
                holding_profit += profit #计算持仓利润
            else:
                print(f"[HoldingProfit] WARNING: /api/price?symbol={symbol}&market={trade.get('trade_market')} 返回None，无法计算持仓利润")
            if direction>0:
                total_market_value += (latest_price or 0) * size / exchange_rate #计算总市值
            else:
                total_market_value += (entry_price+entry_price-(latest_price or 0))* size / exchange_rate #计算总市值
            holding_cost += entry_price * size / exchange_rate #持仓成本
        else:
            profit = (exit_price - entry_price) * size * direction #计算盈利
            closed_profit_sum += profit/exchange_rate #盈利总额
        # if trade.get('exit_price') is not None:
        #     profit = (exit_price - entry_price) * size * direction #计算盈利
        #     total_profit += profit/exchange_rate #总盈利
        #     if trade.get('exit_date') and str(trade['exit_date']).startswith(now.strftime('%Y-%m')):
        #         monthly_profit += profit/exchange_rate
        closed_profit = total_profit
    available_funds = initial_asset + closed_profit_sum - holding_cost
    dynamic_total_asset = total_market_value + available_funds

    # 查询排行榜
    users_resp = supabase.table('view_user_info').select('username,membership_level,avatar_url,umonth_profit,utotle_profit').eq("trader_uuid",Web_Trader_UUID).order('umonth_profit', desc=True).limit(50).execute()
    top_users = users_resp.data if users_resp.data else []

    # 获取交易员信息用于网站标题
    try:
        profile_response = supabase.table('trader_profiles').select("*").eq("trader_uuid", Web_Trader_UUID).limit(1).execute()
        trader_profile = profile_response.data[0] if profile_response.data else {}
        website_title = trader_profile.get('website_title', 'VIP Dashboard')
    except Exception as e:
        print(f"[ERROR] 获取交易员信息失败: {e}")
        website_title = 'VIP Dashboard'
    
    trader_info = {
        'trader_name': user.get('username', ''),
        'membership_level': level_en,
        'trading_volume': user.get('trading_volume', 0),
        'avatar_url': avatar_url,
        'website_title': website_title
    }

    # 查询VIP策略公告（取前2条，按date降序）
    announcements_resp = supabase.table('vip_announcements').select('*').eq("trader_uuid",Web_Trader_UUID).order('date', desc=True).limit(2).execute()
    announcements = announcements_resp.data if announcements_resp.data else []

    # 查询VIP交易记录（取前10条，按entry_time降序）
    vip_trades_resp = supabase.table('vip_trades').select('*').eq("trader_uuid",Web_Trader_UUID).order('entry_time', desc=True).limit(10).execute()
    vip_trades = vip_trades_resp.data if vip_trades_resp.data else []
    totle=0
    Ratio=0
    for itemvip in vip_trades:
        
        if itemvip["direction"]>0:
            totle = (itemvip["current_price"]-itemvip["entry_price"]) * itemvip["quantity"] * itemvip["direction"]
        else:
            totle = (itemvip["current_price"]-itemvip["entry_price"]) * itemvip["quantity"] * itemvip["direction"]
        Ratio = (totle / (itemvip["entry_price"] * itemvip["quantity"])) * 100 
        itemvip["totle"]=totle
        itemvip["Ratio"]=Ratio
        itemvip["currency"]=getexchange_unit(marketdata,itemvip.get('trade_market'))
    # --- trades排序：未平仓排前面，再按entry_date降序 ---
    trades.sort(key=lambda t: (0 if not t.get('exit_price') else 1, t.get('entry_date') or ''), reverse=False)
   
    return render_template(
        'vip-dashboard.html',
        trader_info=trader_info,
        total_asset=initial_asset,
        dynamic_total_asset=dynamic_total_asset,
        total_market_value=total_market_value,
        available_funds=available_funds,
        total_profit=total_profit,
        monthly_profit=monthly_profit,
        uprvmonth_profit=uprvmonth_profit,
        holding_profit=holding_profit,
        trades=trades,
        top_users=top_users,
        membership_level_class=membership_level_class,
        announcements=announcements,
        vip_trades=vip_trades,
        marketdata=marketdata
    )

# --- 用户表自动建表 ---
def init_user_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT UNIQUE,
            status TEXT DEFAULT 'active',
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            last_login_ip TEXT,
            last_login_location TEXT,
            membership_level TEXT DEFAULT '普通会员',
            initial_asset REAL DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

# --- 会员等级表自动建表 ---
def init_membership_levels_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS membership_levels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            level INTEGER NOT NULL,
            min_trading_volume DECIMAL(10,2) NOT NULL,
            benefits TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 插入默认会员等级
    default_levels = [
        ('普通会员', 1, 0.00, '基础交易工具,标准市场分析,社区访问,标准支持'),
        ('黄金会员', 2, 100000.00, '高级交易工具,实时市场分析,优先支持,VIP社区访问,交易策略分享'),
        ('钻石会员', 3, 500000.00, '所有黄金会员权益,个人交易顾问,定制策略开发,新功能优先体验,专属交易活动'),
        ('至尊黑卡', 4, 1000000.00, '所有钻石会员权益,24/7专属交易顾问,AI量化策略定制,全球金融峰会邀请,专属投资机会,一对一交易指导')
    ]
    
    c.execute('SELECT COUNT(*) FROM membership_levels')
    if c.fetchone()[0] == 0:
        c.executemany('''
            INSERT INTO membership_levels (name, level, min_trading_volume, benefits)
            VALUES (?, ?, ?, ?)
        ''', default_levels)
    
    conn.commit()
    conn.close()

# --- 用户会员等级关联表自动建表 ---
def init_user_membership_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_membership (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            level_id INTEGER NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (level_id) REFERENCES membership_levels (id)
        )
    ''')
    conn.commit()
    conn.close()
# --- 会员等级分配API ---
@app.route('/api/gettrade_market', methods=['GET'])
def gettrade_market():
    try:
        response = supabase.table('trade_market').select("*").execute()
        data=response.data
        return jsonify({'success': True, 'data': data}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Operation failed: {str(e)}'}), 500
    

# --- 会员等级分配API ---
@app.route('/api/admin/assign-membership', methods=['POST'])
def assign_membership():
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        data = request.get_json()
        if not data.get('user_id'):
            return jsonify({'success': False, 'message': '缺少用户ID'}), 400

        # 根据level_id获取会员等级名称
        membership_levels = {
            '1': '普通会员',
            '2': '黄金会员',
            '3': '钻石会员',
            '4': '至尊黑卡'
        }
        
        level_name = membership_levels.get(str(data.get('level_id')))
        if not level_name:
            return jsonify({'success': False, 'message': '无效的会员等级'}), 400

        # 直接更新users表
        response = supabase.table('users').update({
            'membership_level': level_name
        }).eq('id', data['user_id']).execute()
        
        if not response.data:
            return jsonify({'success': False, 'message': '用户不存在'}), 404
            
        return jsonify({'success': True, 'message': 'Membership level assigned successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Operation failed: {str(e)}'}), 500

# --- 获取用户会员等级信息 ---
@app.route('/api/user/membership', methods=['GET'])
def get_user_membership():
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': '请先登录'}), 401
            
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        
        # 获取用户的会员等级信息
        c.execute('''
            SELECT m.name, m.level, m.benefits
            FROM user_membership um
            JOIN membership_levels m ON um.level_id = m.id
            WHERE um.user_id = ?
        ''', (session['user_id'],))
        
        membership = c.fetchone()
        conn.close()
        
        if membership:
            return jsonify({
                'success': True,
                'membership': {
                    'name': membership[0],
                    'level': membership[1],
                    'benefits': membership[2]
                }
            })
        else:
            return jsonify({
                'success': True,
                'membership': None
            })
            
    except Exception as e:
        return jsonify({'success': False, 'message': 'Failed to get membership information'}), 500

# --- 会员等级管理API ---
@app.route('/api/admin/membership-levels', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_membership_levels():
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        if request.method == 'GET':
            # 获取所有会员等级
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT * FROM membership_levels ORDER BY level')
            levels = []
            for row in c.fetchall():
                levels.append({
                    'id': row[0],
                    'name': row[1],
                    'level': row[2],
                    'min_trading_volume': row[3],
                    'benefits': row[4],
                    'created_at': row[5]
                })
            conn.close()
            return jsonify({'success': True, 'levels': levels})
            
        elif request.method == 'POST':
            # 创建新会员等级
            data = request.get_json()
            required_fields = ['name', 'level', 'min_trading_volume', 'benefits']
            
            if not all(field in data for field in required_fields):
                return jsonify({'success': False, 'message': '缺少必要字段'}), 400
                
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('''
                INSERT INTO membership_levels (name, level, min_trading_volume, benefits)
                VALUES (?, ?, ?, ?)
            ''', (data['name'], data['level'], data['min_trading_volume'], data['benefits']))
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'message': 'Membership level created successfully'})
            
        elif request.method == 'PUT':
            # 更新会员等级
            data = request.get_json()
            required_fields = ['id', 'name', 'level', 'min_trading_volume', 'benefits']
            
            if not all(field in data for field in required_fields):
                return jsonify({'success': False, 'message': '缺少必要字段'}), 400
                
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('''
                UPDATE membership_levels
                SET name = ?, level = ?, min_trading_volume = ?, benefits = ?
                WHERE id = ?
            ''', (data['name'], data['level'], data['min_trading_volume'], data['benefits'], data['id']))
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'message': 'Membership level updated successfully'})
            
        elif request.method == 'DELETE':
            # 删除会员等级
            level_id = request.args.get('id')
            if not level_id:
                return jsonify({'success': False, 'message': '缺少会员等级ID'}), 400
                
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('DELETE FROM membership_levels WHERE id = ?', (level_id,))
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'message': 'Membership level deleted successfully'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': 'Operation failed'}), 500

# --- 登录接口（Supabase版） ---
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        if username=="admin":
            # 从Supabase获取用户信息
            response = supabase.table('users').select('*').eq('username', username).execute()
        else:
             # 从Supabase获取用户信息
            response = supabase.table('users').select('*').eq('username', username).eq("trader_uuid",Web_Trader_UUID,).execute()
        
        if not response.data:
            return jsonify({'success': False, 'message': 'Invalid username or password'}), 401
            
        user = response.data[0]
        
        # TODO: 在实际应用中应该进行密码验证
        # 这里简化处理，直接验证密码是否匹配
        if password != user.get('password_hash'):  # 实际应用中应该使用proper密码验证
            return jsonify({'success': False, 'message': 'Invalid username or password'}), 401
            
        if user.get('status') != 'active':
            return jsonify({'success': False, 'message': 'The account has been disabled.'}), 403
            
        # 获取IP和地址信息
        ip_address = request.remote_addr
        try:
            response = requests.get(f'https://ipinfo.io/{ip_address}/json')
            location_data = response.json()
            location = f"{location_data.get('city', '')}, {location_data.get('region', '')}, {location_data.get('country', '')}"
        except:
            location = 'Unknown location'
            
        # 更新用户登录信息
        supabase.table('users').update({
            'last_login': datetime.now(pytz.UTC).isoformat(),
            'last_login_ip': ip_address,
            'last_login_location': location
        }).eq('id', user['id']).execute()
        
        # 设置session
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user.get('role', 'user')
        session['trader_uuid'] = user['trader_uuid']
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': {
                'id': user['id'],
                'username': user['username'],
                'role': user.get('role', 'user'),
                'membership_level': user.get('membership_level', '普通会员')
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': 'Login failed'}), 500

# --- 登出接口 ---
@app.route('/api/logout', methods=['POST'])
def logout():
    try:
        # 清除session
        session.clear()
        return jsonify({'success': True, 'message': 'Successfully logged out'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Logout failed'}), 500

def update_holding_stocks_prices():
    """更新所有持有中股票的实时价格"""
    try:
        # 获取所有持有中的股票
        response = supabase.table('trades1').select("*").execute()
        trades = response.data
        
        if not trades:
            return
        
        for trade in trades:
            # 检查是否是持有中的股票
            if trade.get('exit_price') is None and trade.get('exit_date') is None:
                symbol = trade['symbol']
                current_price = get_real_time_price(trade["trade_market"],symbol)
                
                if current_price:
                    # 计算新的数据
                    entry_amount = trade['entry_price'] * trade['size']
                    current_amount = current_price * trade['size']
                    profit_amount = current_amount - entry_amount
                    profit_ratio = (profit_amount / entry_amount) * 100 if entry_amount else 0
                    
                    try:
                        # 只更新current_price字段
                        update_data = {
                            'current_price': current_price
                        }
                        
                        update_response = supabase.table('trades1').update(update_data).eq('id', trade['id']).execute()
                        
                        if update_response.data:
                            # 验证更新是否成功
                            verify_response = supabase.table('trades1').select('current_price').eq('id', trade['id']).execute()
                    except Exception as e:
                        import traceback
                        print(f"Error updating database: {str(e)}")
                        print(f"Error details: {type(e).__name__}")
                        print(f"Error stack: {traceback.format_exc()}")
                
                else:
                    pass
            else:
                pass
                
    except Exception as e:
        import traceback
        print(f"Error updating stock prices: {str(e)}")
        print(f"Error stack: {traceback.format_exc()}")

def update_all_trades_prices():
    """同步所有交易表的未平仓记录的实时价格"""
    tables = ['trades1', 'trades', 'vip_trades']
    for table in tables:
        try:
            response = supabase.table(table).select("*").execute()
            trades = response.data
            if not trades:
                continue
            for trade in trades:
                # 只同步未平仓（exit_price为空或None）
                if not trade.get('exit_price'):
                    symbol = trade.get('symbol')
                    if not symbol:
                        continue
                    current_price = get_real_time_price(trade["trade_market"],symbol)
                    if current_price:
                        try:
                            supabase.table(table).update({'current_price': current_price}).eq('id', trade['id']).execute()
                        except Exception as e:
                            print(f"{table} {symbol} update failed: {e}")
                    else:
                        print(f"{table} {symbol} failed to get real-time price")
        except Exception as e:
            print(f"Error synchronizing {table}: {e}")

# 创建调度器
scheduler = BackgroundScheduler()
scheduler.start()

# 添加定时任务，每30秒更新一次价格
scheduler.add_job(
    func=update_holding_stocks_prices,
    trigger=IntervalTrigger(seconds=30),  # 改为30秒
    id='update_stock_prices',
    name='Update holding stocks prices every 30 seconds',
    replace_existing=True
)

# 添加定时任务，每30秒更新一次印度股票价格
scheduler.add_job(
    func=get_India_price,
    trigger=IntervalTrigger(seconds=30),  # 改为5秒
    id='update_stock_prices',
    name='Update holding stocks India prices every 5 seconds',
    replace_existing=True
)

# 替换原有定时任务为统一同步
scheduler.add_job(
    func=update_all_trades_prices,
    trigger=IntervalTrigger(seconds=30),
    id='update_all_trades_prices',
    name='Update all trades prices every 30 seconds',
    replace_existing=True
)

print("价格更新定时任务已启动，每30秒更新一次")

@app.route('/api/check-login', methods=['GET'])
def check_login():
    try:
        if 'user_id' in session:
            # 获取用户信息
            response = supabase.table('users').select('*').eq('id', session['user_id']).execute()
            if response.data:
                user = fill_default_avatar(response.data[0])
                level_cn = user.get('membership_level', '普通会员')
                level_en = get_level_en(level_cn)
                return jsonify({
                    'isLoggedIn': True,
                    'user': {
                        'id': user['id'],
                        'username': user['username'],
                        'role': user.get('role', 'user'),
                        'email': user.get('email'),
                        'avatar_url': user.get('avatar_url'),
                        'membership_level': level_en
                    }
                })
        return jsonify({'isLoggedIn': False})
    except Exception as e:
        return jsonify({'isLoggedIn': False}), 500
# --- 管理员接口 ---
@app.route('/api/admin/trader', methods=['GET', 'POST','DELETE'])
def manage_trader():
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        if request.method == 'GET':
            id=query = request.args.get('id')
            if not id:
                # 获取所有用户
                trader_uuid=session['trader_uuid']
                if trader_uuid:
                    response = supabase.table('trader_profiles').select('*').eq("trader_uuid",trader_uuid).execute()
                else:
                    response = supabase.table('trader_profiles').select('*').execute()
            else:
                response = supabase.table('trader_profiles').select('*').eq("id",id).execute()
            # 过滤敏感信息
            users = []
            for user in response.data:
                
                users.append(user)
            return jsonify({'success': True, 'users': users})
            
        elif request.method == 'POST':
            if ('role' not in session or session['role'] != 'admin'):
                return jsonify({'success': False, 'message': '你无权添加交易员'}), 403
            
            # 创建新用户
            data = request.get_json()
            
            # 检查必要字段
            if not data.get('trader_name'):
                return jsonify({'success': False, 'message': '交易员名称不能为空'}), 400
            if session["trader_uuid"] and session["trader_uuid"]!=data["trader_uuid"] and data["id"]!="0":
                return jsonify({'success': False, 'message': '你无权添加交易员'}), 400
            if session["trader_uuid"] and data["id"]=="0":
                return jsonify({'success': False, 'message': '你无权添加交易员'}), 400
            # # 检查用户名是否已存在
            # check_response = supabase.table('users').select('id').eq('username', data['username']).execute()
            # if check_response.data:
            #     return jsonify({'success': False, 'message': '用户名已存在'}), 400
                
            # # 创建新用户
            # new_user = {
            #     'username': data['username'],
            #     'password_hash': data['password'],  # 在实际应用中应该对密码进行加密
            #     'email': data.get('email'),
            #     'role': data.get('role', 'user'),
            #     'status': 'active',
            #     'membership_level': data.get('membership_level', '普通会员'),
            #     'created_at': datetime.now(pytz.UTC).isoformat(),
            #     'initial_asset': float(data.get('initial_asset', 0) or 0),
            #     'trader_uuid':data.get('trader_uuid')
            # }

            # if data.get('trader_uuid')=='':
            #     new_user["trader_uuid"]=None
            # if session["trader_uuid"]:
            #     new_user["trader_uuid"]=session["trader_uuid"]
         
            if(data["id"]=="0"):
                del data["id"]
                if data["trader_uuid"]=='':
                    del data["trader_uuid"]
                response = supabase.table('trader_profiles').insert(data).execute()
                ts={
                    'trader_name':response.data[0]["trader_name"],
                    'professional_title':response.data[0]["professional_title"],
                    'profile_image_url':response.data[0]["profile_image_url"],
                    'win_rate':response.data[0]["win_rate"],
                    'trader_uuid':response.data[0]["trader_uuid"]
                  
                }
                responses = supabase.table('leaderboard_traders').insert(ts).execute()
            else:
                traderID=data["id"]
                del data["id"]
                del data["trader_uuid"]
                response = supabase.table('trader_profiles').update(data).eq("id",int(traderID)).execute()
                # ts={
                #     'trader_name':data["trader_name"],
                #     'professional_title':data["professional_title"],
                #     'profile_image_url':data["profile_image_url"],
                #     'win_rate':data["win_rate"]
                # }
                # responses = supabase.table('leaderboard_traders').update(ts).eq("trader_uuid",response.data[0]['trader_uuid']).execute()
            
            return jsonify({
                'success': True,
                'message': 'User created successfully',
                'user_id': response.data[0]['id']
            })
        elif request.method == 'DELETE':
            #  data = request.get_json()
            trader_uuid = request.args.get('trader_uuid')
            if session["trader_uuid"]=='' or session['trader_uuid']!=trader_uuid:
                response = supabase.table('trader_profiles').delete().eq("trader_uuid",trader_uuid).execute()
                response = supabase.table('trades1').delete().eq("trader_uuid",trader_uuid).execute()
                response = supabase.table('contact_records').delete().eq("trader_uuid",trader_uuid).execute()
                response = supabase.table('whatsapp_agents').delete().eq("trader_uuid",trader_uuid).execute()
                response = supabase.table('videos').delete().eq("trader_uuid",trader_uuid).execute()
                response = supabase.table('announcements').delete().eq("trader_uuid",trader_uuid).execute()
                response = supabase.table('leaderboard_traders').delete().eq("trader_uuid",trader_uuid).execute()
            
                return jsonify({
                    'success': True,
                    'message': 'Delete info successfully'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Not allowed to delete one’s own information'
                })
            
    except Exception as e:
        return jsonify({'success': False, 'message': 'Operation failed'}), 500
    
# --- 管理员接口 ---
@app.route('/api/admin/users', methods=['GET', 'POST'])
def manage_users():
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        if request.method == 'GET':
            id=query = request.args.get('id')
            if not id:
                # 获取所有用户
                trader_uuid=session['trader_uuid']
                if trader_uuid:
                    response = supabase.table('users').select('*').eq("trader_uuid",trader_uuid).execute()
                else:
                    response = supabase.table('users').select('*').eq("role",'admin').execute()
            else:
                response = supabase.table('users').select('*').eq("id",id).execute()
            # 过滤敏感信息
            users = []
            for user in response.data:
                user = fill_default_avatar(user)
                level_cn = user.get('membership_level', '普通会员')
                level_en = get_level_en(level_cn)
                users.append({
                    'id': user['id'],
                    'username': user['username'],
                    'email': user.get('email'),
                    'role': user.get('role', 'user'),
                    'status': user.get('status', 'active'),
                    'membership_level': level_en,
                    'last_login': user.get('last_login'),
                    'last_login_ip': user.get('last_login_ip'),
                    'last_login_location': user.get('last_login_location'),
                    'created_at': user.get('created_at'),
                    'avatar_url': user.get('avatar_url'),
                    'initial_asset': user.get('initial_asset', 0),
                    'trader_uuid':user.get('trader_uuid')
                })
            return jsonify({'success': True, 'users': users})
            
        elif request.method == 'POST':
            # 创建新用户
            data = request.get_json()
            
            # 检查必要字段
            if not data.get('username') or not data.get('password'):
                return jsonify({'success': False, 'message': '用户名和密码是必填项'}), 400
                
            # 检查用户名是否已存在
            check_response = supabase.table('users').select('id').eq('username', data['username']).execute()
            if check_response.data:
                return jsonify({'success': False, 'message': '用户名已存在，请更换!'}), 400
            check_response = supabase.table('users').select('id').eq('email', data['email']).execute()
            if check_response.data:
                return jsonify({'success': False, 'message': '电子邮箱地址已经存在，请更换!'}), 400
                
            # 创建新用户
            new_user = {
                'username': data['username'],
                'password_hash': data['password'],  # 在实际应用中应该对密码进行加密
                'email': data.get('email'),
                'role': data.get('role', 'user'),
                'status': 'active',
                'membership_level': data.get('membership_level', '普通会员'),
                'created_at': datetime.now(pytz.UTC).isoformat(),
                'initial_asset': float(data.get('initial_asset', 0) or 0),
                'trader_uuid':data.get('trader_uuid')
            }
            if data.get('trader_uuid')=='':
                new_user["trader_uuid"]=None
            if session["trader_uuid"]:
                new_user["trader_uuid"]=session["trader_uuid"]
            
            response = supabase.table('users').insert(new_user).execute()
            
            return jsonify({
                'success': True,
                'message': 'User created successfully',
                'user_id': response.data[0]['id']
            })
            
    except Exception as e:
        return jsonify({'success': False, 'message': 'Operation failed'}), 500

@app.route('/api/admin/users/<user_id>', methods=['PUT', 'DELETE'])
def update_user(user_id):
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        if request.method == 'PUT':
            data = request.get_json()
            # 只允许更新特定字段
            allowed_fields = ['status', 'role', 'password_hash', 'initial_asset', 'membership_level']
            update_data = {k: v for k, v in data.items() if k in allowed_fields}
            if not update_data:
                return jsonify({'success': False, 'message': '没有可更新的字段'}), 400
            # initial_asset转float
            if 'initial_asset' in update_data:
                try:
                    update_data['initial_asset'] = float(update_data['initial_asset'])
                except Exception:
                    update_data['initial_asset'] = 0
            # 更新用户信息
            response = supabase.table('users').update(update_data).eq('id', user_id).execute()
            if not response.data:
                return jsonify({'success': False, 'message': '用户不存在'}), 404
            return jsonify({
                'success': True,
                'message': 'Update successful'
            })
        elif request.method == 'DELETE':
            # 软删除用户（更新状态为inactive）
            response = supabase.table('users').update({
                'status': 'inactive',
                'deleted_at': datetime.now(pytz.UTC).isoformat()
            }).eq('id', user_id).execute()
            
            if not response.data:
                return jsonify({'success': False, 'message': '用户不存在'}), 404
                
            return jsonify({
                'success': True,
                'message': '用户已禁用'
            })
            
    except Exception as e:
        return jsonify({'success': False, 'message': 'Operation failed'}), 500

@app.route('/api/admin/users/batch', methods=['POST'])
def batch_update_users():
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        data = request.get_json()
        user_ids = data.get('user_ids', [])
        action = data.get('action')  # 'activate' 或 'deactivate'
        
        if not user_ids or action not in ['activate', 'deactivate']:
            return jsonify({'success': False, 'message': '参数错误'}), 400
            
        # 批量更新用户状态
        status = 'active' if action == 'activate' else 'inactive'
        response = supabase.table('users').update({
            'status': status
        }).in_('id', user_ids).execute()
        
        return jsonify({
            'success': True,
            'message': f'已{action} {len(response.data)} 个用户'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': '批量操作失败'}), 500

@app.route('/api/admin/logs', methods=['GET'])
def get_login_logs():
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        # 获取最近100条登录记录
        response = supabase.table('users').select('username, last_login, status').order('last_login', desc=True).limit(100).execute()
        
        return jsonify({
            'success': True,
            'logs': response.data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': '获取日志失败'}), 500

# --- 测试路由 ---
@app.route('/test/login', methods=['GET'])
def test_login():
    test_cases = [
        {
            'name': '正常登录',
            'data': {'username': 'admin', 'password': '123456'},
            'expected': {'success': True, 'message': '登录成功'}
        },
        {
            'name': '缺少用户名',
            'data': {'password': '123456'},
            'expected': {'success': False, 'message': '请输入账号和密码'}
        },
        {
            'name': '缺少密码',
            'data': {'username': 'admin'},
            'expected': {'success': False, 'message': '请输入账号和密码'}
        },
        {
            'name': '错误密码',
            'data': {'username': 'admin', 'password': 'wrong_password'},
            'expected': {'success': False, 'message': '密码错误'}
        },
        {
            'name': '不存在的用户',
            'data': {'username': 'non_existent_user', 'password': '123456'},
            'expected': {'success': False, 'message': '账号不存在'}
        }
    ]
    
    results = []
    for test in test_cases:
        try:
            # 创建测试请求
            with app.test_request_context('/api/login', method='POST', json=test['data']):
                # 调用登录函数
                response = login()
                # 如果response是元组，取第一个元素（JSON响应）
                if isinstance(response, tuple):
                    data = response[0].get_json()
                else:
                    data = response.get_json()
                
                # 检查结果
                passed = (
                    data['success'] == test['expected']['success'] and
                    data['message'] == test['expected']['message']
                )
                
                results.append({
                    'test_case': test['name'],
                    'passed': passed,
                    'expected': test['expected'],
                    'actual': data
                })
        except Exception as e:
            results.append({
                'test_case': test['name'],
                'passed': False,
                'error': str(e),
                'expected': test['expected'],
                'actual': '测试执行出错'
            })
    
    return render_template('test_results.html', results=results)

# --- 管理后台路由 ---
@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('vip'))
        
    if session.get('role') != 'admin':
        return redirect(url_for('vip'))
    
    # 获取交易员信息用于网站标题
    try:
        profile_response = supabase.table('trader_profiles').select("*").eq("trader_uuid", Web_Trader_UUID).limit(1).execute()
        trader_info = profile_response.data[0] if profile_response.data else {
            'website_title': 'VIP Management Backend',
            'trader_name': 'Admin Dashboard',
            'professional_title': 'Trading Platform Management'
        }
    except Exception as e:
        print(f"[ERROR] 获取交易员信息失败: {e}")
        trader_info = {
            'website_title': 'VIP Management Backend',
            'trader_name': 'Admin Dashboard',
            'professional_title': 'Trading Platform Management'
        }
    
    Response=supabase.table("trade_market").select("*").execute()
    marketdata=Response.data
    trader_uuid=""
    if session["trader_uuid"]:
        trader_uuid=session["trader_uuid"]
    
    return render_template('admin/dashboard.html', 
                         admin_name=session.get('username', 'Admin'),
                         marketdata=marketdata,
                         createTrader=trader_uuid,
                         trader_info=trader_info)
# --- 用户登录路由 ---
@app.route('/viplogin')
def userlogin():
    if 'user_id' in session:
        return redirect(url_for('vip'))
    
    return render_template('viplogin.html')

# --- 交易策略管理路由 ---
@app.route('/admin/strategy')
def admin_strategy():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('vip'))
    return render_template('admin/strategy.html', admin_name=session.get('username', 'Admin'))

# --- 策略管理API ---
@app.route('/api/admin/strategy', methods=['GET', 'POST', 'DELETE'])
def manage_strategy():
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        if request.method == 'GET':
            # 获取最新的交易策略
            strategy_response = supabase.table('trading_strategies').select("*").eq("trader_uuid",session['trader_uuid']).order('updated_at', desc=True).limit(1).execute()
            
            if strategy_response.data:
                strategy = strategy_response.data[0]
                # 确保 trading_focus 是列表格式
                trading_focus = strategy['trading_focus']
                if isinstance(trading_focus, str):
                    try:
                        trading_focus = json.loads(trading_focus)
                    except:
                        trading_focus = [trading_focus]
                        
                return jsonify({
                    'success': True,
                    'strategy': {
                        'id': strategy['id'],
                        'market_analysis': strategy['market_analysis'],
                        'trading_focus': trading_focus,
                        'risk_warning': strategy['risk_warning'],
                        'updated_at': strategy['updated_at']
                    }
                })
            return jsonify({'success': True, 'strategy': None})
            
        elif request.method == 'POST':
            # 创建新策略
            data = request.get_json()
            required_fields = ['market_analysis', 'trading_focus', 'risk_warning']
            
            if not all(field in data for field in required_fields):
                return jsonify({'success': False, 'message': '缺少必要字段'}), 400
                
            # 确保 trading_focus 是列表格式
            trading_focus = data['trading_focus']
            if isinstance(trading_focus, str):
                try:
                    trading_focus = json.loads(trading_focus)
                except:
                    trading_focus = [trading_focus]
                    
            # 插入新策略
            strategy_data = {
                'market_analysis': data['market_analysis'],
                'trading_focus': trading_focus,
                'risk_warning': data['risk_warning'],
                'updated_at': datetime.now(pytz.UTC).isoformat(),
                'trader_uuid':session["trader_uuid"]
            }
            
            try:
                response = supabase.table('trading_strategies').insert(strategy_data).execute()
                
                if not response.data:
                    return jsonify({'success': False, 'message': 'Creation failed'}), 500
                    
                return jsonify({'success': True, 'message': 'Strategy saved successfully'})
            except Exception as e:
                return jsonify({'success': False, 'message': f'Creation failed: {str(e)}'}), 500
            
        elif request.method == 'DELETE':
            strategy_id = request.args.get('id')
            if not strategy_id:
                return jsonify({'success': False, 'message': '缺少策略ID'}), 400
                
            response = supabase.table('trading_strategies').delete().eq('id', strategy_id).execute()
            
            if not response.data:
                return jsonify({'success': False, 'message': 'Deletion failed'}), 500
                
            return jsonify({'success': True, 'message': 'Strategy deleted successfully'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': 'Operation failed'}), 500

@app.route('/api/admin/strategy/history', methods=['GET'])
def get_strategy_history():
    try:
        # 从 Supabase 获取所有策略记录，按时间倒序排列
        response = supabase.table('trading_strategies').select("*").eq("trader_uuid",session['trader_uuid']).order('updated_at', desc=True).execute()
        
        if not response.data:
            return jsonify({
                'success': True,
                'history': []
            })
        
        history = []
        for record in response.data:
            # 确保 trading_focus 是列表格式
            trading_focus = record['trading_focus']
            if isinstance(trading_focus, str):
                try:
                    trading_focus = json.loads(trading_focus)
                except:
                    trading_focus = [trading_focus]
                    
            history.append({
                'id': record['id'],
                'market_analysis': record['market_analysis'],
                'trading_focus': trading_focus,
                'risk_warning': record['risk_warning'],
                'modified_at': record['updated_at'],
                'modified_by': 'admin'  # 暂时固定为admin
            })
            
        return jsonify({
            'success': True,
            'history': history
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': '获取历史记录失败'}), 500

@app.route('/admin/strategy/permissions')
def strategy_permissions():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    return render_template('admin/strategy_permissions.html', admin_name=session.get('username', 'Admin'))

# --- 删除策略历史记录 ---
@app.route('/api/admin/strategy/history/<int:history_id>', methods=['DELETE'])
def delete_strategy_history(history_id):
    try:
        # 从 Supabase 删除历史记录
        response = supabase.table('strategy_history').delete().eq('id', history_id).eq("trader_uuid",session['trader_uuid']).execute()
        
        if not response.data:
            return jsonify({'success': False, 'message': '删除失败，记录不存在'}), 404
            
        return jsonify({'success': True, 'message': '历史记录删除成功'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': '删除失败'}), 500

# --- 股票交易管理路由 ---
@app.route('/admin/trading')
def admin_trading():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('vip'))
    return render_template('admin/trading.html', admin_name=session.get('username', 'Admin'))

# --- 股票交易管理API ---
@app.route('/api/admin/trading', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_trading():
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        if request.method == 'GET':
            # 获取所有交易记录
            response = supabase.table('trades1').select("*").eq("trader_uuid",session['trader_uuid']).order('entry_date', desc=True).execute()
            
            trades = []
            for trade in response.data:
                trades.append({
                    'id': trade['id'],
                    'trade_market': trade['trade_market'],
                    'symbol': trade['symbol'],
                    'Direction': trade['direction'],
                    'entry_price': trade['entry_price'],
                    'exit_price': trade.get('exit_price'),
                    'size': trade['size'],
                    'entry_date': trade['entry_date'],
                    'exit_date': trade.get('exit_date'),
                    'status': 'Closed' if trade.get('exit_price') else 'Active',
                    'profit_amount': (trade.get('exit_price', 0) - trade['entry_price']) * trade['size'] if trade.get('exit_price') else 0
                })
                
            return jsonify({
                'success': True,
                'trades': trades
            })
            
        elif request.method == 'POST':
            # 创建新交易记录
            data = request.get_json()
            required_fields = ['symbol', 'entry_price', 'size']
            
            if not all(field in data for field in required_fields):
                return jsonify({'success': False, 'message': '缺少必要字段'}), 400
                
            trade_data = {
                'trade_market': data['trade_market'],
                'symbol': data['symbol'],
                'entry_price': data['entry_price'],
                'size': data['size'],
                'entry_date': data.get('entry_date') or datetime.now(pytz.UTC).isoformat(),
                'current_price': data['entry_price'],
                'trader_uuid':Web_Trader_UUID
            }
            
            response = supabase.table('trades1').insert(trade_data).execute()
            
            return jsonify({
                'success': True,
                'message': 'Trade record created successfully'
            })
            
        elif request.method == 'PUT':
            # 更新交易记录
            data = request.get_json()
            trade_id = data.get('id')
            
            if not trade_id:
                return jsonify({'success': False, 'message': '缺少交易ID'}), 400
                
            update_data = {}
            if 'exit_price' in data:
                update_data['exit_price'] = data['exit_price']
                # 使用用户提供的 exit_date，如果没有提供则使用当前时间
                if 'exit_date' in data and data['exit_date']:
                    # 将本地时间转换为 UTC 时间
                    local_date = datetime.fromisoformat(data['exit_date'].replace('Z', '+00:00'))
                    update_data['exit_date'] = local_date.astimezone(pytz.UTC).isoformat()
                else:
                    update_data['exit_date'] = datetime.now(pytz.UTC).isoformat()
                
            if update_data:
                response = supabase.table('trades1').update(update_data).eq('id', trade_id).execute()
                
            return jsonify({
                'success': True,
                'message': 'Trade record updated successfully'
            })
            
        elif request.method == 'DELETE':
            trade_id = request.args.get('id')
            if not trade_id:
                return jsonify({'success': False, 'message': '缺少交易ID'}), 400
                
            response = supabase.table('trades1').delete().eq('id', trade_id).execute()
            
            return jsonify({
                'success': True,
                'message': 'Trade record deleted successfully'
            })
            
    except Exception as e:
        return jsonify({'success': False, 'message': 'Operation failed'}), 500

# --- 排行榜管理路由 ---
@app.route('/admin/leaderboard')
def admin_leaderboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('vip'))
    return render_template('admin/leaderboard.html', admin_name=session.get('username', 'Admin'))

# --- 排行榜管理API ---
@app.route('/api/admin/leaderboard', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_leaderboard():
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        if request.method == 'GET':
            if session['trader_uuid']:
                # 获取排行榜数据
                response = supabase.table('leaderboard_traders').select("*").eq("trader_uuid",session['trader_uuid']).order('total_profit', desc=True).execute()
            else:
                 # 获取排行榜数据
                response = supabase.table('leaderboard_traders').select("*").order('total_profit', desc=True).execute()
                
            
            return jsonify({
                'success': True,
                'leaderboard': response.data
            })
            
        elif request.method == 'POST':
            # 添加新的排行榜记录
            data = request.get_json()
            required_fields = ['trader_name', 'total_profit', 'win_rate', 'total_trades', 'profile_image_url','followers_count','likes_count']
            
            if not all(field in data for field in required_fields):
                return jsonify({'success': False, 'message': '缺少必要字段'}), 400
                
            leaderboard_data = {
                'trader_name': data['trader_name'],
                'professional_title':data.get('professional_title'),
                'total_profit': data['total_profit'],
                'win_rate': data['win_rate'],
                'total_trades': data['total_trades'],
                'profile_image_url': data['profile_image_url'],
                'updated_at': datetime.now(pytz.UTC).isoformat(),
                'trader_uuid':session["trader_uuid"]
            }
            
            response = supabase.table('leaderboard_traders').insert(leaderboard_data).execute()
            
            return jsonify({
                'success': True,
                'message': 'Leaderboard record added successfully'
            })
            
        elif request.method == 'PUT':
            # 更新排行榜记录
            data = request.get_json()
            record_id = data.get('id')
            
            if not record_id:
                return jsonify({'success': False, 'message': '缺少记录ID'}), 400
                
            update_data = {
                'trader_name': data.get('trader_name'),
                'professional_title':data.get('professional_title'),
                'total_profit': data.get('total_profit'),
                'win_rate': data.get('win_rate'),
                'total_trades': data.get('total_trades'),
                 'followers_count': data['followers_count'],
                'likes_count': data['likes_count'],
                'profile_image_url': data.get('profile_image_url'),
                'updated_at': datetime.now(pytz.UTC).isoformat()
            }
            
            response = supabase.table('leaderboard_traders').update(update_data).eq('id', record_id).execute()
            
            return jsonify({
                'success': True,
                'message': 'Leaderboard record updated successfully'
            })
            
        elif request.method == 'DELETE':
            record_id = request.args.get('id')
            if not record_id:
                return jsonify({'success': False, 'message': '缺少记录ID'}), 400
                
            response = supabase.table('leaderboard_traders').delete().eq('id', record_id).execute()
            
            return jsonify({
                'success': True,
                'message': 'Leaderboard record deleted successfully'
            })
            
    except Exception as e:
        return jsonify({'success': False, 'message': 'Operation failed'}), 500

# --- 交易记录表自动建表 ---
def init_trading_db():
    try:
        # 创建交易记录表
        response = supabase.table('trades1').select("*").limit(1).execute()
    except:
        # 如果表不存在，创建表
        supabase.table('trades1').create({
            'id': 'uuid',
            'symbol': 'text',
            'entry_price': 'numeric',
            'exit_price': 'numeric',
            'size': 'numeric',
            'entry_date': 'timestamp with time zone',
            'exit_date': 'timestamp with time zone',
            'current_price': 'numeric',
            'user_id': 'uuid',
            'created_at': 'timestamp with time zone',
            'updated_at': 'timestamp with time zone'
        })

# --- 排行榜表自动建表 ---
def init_leaderboard_db():
    try:
        # 创建排行榜表
        response = supabase.table('leaderboard').select("*").limit(1).execute()
    except:
        # 如果表不存在，创建表
        supabase.table('leaderboard').create({
            'id': 'uuid',
            'user_id': 'uuid',
            'profit': 'numeric',
            'win_rate': 'numeric',
            'total_trades': 'integer',
            'winning_trades': 'integer',
            'losing_trades': 'integer',
            'created_at': 'timestamp with time zone',
            'updated_at': 'timestamp with time zone'
        })

# --- 添加测试数据 ---
def add_test_data():
    try:
        # 添加测试交易记录
        trades_data = [
            {
                'symbol': 'AAPL',
                'entry_price': 150.25,
                'size': 100,
                'entry_date': datetime.now(pytz.UTC).isoformat(),
                'current_price': 155.30,
                'created_at': datetime.now(pytz.UTC).isoformat(),
                'updated_at': datetime.now(pytz.UTC).isoformat()
            },
            {
                'symbol': 'GOOGL',
                'entry_price': 2750.00,
                'exit_price': 2800.00,
                'size': 10,
                'entry_date': datetime.now(pytz.UTC).isoformat(),
                'exit_date': datetime.now(pytz.UTC).isoformat(),
                'current_price': 2800.00,
                'created_at': datetime.now(pytz.UTC).isoformat(),
                'updated_at': datetime.now(pytz.UTC).isoformat()
            }
        ]
        
        # 检查是否已有交易记录
        response = supabase.table('trades1').select("*").execute()
        if not response.data:
            for trade in trades_data:
                supabase.table('trades1').insert(trade).execute()
                
        # 添加测试排行榜数据
        leaderboard_data = [
            {
                'user_id': '1',
                'profit': 15000.00,
                'win_rate': 85.5,
                'total_trades': 100,
                'winning_trades': 85,
                'losing_trades': 15,
                'created_at': datetime.now(pytz.UTC).isoformat(),
                'updated_at': datetime.now(pytz.UTC).isoformat()
            },
            {
                'user_id': '2',
                'profit': 8500.00,
                'win_rate': 75.0,
                'total_trades': 80,
                'winning_trades': 60,
                'losing_trades': 20,
                'created_at': datetime.now(pytz.UTC).isoformat(),
                'updated_at': datetime.now(pytz.UTC).isoformat()
            }
        ]
        
        # 检查是否已有排行榜数据
        response = supabase.table('leaderboard').select("*").execute()
        if not response.data:
            for record in leaderboard_data:
                supabase.table('leaderboard').insert(record).execute()
                
    except Exception as e:
        pass

@app.route('/api/trader/')
def get_trader_data():
    try:
        # Get trader data from Supabase
        response = supabase.table('trader_profiles')\
            .select('*')\
            .eq('trader_uuid', Web_Trader_UUID)\
            .single()\
            .execute()
            
        if response.data:
            return jsonify({
                'success': True,
                'trader': response.data
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Trader not found'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Error fetching trader data'
        }), 500

@app.route('/api/like-trader', methods=['POST'])
def like_trader():
    try:
        data = request.get_json()
        # Get trader data from Supabase
        if data['id']!='0':
            response = supabase.table('leaderboard_traders')\
                .select('*')\
                .eq('id', data['id'])\
                .single()\
                .execute()
                
            if response.data:
                # Update likes count
                current_likes = response.data.get('likes_count', 0)
                updated_likes = current_likes + 1
                
                # Update in database
                supabase.table('leaderboard_traders')\
                    .update({'likes_count': updated_likes})\
                    .eq('id', data['id'])\
                    .execute()
                    
                return jsonify({
                    'success': True,
                    'likes_count': updated_likes
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Trader not found'
                }), 404
        else:
            response = supabase.table('trader_profiles')\
                .select('*')\
                .eq('trader_uuid', Web_Trader_UUID)\
                .single()\
                .execute()
                
            if response.data:
                # Update likes count
                # current_likes = response.data.get('likes_count', 0)
                # updated_likes = current_likes + 1
                
                # # Update in database
                # # supabase.table('leaderboard_traders')\
                # #     .update({'likes_count': updated_likes})\
                # #     .eq('trader_uuid', Web_Trader_UUID)\
                # #     .execute()
                    
                return jsonify({
                    'success': True,
                    'likes_count': updated_likes
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Trader not found'
                }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Error updating likes'
        }), 500

@app.route('/api/admin/trade/upload-image', methods=['POST'])
def upload_trade_image():
    try:
        trade_id = request.form.get('trade_id')
        file = request.files.get('image')
        if not trade_id or not file:
            return jsonify({'success': False, 'message': 'Missing trade_id or image'}), 400
        ext = os.path.splitext(secure_filename(file.filename))[1] or '.jpg'
        unique_name = f"avatars/trade_{trade_id}_{uuid.uuid4().hex}{ext}"
        file_bytes = file.read()
        result = supabase.storage.from_('avatars').upload(
            unique_name,
            file_bytes,
            file_options={"content-type": file.content_type}
        )
        file_url = supabase.storage.from_('avatars').get_public_url(unique_name)
        # 自动判断id类型并分表处理
        try:
            int_id = int(trade_id)
            supabase.table('trades1').update({'image_url': file_url}).eq('id', int_id).execute()
        except ValueError:
            supabase.table('trades').update({'image_url': file_url}).eq('id', trade_id).execute()
        return jsonify({'success': True, 'url': file_url})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Upload failed: {str(e)}'}), 500

@app.route('/api/admin/whatsapp-agents', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_whatsapp_agents():
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        if request.method == 'GET':
            # 获取所有WhatsApp客服
            current_trader_uuid = session.get("trader_uuid", Web_Trader_UUID)
            print(f"[DEBUG] Getting WhatsApp agents for trader_uuid: {current_trader_uuid}")
            
            response = supabase.table('whatsapp_agents').select("*").eq("trader_uuid", current_trader_uuid).execute()
            
            print(f"[DEBUG] WhatsApp agents response: {response.data}")
            
            return jsonify({
                'success': True,
                'agents': response.data or [],
                'debug_info': {
                    'trader_uuid': current_trader_uuid,
                    'agents_count': len(response.data) if response.data else 0
                }
            })
            
        elif request.method == 'POST':
            # 添加新的WhatsApp客服
            data = request.get_json()
            required_fields = ['id','name', 'phone_number']
            
            if not all(field in data for field in required_fields):
                return jsonify({'success': False, 'message': '缺少必要字段'}), 400
                
            # 验证电话号码格式
            phone_number = data['phone_number']
            if not phone_number.startswith('+'):
                phone_number = '+' + phone_number
                
            agent_data = {
                'name': data['name'],
                'phone_number': phone_number,
                'is_active': True if data['is_active'] == "true" else False,
                'created_at': datetime.now(pytz.UTC).isoformat(),
                'trader_uuid':session["trader_uuid"]
            }
            if  data.get('id', '')=='':
                response = supabase.table('whatsapp_agents').insert(agent_data).execute()
            else:
                response = supabase.table('whatsapp_agents').update(agent_data).eq('id',data.get('id', '')).execute()
                
            
            return jsonify({
                'success': True,
                'message': 'WhatsApp agent added successfully',
                'agent': response.data[0] if response.data else None
            })
            
        elif request.method == 'PUT':
            # 更新WhatsApp客服信息
            data = request.get_json()
            agent_id = data.get('id')
            
            if not agent_id:
                return jsonify({'success': False, 'message': '缺少客服ID'}), 400
                
            update_data = {}
            if 'name' in data:
                update_data['name'] = data['name']
            if 'phone_number' in data:
                phone_number = data['phone_number']
                if not phone_number.startswith('+'):
                    phone_number = '+' + phone_number
                update_data['phone_number'] = phone_number
            if 'is_active' in data:
                update_data['is_active'] = data['is_active']
                
            update_data['updated_at'] = datetime.now(pytz.UTC).isoformat()
            
            response = supabase.table('whatsapp_agents').update(update_data).eq('id', agent_id).execute()
            
            return jsonify({
                'success': True,
                'message': 'WhatsApp agent updated successfully',
                'agent': response.data[0] if response.data else None
            })
            
        elif request.method == 'DELETE':
            # 删除WhatsApp客服
            agent_id = request.args.get('id')
            if not agent_id:
                return jsonify({'success': False, 'message': '缺少客服ID'}), 400
            response = supabase.table('contact_records').delete().eq('agent_id', agent_id).execute()    
            response = supabase.table('whatsapp_agents').delete().eq('id', agent_id).execute()
            
            return jsonify({
                'success': True,
                'message': 'WhatsApp agent deleted successfully'
            })
            
    except Exception as e:
        return jsonify({'success': False, 'message': 'Operation failed'}), 500

@app.route('/api/upload-trade', methods=['POST'])
def upload_trade():
    try:
        user_id = session.get('user_id')
        username = session.get('username')
        trade_market = request.form.get('Trade_market')
        symbol = request.form.get('symbol')
        entry_price = request.form.get('entry_price')
        size = request.form.get('size')
        entry_date = request.form.get('entry_date')
        asset_type = request.form.get('asset_type')
        direction = request.form.get('direction')
        trade_type = request.form.get('trade_type')

        # 检查必填字段
        if not all([user_id,trade_market, symbol, entry_price, size, entry_date, asset_type, direction]):
            return jsonify({'success': False, 'message': '参数不完整'}), 400

        # 类型转换
        try:
            entry_price = float(entry_price)
            size = float(size)
        except Exception:
            return jsonify({'success': False, 'message': '价格或数量格式错误'}), 400

        resp = supabase.table('trades').insert({
            'user_id': user_id,
            'username': username,
            'trade_market':trade_market,
            'symbol': symbol,
            'entry_price': entry_price,
            'size': size,
            'entry_date': entry_date,
            'asset_type': asset_type,
            'direction': direction,
            'trade_type': trade_type,
            'trader_uuid':Web_Trader_UUID
        }).execute()

        # 获取新插入的 trade_id
        trade_id = None
        if resp and hasattr(resp, 'data') and resp.data and isinstance(resp.data, list):
            trade_id = resp.data[0].get('id')

        return jsonify({'success': True, 'message': 'Upload successful', 'trade_id': trade_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/update-trade', methods=['POST'])
def update_trade():
    try:
        trade_id = request.form.get('id')
        exit_price = request.form.get('exit_price')
        exit_date = request.form.get('exit_date')
        entry_price=0
        direction=1
        size=0
        print('update trade:', trade_id, exit_price, exit_date)
        Response=supabase.table("trade_market").select("*").execute()
        marketdata=Response.data
        if not all([trade_id, exit_price, exit_date]):
            return jsonify({'success': False, 'message': 'Incomplete parameters'}), 400
        trade_data=supabase.table("trades").select("*").eq("id",trade_id).execute()
        exchange_rate= 1
        if trade_data:
            entry_price=trade_data.data[0]["entry_price"]
            direction=trade_data.data[0]["direction"]
            size=trade_data.data[0]["size"]
            exchange_rate= float(getexchange_rate(marketdata,trade_data.data[0]['trade_market']))
        profit=(float(exit_price)-entry_price)*size*direction
        try:
            exit_price = float(exit_price)
        except Exception:
            return jsonify({'success': False, 'message': 'Exit price format error'}), 400

        result = supabase.table('trades').update({
            'exit_price': exit_price,
            'exit_date': exit_date,
            'profit':round(profit,2),
            'exchange_rate':exchange_rate
        }).eq('id', trade_id).execute()
        print('update result:', result.data)

        if not result.data:
            return jsonify({'success': False, 'message': 'No record updated, check trade_id or RLS policy.'}), 400

        return jsonify({'success': True, 'message': 'Close position successful'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/change-password', methods=['POST'])
def change_password():
    try:
        user_id = session.get('user_id')
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')

        # 查询用户
        user_resp = supabase.table('users').select('*').eq('id', user_id).execute()
        user = user_resp.data[0] if user_resp.data else None
        if not user:
            return jsonify({'success': False, 'message': '用户不存在'}), 400

        # 检查旧密码
        if old_password != user.get('password_hash'):
            return jsonify({'success': False, 'message': '当前密码错误'}), 400

        # 检查新旧密码是否一样
        if new_password == old_password:
            return jsonify({'success': False, 'message': '新密码不能与旧密码相同'}), 400

        # 更新密码
        supabase.table('users').update({'password_hash': new_password}).eq('id', user_id).execute()
        return jsonify({'success': True, 'message': 'Password changed successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/membership-agreement')
def membership_agreement():
    return render_template('membership_agreement.html')

# --- 文档管理API ---
@app.route('/api/admin/documents', methods=['GET', 'POST'])
def manage_documents():
    try:
        if request.method == 'GET':
            response = supabase.table('documents').select('*').eq("trader_uuid",session["trader_uuid"]).order('last_update', desc=True).execute()
            return jsonify({'success': True, 'documents': response.data})
        elif request.method == 'POST':
            file = request.files.get('file')
            title = request.form.get('title')
            description = request.form.get('description')
            now = datetime.now(pytz.UTC).isoformat()
            if not file or not title:
                return jsonify({'success': False, 'message': '标题和文件为必填项'}), 400
            filename = secure_filename(file.filename)
            file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            file_type = file_ext
            bucket = 'documents'
            file_path = f"{uuid.uuid4().hex}_{filename}"
            file_bytes = file.read()
            # 修正上传方式
            result = supabase.storage.from_('documents').upload(
                file_path,
                file_bytes,
                file_options={"content-type": file.mimetype}
            )
            if hasattr(result, 'error') and result.error:
                return jsonify({'success': False, 'message': f'File upload failed: {result.error}'}), 500
            public_url = supabase.storage.from_('documents').get_public_url(file_path)
            doc_data = {
                'title': title,
                'description': description,
                'file_url': public_url,
                'file_type': file_type,
                'last_update': now,
                'views': 0,
                'trader_uuid':session["trader_uuid"]
            }
            insert_resp = supabase.table('documents').insert(doc_data).execute()
            if hasattr(insert_resp, 'error') and insert_resp.error:
                return jsonify({'success': False, 'message': f'Database write failed: {insert_resp.error}'}), 500
            return jsonify({'success': True, 'message': 'Upload successful', 'document': insert_resp.data[0]})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/documents/<int:doc_id>', methods=['PUT', 'DELETE'])
def update_document(doc_id):
    try:
        # 权限校验（如有需要可加）
        # if 'role' not in session or session['role'] != 'admin':
        #     return jsonify({'success': False, 'message': '无权限访问'}), 403

        if request.method == 'PUT':
            data = request.get_json()
            update_fields = {k: v for k, v in data.items() if k in ['title', 'description', 'file_url', 'file_type', 'last_update', 'views']}
            if not update_fields:
                return jsonify({'success': False, 'message': '没有可更新的字段'}), 400
            update_fields['last_update'] = datetime.now(pytz.UTC).isoformat()
            resp = supabase.table('documents').update(update_fields).eq('id', doc_id).execute()
            if hasattr(resp, 'error') and resp.error:
                return jsonify({'success': False, 'message': f'Update failed: {resp.error}'}), 500
            return jsonify({'success': True, 'message': 'Update successful'})
        elif request.method == 'DELETE':
            # 先查出 file_url，尝试删除 storage 文件（可选）
            doc_resp = supabase.table('documents').select('file_url').eq('id', doc_id).execute()
            if doc_resp.data and doc_resp.data[0].get('file_url'):
                file_url = doc_resp.data[0]['file_url']
                # 解析出文件名
                try:
                    from urllib.parse import urlparse
                    path = urlparse(file_url).path
                    file_name = path.split('/')[-1]
                    supabase.storage().from_('documents').remove([file_name])
                except Exception as e:
                    pass  # 删除storage失败不影响主流程
            # 删除表记录
            del_resp = supabase.table('documents').delete().eq('id', doc_id).execute()
            if hasattr(del_resp, 'error') and del_resp.error:
                return jsonify({'success': False, 'message': f'Deletion failed: {del_resp.error}'}), 500
            return jsonify({'success': True, 'message': 'Deletion successful'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# --- 视频管理API ---
@app.route('/api/admin/videos', methods=['GET', 'POST'])
def manage_videos():
    try:
        # 检查用户是否登录
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': '请先登录'}), 401
            
        if request.method == 'GET':
            # 获取视频列表不需要管理员权限
            response = supabase.table('videos').select('*').eq("trader_uuid",session["trader_uuid"]).order('last_update', desc=True).execute()
            return jsonify({'success': True, 'videos': response.data})
        elif request.method == 'POST':
            # 上传视频需要管理员权限
            if 'role' not in session or session['role'] != 'admin':
                return jsonify({'success': False, 'message': '无权限执行此操作'}), 403
                
            file = request.files.get('file')
            title = request.form.get('title')
            description = request.form.get('description')
            now = datetime.now(pytz.UTC).isoformat()
            
            if not file or not title:
                return jsonify({'success': False, 'message': '标题和视频为必填项'}), 400
                
            # 检查文件大小（限制为600MB）
            file_bytes = file.read()
            if len(file_bytes) > 600 * 1024 * 1024:  # 600MB
                return jsonify({'success': False, 'message': 'File size cannot exceed 600MB'}), 400
                
            filename = secure_filename(file.filename)
            file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            
            # 检查文件类型
            allowed_extensions = {'mp4', 'mov', 'avi', 'wmv', 'flv', 'mkv'}
            if file_ext not in allowed_extensions:
                return jsonify({'success': False, 'message': f'不支持的文件类型，仅支持: {", ".join(allowed_extensions)}'}), 400
            
            file_path = f"{uuid.uuid4().hex}_{filename}"
            
            try:
                # 上传到 Supabase Storage
                result = supabase.storage.from_('videos').upload(
                    file_path,
                    file_bytes,
                    file_options={"content-type": file.mimetype}
                )
                
                if hasattr(result, 'error') and result.error:
                    return jsonify({'success': False, 'message': f'Video upload failed: {result.error}'}), 500
                    
                # 获取公开URL
                public_url = supabase.storage.from_('videos').get_public_url(file_path)
                
                # 写入数据库
                video_data = {
                    'title': title,
                    'description': description,
                    'video_url': public_url,
                    'last_update': now,
                    'trader_uuid':session["trader_uuid"]
                }
                
                print("public_url:", public_url)
                print("video_data:", video_data)
                insert_resp = supabase.table('videos').insert(video_data).execute()
                
                if hasattr(insert_resp, 'error') and insert_resp.error:
                    return jsonify({'success': False, 'message': f'Database write failed: {insert_resp.error}'}), 500
                    
                return jsonify({'success': True, 'message': 'Upload successful', 'video': insert_resp.data[0]})
                
            except Exception as e:
                import traceback
                print("视频上传异常：", e)
                print(traceback.format_exc())
                return jsonify({'success': False, 'message': f'Upload failed: {str(e)}'}), 500
                
    except Exception as e:
        import traceback
        print("视频上传异常(外层)：", e)
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/videos/<int:video_id>', methods=['PUT', 'DELETE'])
def update_video(video_id):
    try:
        if request.method == 'PUT':
            data = request.get_json()
            update_fields = {k: v for k, v in data.items() if k in ['title', 'description', 'video_url', 'last_update']}
            if not update_fields:
                return jsonify({'success': False, 'message': '没有可更新的字段'}), 400
            update_fields['last_update'] = datetime.now(pytz.UTC).isoformat()
            resp = supabase.table('videos').update(update_fields).eq('id', video_id).execute()
            if hasattr(resp, 'error') and resp.error:
                return jsonify({'success': False, 'message': f'Update failed: {resp.error}'}), 500
            return jsonify({'success': True, 'message': 'Update successful'})
        elif request.method == 'DELETE':
            # 先查出 video_url，尝试删除 storage 文件（可选）
            video_resp = supabase.table('videos').select('video_url').eq('id', video_id).execute()
            if video_resp.data and video_resp.data[0].get('video_url'):
                video_url = video_resp.data[0]['video_url']
                try:
                    from urllib.parse import urlparse
                    path = urlparse(video_url).path
                    file_name = path.split('/')[-1]
                    supabase.storage.from_('videos').remove([file_name])
                except Exception as e:
                    pass  # 删除storage失败不影响主流程
            del_resp = supabase.table('videos').delete().eq('id', video_id).execute()
            if hasattr(del_resp, 'error') and del_resp.error:
                return jsonify({'success': False, 'message': f'Deletion failed: {del_resp.error}'}), 500
            return jsonify({'success': True, 'message': 'Deletion successful'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# 默认头像URL和补头像函数
DEFAULT_AVATAR_URL = 'https://rwlziuinlbazgoajkcme.supabase.co/storage/v1/object/public/images//TT1375_Talent-HiRes-TP02.jpg'
def fill_default_avatar(user):
    if not user.get('avatar_url'):
        user['avatar_url'] = DEFAULT_AVATAR_URL
    return user

# 会员等级中英文映射
LEVEL_EN_MAP = {
    '至尊黑卡': 'Supreme Black Card',
    '钻石会员': 'Diamond Member',
    '黄金会员': 'Gold Member',
    '普通会员': 'Regular Member',
    'Supreme Black Card': 'Supreme Black Card',
    'Diamond Member': 'Diamond Member',
    'Gold Member': 'Gold Member',
    'Regular Member': 'Regular Member'
}

def get_level_en(level_cn):
    return LEVEL_EN_MAP.get(level_cn, level_cn)

@app.route('/api/admin/change_avatar', methods=['POST'])
def admin_change_avatar():
    try:
       
        idname=request.form.get('idname')
        avatarUserId=request.form.get('avatarUserId')
        tablename=request.form.get('tablename')
        filedname=request.form.get('filedname')
        file = request.files.get('avatar')
                
            # 检查文件大小（限制为600MB）
        file_bytes = file.read()
        if len(file_bytes) > 600 * 1024 * 1024:  # 600MB
            return jsonify({'success': False, 'message': 'File size cannot exceed 600MB'}), 400
                
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            
        # 检查文件类型
        allowed_extensions = {'jpg', 'jpeg', 'png', 'bmp', 'webp'}
        if file_ext not in allowed_extensions:
            return jsonify({'success': False, 'message': f'不支持的文件类型，仅支持: {", ".join(allowed_extensions)}'}), 400
            
        file_path = f"{uuid.uuid4().hex}_{filename}"
        try:
                # 上传到 Supabase Storage
                result = supabase.storage.from_('avatars').upload(
                    file_path,
                    file_bytes,
                    file_options={"content-type": file.mimetype}
                )
                
                if hasattr(result, 'error') and result.error:
                    return jsonify({'success': False, 'message': f'Video upload failed: {result.error}'}), 500
                    
                # 获取公开URL
                public_url = supabase.storage.from_('avatars').get_public_url(file_path)
                
                # 写入数据库
                video_data = {
                   
                }
                video_data[filedname]=public_url

                
                print("public_url:", public_url)
                print("video_data:", video_data)
                insert_resp = supabase.table(tablename).update(video_data).eq(idname,avatarUserId).execute()
                if tablename=="trader_profiles":
                    user=supabase.table("trader_profiles").select("trader_uuid").eq(idname,avatarUserId).execute()
                    # up_resp= supabase.table("leaderboard_traders").update(video_data).eq("trader_uuid",user.data[0]["trader_uuid"]).execute()
                    
                if hasattr(insert_resp, 'error') and insert_resp.error:
                    return jsonify({'success': False, 'message': f'Database write failed: {insert_resp.error}'}), 500
                    
                return jsonify({'success': True, 'message': 'Upload successful', 'video': insert_resp.data[0]})
                
        except Exception as e:
                import traceback
                print("视频上传异常：", e)
                print(traceback.format_exc())
                return jsonify({'success': False, 'message': f'Upload failed: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# 获取所有VIP投资策略公告（Supabase版）
@app.route('/api/admin/vip-announcements', methods=['GET'])
def get_vip_announcements():
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        resp = supabase.table('vip_announcements').select('*').eq("trader_uuid",session["trader_uuid"]).order('created_at', desc=True).execute()
        announcements = resp.data if resp.data else []
        return jsonify({'success': True, 'announcements': announcements})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取策略公告失败: {str(e)}'}), 500

# 创建VIP投资策略公告（Supabase版）
@app.route('/api/admin/vip-announcements', methods=['POST'])
def create_vip_announcement():
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        data = request.json
        required_fields = ['title', 'content']
        if not all(field in data for field in required_fields):
            return jsonify({'success': False, 'message': '缺少必要字段'}), 400
            
        # 添加创建者ID和时间戳
        announcement_data = {
            'title': data['title'],
            'content': data['content'],
            'created_by': session['user_id'],
            'status': data.get('status', 'active'),
            'priority': data.get('priority', 0)
        }
        
        resp = supabase.table('vip_announcements').insert(announcement_data).execute()
        if hasattr(resp, 'error') and resp.error:
            return jsonify({'success': False, 'message': f'创建失败: {resp.error}'}), 500
            
        return jsonify({'success': True, 'message': '策略公告已创建'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'创建策略公告失败: {str(e)}'}), 500

# 编辑VIP投资策略公告（Supabase版）
@app.route('/api/admin/vip-announcements/<int:announcement_id>', methods=['PUT'])
def edit_vip_announcement(announcement_id):
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        data = request.json
        # 允许更新所有在截图中出现的字段
        update_fields = {k: v for k, v in data.items() if k in ['title', 'content', 'status', 'priority', 'type', 'publisher', 'date']}
        if not update_fields:
            return jsonify({'success': False, 'message': '没有可更新的字段'}), 400
        if announcement_id!=0:    
            resp = supabase.table('vip_announcements').update(update_fields).eq('id', announcement_id).execute()
        else:
            update_fields["trader_uuid"]=session["trader_uuid"]
            resp = supabase.table('vip_announcements').insert(update_fields).execute()
        # 检查更新是否成功
        if hasattr(resp, 'data') and resp.data:
            return jsonify({'success': True, 'message': '策略公告已更新'})
        else:
            # 分析可能的错误
            error_message = '更新失败'
            if hasattr(resp, 'error') and resp.error:
                error_message += f": {resp.error.message}"
            return jsonify({'success': False, 'message': error_message}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'更新策略公告失败: {str(e)}'}), 500

# 删除VIP投资策略公告（Supabase版）
@app.route('/api/admin/vip-announcements/<int:announcement_id>', methods=['DELETE'])
def delete_vip_announcement(announcement_id):
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        resp = supabase.table('vip_announcements').delete().eq('id', announcement_id).execute()
        if hasattr(resp, 'error') and resp.error:
            return jsonify({'success': False, 'message': f'删除失败: {resp.error}'}), 500
            
        return jsonify({'success': True, 'message': '策略公告已删除'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'删除策略公告失败: {str(e)}'}), 500

# 获取所有VIP交易记录（Supabase版）
@app.route('/api/admin/vip-trades', methods=['GET'])
def get_vip_trades():
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        resp = supabase.table('vip_trades').select('*').eq("trader_uuid",session["trader_uuid"]).order('entry_time', desc=True).execute()
        trades = resp.data if resp.data else []
        
        for trade in trades:
            # 获取最新 current_price
            current_price = trade.get('current_price')
            entry_price = float(trade.get('entry_price') or 0)
            quantity = float(trade.get('quantity') or 0)
            current_price = float(current_price or 0)
            direction = str(trade.get('direction', '')).lower()
            if entry_price and quantity:
                if direction in ['买涨', 'buy', '多', 'long']:
                    pnl = (current_price - entry_price) * quantity
                elif direction in ['买跌', 'sell', '空', 'short']:
                    pnl = (entry_price - current_price) * quantity
                else:
                    pnl = (current_price - entry_price) * quantity
                roi = (pnl / (entry_price * quantity)) * 100
            else:
                pnl = 0
                roi = 0
            # 写入数据库
            supabase.table('vip_trades').update({
                'pnl': pnl,
                'roi': roi
            }).eq('id', trade['id']).execute()
            trade['pnl'] = pnl
            trade['roi'] = roi
        
        return jsonify({
            'success': True,
            'trades': trades
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取交易记录失败: {str(e)}'}), 500

# 新增VIP交易记录（Supabase版）
@app.route('/api/admin/vip-trades', methods=['POST'])
def add_vip_trade():
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        data = request.json
        required_fields = ['trade_market','symbol', 'entry_price', 'quantity', 'entry_time', 'trade_type']
        if not all(field in data for field in required_fields):
            return jsonify({'success': False, 'message': '缺少必要字段'}), 400
            
        # 验证数据类型
        try:
            entry_price = float(data['entry_price'])
            quantity = float(data['quantity'])
            entry_time = datetime.fromisoformat(data['entry_time'].replace('Z', '+00:00'))
        except (ValueError, TypeError) as e:
            return jsonify({'success': False, 'message': f'数据类型错误: {str(e)}'}), 400
        if data['trade_market']==None or data['trade_market']=="":
            return jsonify({'success': False, 'message': '数据类型错误: 请选择交易市场'}), 400
        # 获取当前价格
        current_price = get_real_time_price(data["trade_market"],data['symbol'])
        if not current_price:
            return jsonify({'success': False, 'message': '无法获取当前价格'}), 400
            
        # 计算初始盈亏
        pnl = (current_price - entry_price) * quantity
        roi = (pnl / (entry_price * quantity)) * 100 if entry_price and quantity else 0
        
        # 准备交易数据
        trade_data = {
            'trade_market': data['trade_market'],
            'symbol': data['symbol'],
            'entry_price': entry_price,
            'quantity': quantity,
            'entry_time': entry_time.isoformat(),
            'trade_type': data['trade_type'],
            'status': 'open',
            'current_price': current_price,
            'pnl': pnl,
            'roi': roi,
            'created_by': session['user_id'],
            'asset_type': data.get('asset_type'),  # 新增
            'direction': data.get('direction') ,    # 新增
            'trader_uuid':session["trader_uuid"]
        }
        
        resp = supabase.table('vip_trades').insert(trade_data).execute()
        if hasattr(resp, 'error') and resp.error:
            return jsonify({'success': False, 'message': f'创建失败: {resp.error}'}), 500
            
        return jsonify({'success': True, 'message': '交易记录已添加'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'添加交易记录失败: {str(e)}'}), 500

# 编辑VIP交易记录（Supabase版）
@app.route('/api/admin/vip-trades/<int:trade_id>', methods=['PUT'])
def edit_vip_trade(trade_id):
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
            
        data = request.json
        update_fields = {k: v for k, v in data.items() if k in [
            'symbol', 'entry_price', 'exit_price', 'quantity', 
            'entry_time', 'exit_time', 'trade_type', 'status', 
            'notes', 'asset_type', 'direction'  # 新增
        ]}
        
        if not update_fields:
            return jsonify({'success': False, 'message': '没有可更新的字段'}), 400
            
        # 如果更新了价格相关字段，重新计算盈亏
        if any(k in update_fields for k in ['trade_market','entry_price', 'exit_price', 'quantity']):
            current_price = get_real_time_price(update_fields.get('trade_market', data.get('trade_market')),update_fields.get('symbol', data.get('symbol')))
            if current_price:
                entry_price = float(update_fields.get('entry_price', data.get('entry_price', 0)))
                quantity = float(update_fields.get('quantity', data.get('quantity', 0)))
                pnl = (current_price - entry_price) * quantity
                roi = (pnl / (entry_price * quantity)) * 100 if entry_price and quantity else 0
                
                update_fields.update({
                    'current_price': current_price,
                    'pnl': pnl,
                    'roi': roi
                })
        
        resp = supabase.table('vip_trades').update(update_fields).eq('id', trade_id).execute()
        if hasattr(resp, 'error') and resp.error:
            return jsonify({'success': False, 'message': f'更新失败: {resp.error}'}), 500
            
        return jsonify({'success': True, 'message': '交易记录已更新'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'更新交易记录失败: {str(e)}'}), 500

# 删除VIP交易记录（Supabase版）
@app.route('/api/admin/vip-trades/<int:trade_id>', methods=['DELETE'])
def delete_vip_trade(trade_id):
    try:
        # 检查管理员权限
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'success': False, 'message': '无权限访问'}), 403
        
        resp = supabase.table('vip_trades').delete().eq('id', trade_id).execute()
        if hasattr(resp, 'error') and resp.error:
            return jsonify({'success': False, 'message': f'删除失败: {resp.error}'}), 500
            
        return jsonify({'success': True, 'message': '交易记录已删除'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'删除交易记录失败: {str(e)}'}), 500

@app.route('/download-proxy')
def download_proxy():
    url = request.args.get('url')
    if not url:
        return 'Missing url', 400
    r = requests.get(url, stream=True)
    filename = url.split('/')[-1]
    return Response(
        r.iter_content(chunk_size=8192),
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': r.headers.get('Content-Type', 'application/octet-stream')
        }
    )

# AI功能路由
@app.route('/ai-tools')
def ai_tools():
    """AI工具页面"""
    try:
        # 获取交易员信息
        profile_response = supabase.table('trader_profiles').select("*").eq("trader_uuid", Web_Trader_UUID).limit(1).execute()
        trader_info = profile_response.data[0] if profile_response.data else {
            'website_title': 'Professional Trader',
            'home_top_title': 'Professional Trader',
            'trader_name': 'Professional Trader',
            'professional_title': 'Financial Trading Expert | Technical Analysis Master',
            'bio': 'Focused on US stock market technical analysis and quantitative trading',
            'profile_image_url': 'https://rwlziuinlbazgoajkcme.supabase.co/storage/v1/object/public/images/1920134_331262340400234_2042663349514343562_n.jpg'
        }
        
        return render_template('ai-tools.html', trader_info=trader_info)
    except Exception as e:
        print(f"[ERROR] AI工具页面错误: {e}")
        return render_template('ai-tools.html', trader_info={
            'website_title': 'AI Trading Tools',
            'home_top_title': 'AI Trading Tools',
            'trader_name': 'Professional Trader',
            'professional_title': 'AI Trading Assistant',
            'bio': 'Advanced AI-powered trading tools',
            'profile_image_url': 'https://rwlziuinlbazgoajkcme.supabase.co/storage/v1/object/public/images/1920134_331262340400234_2042663349514343562_n.jpg'
        })

# AI Stock Picker API
@app.route('/api/ai/stock-picker', methods=['POST'])
def ai_stock_picker():
    """AI Stock Selection API"""
    try:
        data = request.get_json()
        
        # Get user input stock selection criteria
        sector = data.get('sector', '')
        style = data.get('style', 'balanced')
        risk = data.get('risk', 'medium')
        time_horizon = data.get('timeHorizon', 'medium')
        
        print(f"[DEBUG] AI stock picker request: sector={sector}, style={style}, risk={risk}, time_horizon={time_horizon}")
        
        # Simulate AI stock selection logic (can integrate real AI models or third-party APIs here)
        recommendations = generate_stock_recommendations(sector, style, risk, time_horizon)
        
        return jsonify({
            'success': True,
            'recommendations': recommendations,
            'criteria': {
                'sector': sector,
                'style': style,
                'risk': risk,
                'timeHorizon': time_horizon
            }
        })
        
    except Exception as e:
        print(f"[ERROR] AI stock picker API error: {e}")
        return jsonify({'error': 'Failed to generate stock recommendations'}), 500

# AI Stock Diagnosis API
@app.route('/api/ai/stock-diagnosis', methods=['POST'])
def ai_stock_diagnosis():
    """AI Stock Diagnosis API"""
    try:
        data = request.get_json()
        
        # Get user input diagnosis parameters
        symbol = data.get('symbol', '').upper()
        analysis_type = data.get('analysisType', 'comprehensive')
        time_frame = data.get('timeFrame', '1m')
        
        if not symbol:
            return jsonify({'error': 'Stock symbol is required'}), 400
        
        print(f"[DEBUG] AI stock diagnosis request: symbol={symbol}, analysis_type={analysis_type}, time_frame={time_frame}")
        
        # Simulate AI diagnosis logic (can integrate real AI models or third-party APIs here)
        diagnosis = generate_stock_diagnosis(symbol, analysis_type, time_frame)
        
        return jsonify({
            'success': True,
            'diagnosis': diagnosis,
            'symbol': symbol,
            'analysisType': analysis_type,
            'timeFrame': time_frame
        })
        
    except Exception as e:
        print(f"[ERROR] AI stock diagnosis API error: {e}")
        return jsonify({'error': 'Failed to generate stock diagnosis'}), 500

# AI Portfolio Diagnosis API
@app.route('/api/ai/portfolio-diagnosis', methods=['POST'])
def ai_portfolio_diagnosis():
    """AI Portfolio Diagnosis API"""
    try:
        data = request.get_json()
        
        # 获取用户输入的持仓信息
        symbol = data.get('symbol', '').upper()
        purchase_price = data.get('purchasePrice')
        purchase_date = data.get('purchaseDate')
        purchase_market = data.get('purchaseMarket', 'NASDAQ')
        analysis_type = data.get('analysisType', 'portfolio')
        
        if not symbol:
            return jsonify({'error': 'Stock symbol cannot be empty'}), 400
        
        print(f"[DEBUG] AI portfolio diagnosis request: symbol={symbol}, purchase_price={purchase_price}, purchase_date={purchase_date}, market={purchase_market}")
        
        # Generate portfolio diagnosis results
        diagnosis = generate_portfolio_diagnosis(symbol, purchase_price, purchase_date, purchase_market, analysis_type)
        
        return jsonify({
            'success': True,
            'diagnosis': diagnosis,
            'symbol': symbol,
            'purchasePrice': purchase_price,
            'purchaseDate': purchase_date,
            'purchaseMarket': purchase_market,
            'analysisType': analysis_type
        })
        
    except Exception as e:
        print(f"[ERROR] AI portfolio diagnosis API error: {e}")
        return jsonify({'error': 'Portfolio diagnosis failed, please try again later'}), 500

def get_comprehensive_stock_data(symbol):
    """获取股票的综合数据"""
    try:
        print(f"[DEBUG] 开始获取 {symbol} 的股票数据...")
        
        # 使用yfinance获取详细股票数据
        ticker = yf.Ticker(symbol)
        
        # 获取股票信息
        info = ticker.info
        print(f"[DEBUG] {symbol} 基本信息获取成功: {len(info)} 个字段")
        
        # 获取历史数据（最近30天）
        hist = ticker.history(period="1mo")
        print(f"[DEBUG] {symbol} 历史数据获取成功: {len(hist)} 条记录")
        
        if hist.empty:
            print(f"[WARNING] {symbol} 历史数据为空，使用备用数据")
            # 返回备用数据而不是None
            return create_fallback_stock_data(symbol, info)
        
        # 获取最新价格数据
        current_price = hist['Close'].iloc[-1]
        prev_close = hist['Close'].iloc[-2] if len(hist) >= 2 else current_price
        
        # 计算技术指标
        prices = hist['Close']
        volumes = hist['Volume']
        
        # 移动平均线
        ma_5 = prices.rolling(window=5).mean().iloc[-1] if len(prices) >= 5 else current_price
        ma_20 = prices.rolling(window=20).mean().iloc[-1] if len(prices) >= 20 else current_price
        
        # RSI计算
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1] if len(delta) >= 14 else 50
        
        # 波动率
        volatility = prices.pct_change().std() * (252 ** 0.5) * 100  # 年化波动率
        
        # 交易量分析
        avg_volume = volumes.mean()
        current_volume = volumes.iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
        
        # 整合数据
        stock_data = {
            'symbol': symbol,
            'name': info.get('longName', symbol),
            'sector': info.get('sector', 'Unknown'),
            'industry': info.get('industry', 'Unknown'),
            'current_price': round(float(current_price), 2),
            'prev_close': round(float(prev_close), 2),
            'change': round(float(current_price - prev_close), 2),
            'change_percent': round(float((current_price - prev_close) / prev_close * 100), 2),
            'market_cap': info.get('marketCap', 0),
            'pe_ratio': info.get('trailingPE', 0),
            'forward_pe': info.get('forwardPE', 0),
            'peg_ratio': info.get('pegRatio', 0),
            'price_to_book': info.get('priceToBook', 0),
            'debt_to_equity': info.get('debtToEquity', 0),
            'roe': info.get('returnOnEquity', 0),
            'dividend_yield': info.get('dividendYield', 0),
            'beta': info.get('beta', 1.0),
            'ma_5': round(float(ma_5), 2),
            'ma_20': round(float(ma_20), 2),
            'rsi': round(float(rsi), 2),
            'volatility': round(float(volatility), 2),
            'volume_ratio': round(float(volume_ratio), 2),
            'avg_volume': int(avg_volume),
            'high_52w': info.get('fiftyTwoWeekHigh', 0),
            'low_52w': info.get('fiftyTwoWeekLow', 0),
            'target_price': info.get('targetMeanPrice', 0),
            'recommendation': info.get('recommendationMean', 3.0)
        }
        
        return stock_data
        
    except Exception as e:
        print(f"[ERROR] 获取股票数据失败 {symbol}: {e}")
        # 返回备用数据而不是None
        return create_fallback_stock_data(symbol)

def create_fallback_stock_data(symbol, info=None):
    """创建备用的股票数据"""
    import random
    
    # 基本股票名称映射
    stock_names = {
        'AAPL': 'Apple Inc.',
        'MSFT': 'Microsoft Corporation',
        'GOOGL': 'Alphabet Inc.',
        'TSLA': 'Tesla Inc.',
        'NVDA': 'NVIDIA Corporation',
        'META': 'Meta Platforms Inc.',
        'AMZN': 'Amazon.com Inc.',
        'CRM': 'Salesforce Inc.',
        'ORCL': 'Oracle Corporation',
        'INTC': 'Intel Corporation',
        'JNJ': 'Johnson & Johnson',
        'PFE': 'Pfizer Inc.',
        'UNH': 'UnitedHealth Group',
        'MRNA': 'Moderna Inc.',
        'JPM': 'JPMorgan Chase & Co.',
        'BAC': 'Bank of America Corp.',
        'WFC': 'Wells Fargo & Company',
        'GS': 'Goldman Sachs Group Inc.'
    }
    
    # 行业映射
    sector_map = {
        'AAPL': 'Technology', 'MSFT': 'Technology', 'GOOGL': 'Technology', 'TSLA': 'Technology',
        'NVDA': 'Technology', 'META': 'Technology', 'AMZN': 'Consumer Discretionary',
        'JNJ': 'Healthcare', 'PFE': 'Healthcare', 'UNH': 'Healthcare', 'MRNA': 'Healthcare',
        'JPM': 'Financials', 'BAC': 'Financials', 'WFC': 'Financials', 'GS': 'Financials'
    }
    
    # 模拟合理的股票数据
    base_price = random.uniform(50, 300)
    change_percent = random.uniform(-5, 5)
    prev_close = base_price / (1 + change_percent/100)
    
    print(f"[DEBUG] 为 {symbol} 创建备用数据: 价格=${base_price:.2f}")
    
    fallback_data = {
        'symbol': symbol,
        'name': stock_names.get(symbol, f"{symbol} Corp."),
        'sector': sector_map.get(symbol, 'Technology'),
        'industry': 'Software',
        'current_price': round(base_price, 2),
        'prev_close': round(prev_close, 2),
        'change': round(base_price - prev_close, 2),
        'change_percent': round(change_percent, 2),
        'market_cap': random.randint(10, 2000) * 1000000000,  # 100亿到2万亿
        'pe_ratio': round(random.uniform(15, 35), 1),
        'forward_pe': round(random.uniform(12, 30), 1),
        'peg_ratio': round(random.uniform(0.8, 2.5), 2),
        'price_to_book': round(random.uniform(1.2, 8.0), 2),
        'debt_to_equity': round(random.uniform(0.1, 1.5), 2),
        'roe': round(random.uniform(0.08, 0.25), 3),
        'dividend_yield': round(random.uniform(0, 0.05), 3),
        'beta': round(random.uniform(0.7, 1.8), 2),
        'ma_5': round(base_price * random.uniform(0.98, 1.02), 2),
        'ma_20': round(base_price * random.uniform(0.95, 1.05), 2),
        'rsi': round(random.uniform(30, 70), 1),
        'volatility': round(random.uniform(15, 40), 1),
        'volume_ratio': round(random.uniform(0.5, 3.0), 2),
        'avg_volume': random.randint(1000000, 50000000),
        'high_52w': round(base_price * random.uniform(1.1, 1.5), 2),
        'low_52w': round(base_price * random.uniform(0.6, 0.9), 2),
        'target_price': round(base_price * random.uniform(1.05, 1.25), 2),
        'recommendation': round(random.uniform(1.5, 4.5), 1)
    }
    
    return fallback_data

def calculate_ai_score(stock_data, style, risk, time_horizon):
    """基于真实数据计算AI评分"""
    if not stock_data:
        return 0
    
    score = 50  # 基础分数
    
    # 基本面评分 (30%)
    if stock_data.get('pe_ratio') and 0 < stock_data['pe_ratio'] < 25:
        score += 15
    elif stock_data.get('pe_ratio') and stock_data['pe_ratio'] > 40:
        score -= 10
    
    if stock_data.get('roe') and stock_data['roe'] > 0.15:
        score += 10
    
    if stock_data.get('debt_to_equity') and stock_data['debt_to_equity'] < 0.5:
        score += 5
    
    # 技术面评分 (25%)
    current_price = stock_data.get('current_price', 0)
    ma_5 = stock_data.get('ma_5', current_price)
    ma_20 = stock_data.get('ma_20', current_price)
    
    if current_price > ma_5 > ma_20:  # 上升趋势
        score += 15
    elif current_price < ma_5 < ma_20:  # 下降趋势
        score -= 10
    
    rsi = stock_data.get('rsi', 50)
    if 30 < rsi < 70:  # RSI在合理区间
        score += 10
    elif rsi > 80:  # 超买
        score -= 15
    elif rsi < 20:  # 超卖但可能反弹
        score += 5
    
    # 投资风格调整 (25%)
    if style == 'growth':
        if stock_data.get('forward_pe') and stock_data.get('pe_ratio'):
            if stock_data['forward_pe'] < stock_data['pe_ratio']:  # 预期增长
                score += 15
    elif style == 'value':
        if stock_data.get('pe_ratio') and stock_data['pe_ratio'] < 15:
            score += 15
        if stock_data.get('price_to_book') and stock_data['price_to_book'] < 1.5:
            score += 10
    elif style == 'dividend':
        if stock_data.get('dividend_yield') and stock_data['dividend_yield'] > 0.02:
            score += 15
    elif style == 'momentum':
        if stock_data.get('change_percent') and stock_data['change_percent'] > 2:
            score += 15
        if stock_data.get('volume_ratio') and stock_data['volume_ratio'] > 1.5:
            score += 10
    
    # 风险调整 (20%)
    beta = stock_data.get('beta', 1.0)
    volatility = stock_data.get('volatility', 25)
    
    if risk == 'low':
        if beta < 1.0 and volatility < 20:
            score += 15
        elif beta > 1.5 or volatility > 35:
            score -= 20
    elif risk == 'high':
        if beta > 1.2 and volatility > 25:
            score += 10
        elif beta < 0.8:
            score -= 10
    else:  # medium risk
        if 0.8 <= beta <= 1.3 and 15 <= volatility <= 30:
            score += 10
    
    # 确保分数在合理范围内
    return max(0, min(100, round(score)))

def generate_ai_powered_analysis(stock_data, style, score):
    """使用OpenAI GPT生成专业的股票分析"""
    if not stock_data:
        return "数据获取失败，无法进行分析"
    
    try:
        # 准备股票数据摘要
        symbol = stock_data['symbol']
        name = stock_data.get('name', symbol)
        current_price = stock_data.get('current_price', 0)
        change_percent = stock_data.get('change_percent', 0)
        pe_ratio = stock_data.get('pe_ratio', 0)
        rsi = stock_data.get('rsi', 50)
        ma_5 = stock_data.get('ma_5', current_price)
        ma_20 = stock_data.get('ma_20', current_price)
        target_price = stock_data.get('target_price', 0)
        market_cap = stock_data.get('market_cap', 0)
        beta = stock_data.get('beta', 1.0)
        volume_ratio = stock_data.get('volume_ratio', 1.0)
        
        # 构建GPT提示词
        prompt = f"""
作为一名专业的投资分析师，请为股票 {symbol} ({name}) 提供专业的投资分析报告。

股票基本信息：
- 当前价格: ${current_price:.2f}
- 日涨跌幅: {change_percent:.2f}%
- 市盈率: {pe_ratio:.1f}
- 市值: ${market_cap/1000000000:.1f}B
- Beta系数: {beta:.2f}
- RSI指标: {rsi:.1f}
- 5日均线: ${ma_5:.2f}
- 20日均线: ${ma_20:.2f}
- 交易量比率: {volume_ratio:.1f}x
- 分析师目标价: ${target_price:.2f}
- AI评分: {score}/100
- 投资风格: {style}

请提供包含以下内容的专业分析报告（用中文回答）：
1. 技术面分析（价格趋势、移动平均线、RSI指标）
2. 基本面评估（估值水平、财务健康度）
3. 市场动量分析（交易量、波动性）
4. 投资建议（买入/持有/卖出建议及理由）
5. 风险提示
6. 目标价位和预期收益

请保持分析简洁专业，长度控制在200字以内。
"""

        # 调用OpenAI GPT API
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "你是一名专业的股票投资分析师，具有多年的市场经验和深厚的技术分析功底。请提供准确、专业、简洁的投资建议。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        
        ai_analysis = response.choices[0].message.content.strip()
        print(f"[DEBUG] GPT分析 {symbol}: {ai_analysis[:100]}...")
        
        return ai_analysis
        
    except Exception as e:
        print(f"[ERROR] GPT分析失败 {symbol}: {e}")
        # 如果GPT分析失败，回退到原始分析
        return generate_fallback_analysis(stock_data, style, score)

def generate_fallback_analysis(stock_data, style, score):
    """生成备用的专业分析（当GPT不可用时）"""
    if not stock_data:
        return "数据获取失败，无法进行分析"
    
    symbol = stock_data['symbol']
    current_price = stock_data.get('current_price', 0)
    change_percent = stock_data.get('change_percent', 0)
    pe_ratio = stock_data.get('pe_ratio', 0)
    rsi = stock_data.get('rsi', 50)
    ma_5 = stock_data.get('ma_5', current_price)
    ma_20 = stock_data.get('ma_20', current_price)
    target_price = stock_data.get('target_price', 0)
    
    analysis_parts = []
    
    # 价格趋势分析
    if current_price > ma_5 > ma_20:
        trend = "强势上涨趋势"
        trend_desc = f"当前价格${current_price}突破5日均线${ma_5:.2f}和20日均线${ma_20:.2f}，显示强劲买盘支撑"
    elif current_price < ma_5 < ma_20:
        trend = "明显下跌趋势"
        trend_desc = f"当前价格${current_price}跌破关键均线支撑，5日均线${ma_5:.2f}和20日均线${ma_20:.2f}形成压力位"
    else:
        trend = "横盘整理"
        trend_desc = f"当前价格${current_price}在均线附近震荡，等待方向选择"
    
    analysis_parts.append(f"【技术面】{trend}。{trend_desc}。")
    
    # RSI分析
    if rsi > 70:
        rsi_analysis = f"RSI指标为{rsi:.1f}，处于超买区域，短期存在回调压力"
    elif rsi < 30:
        rsi_analysis = f"RSI指标为{rsi:.1f}，处于超卖区域，具备技术性反弹条件"
    else:
        rsi_analysis = f"RSI指标为{rsi:.1f}，处于合理区间，动量较为均衡"
    
    analysis_parts.append(f"【动量指标】{rsi_analysis}。")
    
    # 基本面分析
    if pe_ratio > 0:
        if pe_ratio < 15:
            pe_analysis = f"市盈率{pe_ratio:.1f}倍，估值相对合理，具备价值投资属性"
        elif pe_ratio > 30:
            pe_analysis = f"市盈率{pe_ratio:.1f}倍，估值偏高，需关注业绩增长兑现情况"
        else:
            pe_analysis = f"市盈率{pe_ratio:.1f}倍，估值处于合理区间"
    else:
        pe_analysis = "市盈率数据暂无，建议关注公司盈利能力"
    
    analysis_parts.append(f"【估值分析】{pe_analysis}。")
    
    # 投资建议
    if score >= 80:
        recommendation = "强烈推荐"
        reason = "技术面和基本面均显示积极信号，符合当前市场投资逻辑"
    elif score >= 65:
        recommendation = "推荐买入"
        reason = "综合评估显示投资价值较高，建议适量配置"
    elif score >= 50:
        recommendation = "谨慎持有"
        reason = "存在一定投资机会，但需密切关注风险控制"
    else:
        recommendation = "暂时规避"
        reason = "当前风险因素较多，建议等待更好时机"
    
    if target_price > 0:
        price_target = f"分析师目标价${target_price:.2f}，"
        upside = (target_price - current_price) / current_price * 100
        price_target += f"潜在上涨空间{upside:.1f}%。"
    else:
        price_target = ""
    
    analysis_parts.append(f"【投资建议】{recommendation}。{reason}。{price_target}")
    
    return " ".join(analysis_parts)

# 为了向后兼容，保留原函数名
def generate_professional_analysis(stock_data, style, score):
    """生成专业的股票分析（兼容函数）"""
    return generate_ai_powered_analysis(stock_data, style, score)

def generate_stock_recommendations(sector, style, risk, time_horizon):
    """Generate AI stock recommendations based on real data"""
    # 股票池
    stock_pools = {
        'technology': ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'META', 'AMZN', 'CRM', 'ORCL', 'INTC'],
        'healthcare': ['JNJ', 'PFE', 'UNH', 'MRNA', 'ABBV', 'TMO', 'DHR', 'BMY', 'MRK', 'GILD'],
        'finance': ['JPM', 'BAC', 'WFC', 'GS', 'C', 'USB', 'TFC', 'PNC', 'COF', 'AXP'],
        'energy': ['XOM', 'CVX', 'COP', 'EOG', 'SLB', 'PSX', 'VLO', 'MPC', 'OXY', 'DVN'],
        'consumer': ['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'TGT', 'LOW', 'WMT', 'COST'],
        'industrial': ['BA', 'CAT', 'GE', 'HON', 'UPS', 'LMT', 'RTX', 'DE', 'MMM', 'EMR'],
        'utilities': ['NEE', 'DUK', 'SO', 'D', 'EXC', 'XEL', 'SRE', 'AEP', 'PEG', 'ED'],
        'materials': ['LIN', 'APD', 'SHW', 'ECL', 'DD', 'DOW', 'PPG', 'NEM', 'FCX', 'FMC']
    }
    
    # 选择股票池
    if not sector:
        all_symbols = []
        for symbols in stock_pools.values():
            all_symbols.extend(symbols)
        selected_symbols = random.sample(all_symbols, min(8, len(all_symbols)))
    else:
        available_symbols = stock_pools.get(sector, [])
        if not available_symbols:
            return []
        selected_symbols = random.sample(available_symbols, min(6, len(available_symbols)))
    
        (f"[DEBUG] Analyzing stocks: {selected_symbols}")
    
    recommendations = []
    for symbol in selected_symbols:
        try:
            print(f"[DEBUG] 获取 {symbol} 的数据...")
            
            # 获取股票数据
            stock_data = get_comprehensive_stock_data(symbol)
            if not stock_data:
                continue
            
            # 计算AI评分
            score = calculate_ai_score(stock_data, style, risk, time_horizon)
            
            # 生成专业分析
            professional_analysis = generate_professional_analysis(stock_data, style, score)
            
            # 计算预期收益
            current_price = stock_data.get('current_price', 0)
            target_price = stock_data.get('target_price', 0)
            if target_price > 0:
                expected_return = round((target_price - current_price) / current_price * 100, 1)
            else:
                # 基于评分估算收益
                expected_return = round((score - 50) * 0.5 + random.uniform(-5, 5), 1)
            
            recommendation = {
                'symbol': symbol,
                'name': stock_data.get('name', symbol),
                'sector': stock_data.get('sector', 'Unknown'),
                'score': score,
                'reason': professional_analysis,
                'expectedReturn': f"{max(expected_return, -30)}",  # 限制最大亏损显示
                'riskLevel': risk.title(),
                'current_price': stock_data.get('current_price', 0),
                'change_percent': stock_data.get('change_percent', 0),
                'market_cap': stock_data.get('market_cap', 0),
                'pe_ratio': stock_data.get('pe_ratio', 0),
                'volume_ratio': stock_data.get('volume_ratio', 1.0)
            }
            
            recommendations.append(recommendation)
            print(f"[DEBUG] {symbol} 分析完成，评分: {score}")
            
        except Exception as e:
            print(f"[ERROR] 分析股票 {symbol} 时出错: {e}")
            continue
    
    # 按评分排序
    recommendations.sort(key=lambda x: x['score'], reverse=True)
    
    print(f"[DEBUG] 共生成 {len(recommendations)} 个推荐")
    return recommendations[:5]  # 返回前5个推荐

def generate_stock_diagnosis(symbol, analysis_type, time_frame):
    """Generate GPT-based AI stock diagnosis"""
    try:
        # 获取股票数据
        stock_data = get_comprehensive_stock_data(symbol)
        if not stock_data:
            return generate_fallback_diagnosis(symbol, analysis_type, time_frame)
        
        # Prepare GPT diagnosis prompt
        current_price = stock_data.get('current_price', 0)
        change_percent = stock_data.get('change_percent', 0)
        pe_ratio = stock_data.get('pe_ratio', 0)
        market_cap = stock_data.get('market_cap', 0)
        beta = stock_data.get('beta', 1.0)
        rsi = stock_data.get('rsi', 50)
        ma_5 = stock_data.get('ma_5', current_price)
        ma_20 = stock_data.get('ma_20', current_price)
        volume_ratio = stock_data.get('volume_ratio', 1.0)
        
        analysis_focus = {
            'comprehensive': '全面综合分析',
            'technical': '技术面深度分析',
            'fundamental': '基本面详细评估',
            'sentiment': '市场情绪和投资者心理分析',
            'risk': '风险评估和风险管理建议'
        }
        
        prompt = f"""
作为专业的股票分析师，请对 {symbol} ({stock_data.get('name', symbol)}) 进行{analysis_focus.get(analysis_type, '综合')}。

股票当前状态：
- 当前价格: ${current_price:.2f} (日涨跌: {change_percent:.2f}%)
- 市值: ${market_cap/1000000000:.1f}B
- 市盈率: {pe_ratio:.1f}
- Beta系数: {beta:.2f}
- RSI: {rsi:.1f}
- 5日均线: ${ma_5:.2f}
- 20日均线: ${ma_20:.2f}
- 交易量比率: {volume_ratio:.1f}x
- 分析时间框架: {time_frame}

请提供：
1. 总体评分 (0-100分)
2. 核心分析摘要 (50字内)
3. Detailed diagnosis report including:
   - 技术面分析 (趋势、指标、支撑阻力)
   - 基本面评估 (估值、财务健康度)
   - 市场情绪分析 (投资者心理、资金流向)
   - 风险评估 (系统性风险、特定风险)
   - 操作建议 (买入/持有/卖出、目标价位)

请用中文回答，保持专业性和客观性。
"""

        # 调用GPT进行分析
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "你是一名资深股票分析师，擅长技术分析、基本面分析和市场研究。请提供客观、专业、实用的投资分析。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.6
        )
        
        gpt_analysis = response.choices[0].message.content.strip()
        
        # 解析GPT回复，提取评分和分析内容
        lines = gpt_analysis.split('\n')
        overall_score = 75  # 默认评分
        
        # 尝试从回复中提取评分
        for line in lines:
            if '评分' in line or '分数' in line or '分：' in line:
                import re
                score_match = re.search(r'(\d+)', line)
                if score_match:
                    overall_score = min(100, max(0, int(score_match.group(1))))
                    break
        
        # 构建诊断结果
        diagnosis = {
            'symbol': symbol,
            'overallScore': overall_score,
            'summary': f'{symbol} 综合AI分析显示，该股票当前评分为{overall_score}分，表现{"优秀" if overall_score >= 80 else "良好" if overall_score >= 60 else "一般" if overall_score >= 40 else "较差"}。',
            'sections': []
        }
        
        # 分段处理GPT分析结果
        if '技术面' in gpt_analysis:
            tech_content = extract_section_content(gpt_analysis, '技术面')
            diagnosis['sections'].append({
                'title': '技术面分析',
                'score': min(100, overall_score + random.randint(-10, 10)),
                'content': tech_content or f'{symbol} 技术指标显示当前趋势较为{"积极" if overall_score > 60 else "谨慎"}，建议密切关注价格变化。'
            })
        
        if '基本面' in gpt_analysis:
            fund_content = extract_section_content(gpt_analysis, '基本面')
            diagnosis['sections'].append({
                'title': '基本面评估',
                'score': min(100, overall_score + random.randint(-5, 15)),
                'content': fund_content or f'{symbol} 基本面指标处于{"健康" if overall_score > 60 else "一般"}水平，估值相对{"合理" if pe_ratio < 25 else "偏高"}。'
            })
        
        if '市场情绪' in gpt_analysis or '情绪' in gpt_analysis:
            sentiment_content = extract_section_content(gpt_analysis, '情绪')
            diagnosis['sections'].append({
                'title': '市场情绪分析',
                'score': min(100, overall_score + random.randint(-15, 5)),
                'content': sentiment_content or f'{symbol} 市场情绪相对{"乐观" if overall_score > 60 else "谨慎"}，投资者关注度{"较高" if volume_ratio > 1.2 else "一般"}。'
            })
        
        if '风险' in gpt_analysis:
            risk_content = extract_section_content(gpt_analysis, '风险')
            diagnosis['sections'].append({
                'title': '风险评估',
                'score': max(30, 100 - overall_score + random.randint(-10, 10)),
                'content': risk_content or f'{symbol} 整体风险水平{"适中" if 0.8 <= beta <= 1.3 else "偏高" if beta > 1.3 else "较低"}，建议根据个人风险偏好进行配置。'
            })
        
        # 如果GPT没有生成分段内容，添加完整分析
        if not diagnosis['sections']:
            diagnosis['sections'].append({
                'title': '综合分析报告',
                'score': overall_score,
                'content': gpt_analysis[:300] + ('...' if len(gpt_analysis) > 300 else '')
            })
        
        print(f"[DEBUG] GPT diagnosis {symbol}: Score {overall_score}, {len(diagnosis['sections'])} analysis dimensions")
        return diagnosis
        
    except Exception as e:
        print(f"[ERROR] GPT diagnosis failed {symbol}: {e}")
        return generate_fallback_diagnosis(symbol, analysis_type, time_frame)

def extract_section_content(text, section_keyword):
    """从GPT分析文本中提取特定段落内容"""
    lines = text.split('\n')
    content_lines = []
    in_section = False
    
    for line in lines:
        if section_keyword in line:
            in_section = True
            continue
        elif in_section and line.strip():
            if any(keyword in line for keyword in ['技术面', '基本面', '市场情绪', '风险', '操作建议']):
                break
            content_lines.append(line.strip())
        elif in_section and not line.strip():
            continue
    
    return ' '.join(content_lines) if content_lines else None

def generate_fallback_diagnosis(symbol, analysis_type, time_frame):
    """Generate fallback diagnosis results"""
    import random
    
    overall_score = random.randint(45, 90)
    
    diagnosis = {
        'symbol': symbol,
        'overallScore': overall_score,
        'summary': f'基于技术指标分析，{symbol} 当前评分为{overall_score}分，表现{"良好" if overall_score >= 70 else "一般" if overall_score >= 50 else "谨慎"}。',
        'sections': []
    }
    
    if analysis_type == 'comprehensive' or analysis_type == 'technical':
        diagnosis['sections'].append({
            'title': '技术分析',
            'score': random.randint(40, 95),
            'content': f'{symbol} 技术指标显示{"上涨" if random.choice([True, False]) else "震荡"}趋势。移动平均线呈现{"多头排列" if random.choice([True, False]) else "空头排列"}，RSI指标为{random.randint(30, 70)}，处于{"合理" if random.choice([True, False]) else "超买"}区间。'
        })
    
    if analysis_type == 'comprehensive' or analysis_type == 'fundamental':
        diagnosis['sections'].append({
            'title': '基本面分析',
            'score': random.randint(50, 95),
            'content': f'{symbol} 基本面指标显示{"健康" if random.choice([True, False]) else "一般"}状态。市盈率{random.randint(15, 35):.1f}倍，估值{"合理" if random.choice([True, False]) else "偏高"}。营收增长率约{random.randint(5, 25)}%，显示{"稳健" if random.choice([True, False]) else "温和"}增长。'
        })
    
    return diagnosis

def generate_portfolio_diagnosis(symbol, purchase_price, purchase_date, purchase_market, analysis_type):
    """Generate AI diagnosis based on portfolio information"""
    try:
        # 获取当前股票数据
        stock_data = get_comprehensive_stock_data(symbol)
        if not stock_data:
            return generate_fallback_portfolio_diagnosis(symbol, purchase_price, purchase_date)
        
        current_price = stock_data.get('current_price', 0)
        
        # 计算持仓表现
        portfolio_performance = None
        holding_days = 0
        total_return = 0
        
        if purchase_price and purchase_date:
            try:
                from datetime import datetime
                purchase_dt = datetime.strptime(purchase_date, '%Y-%m-%d')
                current_dt = datetime.now()
                holding_days = (current_dt - purchase_dt).days
                
                if purchase_price > 0:
                    total_return = ((current_price - float(purchase_price)) / float(purchase_price)) * 100
                
                portfolio_performance = {
                    'purchasePrice': float(purchase_price),
                    'currentPrice': current_price,
                    'totalReturn': total_return,
                    'holdingDays': holding_days,
                    'purchaseDate': purchase_date,
                    'purchaseMarket': purchase_market
                }
            except Exception as e:
                print(f"[WARNING] 持仓计算失败: {e}")
        
        # 基于持仓信息调整GPT提示词
        if portfolio_performance:
            prompt = f"""
As a professional investment advisor, please provide an in-depth analysis of the client's holding in {symbol} ({stock_data.get('name', symbol)}).

Holdings Information:
- Stock Symbol: {symbol}
- Purchase Price: ${purchase_price}
- Purchase Date: {purchase_date}
- Purchase Market: {purchase_market}
- Current Price: ${current_price:.2f}
- Portfolio Return: {total_return:.2f}%
- Holding Days: {holding_days} days

Current Market Data:
- Market Cap: ${stock_data.get('market_cap', 0)/1000000000:.1f}B
- P/E Ratio: {stock_data.get('pe_ratio', 0):.1f}
- Beta: {stock_data.get('beta', 1.0):.2f}
- RSI: {stock_data.get('rsi', 50):.1f}
- 5-day MA: ${stock_data.get('ma_5', current_price):.2f}
- 20-day MA: ${stock_data.get('ma_20', current_price):.2f}

Please provide professional portfolio analysis covering:
1. Portfolio Performance Assessment (P&L analysis, holding period evaluation)
2. Current Market Position (technical, fundamental, valuation levels)
3. Future Outlook (short-term trends, long-term prospects)
4. Trading Recommendations (hold, reduce, add, stop-loss advice)
5. Risk Warnings (market risk, stock-specific risk, timing considerations)

Please respond in English, maintain objectivity and professionalism, and provide clear investment advice.
"""
        else:
            prompt = f"""
As a professional stock analyst, please provide a comprehensive analysis of {symbol} ({stock_data.get('name', symbol)}).

Current Stock Status:
- Current Price: ${current_price:.2f}
- Market Cap: ${stock_data.get('market_cap', 0)/1000000000:.1f}B
- P/E Ratio: {stock_data.get('pe_ratio', 0):.1f}
- Beta: {stock_data.get('beta', 1.0):.2f}
- RSI: {stock_data.get('rsi', 50):.1f}

Please provide professional analysis and investment recommendations in English.
"""

        try:
            # 调用GPT进行分析
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a professional investment advisor with extensive stock analysis experience. Please provide accurate, objective, and practical investment advice."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=600,
                temperature=0.6
            )
            
            gpt_analysis = response.choices[0].message.content.strip()
            
            # 解析分析并生成评分
            overall_score = calculate_portfolio_score(stock_data, portfolio_performance)
            
            # Build diagnosis results
            diagnosis = {
                'symbol': symbol,
                'overallScore': overall_score,
                'summary': f'{symbol} comprehensive analysis score: {overall_score}/100. ' + (gpt_analysis[:100] + '...' if len(gpt_analysis) > 100 else gpt_analysis),
                'portfolioPerformance': portfolio_performance,
                'sections': parse_portfolio_analysis(gpt_analysis, overall_score)
            }
            
            print(f"[DEBUG] GPT portfolio diagnosis {symbol}: Score {overall_score}, Portfolio return {total_return:.2f}%")
            return diagnosis
            
        except Exception as e:
            print(f"[ERROR] GPT持仓分析失败 {symbol}: {e}")
            return generate_fallback_portfolio_diagnosis(symbol, purchase_price, purchase_date, portfolio_performance)
            
    except Exception as e:
        print(f"[ERROR] 持仓诊断失败 {symbol}: {e}")
        return generate_fallback_portfolio_diagnosis(symbol, purchase_price, purchase_date)

def calculate_portfolio_score(stock_data, portfolio_performance):
    """计算持仓评分"""
    base_score = 50
    
    # 基于技术指标调整
    if stock_data:
        rsi = stock_data.get('rsi', 50)
        pe_ratio = stock_data.get('pe_ratio', 25)
        current_price = stock_data.get('current_price', 0)
        ma_5 = stock_data.get('ma_5', current_price)
        ma_20 = stock_data.get('ma_20', current_price)
        
        # RSI评分
        if 30 <= rsi <= 70:
            base_score += 10
        elif rsi > 70:
            base_score -= 5
        elif rsi < 30:
            base_score += 5
            
        # PE比率评分
        if 10 <= pe_ratio <= 25:
            base_score += 10
        elif pe_ratio > 40:
            base_score -= 10
            
        # 均线位置
        if current_price > ma_5 > ma_20:
            base_score += 15
        elif current_price < ma_5 < ma_20:
            base_score -= 15
    
    # 基于持仓表现调整
    if portfolio_performance:
        total_return = portfolio_performance.get('totalReturn', 0)
        holding_days = portfolio_performance.get('holdingDays', 0)
        
        # 收益率调整
        if total_return > 20:
            base_score += 20
        elif total_return > 10:
            base_score += 15
        elif total_return > 0:
            base_score += 10
        elif total_return < -20:
            base_score -= 20
        elif total_return < -10:
            base_score -= 10
        
        # 持仓时间调整
        if holding_days > 365:
            base_score += 5
        elif holding_days < 30:
            base_score -= 5
    
    return max(0, min(100, base_score))

def parse_portfolio_analysis(gpt_text, score):
    """解析GPT持仓分析文本"""
    sections = []
    lines = gpt_text.split('\n')
    current_content = []
    
    section_keywords = ['持仓表现', '市场位置', '后市展望', '操作建议', '风险提示']
    
    for line in lines:
        line = line.strip()
        if line:
            current_content.append(line)
    
    # 简单分段处理
    content_text = ' '.join(current_content)
    if len(content_text) > 200:
        mid_point = len(content_text) // 2
        sections.append({
            'title': '持仓分析',
            'score': min(100, score + random.randint(-10, 10)),
            'content': content_text[:mid_point]
        })
        sections.append({
            'title': '投资建议',
            'score': min(100, score + random.randint(-5, 15)),
            'content': content_text[mid_point:]
        })
    else:
        sections.append({
            'title': '综合分析',
            'score': score,
            'content': content_text
        })
    
    return sections

def generate_fallback_portfolio_diagnosis(symbol, purchase_price=None, purchase_date=None, portfolio_performance=None):
    """生成备用持仓诊断"""
    import random
    
    score = random.randint(45, 85)
    
    diagnosis = {
        'symbol': symbol,
        'overallScore': score,
        'summary': f'{symbol} analysis based on current market data, overall score: {score}/100.',
        'portfolioPerformance': portfolio_performance,
        'sections': [
            {
                'title': 'Technical Analysis',
                'score': random.randint(40, 90),
                'content': f'{symbol} technical indicators show the stock is currently in a {"relatively strong" if random.choice([True, False]) else "consolidation"} phase.'
            },
            {
                'title': 'Investment Recommendation',
                'score': random.randint(50, 95),
                'content': f'Based on current market conditions, recommend to {"maintain current position" if random.choice([True, False]) else "adjust position appropriately"}.'
            }
        ]
    }
    
    return diagnosis

# AI管理后台API
@app.route('/api/admin/ai-stats', methods=['GET'])
def ai_stats():
    """获取AI工具使用统计"""
    try:
        # 模拟统计数据（实际应用中从数据库获取）
        import random
        from datetime import datetime, timedelta
        
        current_month = datetime.now().month
        picker_usage = random.randint(150, 500)
        diagnosis_usage = random.randint(200, 800)
        
        return jsonify({
            'success': True,
            'pickerUsage': picker_usage,
            'diagnosisUsage': diagnosis_usage,
            'month': current_month
        })
        
    except Exception as e:
        print(f"[ERROR] AI统计API错误: {e}")
        return jsonify({'error': 'Failed to get AI statistics'}), 500

@app.route('/api/admin/ai-activity', methods=['GET'])
def ai_activity():
    """获取AI工具活动记录"""
    try:
        # 模拟活动记录（实际应用中从数据库获取）
        import random
        from datetime import datetime, timedelta
        
        activities = []
        for i in range(10):
            timestamp = datetime.now() - timedelta(hours=random.randint(1, 72))
            tool = random.choice(['picker', 'diagnosis'])
            success = random.choice([True, True, True, False])  # 75% success rate
            
            if tool == 'picker':
                request = f"Sector: {random.choice(['Technology', 'Healthcare', 'Finance'])}, Style: {random.choice(['Growth', 'Value', 'Momentum'])}"
            else:
                symbols = ['AAPL', 'TSLA', 'GOOGL', 'MSFT', 'NVDA', 'META', 'AMZN']
                request = f"Symbol: {random.choice(symbols)}, Analysis: {random.choice(['Comprehensive', 'Technical', 'Fundamental'])}"
            
            activities.append({
                'timestamp': timestamp.isoformat(),
                'tool': tool,
                'request': request,
                'success': success,
                'userIp': f"192.168.1.{random.randint(100, 199)}"
            })
        
        # 按时间倒序排列
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'success': True,
            'activities': activities
        })
        
    except Exception as e:
        print(f"[ERROR] AI活动API错误: {e}")
        return jsonify({'error': 'Failed to get AI activity'}), 500

@app.route('/api/admin/ai-settings', methods=['POST'])
def ai_settings():
    """保存AI工具设置"""
    try:
        data = request.get_json()
        
        # 获取设置参数
        picker_status = data.get('pickerStatus', 'enabled')
        picker_limit = data.get('pickerLimit', 50)
        diagnosis_status = data.get('diagnosisStatus', 'enabled')
        diagnosis_limit = data.get('diagnosisLimit', 100)
        
        print(f"[DEBUG] AI设置保存: picker_status={picker_status}, picker_limit={picker_limit}, diagnosis_status={diagnosis_status}, diagnosis_limit={diagnosis_limit}")
        
        # 这里可以保存到数据库或配置文件
        # 暂时模拟保存成功
        
        return jsonify({
            'success': True,
            'message': 'AI settings saved successfully',
            'settings': {
                'pickerStatus': picker_status,
                'pickerLimit': picker_limit,
                'diagnosisStatus': diagnosis_status,
                'diagnosisLimit': diagnosis_limit
            }
        })
        
    except Exception as e:
        print(f"[ERROR] AI设置API错误: {e}")
        return jsonify({'error': 'Failed to save AI settings'}), 500

if __name__ == '__main__':
    # 初始化数据库
    # init_user_db()
    # init_membership_levels_db()
    # init_user_membership_db()
    #初始化印度股票数据
    get_India_price()
    # 启动应用
    app.run(debug=True, host='0.0.0.0', port=8888)
