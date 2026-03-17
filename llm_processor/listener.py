import time
import logging
import signal
import sys
from typing import List, Dict
from datetime import datetime

from llm_processor.config import POLL_INTERVAL, BATCH_SIZE, LOG_DIR, LOG_LEVEL, STATE_FILE
from llm_processor.database import DatabaseManager
from llm_processor.llm_client import LLMClient
from llm_processor.state_manager import StateManager


class LLMListener:
    def __init__(self):
        self.running = False
        self.logger = self._setup_logger()
        self.db_manager = DatabaseManager()
        self.llm_client = LLMClient(self.logger)
        self.state_manager = StateManager(STATE_FILE)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger("LLMListener")
        logger.setLevel(getattr(logging, LOG_LEVEL))

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)

        log_file = f"{LOG_DIR}/llm_processor_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)

        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

        return logger

    def _signal_handler(self, signum, frame):
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop()

    def start(self):
        self.running = True
        self.logger.info("=" * 60)
        self.logger.info("LLM Listener Started")
        self.logger.info(f"Poll Interval: {POLL_INTERVAL} seconds")
        self.logger.info(f"Batch Size: {BATCH_SIZE}")
        self.logger.info("=" * 60)

        try:
            while self.running:
                self._process_cycle()
                time.sleep(POLL_INTERVAL)
        except Exception as e:
            self.logger.error(f"Fatal error: {e}", exc_info=True)
        finally:
            self.cleanup()

    def _process_cycle(self):
        try:
            # 获取 llm_filter 为空的笔记
            new_notes = self.db_manager.get_new_notes(BATCH_SIZE)

            if not new_notes:
                return

            self.logger.info(f"Found {len(new_notes)} unprocessed notes (llm_filter is empty)")

            llm_results = self.llm_client.filter_notes(new_notes)

            if llm_results:
                self._save_results(llm_results)

            self.state_manager.increment_processed(len(new_notes))
            self.state_manager.save_state()

        except Exception as e:
            self.logger.error(f"Error in process cycle: {e}", exc_info=True)

    def _save_results(self, llm_results: List[Dict]):
        for result in llm_results:
            try:
                note_id = result.get("id")
                if note_id:
                    self.db_manager.update_note_llm_filter(note_id, result)
                    self.logger.info(f"Updated note {note_id} with LLM filter data")
            except Exception as e:
                self.logger.error(f"Failed to save result for note {result.get('id')}: {e}")

    def stop(self):
        self.running = False
        self.logger.info("Stopping LLM Listener...")

    def cleanup(self):
        self.logger.info("Cleaning up resources...")
        self.state_manager.save_state()
        self.db_manager.close()
        self.logger.info("LLM Listener stopped")


def main():
    listener = LLMListener()
    listener.start()


if __name__ == "__main__":
    main()
