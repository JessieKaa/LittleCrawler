import os
import json
import time
import requests
from typing import Set
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from database import DatabaseManager

# 加载.env文件
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
POLL_INTERVAL = int(os.getenv("TG_POLL_INTERVAL", "60"))  # 默认60秒
SENT_NOTES_FILE = Path(__file__).parent / "sent_notes.json"

class TelegramNotifier:
    def __init__(self):
        self.db = DatabaseManager()
        self.sent_notes = self._load_sent_notes()

    def _load_sent_notes(self) -> Set[str]:
        if SENT_NOTES_FILE.exists():
            with open(SENT_NOTES_FILE, 'r') as f:
                return set(json.load(f))
        return set()

    def _save_sent_notes(self):
        with open(SENT_NOTES_FILE, 'w') as f:
            json.dump(list(self.sent_notes), f)

    def _send_telegram(self, message: str):
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            print("Telegram配置缺失")
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "MarkdownV2", "disable_web_page_preview": False}
        try:
            resp = requests.post(url, json=data, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            print(f"发送失败: {e}")

    def _escape_markdown(self, text: str) -> str:
        """转义MarkdownV2特殊字符"""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

    def _infer_source_type(self, llm_data: dict) -> str:
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

    def _extract_display_fields(self, llm_data: dict) -> dict:
        """兼容旧格式(顶层字段)与新格式(details嵌套字段)"""
        details = llm_data.get("details") if isinstance(llm_data.get("details"), dict) else {}
        return {
            "type": llm_data.get("type") or details.get("type") or "未知",
            "price": llm_data.get("price") or details.get("price") or "未知",
            "location": llm_data.get("location") or details.get("location") or "未知",
            # 旧版本叫 transport，新版本叫 utilities，这里做兜底兼容
            "transport": llm_data.get("transport") or llm_data.get("utilities") or details.get("transport") or details.get("utilities") or "未知",
            "source_type": self._infer_source_type(llm_data),
        }

    def _format_message(self, note, llm_data: dict) -> str:
        match_level = llm_data.get('match_level', '未知')
        if match_level == "值得一看":
            match_emoji = "🔥"
            level_text = f"*🔥 强烈推荐 \\- {self._escape_markdown(match_level)}*"
        else:
            match_emoji = "✨"
            level_text = f"*✨ {self._escape_markdown(match_level)}*"

        # 发布时间
        pub_time = datetime.fromtimestamp(note['time'] / 1000).strftime('%Y-%m-%d %H:%M') if note.get('time') else '未知'

        # 可信度评分条
        score = llm_data.get('confidence_score', 0)
        score_bar = "🟢" * (score // 20) + "⚪" * (5 - score // 20)

        # 用户名 - 直接从 note 字典的顶层获取
        user_name = note.get('nickname', '未知用户') or '未知用户'

        # 帖子内容 - 使用 spoiler 标签折叠
        desc = note.get('desc', '无内容') or '无内容'
        # 截取前1000字符避免消息过长
        if len(desc) > 1000:
            desc = desc[:1000] + "..."
        # 使用 ||spoiler|| 语法折叠内容
        desc_spoiler = f"||{self._escape_markdown(desc)}||"

        fields = self._extract_display_fields(llm_data)

        msg = f"{level_text}\n"
        msg += f"━━━━━━━━━━━━━━━━━━\n\n"
        msg += f"📝 *标题*\n{self._escape_markdown(note['title'])}\n\n"
        msg += f"👤 *发布者*: {self._escape_markdown(user_name)}\n"
        msg += f"🏷️ *类型*: `{self._escape_markdown(str(fields.get('type', '未知')))}`\n"
        msg += f"💰 *租金*: `{self._escape_markdown(str(fields.get('price', '未知')))}`\n"
        msg += f"📍 *位置*: {self._escape_markdown(str(fields.get('location', '未知')))}\n"
        msg += f"🚇 *交通/水电*: {self._escape_markdown(str(fields.get('transport', '未知')))}\n"
        msg += f"👥 *来源*: {self._escape_markdown(str(fields.get('source_type', '未知')))}\n"
        msg += f"🕐 *发布*: {self._escape_markdown(pub_time)}\n\n"
        msg += f"📊 *可信度*: {score_bar} `{score}/100`\n\n"
        msg += f"📄 *内容* \\(点击展开\\)\n{desc_spoiler}\n\n"
        msg += f"💡 *分析*\n_{self._escape_markdown(llm_data.get('reason', '无'))}_\n\n"
        msg += f"━━━━━━━━━━━━━━━━━━\n"
        msg += f"[🔗 查看详情]({note['note_url']})"
        return msg

    def run(self):
        with self.db.get_session() as session:
            from sqlalchemy import select
            from src.storage.base.models import XhsNote

            stmt = select(XhsNote).where(XhsNote.llm_filter.isnot(None))
            notes = session.execute(stmt).scalars().all()

            sent_count = 0
            for note in notes:
                if note.note_id in self.sent_notes:
                    continue

                try:
                    llm_data = json.loads(note.llm_filter)
                    if llm_data.get("match_level") in ["值得一看", "稍微符合"]:
                        note_dict = self.db._note_to_dict(note)
                        message = self._format_message(note_dict, llm_data)
                        self._send_telegram(message)
                        self.sent_notes.add(note.note_id)
                        self._save_sent_notes()
                        sent_count += 1
                        time.sleep(1)
                except Exception as e:
                    print(f"处理笔记 {note.note_id} 失败: {e}")

            return sent_count

    def run_loop(self):
        print(f"Telegram通知服务启动，轮询间隔: {POLL_INTERVAL}秒")
        while True:
            try:
                sent = self.run()
                if sent > 0:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发送了 {sent} 条消息")
                time.sleep(POLL_INTERVAL)
            except KeyboardInterrupt:
                print("\n服务已停止")
                break
            except Exception as e:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: {e}")
                time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    notifier = TelegramNotifier()
    notifier.run_loop()
