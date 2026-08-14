from __future__ import annotations
import json, mimetypes, os, sqlite3
from datetime import datetime, timezone
from pathlib import Path

import httpx
import matplotlib.pyplot as plt
import numpy as np
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak

BASE_DIR = Path(__file__).resolve().parent
MATRIX = json.loads((BASE_DIR / "matrix.json").read_text(encoding="utf-8"))
DIMENSIONS = []
for item in MATRIX:
    if item["dimension"] not in [d[0] for d in DIMENSIONS]:
        DIMENSIONS.append((item["dimension"], item["dimension_name"]))

TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN", "") or "").strip()
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "personal_ai_maturity.db")))
PUBLIC_BOT_USERNAME = (os.getenv("PUBLIC_BOT_USERNAME", "") or "").strip()
CONTACT_EMAIL = (os.getenv("CONTACT_EMAIL", "") or "").strip()
AUTHOR = (os.getenv("AUTHOR_NAME", "Антон Осьмак") or "Антон Осьмак").strip()
if not TOKEN:
    raise SystemExit("Не задано TELEGRAM_BOT_TOKEN")
API = f"https://api.telegram.org/bot{TOKEN}"

SCALE = {
    0: "Не знаю / не використовую",
    1: "Загальне уявлення / поодинокий досвід",
    2: "Несистемно / невпевнено",
    3: "Самостійно у типових ситуаціях",
    4: "Системно, усвідомлено та впевнено",
    5: "Системно, адаптивно, можу пояснити іншим",
}

def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS assessments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER,
            username TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            current_index INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS answers(
            assessment_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            score INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(assessment_id,code)
        );
        """)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def maturity_level(v):
    return (
        "I — Початковий" if v <= 20 else
        "II — Фрагментарний" if v <= 40 else
        "III — Системний" if v <= 60 else
        "IV — Інтегрований" if v <= 80 else
        "V — Трансформаційний"
    )

def calc_results(aid):
    with db() as c:
        rows = c.execute("SELECT code,score FROM answers WHERE assessment_id=?", (aid,)).fetchall()
    scores = {r["code"]: int(r["score"]) for r in rows}
    dims = {}
    for d, _ in DIMENSIONS:
        codes = [x["code"] for x in MATRIX if x["dimension"] == d]
        vals = [scores[k] for k in codes if k in scores]
        dims[d] = (sum(vals) / (5 * len(vals)) * 100) if vals else None
    n = len(scores)
    paimi = sum(scores.values()) / (5 * n) * 100 if n else 0
    return {"scores": scores, "dims": dims, "paimi": paimi, "answered": n, "complete": n == 48}

async def tg(method, payload=None, files=None):
    async with httpx.AsyncClient(timeout=60) as client:
        if files:
            r = await client.post(f"{API}/{method}", data=payload or {}, files=files)
        else:
            r = await client.post(f"{API}/{method}", json=payload or {})
        if r.status_code >= 400:
            print("Telegram API error:", method, r.status_code, r.text[:1000], flush=True)
            raise RuntimeError(f"Telegram {method}: HTTP {r.status_code}")
        data = r.json()
        if not data.get("ok", True):
            raise RuntimeError(data)
        return data.get("result")

async def send(chat, text, keyboard=None):
    payload = {"chat_id": chat, "text": text}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    await tg("sendMessage", payload)

async def send_start(chat, text):
    await tg("sendMessage", {
        "chat_id": chat,
        "text": text,
        "reply_markup": {
            "keyboard": [[{"text": "▶️ Розпочати оцінювання"}]],
            "resize_keyboard": True,
            "one_time_keyboard": False,
        },
    })

async def send_document(chat, path, caption=""):
    with path.open("rb") as f:
        await tg("sendDocument", {"chat_id": str(chat), "caption": caption},
                 {"document": (path.name, f, "application/pdf")})

async def send_photo(chat, path, caption=""):
    with path.open("rb") as f:
        await tg("sendPhoto", {"chat_id": str(chat), "caption": caption},
                 {"photo": (path.name, f, "image/png")})

async def configure_telegram_ui():
    commands = [
        {"command": "start", "description": "▶️ Старт / головний екран"},
        {"command": "new", "description": "Розпочати нове оцінювання"},
        {"command": "status", "description": "Стан оцінювання"},
        {"command": "log", "description": "Журнал оцінювань"},
        {"command": "pdf", "description": "Останній PDF-звіт"},
        {"command": "cancel", "description": "Скасувати поточне оцінювання"},
    ]
    try:
        await tg("setMyCommands", {"commands": commands})
        await tg("setChatMenuButton", {"menu_button": {"type": "commands"}})
        await tg("setMyShortDescription", {
            "short_description": "Самооцінювання персональної ШІ-зрілості за 48 показниками D1–D8."
        })
        await tg("setMyDescription", {
            "description": (
                "Personal AI Maturity Bot — експериментальний дослідницький інструмент "
                "самооцінювання персональної ШІ-зрілості. 48 показників, 8 блоків, "
                "індекс PAIMI та PDF-звіт. Результат є самооцінкою і не є об’єктивним "
                "вимірюванням компетентностей.\n/start — розпочати оцінювання"
            )
        })
    except Exception as e:
        print("Telegram UI warning:", repr(e), flush=True)

def score_keyboard(aid, idx):
    return [[{"text": str(score), "callback_data": f"score:{aid}:{idx}:{score}"} for score in range(6)]]

def repeat_keyboard(aid):
    return [[{"text": "🔄 Повторити оцінювання", "callback_data": f"repeat:{aid}"}]]

async def start_assessment(chat, user):
    with db() as c:
        active = c.execute(
            "SELECT id FROM assessments WHERE chat_id=? AND status='running' ORDER BY id DESC LIMIT 1",
            (chat,),
        ).fetchone()
        if active:
            await send(chat, f"У вас уже є незавершене оцінювання №{active['id']}. Продовжіть його або використайте /cancel.")
            return
        cur = c.execute(
            "INSERT INTO assessments(chat_id,user_id,username,status,current_index,created_at) VALUES(?,?,?,?,?,?)",
            (chat, user.get("id"), user.get("username"), "running", 0, now_iso()),
        )
        aid = cur.lastrowid
    await send(
        chat,
        "Оцінювання містить 48 тверджень у 8 блоках D1–D8.\n\n"
        "Оберіть для кожного твердження бал 0–5 відповідно до фактичної сформованості вашої практики взаємодії зі ШІ.\n\n"
        "0 — не знаю / не використовую;\n1 — загальне уявлення / поодинокий досвід;\n"
        "2 — використовую інколи, несистемно;\n3 — самостійно у типових ситуаціях;\n"
        "4 — системно, усвідомлено та впевнено;\n5 — системно, адаптивно, можу пояснити іншим."
    )
    await ask_question(chat, aid, 0)

async def ask_question(chat, aid, idx):
    x = MATRIX[idx]
    await send(
        chat,
        f"{idx+1}/48  {x['code']} — {x['criterion']}\n{x['dimension']} — {x['dimension_name']}\n\n{x['statement']}\n\nОцініть 0–5:",
        score_keyboard(aid, idx),
    )

def make_radar(aid):
    r = calc_results(aid)
    labels = [d[0] for d in DIMENSIONS]
    values = [r["dims"][d] or 0 for d in labels]
    vals = values + values[:1]
    angles = np.linspace(0, 2*np.pi, len(labels), endpoint=False).tolist()
    angles += angles[:1]
    fig = plt.figure(figsize=(8, 8))
    ax = plt.subplot(111, polar=True)
    ax.plot(angles, vals, linewidth=2)
    ax.fill(angles, vals, alpha=.15)
    ax.set_thetagrids(np.degrees(angles[:-1]), labels)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_title(f'Профіль персональної ШІ-зрілості\nPAIMI = {r["paimi"]:.1f}%', pad=25)
    out = BASE_DIR / "exports" / f"personal_ai_radar_{aid}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out

def _fonts():
    reg = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if Path(reg).exists():
        if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("DejaVu", reg))
            pdfmetrics.registerFont(TTFont("DejaVuBold", bold))
        return "DejaVu", "DejaVuBold"
    return "Helvetica", "Helvetica-Bold"

def export_pdf(aid):
    with db() as c:
        a = c.execute("SELECT * FROM assessments WHERE id=?", (aid,)).fetchone()
        rows = c.execute("SELECT code,score FROM answers WHERE assessment_id=?", (aid,)).fetchall()
    if not a:
        raise RuntimeError("Оцінювання не знайдено")
    by = {r["code"]: int(r["score"]) for r in rows}
    r = calc_results(aid)
    out = BASE_DIR / "exports" / f"Personal_AI_Maturity_Assessment_{aid}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    font, bold = _fonts()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="U", parent=styles["BodyText"], fontName=font, fontSize=8.5, leading=11))
    styles.add(ParagraphStyle(name="H", parent=styles["Heading2"], fontName=bold, fontSize=13))
    styles.add(ParagraphStyle(name="T", parent=styles["Title"], fontName=bold, fontSize=17, alignment=TA_CENTER))
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 6.2)
        canvas.drawCentredString(A4[0]/2, 10*mm, "Personal AI Maturity Bot — експериментальний дослідницький інструмент оцінювання персональної ШІ-зрілості.")
        canvas.drawCentredString(A4[0]/2, 7*mm, "Результат відображає самооцінку респондента і не є об’єктивним вимірюванням знань, компетентностей або професійної кваліфікації.")
        contact = []
        if PUBLIC_BOT_USERNAME:
            contact.append(PUBLIC_BOT_USERNAME if PUBLIC_BOT_USERNAME.startswith("@") else "@" + PUBLIC_BOT_USERNAME)
        if CONTACT_EMAIL:
            contact.append(CONTACT_EMAIL)
        contact.append(f"©2026, {AUTHOR}")
        canvas.drawCentredString(A4[0]/2, 4*mm, " · ".join(contact))
        canvas.restoreState()
    doc = SimpleDocTemplate(str(out), pagesize=A4, rightMargin=12*mm, leftMargin=12*mm, topMargin=12*mm, bottomMargin=21*mm)
    story = [Paragraph("Personal AI Maturity Assessment", styles["T"]), Paragraph("Звіт за результатами самооцінювання персональної ШІ-зрілості", styles["H"])]
    meta = [["ID оцінювання", str(a["id"])], ["PAIMI", f"{r['paimi']:.1f}%"], ["Рівень", maturity_level(r["paimi"])], ["Відповідей", f"{r['answered']}/48"]]
    t = Table([[Paragraph(str(v), styles["U"]) for v in row] for row in meta], colWidths=[45*mm, 135*mm])
    t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.4,colors.grey),("FONTNAME",(0,0),(0,-1),bold),("VALIGN",(0,0),(-1,-1),"TOP")]))
    story += [t, Spacer(1,4*mm), Paragraph("<b>Методологічне застереження.</b> Результат відображає самооцінку персональної ШІ-зрілості респондента та не є об’єктивним вимірюванням його знань, компетентностей або професійної кваліфікації. Інструмент має експериментальний дослідницький характер і використовується в межах розробки та апробації методики оцінювання персональної ШІ-зрілості.", styles["U"]), Spacer(1,4*mm), Image(str(make_radar(aid)), width=125*mm, height=125*mm), PageBreak(), Paragraph("Результати за блоками D1–D8", styles["H"])]
    dimdata = [["Блок","Назва","Результат"]]
    for d, dname in DIMENSIONS:
        value = r["dims"][d]
        dimdata.append([d,dname,f"{value:.1f}%" if value is not None else "—"])
    td = Table([[Paragraph(str(v),styles["U"]) for v in row] for row in dimdata], colWidths=[20*mm,125*mm,35*mm], repeatRows=1)
    td.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.4,colors.grey),("FONTNAME",(0,0),(-1,0),bold),("VALIGN",(0,0),(-1,-1),"TOP")]))
    story += [td, Spacer(1,5*mm), Paragraph("Деталізація 48 показників", styles["H"])]
    data = [["Код","Маркер","Бал","Інтерпретація"]]
    for x in MATRIX:
        score = by.get(x["code"])
        data.append([x["code"], x["criterion"], str(score) if score is not None else "—", SCALE.get(score,"—") if score is not None else "—"])
    tt = Table([[Paragraph(str(v),styles["U"]) for v in row] for row in data], colWidths=[16*mm,92*mm,18*mm,54*mm], repeatRows=1)
    tt.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.3,colors.grey),("FONTNAME",(0,0),(-1,0),bold),("VALIGN",(0,0),(-1,-1),"TOP")]))
    story.append(tt)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out

async def finish_assessment(chat, aid):
    with db() as c:
        c.execute("UPDATE assessments SET status='finished',finished_at=? WHERE id=?", (now_iso(), aid))
    r = calc_results(aid)
    await send_photo(chat, make_radar(aid), "Профіль персональної ШІ-зрілості")
    dims = "\n".join(f"{d}: {r['dims'][d]:.1f}%" for d,_ in DIMENSIONS if r["dims"][d] is not None)
    await send(chat, f"Оцінювання №{aid} завершено.\nPAIMI: {r['paimi']:.1f}%\nРівень: {maturity_level(r['paimi'])}\n\n{dims}\n\nРезультат є самооцінкою персональної ШІ-зрілості і не є об’єктивним вимірюванням компетентностей.")
    await send_document(chat, export_pdf(aid), "Фінальний PDF-звіт персональної ШІ-зрілості")
    await send(chat, "Оцінювання завершено. Ви можете пройти його повторно.", repeat_keyboard(aid))

async def handle_message(msg):
    chat = msg["chat"]["id"]
    user = msg.get("from", {})
    text = (msg.get("text") or "").strip()
    if not text:
        return
    if text == "/start":
        welcome = ("Вітаємо в Personal AI Maturity Bot!\n\nЦе експериментальний дослідницький інструмент для самооцінювання персональної ШІ-зрілості.\n\nОцінювання складається з 48 показників у 8 блоках D1–D8. Після проходження ви отримаєте індекс PAIMI, профіль D1–D8 та PDF-звіт.\n\nВажливо: результат відображає самооцінку респондента та не є об’єктивним вимірюванням знань, компетентностей або професійної кваліфікації.\n\n" + f"©2026, {AUTHOR}")
        await send_start(chat, welcome)
        return
    if text in ("/new", "▶️ Розпочати оцінювання"):
        await start_assessment(chat, user)
        return
    if text == "/cancel":
        with db() as c:
            a = c.execute("SELECT id FROM assessments WHERE chat_id=? AND status='running' ORDER BY id DESC LIMIT 1", (chat,)).fetchone()
            if a:
                c.execute("UPDATE assessments SET status='cancelled' WHERE id=?", (a["id"],))
        await send(chat, "Поточне оцінювання скасовано." if a else "Немає активного оцінювання.")
        return
    if text == "/status":
        with db() as c:
            a = c.execute("SELECT * FROM assessments WHERE chat_id=? ORDER BY id DESC LIMIT 1", (chat,)).fetchone()
        if not a:
            await send(chat, "Оцінювань ще немає. /new")
            return
        r = calc_results(a["id"])
        await send(chat, f"Оцінювання №{a['id']} | статус: {a['status']} | відповідей: {r['answered']}/48")
        return
    if text == "/log":
        with db() as c:
            rows = c.execute("SELECT id,status FROM assessments WHERE chat_id=? ORDER BY id DESC LIMIT 10", (chat,)).fetchall()
        if not rows:
            await send(chat, "Журнал порожній.")
            return
        lines = ["Останні оцінювання:"]
        for a in rows:
            r = calc_results(a["id"])
            lines.append(f"№{a['id']} — {a['status']} — {r['answered']}/48 — PAIMI {r['paimi']:.1f}%")
        await send(chat, "\n".join(lines))
        return
    if text.startswith("/pdf"):
        parts = text.split()
        with db() as c:
            last = c.execute("SELECT id FROM assessments WHERE chat_id=? AND status='finished' ORDER BY id DESC LIMIT 1", (chat,)).fetchone()
        aid = int(parts[1]) if len(parts)>1 and parts[1].isdigit() else (last["id"] if last else None)
        if not aid:
            await send(chat, "Завершених оцінювань ще немає.")
            return
        await send_document(chat, export_pdf(aid), "PDF-звіт персональної ШІ-зрілості")
        return

async def handle_callback(cb):
    data = cb.get("data", "")
    chat = (cb.get("message") or {}).get("chat", {}).get("id")
    if not chat:
        return
    await tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
    parts = data.split(":")
    if parts[0] == "repeat" and len(parts) == 2:
        await start_assessment(chat, cb.get("from", {}))
        return
    if parts[0] == "score" and len(parts) == 4:
        aid, idx, score = map(int, parts[1:])
        if idx < 0 or idx >= 48 or score not in range(6):
            return
        with db() as c:
            a = c.execute("SELECT * FROM assessments WHERE id=? AND chat_id=?", (aid,chat)).fetchone()
            if not a or a["status"] != "running":
                return
            x = MATRIX[idx]
            c.execute("INSERT OR REPLACE INTO answers(assessment_id,code,score,created_at) VALUES(?,?,?,?)", (aid,x["code"],score,now_iso()))
            c.execute("UPDATE assessments SET current_index=? WHERE id=?", (idx+1,aid))
        await send(chat, f"{MATRIX[idx]['code']}: {score}/5 — {SCALE[score]}")
        if idx+1 < 48:
            await ask_question(chat, aid, idx+1)
        else:
            await finish_assessment(chat, aid)

async def process_update(update):
    if "message" in update:
        await handle_message(update["message"])
    elif "callback_query" in update:
        await handle_callback(update["callback_query"])
