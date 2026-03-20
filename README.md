# TON Split AI

Telegram bot on Python for:
- receipt photo parsing with OpenAI Vision
- natural-language bill splitting
- TON payment link generation

## Why this version is simple
Only 4 environment variables are needed in normal use:
- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY`
- `DATABASE_URL` (optional)
- `TON_RECEIVER_ADDRESS` (optional)

## Quick start
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e .
cp .env.example .env
python -m app.main
```

The bot runs with long polling. A tiny FastAPI server is also started on `http://127.0.0.1:8080` for health checks.

## Telegram flow
1. Send `/start`
2. Send a receipt photo
3. Bot parses and verifies the receipt
4. Send participants, for example: `me, Sasha, Dima`
5. Assign items in plain language, for example:
   - `coffee me`
   - `pasta Sasha`
   - `water split between me and Dima`
   - `service charge all`
   - `done`
6. Bot shows each share and generates TON payment links

## Accuracy strategy
This project favors correctness over cost:
- image preprocessing with OpenCV + Pillow
- first OpenAI parse pass
- second OpenAI verification pass
- server-side arithmetic validation
- manual correction commands when needed

## Minimal TON integration
MVP uses TON transfer deep links:
- `ton://transfer/<address>?amount=<nanotons>&text=<comment>`

That keeps the project simple while still showing a real TON-native settlement flow.

## Main commands
- `/start`
- `/new`
- `/help`
- `/cancel`

## Notes
- The bot stores receipts and split sessions in SQLite by default.
- OpenAI is used for receipt extraction and intent parsing, but all final math is done in Python.
