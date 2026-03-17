from flask import Flask, render_template, jsonify, request
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker
import sys
import os
import json
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from src.storage.base.models import XhsNote
from config.db_config import mysql_db_config

app = Flask(__name__)

engine = create_engine(
    f"mysql+pymysql://{mysql_db_config['user']}:{mysql_db_config['password']}@"
    f"{mysql_db_config['host']}:{mysql_db_config['port']}/{mysql_db_config['db_name']}"
)
Session = sessionmaker(bind=engine)


def _infer_source_type(llm_data: dict) -> str:
    """兼容新旧 llm_filter 字段，推断来源类型"""
    source = llm_data.get("source_type")
    if source:
        return str(source)

    check_text = f"{llm_data.get('authenticity_check', '')} {llm_data.get('reason', '')}".lower()
    if "中介" in check_text or "引流" in check_text:
        return "疑似中介/引流"
    if "房东" in check_text:
        return "房东直租"
    if "转租" in check_text or "个人" in check_text:
        return "个人转租"

    is_authentic = llm_data.get("is_authentic")
    if is_authentic is True:
        return "个人/房东（推断）"
    if is_authentic is False:
        return "疑似中介/引流（推断）"
    return "未知"


def _extract_display_fields(llm_data: dict) -> dict:
    """兼容旧格式(顶层字段)与新格式(details嵌套字段)"""
    details = llm_data.get("details") if isinstance(llm_data.get("details"), dict) else {}
    return {
        "type": llm_data.get("type") or details.get("type") or "未知",
        "price": llm_data.get("price") or details.get("price") or "未知",
        "location": llm_data.get("location") or details.get("location") or "未知",
        # 旧版本叫 transport，新版本叫 utilities，这里做兜底兼容
        "transport": llm_data.get("transport") or llm_data.get("utilities") or details.get("transport") or details.get("utilities") or "未知",
        "source_type": _infer_source_type(llm_data),
        "match_level": llm_data.get("match_level", "未知"),
        "confidence_score": llm_data.get("confidence_score", 0),
        "is_authentic": llm_data.get("is_authentic"),
        "reason": llm_data.get("reason", ""),
        "authenticity_check": llm_data.get("authenticity_check", ""),
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/notes')
def get_notes():
    # 获取筛选参数
    min_confidence = request.args.get('min_confidence', type=float)
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    match_level = request.args.get('match_level')  # 值得一看, 稍微符合
    source_type = request.args.get('source_type')  # 房东直租, 个人转租, 疑似中介/引流
    note_type = request.args.get('note_type')  # 租房类型

    # 获取分页参数
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    # 获取排序参数
    sort_by = request.args.get('sort_by', 'time')  # time, liked_count, collected_count, comment_count
    sort_order = request.args.get('sort_order', 'desc')  # asc, desc

    session = Session()
    try:
        # 构建查询
        query = session.query(XhsNote).filter(XhsNote.llm_filter.isnot(None))

        # 日期筛选
        if start_date:
            query = query.filter(XhsNote.time >= start_date)
        if end_date:
            query = query.filter(XhsNote.time <= end_date)

        # 排序
        sort_column = getattr(XhsNote, sort_by, XhsNote.time)
        if sort_order == 'asc':
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        # 获取所有符合条件的笔记（需要在内存中过滤JSON字段）
        all_notes = query.all()

        # 解析并过滤数据
        filtered_notes = []
        for note in all_notes:
            llm_filter = note.llm_filter or ''

            # 解析llm_filter JSON
            filter_data = {}
            if llm_filter:
                try:
                    filter_data = json.loads(llm_filter)
                except:
                    continue

            # 提取展示字段（兼容新旧格式）
            fields = _extract_display_fields(filter_data)

            # 筛选条件
            # 1. 可信度筛选
            if min_confidence is not None:
                confidence = fields.get('confidence_score', 0)
                if confidence < min_confidence:
                    continue

            # 2. 价格筛选
            if min_price is not None or max_price is not None:
                price = fields.get('price', 0)
                # 尝试从价格字符串中提取数字
                try:
                    # 处理价格格式，如 "3000元/月" -> 3000
                    import re
                    price_match = re.search(r'\d+', str(price))
                    if price_match:
                        price_num = int(price_match.group())
                    else:
                        price_num = 0

                    if min_price is not None and price_num < min_price:
                        continue
                    if max_price is not None and price_num > max_price:
                        continue
                except:
                    pass

            # 3. 匹配等级筛选
            if match_level and match_level != 'all':
                if fields.get('match_level', '') != match_level:
                    continue

            # 4. 来源类型筛选
            if source_type and source_type != 'all':
                if source_type not in fields.get('source_type', ''):
                    continue

            # 5. 租房类型筛选
            if note_type and note_type != 'all':
                if note_type not in fields.get('type', ''):
                    continue

            filtered_notes.append({
                'note': note,
                'fields': fields
            })

        # 获取筛选后的总数
        total = len(filtered_notes)

        # 分页
        offset = (page - 1) * page_size
        paginated_notes = filtered_notes[offset:offset + page_size]

        data = []
        for item in paginated_notes:
            note = item['note']
            fields = item['fields']

            data.append({
                'id': note.id,
                'note_id': note.note_id,
                'title': note.title,
                'desc': note.desc,
                'nickname': note.nickname,
                'time': note.time,
                'liked_count': note.liked_count,
                'collected_count': note.collected_count,
                'comment_count': note.comment_count,
                'note_url': note.note_url,
                'llm_filter': fields
            })

        return jsonify({
            'data': data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_pages': (total + page_size - 1) // page_size
            }
        })
    finally:
        session.close()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5050)
