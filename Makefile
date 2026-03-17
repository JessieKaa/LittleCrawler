llm-processor:
	uv run -m llm_processor.listener

# TELEGRAM_BOT_TOKEN
# TELEGRAM_CHAT_ID
llm-tg-notifier:
	uv run llm_processor/telegram_notifier.py

# OPENAI_MODEL
# OPENAI_API_KEY
# OPENAI_API_BASE
run-schedule:
	uv run main.py --schedule

run-note-viewer:
	uv run note_viewer/app.py