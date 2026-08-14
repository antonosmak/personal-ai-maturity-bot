# Personal AI Maturity Bot — v0.2.0

Telegram-бот для самооцінювання персональної ШІ-зрілості (PAIMI).

## v0.2.0
- 4 необов'язкові класифікаційні питання перед тестом;
- 48 тверджень у 8 вимірах D1–D8, шкала 0–5;
- PAIMI = сума балів / 240 × 100%;
- рівні I–V;
- PDF-звіт з D1–D8, радарним профілем та відповідями;
- псевдонімний `Test_ID`;
- передавання завершених тестів у Google Sheets через Apps Script;
- `RESULTS`: 1 тест = 1 рядок;
- `ANSWERS`: 48 рядків на тест;
- помилка Google Sheets не скасовує тест і не блокує PDF.

## Render
Build Command:
`pip install -r requirements.txt`

Start Command:
`gunicorn --bind 0.0.0.0:$PORT app:app`

Environment:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `GOOGLE_SHEETS_WEBHOOK_URL`
- `GOOGLE_SHEETS_WEBHOOK_SECRET`

`RENDER_EXTERNAL_URL` Render встановлює автоматично.

## Google Sheets
Очікувані аркуші:
- `RESULTS`: `Test_ID | Timestamp | Sector | Position | Age_Group | AI_Experience | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | PAIM | Level | Profile`
- `ANSWERS`: `Test_ID | Question | Dimension | Score`
- `SUMMARY`: формули/агрегація на стороні Google Sheets.

Apps Script має приймати JSON-поля, визначені у `save_to_sheets()`.

## Приватність
У Google Sheets не передаються Telegram ID, username, ім'я або ПІБ. Зв'язувальним ключем є випадковий `Test_ID`.

## Команди
`/start`, `/help`, `/new`, `/status`, `/report`, `/cancel`

## Важливо
PAIMI є самооцінкою респондента і не є об'єктивним вимірюванням професійної кваліфікації.
