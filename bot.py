from __future__ import annotations

import json
import os
import secrets
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import requests
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
)

BASE_DIR = Path(__file__).resolve().parent
MATRIX = json.loads((BASE_DIR / "matrix.json").read_text(encoding="utf-8"))

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
SHEETS_URL = os.getenv("GOOGLE_SHEETS_WEBHOOK_URL", "").strip()
SHEETS_SECRET = os.getenv("GOOGLE_SHEETS_WEBHOOK_SECRET", "").strip()
DB_PATH = Path(os.getenv("DB_PATH", "/tmp/personal_ai_maturity.db"))
AUTHOR_NAME = os.getenv("AUTHOR_NAME", "Антон Осьмак").strip()
VERSION = "1.0"

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

TG_API = f"https://api.telegram.org/bot{TOKEN}"

DIMENSIONS = []
for item in MATRIX:
    if item["dimension"] not in [x[0] for x in DIMENSIONS]:
        DIMENSIONS.append((item["dimension"], item["dimension_name"]))

SCALE = {
    0: "Не знаю / не використовую / така практика відсутня",
    1: "Маю лише загальне уявлення або поодинокий досвід",
    2: "Використовую інколи, але несистемно та невпевнено",
    3: "Використовую самостійно у типових ситуаціях",
    4: "Використовую системно, усвідомлено та впевнено",
    5: "Використовую системно, можу адаптувати практику до нових ситуацій та пояснити її іншим",
}

CLASSIFIERS = [
    ("sector", "Сфера діяльності", [
        "Публічний сектор", "Бізнес", "Освіта і наука", "Громадський сектор", "Інше"
    ]),
    ("position", "Тип посади / статус", [
        "Керівник", "Фахівець", "Викладач-дослідник", "Здобувач освіти", "Інше"
    ]),
    ("age_group", "Вікова група", ["до 25", "25–34", "35–44", "45–54", "55+"]),
    ("ai_experience", "Досвід використання ШІ", ["<1 року", "1–2 роки", "3+ роки"]),
]

RECOMMENDATIONS = {
    "D1": (
        "Розуміння ШІ",
        "Поглиблюйте базове розуміння принципів роботи сучасних моделей ШІ, їхніх можливостей, "
        "обмежень, залежності від даних і ролі людини у прийнятті остаточного рішення."
    ),
    "D2": (
        "Практичне використання ШІ",
        "Розширюйте спектр практичних сценаріїв використання ШІ та поступово інтегруйте його у "
        "регулярні робочі або навчальні процеси, оцінюючи реальну економію часу й якість результату."
    ),
    "D3": (
        "Постановка завдань і взаємодія з ШІ",
        "Удосконалюйте формулювання запитів: задавайте контекст, критерії результату, формат відповіді, "
        "розбивайте складні завдання на етапи та використовуйте ітеративне уточнення."
    ),
    "D4": (
        "Критичне оцінювання результатів",
        "Посилюйте практики перевірки фактів, джерел і логіки відповідей ШІ. Для важливих рішень "
        "порівнюйте результат із незалежними джерелами та зберігайте критичну дистанцію до рекомендацій моделі."
    ),
    "D5": (
        "Дані, приватність і безпека",
        "Систематизуйте правила роботи з персональними, конфіденційними та службовими даними: "
        "мінімізуйте їх передавання, застосовуйте анонімізацію та перевіряйте умови використання даних сервісами ШІ."
    ),
    "D6": (
        "Етичне та відповідальне використання",
        "Формалізуйте власні правила відповідального використання ШІ: дотримуйтеся академічної та професійної "
        "доброчесності, позначайте використання ШІ там, де це потрібно, і враховуйте ризики упередженості."
    ),
    "D7": (
        "Людино-машинна співпраця",
        "Розвивайте модель співпраці «людина + ШІ»: свідомо розподіляйте функції, зберігайте контроль над "
        "кінцевим результатом, підтримуйте незалежність судження та власну здатність до аналізу."
    ),
    "D8": (
        "Розвиток і адаптивність",
        "Регулярно тестуйте нові інструменти та функції ШІ, оцінюйте їхню реальну корисність і коригуйте "
        "власні практики на основі досвіду, а не лише технологічної новизни."
    ),
}

FOOTER_LINES = [
    "Personal AI Maturity Bot — дослідницький інформаційно-аналітичний інструмент для комплексного оцінювання персональної AI-зрілості.",
    "Результат є самооцінкою і не є об’єктивним вимірюванням професійної кваліфікації.",
    "@AI_Maturity_Bot · ai.maturity.bot@gmail.com · ©2026, Антон Осьмак",
]

def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS tests(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          chat_id INTEGER NOT NULL,
          test_id TEXT NOT NULL UNIQUE,
          status TEXT NOT NULL,
          classifier_index INTEGER NOT NULL DEFAULT 0,
          question_index INTEGER NOT NULL DEFAULT 0,
          sector TEXT, position TEXT, age_group TEXT, ai_experience TEXT,
          created_at TEXT NOT NULL, finished_at TEXT, sheets_saved INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS answers(
          test_id TEXT NOT NULL, code TEXT NOT NULL, score INTEGER NOT NULL,
          PRIMARY KEY(test_id, code)
        );
        """)
init_db()

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def tg(method: str, payload=None, files=None):
    r = requests.post(f"{TG_API}/{method}", data=payload or {}, files=files, timeout=45)
    r.raise_for_status()
    return r.json()

def send(chat_id, text, reply_markup=None):
    p = {"chat_id": chat_id, "text": text}
    if reply_markup:
        p["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    return tg("sendMessage", p)

def answer_callback(callback_id):
    try:
        tg("answerCallbackQuery", {"callback_query_id": callback_id})
    except Exception:
        pass

def main_menu_markup():
    return {
        "keyboard": [
            [{"text": "▶️ Розпочати оцінювання"}],
            [{"text": "ℹ️ Про інструмент"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def send_main_menu(chat_id):
    send(
        chat_id,
        "Оберіть подальшу дію:",
        main_menu_markup()
    )

def about_text():
    return """ℹ️ Про інструмент

Personal AI Maturity Bot — дослідницький інформаційно-аналітичний інструмент для комплексного самооцінювання персональної AI-зрілості.

Інструмент дає змогу оцінити готовність людини до усвідомленого, системного, критичного та відповідального використання технологій штучного інтелекту у професійній, освітній та повсякденній діяльності.

Оцінювання містить 48 тверджень, об’єднаних у 8 взаємопов’язаних вимірів персональної AI-зрілості (D1–D8). Кожне твердження оцінюється за шкалою від 0 до 5.

За результатами формується:
• інтегральний Personal AI Maturity Index (PAIMI);
• рівень персональної AI-зрілості I–V;
• профіль за вісьмома вимірами D1–D8;
• графічна візуалізація профілю;
• рекомендації щодо подальшого підвищення рівня персональної AI-зрілості;
• персональний PDF-звіт.

Перед основним оцінюванням пропонуються 4 необов’язкові класифікаційні питання щодо сфери діяльності, типу посади/статусу, вікової групи та досвіду використання ШІ. Вони використовуються виключно для агрегованого аналізу результатів дослідження, не впливають на значення PAIMI та можуть бути пропущені.

🔒 Конфіденційність

Інструмент не запитує та не зберігає у дослідницькій базі персональні дані, які дають змогу безпосередньо ідентифікувати респондента: ім’я та прізвище, номер телефону, адресу електронної пошти або Telegram username.

Результати оцінювання передаються до дослідницької бази у псевдонімізованому вигляді та пов’язуються лише з автоматично сформованим Test ID. Telegram ID користувача до дослідницької бази результатів не передається.

Отримані дані можуть використовуватися в узагальненому та статистично агрегованому вигляді для наукового дослідження персональної AI-зрілості.

Важливо: результат є самооцінкою і не є об’єктивним вимірюванням професійної кваліфікації, сертифікацією або експертною оцінкою компетентності.

Personal AI Maturity Bot
Дослідницький інформаційно-аналітичний інструмент
@AI_Maturity_Bot · ai.maturity.bot@gmail.com
©2026, Антон Осьмак"""

def configure_telegram_webhook():
    if not RENDER_EXTERNAL_URL:
        return
    url = RENDER_EXTERNAL_URL + "/telegram/webhook"
    p = {"url": url, "allowed_updates": json.dumps(["message", "callback_query"])}
    if TG_SECRET:
        p["secret_token"] = TG_SECRET
    try:
        tg("setWebhook", p)
        # Мінімальне меню команд: без журналу та останнього PDF.
        commands = [
            {"command": "start", "description": "Головне меню"},
            {"command": "new", "description": "Розпочати оцінювання"},
            {"command": "status", "description": "Стан поточного оцінювання"},
            {"command": "cancel", "description": "Скасувати поточне оцінювання"},
        ]
        tg("setMyCommands", {"commands": json.dumps(commands, ensure_ascii=False)})
    except Exception as e:
        print("Webhook/UI setup error:", e)

def make_test_id():
    return "PAIM-" + datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + secrets.token_hex(3).upper()

def latest_test(chat_id):
    with db() as c:
        return c.execute("SELECT * FROM tests WHERE chat_id=? ORDER BY id DESC LIMIT 1", (chat_id,)).fetchone()

def start_test(chat_id):
    prev = latest_test(chat_id)
    if prev and prev["status"] in ("classify", "testing"):
        send(chat_id, "У вас уже є незавершене оцінювання. Продовжіть його або скасуйте командою /cancel.")
        return
    tid = make_test_id()
    with db() as c:
        c.execute(
            "INSERT INTO tests(chat_id,test_id,status,created_at) VALUES(?,?,?,?)",
            (chat_id, tid, "classify", now_iso())
        )
    send(
        chat_id,
        "PERSONAL AI MATURITY INDEX (PAIMI)\n\n"
        "Самооцінювання персональної AI-зрілості: 48 тверджень у 8 вимірах D1–D8.\n"
        "Перед тестом — 4 необов’язкові класифікаційні питання для агрегованого дослідження. "
        "Вони не впливають на результат і їх можна пропустити.\n\n"
        "Шкала відповідей: 0–5.",
        {"remove_keyboard": True}
    )
    ask_classifier(chat_id, tid, 0)

def ask_classifier(chat_id, test_id, idx):
    if idx >= len(CLASSIFIERS):
        with db() as c:
            c.execute("UPDATE tests SET status='testing', classifier_index=4 WHERE test_id=?", (test_id,))
        send(chat_id, "Класифікаційний блок завершено. Починаємо основне оцінювання.")
        ask_question(chat_id, test_id, 0)
        return
    key, title, options = CLASSIFIERS[idx]
    rows = [[{"text": opt, "callback_data": f"cls:{idx}:{i}"}] for i, opt in enumerate(options)]
    rows.append([{"text": "Пропустити", "callback_data": f"cls:{idx}:skip"}])
    send(chat_id, f"{idx+1}/4. {title}", {"inline_keyboard": rows})

def ask_question(chat_id, test_id, idx):
    item = MATRIX[idx]
    buttons = [[{"text": str(s), "callback_data": f"score:{idx}:{s}"} for s in range(6)]]
    text = (
        f"{idx+1}/48  {item['code']} — {item['criterion']}\n"
        f"{item['dimension']}. {item['dimension_name']}\n\n"
        f"{item['question']}\n\n"
        "Оцініть від 0 до 5."
    )
    send(chat_id, text, {"inline_keyboard": buttons})

def calc(test_id):
    with db() as c:
        rows = c.execute("SELECT code,score FROM answers WHERE test_id=?", (test_id,)).fetchall()
    scores = {r["code"]: int(r["score"]) for r in rows}
    dims = {}
    for dim, _ in DIMENSIONS:
        codes = [x["code"] for x in MATRIX if x["dimension"] == dim]
        vals = [scores[c] for c in codes if c in scores]
        dims[dim] = sum(vals) / (len(codes) * 5) * 100 if len(vals) == len(codes) else 0.0
    complete = len(scores) == 48
    paim = sum(scores.values()) / (48 * 5) * 100 if complete else 0.0
    return {"scores": scores, "dims": dims, "paim": paim, "complete": complete}

def maturity_level(p):
    if p <= 20: return "I — Початковий"
    if p <= 40: return "II — Фрагментарний"
    if p <= 60: return "III — Системний"
    if p <= 80: return "IV — Інтегрований"
    return "V — Трансформаційний"

def profile_name(dims):
    vals = list(dims.values())
    if max(vals) - min(vals) <= 10:
        return "Збалансований профіль"
    strongest = max(dims, key=dims.get)
    return f"Профіль з провідним виміром {strongest}"

def build_recommendations(result):
    dims = result["dims"]
    ordered = sorted(dims.items(), key=lambda x: x[1])

    # Фокус на трьох найнижчих вимірах; якщо профіль дуже сильний — на двох.
    n = 2 if result["paim"] >= 80 else 3
    selected = ordered[:n]

    recs = []
    for dim, value in selected:
        title, text = RECOMMENDATIONS[dim]
        recs.append((dim, title, value, text))

    if result["paim"] < 40:
        general = (
            "Загальний пріоритет: сформувати базові, регулярні та безпечні практики використання ШІ. "
            "Доцільно рухатися від простих повторюваних завдань до складніших сценаріїв, зберігаючи перевірку результатів."
        )
    elif result["paim"] < 60:
        general = (
            "Загальний пріоритет: перейти від фрагментарного використання ШІ до системної особистої практики — "
            "з чіткими правилами постановки завдань, перевірки результатів і захисту даних."
        )
    elif result["paim"] < 80:
        general = (
            "Загальний пріоритет: вирівняти профіль D1–D8 та посилити слабші виміри, щоб системне використання ШІ "
            "поєднувалося з критичністю, безпекою, етичністю та збереженням когнітивної автономності."
        )
    else:
        general = (
            "Загальний пріоритет: підтримувати високий рівень зрілості, регулярно переглядати власні практики, "
            "експериментувати з новими інструментами та поширювати перевірені підходи без втрати критичності й автономності."
        )
    return general, recs

def recommendations_text(result):
    general, recs = build_recommendations(result)
    lines = ["Рекомендації щодо підвищення рівня персональної AI-зрілості", "", general, ""]
    for dim, title, value, text in recs:
        lines.append(f"{dim} — {title} ({value:.1f}%).")
        lines.append(text)
        lines.append("")
    lines.append("Рекомендації сформовано на основі результатів самооцінювання та профілю D1–D8.")
    return "\n".join(lines).strip()

def make_radar(test_id, dims):
    labels = [d for d, _ in DIMENSIONS]
    values = [dims[d] for d in labels]
    values += values[:1]
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    angles += angles[:1]
    fig = plt.figure(figsize=(6.4, 6.4))
    ax = plt.subplot(111, polar=True)
    ax.plot(angles, values, linewidth=2)
    ax.fill(angles, values, alpha=.12)
    ax.set_thetagrids(np.degrees(angles[:-1]), labels)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_title("Профіль персональної AI-зрілості", pad=22)
    p = Path(tempfile.gettempdir()) / f"{test_id}_radar.png"
    fig.savefig(p, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return p

def _fonts():
    regular_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    bold_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]
    reg_name, bold_name = "Helvetica", "Helvetica-Bold"
    for p in regular_candidates:
        if Path(p).exists():
            try:
                pdfmetrics.registerFont(TTFont("PAIMRegular", p))
                reg_name = "PAIMRegular"
                break
            except Exception:
                pass
    for p in bold_candidates:
        if Path(p).exists():
            try:
                pdfmetrics.registerFont(TTFont("PAIMBold", p))
                bold_name = "PAIMBold"
                break
            except Exception:
                pass
    return reg_name, bold_name

def make_pdf(test_row, result):
    font, bold = _fonts()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("TitleUA", parent=styles["Title"], fontName=bold, fontSize=18, leading=23, alignment=TA_CENTER)
    h = ParagraphStyle("HUA", parent=styles["Heading2"], fontName=bold, fontSize=12.5, leading=16)
    body = ParagraphStyle("BodyUA", parent=styles["BodyText"], fontName=font, fontSize=9.2, leading=12.5)
    small = ParagraphStyle("SmallUA", parent=body, fontSize=7.5, leading=9.5)
    path = Path(tempfile.gettempdir()) / f"PAIM_Report_{test_row['test_id']}.pdf"

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#BDBDBD"))
        canvas.setLineWidth(0.3)
        canvas.line(15 * mm, 18 * mm, A4[0] - 15 * mm, 18 * mm)
        canvas.setFont(font, 6.1)
        y = 14.5 * mm
        for line in FOOTER_LINES:
            canvas.drawCentredString(A4[0] / 2, y, line)
            y -= 3.3 * mm
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        rightMargin=16 * mm, leftMargin=16 * mm,
        topMargin=15 * mm, bottomMargin=27 * mm
    )

    story = [
        Spacer(1, 12 * mm),
        Paragraph("PERSONAL AI MATURITY INDEX (PAIMI)", title),
        Spacer(1, 4 * mm),
        Paragraph("Звіт про самооцінювання персональної AI-зрілості", h),
        Spacer(1, 9 * mm),
        Paragraph(f"Test ID: {test_row['test_id']}", body),
        Paragraph(f"Дата: {test_row['finished_at'] or test_row['created_at']}", body),
        Spacer(1, 12 * mm),
        Paragraph(f"PAIMI: <b>{result['paim']:.1f}%</b>", title),
        Paragraph(f"Рівень: <b>{maturity_level(result['paim'])}</b>", h),
        Spacer(1, 7 * mm),
        Paragraph(
            "Методика: 48 тверджень, 8 вимірів, шкала 0–5. "
            "PAIMI = сума балів / 240 × 100%. Результат відображає самооцінку респондента.",
            body
        ),
        Spacer(1, 7 * mm),
        Image(str(make_radar(test_row["test_id"], result["dims"])), width=112 * mm, height=112 * mm),
        PageBreak(),
        Paragraph("Результати за вимірами D1–D8", h),
        Spacer(1, 3 * mm),
    ]

    data = [["Вимір", "Назва", "Результат, %"]]
    for dim, name in DIMENSIONS:
        data.append([dim, name, f"{result['dims'][dim]:.1f}"])
    t = Table(data, colWidths=[18 * mm, 105 * mm, 30 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTNAME", (0, 0), (-1, 0), bold),
        ("FONTSIZE", (0, 0), (-1, -1), 8.3),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8E8E8")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (2, 1), (2, -1), "RIGHT")
    ]))
    story += [t, Spacer(1, 7 * mm)]

    general, recs = build_recommendations(result)
    story += [
        Paragraph("Рекомендації щодо підвищення рівня персональної AI-зрілості", h),
        Spacer(1, 3 * mm),
        Paragraph(general, body),
        Spacer(1, 4 * mm),
    ]
    for dim, rtitle, value, rtext in recs:
        story.append(Paragraph(f"<b>{dim} — {rtitle} ({value:.1f}%)</b>", body))
        story.append(Paragraph(rtext, body))
        story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Рекомендації сформовано на основі результатів самооцінювання та профілю D1–D8.", small))

    story += [PageBreak(), Paragraph("Деталізація відповідей", h)]
    ans = [["Код", "Бал", "Твердження"]]
    for item in MATRIX:
        ans.append([
            item["code"],
            str(result["scores"].get(item["code"], "")),
            Paragraph(item["question"], small)
        ])
    at = Table(ans, colWidths=[18 * mm, 14 * mm, 140 * mm], repeatRows=1)
    at.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTNAME", (0, 0), (-1, 0), bold),
        ("FONTSIZE", (0, 0), (-1, -1), 7.3),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8E8E8")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 1), (1, -1), "CENTER")
    ]))
    story.append(at)

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path

def save_to_sheets(test_row, result):
    if not SHEETS_URL or not SHEETS_SECRET:
        return False
    level_full = maturity_level(result["paim"])
    level_roman = level_full.split(" ", 1)[0]
    payload = {
        "secret": SHEETS_SECRET,
        "test_id": test_row["test_id"],
        "timestamp": test_row["finished_at"] or now_iso(),
        "sector": test_row["sector"] or "",
        "position": test_row["position"] or "",
        "age_group": test_row["age_group"] or "",
        "ai_experience": test_row["ai_experience"] or "",
        **{d.lower(): round(result["dims"][d], 2) for d, _ in DIMENSIONS},
        "paim": round(result["paim"], 2),
        "level": level_roman,
        "profile": profile_name(result["dims"]),
        "answers": [
            {"question": item["code"], "dimension": item["dimension"], "score": result["scores"][item["code"]]}
            for item in MATRIX
        ]
    }
    try:
        r = requests.post(SHEETS_URL, json=payload, timeout=30, allow_redirects=True)
        r.raise_for_status()
        data = r.json()
        return bool(data.get("ok"))
    except Exception as e:
        print("Google Sheets write error:", repr(e))
        return False

def finish(chat_id, test_id):
    result = calc(test_id)
    if not result["complete"]:
        send(chat_id, "Не всі 48 відповідей отримано. Продовжіть оцінювання.")
        return

    finished = now_iso()
    with db() as c:
        c.execute("UPDATE tests SET status='finished',finished_at=? WHERE test_id=?", (finished, test_id))
        row = c.execute("SELECT * FROM tests WHERE test_id=?", (test_id,)).fetchone()

    sheets_ok = save_to_sheets(row, result)
    if sheets_ok:
        with db() as c:
            c.execute("UPDATE tests SET sheets_saved=1 WHERE test_id=?", (test_id,))

    lines = [
        "Оцінювання завершено.",
        f"PAIMI: {result['paim']:.1f}%",
        f"Рівень: {maturity_level(result['paim'])}",
        "",
        *[f"{d}: {result['dims'][d]:.1f}%" for d, _ in DIMENSIONS],
    ]
    send(chat_id, "\n".join(lines))
    send(chat_id, recommendations_text(result))

    pdf = make_pdf(row, result)
    with open(pdf, "rb") as f:
        tg(
            "sendDocument",
            {"chat_id": chat_id, "caption": f"PAIMI — {row['test_id']}"},
            {"document": (pdf.name, f, "application/pdf")}
        )

    # Передостаннє повідомлення
    send(chat_id, "Дякую за увагу!")

    # Останнє повідомлення — базове меню
    send_main_menu(chat_id)

def process_update(update: dict[str, Any]):
    if "callback_query" in update:
        cb = update["callback_query"]
        answer_callback(cb["id"])
        msg = cb.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        data = cb.get("data", "")
        if not chat_id:
            return
        row = latest_test(chat_id)
        if not row:
            return

        if data.startswith("cls:") and row["status"] == "classify":
            _, idx_s, val = data.split(":", 2)
            idx = int(idx_s)
            if idx != row["classifier_index"]:
                return
            key, title, options = CLASSIFIERS[idx]
            chosen = "" if val == "skip" else options[int(val)]
            with db() as c:
                c.execute(
                    f"UPDATE tests SET {key}=?,classifier_index=? WHERE test_id=?",
                    (chosen, idx + 1, row["test_id"])
                )
            ask_classifier(chat_id, row["test_id"], idx + 1)
            return

        if data.startswith("score:") and row["status"] == "testing":
            _, idx_s, score_s = data.split(":")
            idx, score = int(idx_s), int(score_s)
            if idx != row["question_index"] or score not in range(6):
                return
            item = MATRIX[idx]
            with db() as c:
                c.execute(
                    "INSERT OR REPLACE INTO answers(test_id,code,score) VALUES(?,?,?)",
                    (row["test_id"], item["code"], score)
                )
                c.execute(
                    "UPDATE tests SET question_index=? WHERE test_id=?",
                    (idx + 1, row["test_id"])
                )
            if idx + 1 < 48:
                ask_question(chat_id, row["test_id"], idx + 1)
            else:
                finish(chat_id, row["test_id"])
            return

    msg = update.get("message") or {}
    chat_id = msg.get("chat", {}).get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id:
        return

    if text == "/start":
        send(chat_id, about_text(), main_menu_markup())
        return

    if text in ("/new", "▶️ Розпочати оцінювання"):
        start_test(chat_id)
        return

    if text == "ℹ️ Про інструмент":
        send(chat_id, about_text(), main_menu_markup())
        return

    if text == "/status":
        row = latest_test(chat_id)
        if not row:
            send(chat_id, "Активних оцінювань немає.", main_menu_markup())
            return
        send(
            chat_id,
            f"Test ID: {row['test_id']}\nСтатус: {row['status']}\nВідповідей: {row['question_index']}/48"
        )
        return

    if text == "/cancel":
        row = latest_test(chat_id)
        if row and row["status"] in ("classify", "testing"):
            with db() as c:
                c.execute("UPDATE tests SET status='cancelled' WHERE test_id=?", (row["test_id"],))
            send(chat_id, "Поточне оцінювання скасовано.")
            send_main_menu(chat_id)
        else:
            send(chat_id, "Активного оцінювання немає.", main_menu_markup())
        return

    send(chat_id, "Не розпізнав команду.", main_menu_markup())
