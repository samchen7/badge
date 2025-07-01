from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime, timedelta
import os
import shutil
from werkzeug.utils import secure_filename
import jieba
from collections import Counter
import re
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import base64
from io import BytesIO
import json
import traceback

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def verify_database(db_path):
    """验证数据库文件的有效性"""
    if not db_path.endswith('.db'):
        raise Exception("请选择正确的.db数据库文件")
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查必要的表是否存在
        tables_query = """
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name IN ('WL_MSG', 'Contact')
        """
        tables = cursor.execute(tables_query).fetchall()
        existing_tables = [t[0] for t in tables]
        
        if 'WL_MSG' not in existing_tables or 'Contact' not in existing_tables:
            conn.close()
            raise Exception("数据库缺少必要的表格，请选择正确的数据库文件")
            
        # 检查表结构
        cursor.execute("SELECT room_name, talker, type_name, content FROM WL_MSG LIMIT 1")
        cursor.execute("SELECT UserName, NickName, Remark FROM Contact LIMIT 1")
        
        conn.close()
    except sqlite3.DatabaseError:
        raise Exception("无法读取数据库文件，请确保选择了正确的文件")

def safe_connect_db(db_path):
    """安全地连接数据库，并进行基本验证"""
    try:
        conn = sqlite3.connect(db_path)
        # 启用外键约束
        conn.execute('PRAGMA foreign_keys = ON')
        # 检查数据库完整性
        conn.execute('PRAGMA integrity_check')
        return conn
    except sqlite3.DatabaseError as e:
        raise Exception(f"数据库文件损坏或格式不正确: {str(e)}")

def get_group_list(db_path):
    try:
        verify_database(db_path)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        query = """
        SELECT DISTINCT 
            m.room_name,
            CASE 
                WHEN c.NickName IS NULL OR c.NickName = '' THEN m.room_name
                ELSE c.NickName
            END as display_name,
            MAX(m.CreateTime) as last_msg_time
        FROM WL_MSG m 
        LEFT JOIN Contact c ON m.room_name = c.UserName 
        WHERE m.room_name LIKE '%chatroom%'
        GROUP BY m.room_name
        ORDER BY last_msg_time DESC
        """
        
        groups = cursor.execute(query).fetchall()
        conn.close()
        
        if not groups:
            raise Exception("未找到群聊记录，请确认选择了正确的数据库文件")
            
        # 格式化时间
        def format_time(timestamp):
            try:
                return datetime.fromtimestamp(int(timestamp)).strftime('%Y-%m-%d')
            except:
                return ''
            
        return [{
            'room_name': g[0], 
            'nickname': f"{g[1]} ({format_time(g[2])})"
        } for g in groups]
    except Exception as e:
        raise Exception(f"数据库读取失败: {str(e)}")

def extract_content_from_json(text):
    """从JSON格式的content字段中提取实际内容"""
    try:
        # 尝试解析JSON
        data = json.loads(text)
        return data.get('content', '')
    except:
        # 如果不是JSON格式，直接返回原文本
        return text

def generate_wordcloud(text):
    try:
        print("\n=== 开始生成词云 ===")
        print(f"输入文本长度: {len(text)}")
        
        # 1. 处理Unicode转义字符串
        try:
            text = text.encode('utf-8').decode('unicode_escape')
            print(f"Unicode解码后的文本: {text[:100]}")
        except Exception as e:
            print(f"Unicode解码失败: {str(e)}")
            pass
            
        # 2. 分词
        words = jieba.cut(text)
        word_list = []
        
        # 3. 过滤词组
        stop_words = {'的', '了', '吗', '吧', '啊', '呢', '么', '哦', '哈', '呀', '嘛', '啦',
                     '着', '呵', '哎', '唉', '哼', '嗯', '这', '那', '就', '是', '也', '和',
                     '与', '或', '在', '上', '下', '中', '里', '到', '为', '及', '等', '把',
                     '要', '会', '对', '能', '都', '还', '去', '说', '来', '做', '看', '想',
                     '得', '过', '没', '有', '好', '被', '将', '从', '到', '更', '又', '并'}
        
        for word in words:
            word = word.strip()
            if (len(word) > 1 and word not in stop_words):
                word_list.append(word)
        
        print(f"过滤后词组数量: {len(word_list)}")
        if not word_list:
            print("没有有效词组")
            return None
        
        # 4. 统计词频并标准化
        word_count = Counter(word_list)
        
        # 获取前30个最常见的词
        top_words = word_count.most_common(30)
        
        # 标准化词频到固定范围（9-120）并增加重复
        if top_words:
            max_freq = top_words[0][1]
            min_freq = top_words[-1][1]
            freq_range = max_freq - min_freq
            
            normalized_counts = {}
            # 首先处理高频词（前10个）
            for i, (word, count) in enumerate(top_words[:10]):
                if freq_range > 0:
                    # 使用指数映射增加差异
                    norm_count = 40 + (((count - min_freq) / freq_range) ** 0.5) * 80
                else:
                    norm_count = 80
                normalized_counts[word] = norm_count
            
            # 处理中频词（10-20）
            for i, (word, count) in enumerate(top_words[10:20]):
                if freq_range > 0:
                    norm_count = 25 + (((count - min_freq) / freq_range) ** 0.6) * 35
                else:
                    norm_count = 35
                # 对相同的词增加后缀以实现重复
                normalized_counts[word] = norm_count
                normalized_counts[word + '_'] = norm_count * 0.8  # 添加一个略小的副本
            
            # 处理低频词（20-30），用于填充空隙
            for i, (word, count) in enumerate(top_words[20:]):
                base_size = 15 + (i % 3) * 2  # 9-15之间浮动
                normalized_counts[word] = base_size
                # 为每个低频词创建多个副本，用于填充空隙
                for j in range(2):  # 每个词创建2个副本
                    normalized_counts[f"{word}_{j}"] = base_size * (0.9 + j * 0.1)
        
        print(f"标准化后的词频: {list(normalized_counts.items())[:10]}")
        
        # 5. 生成词云
        try:
            # 尝试多个中文字体路径
            font_paths = [
                '/System/Library/Fonts/PingFang.ttc',  # macOS
                'C:/Windows/Fonts/simhei.ttf',  # Windows
                'C:/Windows/Fonts/msyh.ttc',    # Windows
                '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',  # Linux
                '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',     # Linux
                '/usr/share/fonts/wqy-microhei/wqy-microhei.ttc'             # Linux
            ]
            
            font_path = None
            for path in font_paths:
                if os.path.exists(path):
                    font_path = path
                    print(f"使用字体: {path}")
                    break
            
            wc = WordCloud(
                width=400,
                height=400,
                background_color='white',
                max_words=80,  # 增加显示词数以容纳重复词
                font_path=font_path,
                prefer_horizontal=0.5,  # 更平衡的水平/垂直分布
                min_font_size=9,    # 最小字号
                max_font_size=120,  # 增加最大字号
                collocations=False,
                relative_scaling=0.7,  # 增加词频对字体大小的影响
                regexp=r"[\w'_]+|[^\s]+",  # 支持带下划线的词
                margin=1,  # 保持较小的词间距
                random_state=42  # 固定随机数种子，使布局更稳定
            )
            
            # 使用标准化后的词频生成词云
            wc.generate_from_frequencies(normalized_counts)
            print("词云对象生成成功")
            
            # 保存图片
            img = BytesIO()
            wc.to_image().save(img, format='PNG')
            img.seek(0)
            print("图片保存成功")
            
            # 转换为base64
            result = base64.b64encode(img.getvalue()).decode()
            print(f"生成的base64长度: {len(result)}")
            return result
            
        except Exception as e:
            print(f"词云生成失败: {str(e)}")
            traceback.print_exc()
            return None
            
    except Exception as e:
        print(f"词云处理失败: {str(e)}")
        traceback.print_exc()
        return None

def analyze_friend(db_path):
    try:
        print("开始分析好友数据...")
        verify_database(db_path)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 首先找出最亲密的好友
        query = """
        SELECT 
            COALESCE(c.NickName, c.Remark, m.talker) as name,
            m.talker as user_id,
            COUNT(*) as msg_count,
            SUM(LENGTH(m.content)) as content_length,
            COUNT(DISTINCT date(m.CreateTime, 'unixepoch')) as active_days
        FROM WL_MSG m
        LEFT JOIN Contact c ON m.talker = c.UserName
        WHERE m.room_name NOT LIKE '%chatroom%'
        AND m.type_name NOT IN ('系统通知', '系统消息')
        AND m.Is_sender = 0
        AND m.talker != ''
        GROUP BY m.talker
        HAVING msg_count >= 10
        ORDER BY (
            msg_count * 0.4 +
            content_length * 0.3 +
            active_days * 0.3
        ) DESC
        LIMIT 1
        """
        
        best_friend = cursor.execute(query).fetchone()
        if not best_friend:
            return "暂无数据"
            
        friend_name, friend_id = best_friend[0], best_friend[1]
        
        # 获取与该好友的所有文本消息
        detail_query = """
        SELECT 
            SUM(CASE WHEN Is_sender = 0 THEN 1 ELSE 0 END) as received_count,
            SUM(CASE WHEN Is_sender = 1 THEN 1 ELSE 0 END) as sent_count,
            GROUP_CONCAT(content) as all_content
        FROM WL_MSG
        WHERE (talker = ? OR (room_name = ? AND Is_sender = 1))
        AND type_name = '文本'
        AND content != ''
        """
        
        details = cursor.execute(detail_query, (friend_id, friend_id)).fetchone()
        conn.close()
        
        received_count = details[0] or 0
        sent_count = details[1] or 0
        all_text = details[2] or ''
        
        # 获取消息内容后立即打印
        print(f"获取到的文本内容长度: {len(all_text)}")
        print(f"文本样例: {all_text[:200]}")  # 打印前200个字符
        
        # 生成分析报告文字
        report_text = (
            f"您最亲密的好友是【{friend_name}】\n"
            f"你们互动了{best_friend[4]}天\n"
            f"共收到{received_count}条消息\n"
            f"发出{sent_count}条消息\n"
            f"总计{received_count + sent_count}条消息\n"
            f"日均{round((received_count + sent_count) / best_friend[4], 1)}条\n"
        )
        
        # 生成词云前打印信息
        print("开始生成词云...")
        wordcloud = None
        if all_text:
            wordcloud = generate_wordcloud(all_text)
            if wordcloud:
                print("词云生成成功")
                print(f"词云数据长度: {len(wordcloud)}")
            else:
                print("词云生成失败")
        else:
            print("没有文本内容，无法生成词云")
            
        return {
            'text': report_text,
            'wordcloud': wordcloud
        }
    except Exception as e:
        print(f"分析失败，错误信息: {str(e)}")
        traceback.print_exc()  # 打印完整的错误堆栈
        raise

def analyze_chatty(db_path, group_id):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 获取群名称和消息内容
        query = """
        SELECT 
            COALESCE(c.NickName, c.Remark, m.room_name) as group_name,
            m.content
        FROM WL_MSG m
        LEFT JOIN Contact c ON m.room_name = c.UserName
        WHERE m.room_name = ?
        AND m.type_name = '文本'
        AND m.content != ''
        AND m.content IS NOT NULL
        """
        
        result = cursor.execute(query, (group_id,)).fetchall()
        conn.close()
        
        if not result:
            return {
                'text': "暂无数据",
                'wordcloud': None
            }
            
        group_name = result[0][0]
        all_content = [row[1] for row in result]
        
        # 生成分析报告文字
        report_text = f"在【{group_name}】中共有{len(all_content)}条消息记录。\n"
        
        # 生成词云
        wordcloud = generate_wordcloud('\n'.join(all_content)) if all_content else None
        
        return {
            'text': report_text,
            'wordcloud': wordcloud
        }
    except Exception as e:
        raise Exception(f"数据库分析失败: {str(e)}")

@app.route('/')
def home():
    return render_template('medals.html')

@app.route('/get_groups', methods=['POST'])
def get_groups():
    if 'db_file' not in request.files:
        return jsonify({'success': False, 'error': '请选择数据库文件'})
    
    file = request.files['db_file']
    if not file:
        return jsonify({'success': False, 'error': '请选择数据库文件'})
    
    try:
        # 使用临时文件
        temp_path = 'temp.db'
        file.save(temp_path)
        
        # 尝试打开数据库
        try:
            conn = sqlite3.connect(temp_path)
            cursor = conn.cursor()
            
            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='WL_MSG'")
            if not cursor.fetchone():
                conn.close()
                os.remove(temp_path)
                return jsonify({'success': False, 'error': '无效的数据库文件：未找到消息表'})
            
            # 获取群聊列表
            groups = get_group_list(temp_path)
            conn.close()
            os.remove(temp_path)
            return jsonify({'success': True, 'groups': groups})
            
        except sqlite3.DatabaseError as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return jsonify({'success': False, 'error': f'数据库文件损坏或格式不正确：{str(e)}'})
            
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({'success': False, 'error': str(e)})

@app.route('/analyze_friend', methods=['POST'])
def analyze_friend_route():
    if 'db_file' not in request.files:
        return jsonify({'success': False, 'error': '请选择数据库文件'})
    
    file = request.files['db_file']
    if not file:
        return jsonify({'success': False, 'error': '请选择数据库文件'})
    
    temp_path = None
    try:
        # 生成唯一的临时文件名
        temp_path = f'temp_{datetime.now().strftime("%Y%m%d%H%M%S")}.db'
        file.save(temp_path)
        
        # 分析数据
        result = analyze_friend(temp_path)
        
        # 删除临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        if isinstance(result, str):
            return jsonify({'success': True, 'result': {'text': result, 'wordcloud': None}})
            
        return jsonify({'success': True, 'result': result})
        
    except Exception as e:
        # 确保清理临时文件
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        print(f"处理失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/analyze_chatty', methods=['POST'])
def analyze_chatty_route():
    if 'db_file' not in request.files:
        return jsonify({'success': False, 'error': '请选择数据库文件'})
    
    file = request.files['db_file']
    group_id = request.form.get('group_id')
    if not file:
        return jsonify({'success': False, 'error': '请选择数据库文件'})
    
    try:
        temp_path = 'temp.db'
        file.save(temp_path)
        result = analyze_chatty(temp_path, group_id)
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True, port=8080)
