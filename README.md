# 微信聊天分析与词云生成工具

本项目是一个基于 Flask 的微信聊天数据库分析工具，支持上传微信数据库（.db）文件，自动分析最亲密好友、群聊活跃度，并生成词云可视化。

## 功能简介
- 支持上传微信聊天数据库（.db）文件
- 自动识别最亲密好友，统计互动天数、消息数等
- 群聊分析，统计消息数并生成词云
- 词云支持中文分词与常用停用词过滤
- 支持网页端交互，结果可视化

## 依赖环境
- Python 3.7+
- Flask
- jieba
- wordcloud
- matplotlib

## 快速开始
1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
2. 启动服务：
   ```bash
   python app.py
   ```
3. 浏览器访问：http://localhost:8080

## 文件说明
- `app.py`：主程序，包含后端逻辑
- `templates/`：前端页面模板
- `static/`：静态资源（图片、样式）
- `uploads/`：临时上传文件夹

## 注意事项
- 仅支持特定格式的微信数据库（需包含 WL_MSG 和 Contact 表）
- 词云生成需本地有中文字体（如 macOS 的 PingFang.ttc）

## License
MIT 