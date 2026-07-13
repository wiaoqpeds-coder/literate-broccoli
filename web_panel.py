"""
Веб-панель администратора для юзербота.
Запускается автоматически вместе с userbot.py (в отдельном потоке),
слушает порт, который выдаёт Railway (переменная окружения PORT).

Вход: логин + пароль (можно несколько пользователей — см. auth_store.py).
Главный админ задаётся переменными окружения ADMIN_USERNAME / ADMIN_PASSWORD.
Из панели можно выдавать дополнительные логины/пароли другим людям.

"Вес" фразы (число в phrases_store.py) здесь показывается и вводится как
проценты — по сути это то же самое число, просто рядом сразу считается
и показывается итоговая реальная вероятность в %, чтобы было нагляднее.
"""

import asyncio
import os
from functools import wraps

from flask import Flask, request, redirect, url_for, session, render_template_string
from telethon.tl.types import Channel, User
from telethon import utils

import groups_store as groups
import dm_store as dms
import phrases_store as phrases
import settings_store as settings
import auth_store as auth

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
SECRET_KEY = os.getenv("FLASK_SECRET_KEY", os.urandom(24).hex())

app = Flask(__name__)
app.secret_key = SECRET_KEY

_client = None
_loop = None


def set_client(client, loop):
    global _client, _loop
    _client = client
    _loop = loop


def run_async(coro, timeout=20):
    if _loop is None:
        raise RuntimeError("Юзербот ещё не запущен.")
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=timeout)


def normalize_username(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("@"):
        raw = raw[1:]
    return raw


def panel_configured() -> bool:
    return bool(ADMIN_USERNAME and ADMIN_PASSWORD) or bool(auth.list_users())


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not panel_configured():
            return (
                "Панель отключена: не заданы переменные окружения "
                "ADMIN_USERNAME / ADMIN_PASSWORD.",
                503,
            )
        if not session.get("username"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def _flash_redirect(endpoint, message, is_error=False):
    session["_flash"] = message
    session["_flash_err"] = is_error
    return redirect(url_for(endpoint))


def _pop_flash():
    return session.pop("_flash", None), session.pop("_flash_err", False)


# =========================================================
#                     ОБЩИЙ ДИЗАЙН
# =========================================================

BASE_STYLE = """
<style>
:root{
  --bg:#0b0d12; --card:#151822; --card2:#1b1f2b; --border:#262b3a;
  --text:#eef0f5; --muted:#8b93a7; --accent:#6c8cff; --accent2:#4f6fe0;
  --green:#3ecf8e; --red:#ef5b5b; --yellow:#e0b04f;
}
*{box-sizing:border-box}
body{font-family:-apple-system,system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--text);margin:0;padding-bottom:60px}
a{color:var(--accent);text-decoration:none}
.topbar{position:sticky;top:0;background:rgba(11,13,18,0.95);backdrop-filter:blur(6px);padding:14px 16px 0;z-index:10;border-bottom:1px solid var(--border)}
.topbar h1{font-size:18px;margin:0 0 12px;display:flex;justify-content:space-between;align-items:center}
.topbar h1 span.logout{font-size:12px;color:var(--muted);font-weight:400}
.nav{display:flex;gap:4px;overflow-x:auto;padding-bottom:10px;-webkit-overflow-scrolling:touch}
.nav a{white-space:nowrap;padding:8px 14px;border-radius:20px;font-size:13px;color:var(--muted);background:var(--card)}
.nav a.active{color:#fff;background:var(--accent2);font-weight:600}
.content{padding:16px}
h2.section{font-size:15px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin:22px 0 10px;font-weight:600}
h2.section:first-child{margin-top:0}
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:14px 16px;margin-bottom:10px}
.card.dim{opacity:.7}
input[type=text],input[type=password],input[type=number],select{
  padding:9px 10px;border-radius:8px;border:1px solid var(--border);
  background:var(--card2);color:var(--text);box-sizing:border-box;font-size:14px}
input[type=text]:focus,input[type=number]:focus{outline:none;border-color:var(--accent)}
button{padding:9px 16px;border-radius:8px;border:none;background:var(--accent2);
  color:#fff;font-weight:600;cursor:pointer;font-size:13px}
button.danger{background:transparent;color:var(--red);border:1px solid var(--red)}
button.ghost{background:transparent;color:var(--accent);border:1px solid var(--border)}
button.small{padding:6px 10px;font-size:12px}
.row{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.stack{display:flex;flex-direction:column;gap:8px}
.pill{background:var(--card2);padding:3px 10px;border-radius:20px;font-size:12px;color:var(--muted)}
.pill.on{color:var(--green)}
.pill.off{color:var(--red)}
.muted{color:var(--muted);font-size:13px}
form.inline{display:inline-flex;align-items:center;gap:6px}
.msg{padding:10px 14px;border-radius:10px;margin-bottom:14px;font-size:14px;background:#173328;color:var(--green);border:1px solid #235b41}
.msg.err{background:#3a1d1f;color:var(--red);border-color:#6b2a2a}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.bar-outer{height:6px;border-radius:4px;background:var(--card2);overflow:hidden;margin-top:6px}
.bar-inner{height:100%;background:var(--accent)}
label.toggle{display:flex;align-items:center;gap:8px;cursor:pointer;font-size:14px}
.empty{color:var(--muted);font-size:13px;padding:6px 0}
</style>
"""


def render_page(active, content_html, message=None, is_error=False):
    tabs = [
        ("dashboard", "⚙️ Обзор"),
        ("groups_page", "📋 Группы"),
        ("dms_page", "👤 Личные чаты"),
        ("phrases_page", "💬 Фразы"),
        ("users_page", "🔑 Доступ"),
    ]
    nav_html = "".join(
        f'<a href="{url_for(ep)}" class="{"active" if ep == active else ""}">{label}</a>'
        for ep, label in tabs
    )
    msg_html = ""
    if message:
        msg_html = f'<div class="msg {"err" if is_error else ""}">{message}</div>'

    page = """
<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Панель юзербота</title>
""" + BASE_STYLE + """
</head><body>
<div class="topbar">
  <h1>🤖 Панель юзербота <span class="logout"><a href="/logout">Выйти ({{ user }})</a></span></h1>
  <div class="nav">""" + nav_html + """</div>
</div>
<div class="content">
""" + msg_html + content_html + """
</div>
</body></html>
"""
    return render_template_string(page, user=session.get("username", ""))


# =========================================================
#                        ВХОД
# =========================================================

LOGIN_PAGE = """
<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Вход — панель юзербота</title>
""" + BASE_STYLE + """
</head><body style="display:flex;height:100vh;align-items:center;justify-content:center">
<div class="card" style="width:300px">
<h2 style="margin-top:0">🔐 Вход в панель</h2>
{% if error %}<div class="msg err">{{ error }}</div>{% endif %}
<form method="post" class="stack">
<input type="text" name="username" placeholder="Логин" autofocus>
<input type="password" name="password" placeholder="Пароль">
<button type="submit">Войти</button>
</form>
</div></body></html>
"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if not panel_configured():
        return (
            "Панель отключена: не заданы переменные окружения "
            "ADMIN_USERNAME / ADMIN_PASSWORD.",
            503,
        )
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if auth.verify(username, password):
            session["username"] = username
            return redirect(url_for("dashboard"))
        error = "Неверный логин или пароль."
    return render_template_string(LOGIN_PAGE, error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =========================================================
#                  ВКЛАДКА: ОБЗОР
# =========================================================

@app.route("/", methods=["GET"])
@app.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    message, is_error = _pop_flash()

    enabled = settings.is_enabled()
    mode = settings.get_mode()
    mode_label = "Комментировать посты канала" if mode == settings.MODE_AUTOCOMMENT else "Отвечать на сообщения людей"

    content = f"""
<h2 class="section">Статус</h2>
<div class="card">
  <div class="row">
    <span class="pill {'on' if enabled else 'off'}">{'● Бот включён' if enabled else '● Бот выключен'}</span>
    <form method="post" action="{url_for('settings_toggle')}">
      <button type="submit" class="{'danger' if enabled else ''}">{'Выключить' if enabled else 'Включить'}</button>
    </form>
  </div>
</div>

<h2 class="section">Режим работы</h2>
<div class="card">
  <div class="stack">
    <span class="muted">Сейчас: <b>{mode_label}</b></span>
    <form method="post" action="{url_for('settings_mode')}" class="row">
      <select name="mode" style="flex:1">
        <option value="autocomment" {"selected" if mode == "autocomment" else ""}>Комментировать посты канала</option>
        <option value="chat" {"selected" if mode == "chat" else ""}>Отвечать на сообщения людей</option>
      </select>
      <button type="submit">Сохранить</button>
    </form>
  </div>
</div>

<h2 class="section">Интервалы</h2>
<div class="card">
  <div class="row" style="margin-bottom:10px">
    <span class="muted">Комментарии: раз в N постов канала</span>
    <form method="post" action="{url_for('settings_interval')}" class="inline">
      <input type="number" name="value" value="{settings.get_interval()}" min="1" style="width:70px">
      <button type="submit" class="small">Сохранить</button>
    </form>
  </div>
  <div class="row">
    <span class="muted">Чат-режим: раз в N сообщений людей</span>
    <form method="post" action="{url_for('settings_chatinterval')}" class="inline">
      <input type="number" name="value" value="{settings.get_chat_interval()}" min="1" style="width:70px">
      <button type="submit" class="small">Сохранить</button>
    </form>
  </div>
</div>

<h2 class="section">Краткая сводка</h2>
<div class="card grid2">
  <div><span class="muted">Групп подключено</span><br><b>{len(groups.list_groups())}</b></div>
  <div><span class="muted">Личных чатов</span><br><b>{len(dms.list_dms())}</b></div>
  <div><span class="muted">Фраз включено</span><br><b>{len(phrases.get_enabled_texts())}</b></div>
  <div><span class="muted">Автоответ в личке</span><br><b>{'включён' if settings.is_dm_enabled() else 'выключен'}</b></div>
</div>
"""
    return render_page("dashboard", content, message, is_error)


@app.route("/settings/toggle", methods=["POST"])
@login_required
def settings_toggle():
    settings.set_enabled(not settings.is_enabled())
    return redirect(url_for("dashboard"))


@app.route("/settings/mode", methods=["POST"])
@login_required
def settings_mode():
    settings.set_mode(request.form.get("mode", "autocomment"))
    return redirect(url_for("dashboard"))


@app.route("/settings/interval", methods=["POST"])
@login_required
def settings_interval():
    try:
        settings.set_interval(int(request.form.get("value", 1)))
    except ValueError:
        pass
    return redirect(url_for("dashboard"))


@app.route("/settings/chatinterval", methods=["POST"])
@login_required
def settings_chatinterval():
    try:
        settings.set_chat_interval(int(request.form.get("value", 5)))
    except ValueError:
        pass
    return redirect(url_for("dashboard"))


# =========================================================
#                  ВКЛАДКА: ГРУППЫ
# =========================================================

async def _add_group_coro(username):
    entity = await _client.get_entity(username)
    if not isinstance(entity, Channel) or not entity.megagroup:
        raise ValueError("Это не группа обсуждений (супергруппа).")
    groups.add_group(utils.get_peer_id(entity), username)


async def _discover_groups_coro():
    """Возвращает список групп (супергрупп), в которых состоит аккаунт."""
    results = []
    async for dialog in _client.iter_dialogs(limit=300):
        entity = dialog.entity
        if isinstance(entity, Channel) and entity.megagroup:
            results.append({
                "id": utils.get_peer_id(entity),
                "username": entity.username,
                "title": dialog.name,
            })
    return results


@app.route("/groups", methods=["GET"])
@login_required
def groups_page():
    message, is_error = _pop_flash()
    data = groups.list_groups()

    cards = ""
    for gid, g in data.items():
        cards += f"""
<div class="card">
  <div class="row">
    <b>@{g['username']}</b>
    <form method="post" action="{url_for('groups_remove')}" onsubmit="return confirm('Отключить @{g['username']}?')">
      <input type="hidden" name="chat_id" value="{gid}">
      <button class="danger small" type="submit">Отключить</button>
    </form>
  </div>
</div>
"""
    if not data:
        cards = '<div class="empty">Групп пока не подключено.</div>'

    discover_html = ""
    if request.args.get("discover") == "1":
        try:
            found = run_async(_discover_groups_coro())
        except Exception as e:
            found = []
            discover_html += f'<div class="msg err">Не удалось получить список: {e}</div>'

        connected_ids = set(data.keys())
        rows = ""
        for g in found:
            already = str(g["id"]) in connected_ids
            if g["username"]:
                label = f"@{g['username']}"
            else:
                label = f"{g['title']} (приватная группа)"
            btn = (
                '<span class="pill on">Уже подключена</span>' if already else f"""
                <form method="post" action="{url_for('groups_quickadd')}">
                  <input type="hidden" name="chat_id" value="{g['id']}">
                  <input type="hidden" name="label" value="{(g['username'] or g['title'] or str(g['id']))}">
                  <button type="submit" class="small">Подключить</button>
                </form>
                """
            )
            rows += f"""
<div class="card">
  <div class="row">
    <span>{label}</span>
    {btn}
  </div>
</div>
"""
        if not rows:
            rows = '<div class="empty">Групп (супергрупп с обсуждениями) не найдено среди ваших чатов.</div>'

        discover_html += f"""
<h2 class="section">Найдено в Telegram ({len(found)})</h2>
{rows}
"""
    else:
        discover_html = f"""
<div class="card">
  <a href="{url_for('groups_page')}?discover=1"><button type="button" onclick="window.location='{url_for('groups_page')}?discover=1'">🔍 Показать мои группы из Telegram</button></a>
</div>
"""

    content = f"""
<h2 class="section">Подключённые группы ({len(data)})</h2>
{cards}

<h2 class="section">Автообнаружение</h2>
{discover_html}

<h2 class="section">Подключить вручную</h2>
<div class="card">
  <form method="post" action="{url_for('groups_add')}" class="stack">
    <input type="text" name="username" placeholder="@username_группы" required>
    <button type="submit">➕ Подключить группу</button>
  </form>
  <p class="muted" style="margin-bottom:0">Группа должна быть публичной, а бот — уже состоять в ней как администратор.</p>
</div>
"""
    return render_page("groups_page", content, message, is_error)


@app.route("/groups/quickadd", methods=["POST"])
@login_required
def groups_quickadd():
    chat_id = request.form.get("chat_id")
    label = request.form.get("label", "").strip()
    try:
        groups.add_group(int(chat_id), normalize_username(label))
        return _flash_redirect("groups_page", f"Группа «{label}» подключена.")
    except Exception as e:
        return _flash_redirect("groups_page", f"Не удалось подключить: {e}", True)


@app.route("/groups/add", methods=["POST"])
@login_required
def groups_add():
    username = normalize_username(request.form.get("username", ""))
    if not username:
        return _flash_redirect("groups_page", "Укажите юзернейм группы.", True)
    try:
        run_async(_add_group_coro(username))
        return _flash_redirect("groups_page", f"Группа @{username} подключена.")
    except Exception as e:
        return _flash_redirect("groups_page", f"Не удалось подключить @{username}: {e}", True)


@app.route("/groups/remove", methods=["POST"])
@login_required
def groups_remove():
    chat_id = request.form.get("chat_id")
    groups.remove_group_by_chat_id(chat_id)
    return redirect(url_for("groups_page"))


# =========================================================
#               ВКЛАДКА: ЛИЧНЫЕ ЧАТЫ
# =========================================================

async def _add_dm_coro(raw):
    if raw.lstrip('-').isdigit():
        entity = await _client.get_entity(int(raw))
    else:
        entity = await _client.get_entity(normalize_username(raw))
    if not isinstance(entity, User):
        raise ValueError("Это не личный пользователь.")
    label = entity.username or entity.first_name or str(entity.id)
    dms.add_dm(utils.get_peer_id(entity), label)
    return label


async def _discover_dms_coro():
    """Возвращает список личных диалогов (людей), с которыми есть переписка."""
    results = []
    async for dialog in _client.iter_dialogs(limit=300):
        entity = dialog.entity
        if isinstance(entity, User) and not entity.bot and not entity.is_self:
            results.append({
                "id": utils.get_peer_id(entity),
                "username": entity.username,
                "name": dialog.name,
            })
    return results


@app.route("/dms", methods=["GET"])
@login_required
def dms_page():
    message, is_error = _pop_flash()
    dm_enabled = settings.is_dm_enabled()
    dm_interval = settings.get_dm_interval()
    data = dms.list_dms()

    cards = ""
    for cid, d in data.items():
        cards += f"""
<div class="card">
  <div class="row">
    <span>{d['label']}</span>
    <form method="post" action="{url_for('dm_remove')}" onsubmit="return confirm('Отключить {d['label']}?')">
      <input type="hidden" name="chat_id" value="{cid}">
      <button class="danger small" type="submit">Отключить</button>
    </form>
  </div>
</div>
"""
    if not data:
        cards = '<div class="empty">Личных чатов пока не подключено.</div>'

    discover_html = ""
    if request.args.get("discover") == "1":
        try:
            found = run_async(_discover_dms_coro())
        except Exception as e:
            found = []
            discover_html += f'<div class="msg err">Не удалось получить список: {e}</div>'

        connected_ids = set(data.keys())
        rows = ""
        for u in found:
            already = str(u["id"]) in connected_ids
            label = u["name"] or (f"@{u['username']}" if u["username"] else str(u["id"]))
            btn = (
                '<span class="pill on">Уже подключён</span>' if already else f"""
                <form method="post" action="{url_for('dm_quickadd')}">
                  <input type="hidden" name="chat_id" value="{u['id']}">
                  <input type="hidden" name="label" value="{label}">
                  <button type="submit" class="small">Подключить</button>
                </form>
                """
            )
            rows += f"""
<div class="card">
  <div class="row">
    <span>{label}</span>
    {btn}
  </div>
</div>
"""
        if not rows:
            rows = '<div class="empty">Личных переписок не найдено.</div>'

        discover_html += f"""
<h2 class="section">Найдено в Telegram ({len(found)})</h2>
{rows}
"""
    else:
        discover_html = f"""
<div class="card">
  <button type="button" onclick="window.location='{url_for('dms_page')}?discover=1'">🔍 Показать мои переписки из Telegram</button>
</div>
"""

    content = f"""
<h2 class="section">Авто-ответчик</h2>
<div class="card">
  <div class="row" style="margin-bottom:10px">
    <span class="pill {'on' if dm_enabled else 'off'}">{'● Включён' if dm_enabled else '● Выключен'}</span>
    <form method="post" action="{url_for('dm_toggle')}">
      <button type="submit" class="{'danger' if dm_enabled else ''}">{'Выключить' if dm_enabled else 'Включить'}</button>
    </form>
  </div>
  <div class="row">
    <span class="muted">Отвечать раз в N сообщений</span>
    <form method="post" action="{url_for('dm_interval')}" class="inline">
      <input type="number" name="value" value="{dm_interval}" min="1" style="width:70px">
      <button type="submit" class="small">Сохранить</button>
    </form>
  </div>
</div>

<h2 class="section">Подключённые чаты ({len(data)})</h2>
{cards}

<h2 class="section">Автообнаружение</h2>
{discover_html}

<h2 class="section">Подключить вручную</h2>
<div class="card">
  <form method="post" action="{url_for('dm_add')}" class="stack">
    <input type="text" name="target" placeholder="@username или ID пользователя" required>
    <button type="submit">➕ Подключить личный чат</button>
  </form>
</div>
"""
    return render_page("dms_page", content, message, is_error)


@app.route("/dm/quickadd", methods=["POST"])
@login_required
def dm_quickadd():
    chat_id = request.form.get("chat_id")
    label = request.form.get("label", "").strip()
    try:
        dms.add_dm(int(chat_id), label)
        return _flash_redirect("dms_page", f"Личный чат «{label}» подключён.")
    except Exception as e:
        return _flash_redirect("dms_page", f"Не удалось подключить: {e}", True)


@app.route("/dm/add", methods=["POST"])
@login_required
def dm_add():
    target = request.form.get("target", "").strip()
    if not target:
        return _flash_redirect("dms_page", "Укажите @username или ID.", True)
    try:
        label = run_async(_add_dm_coro(target))
        return _flash_redirect("dms_page", f"Личный чат «{label}» подключён.")
    except Exception as e:
        return _flash_redirect("dms_page", f"Не удалось подключить «{target}»: {e}", True)


@app.route("/dm/remove", methods=["POST"])
@login_required
def dm_remove():
    chat_id = request.form.get("chat_id")
    dms.remove_dm_by_chat_id(chat_id)
    return redirect(url_for("dms_page"))


@app.route("/dm/toggle", methods=["POST"])
@login_required
def dm_toggle():
    settings.set_dm_enabled(not settings.is_dm_enabled())
    return redirect(url_for("dms_page"))


@app.route("/dm/interval", methods=["POST"])
@login_required
def dm_interval():
    try:
        settings.set_dm_interval(int(request.form.get("value", 1)))
    except ValueError:
        pass
    return redirect(url_for("dms_page"))


# =========================================================
#                  ВКЛАДКА: ФРАЗЫ
# =========================================================

@app.route("/phrases", methods=["GET"])
@login_required
def phrases_page():
    message, is_error = _pop_flash()
    data = phrases.list_phrases()

    # Если сумма весов не равна 100 (например, старые данные весом "1" у каждой) —
    # один раз пропорционально приводим к сумме 100, сохраняя те же соотношения.
    # Обёрнуто в try/except: если с данными что-то не так, просто пропускаем
    # выравнивание вместо падения всей страницы.
    try:
        total_raw = sum(p.get("weight", 1) for p in data)
        if total_raw > 0 and total_raw != 100 and len(data) > 0:
            running = 0
            for i, p in enumerate(data, start=1):
                if i < len(data):
                    new_weight = round(p.get("weight", 1) / total_raw * 100)
                    running += new_weight
                else:
                    new_weight = 100 - running  # последней достаётся остаток
                phrases.set_weight(i, max(0, new_weight))
            data = phrases.list_phrases()
    except Exception:
        app.logger.exception("Не удалось выровнять проценты фраз — показываю как есть.")

    total_weight = sum(p.get("weight", 1) for p in data if p.get("enabled")) or 1

    cards = ""
    for i, p in enumerate(data, start=1):
        enabled = p.get("enabled", True)
        weight = p.get("weight", 1)
        percent = (weight / total_weight * 100) if enabled else 0

        cards += f"""
<div class="card {'' if enabled else 'dim'}">
  <form method="post" action="{url_for('phrases_settext')}" class="row" style="margin-bottom:8px">
    <input type="hidden" name="index" value="{i}">
    <input type="text" name="text" value="{p['text']}" style="flex:1">
    <button type="submit" class="small">Сохранить</button>
  </form>
  <div class="row">
    <form method="post" action="{url_for('phrases_toggle')}">
      <input type="hidden" name="index" value="{i}">
      <input type="hidden" name="enabled" value="{'false' if enabled else 'true'}">
      <button type="submit" class="small {'ghost' if enabled else ''}">{'✅ Включена' if enabled else '⛔ Выключена'}</button>
    </form>
    <form method="post" action="{url_for('phrases_setweight')}" class="inline">
      <input type="number" name="weight" value="{weight}" min="0" max="100" style="width:60px">
      <span class="muted">%</span>
      <button type="submit" class="small">Сохранить</button>
    </form>
  </div>
  <div class="bar-outer"><div class="bar-inner" style="width:{percent:.1f}%"></div></div>
  <div class="muted" style="margin-top:4px">{'~' + format(percent, '.1f') + '% шанс выпадения' if enabled else 'не участвует в выборе'}</div>
</div>
"""

    grand_total = sum(p.get("weight", 1) for p in data)
    content = f"""
<h2 class="section">Фразы для авто-ответов ({len(data)})</h2>
<p class="muted">Проценты всех фраз в сумме дают 100%. Сейчас указано: <b>{grand_total}%</b>. Чтобы увеличить одну фразу — сначала уменьшите другую, иначе сумма превысит 100%, и сохранить не получится.</p>
{cards}
"""
    return render_page("phrases_page", content, message, is_error)


@app.route("/phrases/settext", methods=["POST"])
@login_required
def phrases_settext():
    index = int(request.form.get("index"))
    text = request.form.get("text", "").strip()
    if text:
        phrases.set_phrase(index, text)
    return redirect(url_for("phrases_page"))


@app.route("/phrases/toggle", methods=["POST"])
@login_required
def phrases_toggle():
    index = int(request.form.get("index"))
    enabled = request.form.get("enabled") == "true"
    phrases.set_enabled(index, enabled)
    return redirect(url_for("phrases_page"))


@app.route("/phrases/setweight", methods=["POST"])
@login_required
def phrases_setweight():
    try:
        index = int(request.form.get("index"))
        try:
            weight = int(request.form.get("weight", 1))
        except ValueError:
            weight = 1
        weight = max(0, min(100, weight))

        data = phrases.list_phrases()
        others_total = sum(p.get("weight", 1) for j, p in enumerate(data, start=1) if j != index)

        if others_total + weight > 100:
            max_allowed = max(0, 100 - others_total)
            return _flash_redirect(
                "phrases_page",
                f"Сумма процентов по всем фразам не может превышать 100%. "
                f"У остальных фраз сейчас: {others_total}%. Максимум для этой фразы: {max_allowed}%.",
                True,
            )

        phrases.set_weight(index, weight)
        return redirect(url_for("phrases_page"))
    except Exception:
        app.logger.exception("Ошибка при сохранении процента фразы")
        return _flash_redirect("phrases_page", "Не удалось сохранить процент — попробуйте ещё раз.", True)


# =========================================================
#              ВКЛАДКА: ДОСТУП (логины/пароли)
# =========================================================

@app.route("/users", methods=["GET"])
@login_required
def users_page():
    message, is_error = _pop_flash()
    extra_users = auth.list_users()

    cards = ""
    for u in extra_users:
        cards += f"""
<div class="card">
  <div class="row">
    <span>{u}</span>
    <form method="post" action="{url_for('users_remove')}" onsubmit="return confirm('Удалить доступ у {u}?')">
      <input type="hidden" name="username" value="{u}">
      <button class="danger small" type="submit">Удалить</button>
    </form>
  </div>
</div>
"""
    if not extra_users:
        cards = '<div class="empty">Дополнительных пользователей пока нет.</div>'

    content = f"""
<h2 class="section">Кто имеет доступ</h2>
<p class="muted">Главный администратор задан в переменных окружения Railway и здесь не отображается — его нельзя удалить из панели.</p>
{cards}

<h2 class="section">Выдать новый доступ</h2>
<div class="card">
  <form method="post" action="{url_for('users_add')}" class="stack">
    <input type="text" name="username" placeholder="Логин" required>
    <input type="text" name="password" placeholder="Пароль" required>
    <button type="submit">➕ Выдать доступ</button>
  </form>
</div>
"""
    return render_page("users_page", content, message, is_error)


@app.route("/users/add", methods=["POST"])
@login_required
def users_add():
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    ok, error = auth.add_user(username, password)
    if ok:
        return _flash_redirect("users_page", f"Логин «{username}» создан.")
    return _flash_redirect("users_page", error, True)


@app.route("/users/remove", methods=["POST"])
@login_required
def users_remove():
    username = request.form.get("username", "")
    auth.remove_user(username)
    return redirect(url_for("users_page"))


@app.errorhandler(500)
def handle_500(e):
    app.logger.exception("Необработанная ошибка на странице панели")
    return (
        "<h2>⚠️ Что-то пошло не так</h2>"
        "<p>Произошла внутренняя ошибка. Подробности записаны в логи Railway "
        "(Deployments → последний деплой → прокрутить вниз).</p>"
        f'<p><a href="{url_for("dashboard")}">← Вернуться на главную</a></p>',
        500,
    )


def run_panel():
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
