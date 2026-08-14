# Personal AI Maturity Bot — v0.1.0

Перший робочий прототип Telegram-бота для самооцінювання персональної ШІ-зрілості.

Функції: 48 питань / 8 блоків D1–D8; ручний режим; шкала 0–5; автоматичний PAIMI; рівні I–V; радарний профіль; PDF-звіт; журнал оцінювань; повторне проходження.

## Render Environment
- `TELEGRAM_BOT_TOKEN` — обов'язково
- `TELEGRAM_WEBHOOK_SECRET` — рекомендовано
- `RENDER_EXTERNAL_URL` — Render задає автоматично
- `PUBLIC_BOT_USERNAME` — опційно
- `CONTACT_EMAIL` — опційно
- `AUTHOR_NAME` — опційно, за замовчуванням Антон Осьмак
- `DB_PATH` — опційно

## Render Start Command
`gunicorn --bind 0.0.0.0:$PORT app:app`
