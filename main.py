import sys
import io

# Force UTF-8 encoding for stdout/stderr to prevent encoding errors
# when outputting Chinese characters in non-UTF-8 terminals
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import asyncio
from datetime import datetime
from typing import Optional, Type

from src.core import arg as cmd
import config
from src.storage.base import db
from src.core.base_crawler import AbstractCrawler
from src.platforms.xhs import XiaoHongShuCrawler
from src.platforms.zhihu import ZhihuCrawler
from src.utils.async_file_writer import AsyncFileWriter
from src.core.var import crawler_type_var


class CrawlerFactory:
    CRAWLERS: dict[str, Type[AbstractCrawler]] = {
        "xhs": XiaoHongShuCrawler,
        "zhihu": ZhihuCrawler,
    }

    @staticmethod
    def create_crawler(platform: str) -> AbstractCrawler:
        crawler_class = CrawlerFactory.CRAWLERS.get(platform)
        if not crawler_class:
            supported = ", ".join(sorted(CrawlerFactory.CRAWLERS))
            raise ValueError(f"Invalid media platform: {platform!r}. Supported: {supported}")
        return crawler_class()


crawler: Optional[AbstractCrawler] = None


def _parse_hhmm(value: str) -> int:
    value = value.strip()
    try:
        hour_str, minute_str = value.split(":")
        hour = int(hour_str)
        minute = int(minute_str)
    except ValueError as exc:
        raise ValueError(f"Invalid time format: {value!r}, expected HH:MM") from exc

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid time value: {value!r}, expected HH:MM within 00:00-23:59")

    return hour * 60 + minute


def _parse_skip_ranges(ranges_text: str) -> list[tuple[int, int]]:
    if not ranges_text or not ranges_text.strip():
        return []

    ranges: list[tuple[int, int]] = []
    for raw_item in ranges_text.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if "-" not in item:
            raise ValueError(f"Invalid range: {item!r}, expected HH:MM-HH:MM")

        start_text, end_text = item.split("-", 1)
        start_min = _parse_hhmm(start_text)
        end_min = _parse_hhmm(end_text)
        if start_min == end_min:
            raise ValueError(f"Invalid range: {item!r}, start and end cannot be the same")

        ranges.append((start_min, end_min))

    return ranges


def _seconds_until_allowed(ranges: list[tuple[int, int]], now: datetime) -> int:
    now_min = now.hour * 60 + now.minute
    now_sec = now.second
    waits: list[int] = []

    for start_min, end_min in ranges:
        if start_min < end_min:
            in_range = start_min <= now_min < end_min
            if not in_range:
                continue
            wait = (end_min - now_min) * 60 - now_sec
        else:
            in_range = now_min >= start_min or now_min < end_min
            if not in_range:
                continue
            if now_min >= start_min:
                wait = ((24 * 60 - now_min) + end_min) * 60 - now_sec
            else:
                wait = (end_min - now_min) * 60 - now_sec

        waits.append(max(wait, 1))

    return min(waits) if waits else 0


async def _run_crawler_once() -> None:
    global crawler

    crawler = CrawlerFactory.create_crawler(platform=config.PLATFORM)
    await crawler.start()

    _flush_excel_if_needed()

    # Generate wordcloud after crawling is complete
    # Only for JSON save mode
    await _generate_wordcloud_if_needed()


def _flush_excel_if_needed() -> None:
    if config.SAVE_DATA_OPTION != "excel":
        return

    try:
        from src.storage.base.excel_store_base import ExcelStoreBase

        ExcelStoreBase.flush_all()
        print("[Main] Excel files saved successfully")
    except Exception as e:
        print(f"[Main] Error flushing Excel data: {e}")


async def _run_scheduled_crawler() -> None:
    skip_ranges = _parse_skip_ranges(config.SCHEDULE_SKIP_TIME_RANGES)
    if skip_ranges:
        print(f"[Main] Schedule skip ranges enabled: {config.SCHEDULE_SKIP_TIME_RANGES}")

    while True:
        now = datetime.now()
        wait_seconds = _seconds_until_allowed(skip_ranges, now)
        if wait_seconds > 0:
            print(
                f"[Main] Current time {now.strftime('%H:%M:%S')} is in skip ranges, "
                f"sleeping {wait_seconds} seconds"
            )
            await asyncio.sleep(wait_seconds)
            continue

        print(f"[Main] Scheduled crawl started, next interval: {config.SCHEDULE_INTERVAL_SEC} seconds")
        try:
            await _run_crawler_once()
        finally:
            await async_cleanup()

        print(f"[Main] Scheduled crawl finished, sleeping {config.SCHEDULE_INTERVAL_SEC} seconds")
        await asyncio.sleep(config.SCHEDULE_INTERVAL_SEC)


async def _generate_wordcloud_if_needed() -> None:
    if config.SAVE_DATA_OPTION != "json" or not config.ENABLE_GET_WORDCLOUD:
        return

    try:
        file_writer = AsyncFileWriter(
            platform=config.PLATFORM,
            crawler_type=crawler_type_var.get(),
        )
        await file_writer.generate_wordcloud_from_comments()
    except Exception as e:
        print(f"[Main] Error generating wordcloud: {e}")


async def main() -> None:
    args = await cmd.parse_cmd()
    try:
        _parse_skip_ranges(args.schedule_skip_time_ranges)
    except ValueError as exc:
        raise SystemExit(f"[Main] Invalid --schedule_skip_time_ranges: {exc}") from exc

    if args.init_db:
        await db.init_db(args.init_db)
        print(f"Database {args.init_db} initialized successfully.")
        return

    if args.schedule:
        await _run_scheduled_crawler()
        return

    await _run_crawler_once()


async def async_cleanup() -> None:
    global crawler
    if crawler:
        if getattr(crawler, "cdp_manager", None):
            try:
                await crawler.cdp_manager.cleanup(force=True)
            except Exception as e:
                error_msg = str(e).lower()
                if "closed" not in error_msg and "disconnected" not in error_msg:
                    print(f"[Main] Error cleaning up CDP browser: {e}")

        elif getattr(crawler, "browser_context", None):
            try:
                await crawler.browser_context.close()
            except Exception as e:
                error_msg = str(e).lower()
                if "closed" not in error_msg and "disconnected" not in error_msg:
                    print(f"[Main] Error closing browser context: {e}")

        crawler = None

    if config.SAVE_DATA_OPTION in ("db", "sqlite"):
        await db.close()

if __name__ == "__main__":
    from src.utils.app_runner import run

    def _force_stop() -> None:
        c = crawler
        if not c:
            return
        cdp_manager = getattr(c, "cdp_manager", None)
        launcher = getattr(cdp_manager, "launcher", None)
        if not launcher:
            return
        try:
            launcher.cleanup()
        except Exception:
            pass

    run(main, async_cleanup, cleanup_timeout_seconds=15.0, on_first_interrupt=_force_stop)
