# TON Split AI

Simple Telegram bot that:
- reads receipt photos using AI
- understands natural language
- splits bills between people
- generates TON payment links

## Quick Start

```bash
python -m venv .venv
pip install -e .
cp .env.example .env
python -m app.main
```

## Required ENV

- TELEGRAM_BOT_TOKEN
- OPENAI_API_KEY

Optional:
- DATABASE_URL (default: SQLite file)
- TON_RECEIVER_ADDRESS

## How it works

1. Send receipt photo
2. Bot extracts items using AI
3. Add participants (e.g. `me, Sasha, Dima`)
4. Describe who pays in plain language:
   - `coffee me`
   - `all drinks Sasha`
   - `dessert split between me and Dima`
   - `everything else Anna`
5. Bot builds final split and shows summary
6. Generate TON payment links

## Key Features

- AI receipt parsing (Vision)
- Natural language understanding
- Smart matching + AI fallback
- Works with RU/EN mixed input
- Handles corrections like a human

## Storage

- SQLite by default (`./data/app.db`)
- No setup needed

## Notes

- AI is used only for understanding
- All calculations are done on backend
- Designed for demo + hackathon usage
