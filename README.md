# Boostora

Working Telegram bot build for launch on Bothost.

## Included
- language choice on first start
- Russian, English, German, Spanish, Portuguese, Turkish
- role choice: earner / advertiser
- mandatory chat subscription gate
- profile and wallet
- demo tasks for earners
- demo campaigns for advertisers
- support screen
- admin stats screen
- SQLite database in local file

## Start
1. Copy `.env.example` to `.env`
2. Fill `BOT_TOKEN`
3. Run `python main.py`

## Important
- Add the bot to the required chat from `.env`
- For stable subscription checks, make the bot an admin in that chat
