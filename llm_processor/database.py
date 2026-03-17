import json
import sys
from typing import List, Dict
from pathlib import Path
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.base.models import XhsNote
from llm_processor.config import (
    MYSQL_DB_USER, MYSQL_DB_PWD, MYSQL_DB_HOST,
    MYSQL_DB_PORT, MYSQL_DB_NAME, SQLITE_DB_PATH, DB_TYPE
)


class DatabaseManager:
    def __init__(self):
        self.engine = self._create_engine()
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _create_engine(self):
        if DB_TYPE == "mysql":
            db_url = f"mysql+pymysql://{MYSQL_DB_USER}:{MYSQL_DB_PWD}@{MYSQL_DB_HOST}:{MYSQL_DB_PORT}/{MYSQL_DB_NAME}?charset=utf8mb4"
        else:
            db_url = f"sqlite:///{SQLITE_DB_PATH}"
        return create_engine(db_url, poolclass=QueuePool, pool_size=5, max_overflow=10, pool_pre_ping=True, echo=False)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def get_new_notes(self, limit: int) -> List[Dict]:
        """获取 llm_filter 为空的笔记"""
        with self.get_session() as session:
            # 查询 llm_filter 为空的笔记，按时间排序
            stmt = select(XhsNote).where(
                (XhsNote.llm_filter.is_(None)) | (XhsNote.llm_filter == '')
            ).order_by(XhsNote.add_ts.asc()).limit(limit)
            results = session.execute(stmt).scalars().all()
            return [self._note_to_dict(note) for note in results]

    def update_note_llm_filter(self, note_id: str, llm_filter_data: Dict):
        with self.get_session() as session:
            # 提取额外字段保存到 llm_filter
            extra_fields = {k: v for k, v in llm_filter_data.items() if k != "id"}
            llm_filter_json = json.dumps(extra_fields, ensure_ascii=False)

            stmt = update(XhsNote).where(XhsNote.note_id == note_id).values(llm_filter=llm_filter_json)
            session.execute(stmt)
            session.commit()

    @staticmethod
    def _note_to_dict(note: XhsNote) -> Dict:
        return {
            "id": note.id,
            "note_id": note.note_id,
            "user_id": note.user_id,
            "nickname": note.nickname,
            "avatar": note.avatar,
            "ip_location": note.ip_location,
            "type": note.type,
            "title": note.title,
            "desc": note.desc,
            "video_url": note.video_url,
            "time": note.time,
            "last_update_time": note.last_update_time,
            "liked_count": note.liked_count,
            "collected_count": note.collected_count,
            "comment_count": note.comment_count,
            "share_count": note.share_count,
            "image_list": note.image_list,
            "tag_list": note.tag_list,
            "note_url": note.note_url,
            "source_keyword": note.source_keyword,
            "xsec_token": note.xsec_token,
            "add_ts": note.add_ts,
            "last_modify_ts": note.last_modify_ts,
        }

    def close(self):
        self.engine.dispose()
