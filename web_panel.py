"""
Веб-панель администратора для юзербота.
Запускается автоматически вместе с userbot.py (в отдельном потоке),
слушает порт, который выдаёт Railway (переменная окружения PORT).

Вход: логин + пароль (можно несколько пользователей — см. auth_store.py).
Главный админ задаётся переменными окружения ADMIN_USERNAME / ADMIN_PASSWORD.
Из панели можно выдавать дополнительные логины/пароли другим людям.

Панель умеет не только показывать настройки, но и реально добавлять
группы/личные чаты — так же, как команды в Telegram, через тот же
запущенный Telethon-клиент (безопасный вызов из другого потока).
"""

import asyncio
import os
from functools import wraps

from flask import Flask, request, redirect, url_for, session, render_template_string
from telethon.tl.types import Channel, User

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
    """Вызывается из userbot.py после запуска, чтобы панель могла
    безопасно обращаться к тому же Telethon-клиенту из другого потока."""
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


BASE_STYLE = """
<style>
body{font-family:system-ui,sans-serif;background:#0f1117;color:#eee;margin:0;padding:16px 12px 60px}
h1{font-size:20px}
h2{font-size:16px;margin-top:28px;border-bottom:1px solid #2a2d38;padding-bottom:6px}
.card{background:#1a1d27;border-radius:10px;padding:14px;margin:10px 0}
input,select{padding:8px;border-radius:6px;border:1px solid #333;background:#0f1117;color:#eee;box-sizing:border-box}
input[type=text],input[type=password]{width:100%;margin-bottom:8px}
button{padding:8px 14px;border-radius:6px;border:none;background:#5b8def;color:#fff;font-weight:600;cursor:pointer;margin-top:6px}
button.danger{background:#e5534b}
.row{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
.top{display:flex;justify-content:space-between;align-items:center}
a.logout{color:#aaa;font-size:13px;text-decoration:none}
small{color:#888}
form.inline{display:inline}
.msg{background:#20361f;color:#8fd67f;padding:8px 12px;border-radius:8px;margin-bottom:10px;font-size:14px}
.msg.err{background:#3a1d1d;color:#ff8f8f}
.pill{background:#2a2d38;padding:2px 8px;border-radius:12px;font-size:12px}
</style>
"""

LOGIN_PAGE = """
<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Вход — панель юзербота</title>
""" + BASE_STYLE + """
</head><body style="display:flex;height:100vh;align-items:center;justify-content:center">
<div class="card" style="width:280px">
<h2>🔐 Вход в панель</h2>
{% if error %}<p class="msg err">{{ error }}</p>{% endif %}
<form method="post">
<input type="text" name="username" placeholder="Логин" autofocus>
<input type="password" name="password" placeholder="Пароль">
<button type="submit" style="width:100%">Войти</button>
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


DASHBOARD_PAGE = """
<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Панель юзербота</title>
""" + BASE_STYLE + """
</head><body>

<div class="top"><h1>🤖 Панель юзербота</h1><a class="logout" href="/logout">Выйти ({{ current_user }})</a></div>

{% if message %}<p class="msg {{ 'err' if is_error else '' }}">{{ message }}</p>{% endif %}

<h2>⚙️ Общее</h2>
<div class="card">
  <div class="row">
    <span>Бот: <b>{{ 'включён ✅' if enabled else 'выключен ⛔' }}</b></span>
    <form method="post" action="/settings/toggle">
      <button type="submit">{{ 'Выключить' if enabled else 'Включить' }}</button>
    </form>
  </div>
  <div class="row" style="margin-top:10px">
    <span>Режим:</span>
    <form method="post" action="/settings/mode">
      <select name="mode" onchange="this.form.submit()">
        <option value="autocomment" {{ 'selected' if mode == 'autocomment' else '' }}>Комментировать посты канала</option>
        <option value="chat" {{ 'selected' if mode == 'chat' else '' }}>Отвечать на сообщения людей</option>
      </select>
    </form>
  </div>
  <div class="row" style="margin-top:10px">
    <span>Интервал комментариев (раз в N постов):</span>
    <form method="post" action="/settings/interval" class="inline">
      <input type="number" name="value" value="{{ interval }}" min="1" style="width:70px">
      <button type="submit">Сохранить</button>
    </form>
  </div>
  <div class="row" style="margin-top:10px">
    <span>Интервал чат-режима (раз в N сообщений людей):</span>
    <form method="post" action="/settings/chatinterval" class="inline">
      <input type="number" name="value" value="{{ chat_interval }}" min="1" style="width:70px">
      <button type="submit">Сохранить</button>
    </form>
  </div>
</div>

<h2>📋 Группы (посты/сообщения)</h2>
{% for gid, g in groups.items() %}
<div class="card">
  <div class="row">
    <b>@{{ g.username }}</b>
    <form method="post" action="/groups/remove" onsubmit="return confirm('Отключить @{{ g.username }}?')">
      <input type="hidden" name="chat_id" value="{{ gid }}">
      <button class="danger" type="submit">Отключить</button>
    </form>
  </div>
</div>
{% else %}
<p><small>Групп пока не подключено.</small></p>
{% endfor %}

<div class="card">
  <form method="post" action="/groups/add">
    <input type="text" name="username" placeholder="@username_группы" required>
    <button type="submit">➕ Подключить группу</button>
  </form>
  <small>Группа должна быть публичной, а бот — уже состоять в ней как администратор.</small>
</div>

<h2>👤 Личные чаты (авто-ответчик)</h2>
<div class="card">
  <div class="row">
    <span>Авто-ответы в личке: <b>{{ 'включены ✅' if dm_enabled else 'выключены ⛔' }}</b></span>
    <form method="post" action="/dm/toggle">
      <button type="submit">{{ 'Выключить' if dm_enabled else 'Включить' }}</button>
    </form>
  </div>
  <div class="row" style="margin-top:10px">
    <span>Отвечать раз в N сообщений:</span>
    <form method="post" action="/dm/interval" class="inline">
      <input type="number" name="value" value="{{ dm_interval }}" min="1" style="width:70px">
      <button type="submit">Сохранить</button>
    </form>
  </div>
</div>

{% for cid, d in dm_list.items() %}
<div class="card">
  <div class="row">
    <span>{{ d.label }}</span>
    <form method="post" action="/dm/remove" onsubmit="return confirm('Отключить {{ d.label }}?')">
      <input type="hidden" name="chat_id" value="{{ cid }}">
      <button class="danger" type="submit">Отключить</button>
    </form>
  </div>
</div>
{% else %}
<p><small>Личных чатов пока не подключено.</small></p>
{% endfor %}

<div class="card">
  <form method="post" action="/dm/add">
    <input type="text" name="target" placeholder="@username или ID пользователя" required>
    <button type="submit">➕ Подключить личный чат</button>
  </form>
</div>

<h2>💬 Фразы</h2>
{% for p in phrase_list %}
<div class="card">
  <div class="row">
    <form class="inline" method="post" action="/phrases/settext" style="flex:1">
      <input type="hidden" name="index" value="{{ loop.index }}">
      <input type="text" name="text" value="{{ p.text }}" style="width:55%">
      <span class="pill">вес {{ p.weight }}</span>
      <button type="submit">Сохранить</button>
    </form>
  </div>
  <div class="row" style="margin-top:6px">
    <form class="inline" method="post" action="/phrases/toggle">
      <input type="hidden" name="index" value="{{ loop.index }}">
      <input type="hidden" name="enabled" value="{{ 'false' if p.enabled else 'true' }}">
      <button type="submit">{{ '✅ Вкл' if p.enabled else '⛔ Выкл' }}</button>
    </form>
    <form class="inline" method="post" action="/phrases/setweight">
      <input type="hidden" name="index" value="{{ loop.index }}">
      <input type="number" name="weight" value="{{ p.weight }}" min="0" style="width:60px">
      <button type="submit">Вес</button>
    </form>
  </div>
</div>
{% endfor %}

<h2>🔑 Доступ к панели (логины/пароли)</h2>
<div class="card">
  <p><small>Главный админ задан в переменных окружения и не отображается здесь.</small></p>
  {% for u in extra_users %}
  <div class="row">
    <span>{{ u }}</span>
    <form method="post" action="/users/remove" onsubmit="return confirm('Удалить доступ у {{ u }}?')">
      <input type="hidden" name="username" value="{{ u }}">
      <button class="danger" type="submit">Удалить</button>
    </form>
  </div>
  {% else %}
  <p><small>Дополнительных пользователей пока нет.</small></p>
  {% endfor %}
</div>
<div class="card">
  <form method="post" action="/users/add">
    <input type="text" name="username" placeholder="Новый логин" required>
    <input type="text" name="password" placeholder="Пароль для него" required>
    <button type="submit">➕ Выдать доступ</button>
  </form>
</div>

</body></html>
"""


def _flash_redirect(message, is_error=False):
    session["_flash"] = message
    session["_flash_err"] = is_error
    return redirect(url_for("dashboard"))


@app.route("/", methods=["GET"])
@app.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    message = session.pop("_flash", None)
    is_error = session.pop("_flash_err", False)
    return render_template_string(
        DASHBOARD_PAGE,
        current_user=session.get("username"),
        message=message,
        is_error=is_error,
        enabled=settings.is_enabled(),
        mode=settings.get_mode(),
        interval=settings.get_interval(),
        chat_interval=settings.get_chat_interval(),
        groups=groups.list_groups(),
        dm_enabled=settings.is_dm_enabled(),
        dm_interval=settings.get_dm_interval(),
        dm_list=dms.list_dms(),
        phrase_list=phrases.list_phrases(),
        extra_users=auth.list_users(),
    )


# ---------- Общие настройки ----------

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


# ---------- Группы ----------

async def _add_group_coro(username):
    entity = await _client.get_entity(username)
    if not isinstance(entity, Channel) or not entity.megagroup:
        raise ValueError("Это не группа обсуждений (супергруппа).")
    from telethon import utils
    groups.add_group(utils.get_peer_id(entity), username)


@app.route("/groups/add", methods=["POST"])
@login_required
def groups_add():
    username = normalize_username(request.form.get("username", ""))
    if not username:
        return _flash_redirect("Укажите юзернейм группы.", True)
    try:
        run_async(_add_group_coro(username))
        return _flash_redirect(f"Группа @{username} подключена.")
    except Exception as e:
        return _flash_redirect(f"Не удалось подключить @{username}: {e}", True)


@app.route("/groups/remove", methods=["POST"])
@login_required
def groups_remove():
    chat_id = request.form.get("chat_id")
    groups.remove_group_by_chat_id(chat_id)
    return redirect(url_for("dashboard"))


# ---------- Личные чаты ----------

async def _add_dm_coro(raw):
    if raw.lstrip('-').isdigit():
        entity = await _client.get_entity(int(raw))
    else:
        entity = await _client.get_entity(normalize_username(raw))
    if not isinstance(entity, User):
        raise ValueError("Это не личный пользователь.")
    from telethon import utils
    label = entity.username or entity.first_name or str(entity.id)
    dms.add_dm(utils.get_peer_id(entity), label)
    return label


@app.route("/dm/add", methods=["POST"])
@login_required
def dm_add():
    target = request.form.get("target", "").strip()
    if not target:
        return _flash_redirect("Укажите @username или ID.", True)
    try:
        label = run_async(_add_dm_coro(target))
        return _flash_redirect(f"Личный чат «{label}» подключён.")
    except Exception as e:
        return _flash_redirect(f"Не удалось подключить «{target}»: {e}", True)


@app.route("/dm/remove", methods=["POST"])
@login_required
def dm_remove():
    chat_id = request.form.get("chat_id")
    dms.remove_dm_by_chat_id(chat_id)
    return redirect(url_for("dashboard"))


@app.route("/dm/toggle", methods=["POST"])
@login_required
def dm_toggle():
    settings.set_dm_enabled(not settings.is_dm_enabled())
    return redirect(url_for("dashboard"))


@app.route("/dm/interval", methods=["POST"])
@login_required
def dm_interval():
    try:
        settings.set_dm_interval(int(request.form.get("value", 1)))
    except ValueError:
        pass
    return redirect(url_for("dashboard"))


# ---------- Фразы ----------

@app.route("/phrases/settext", methods=["POST"])
@login_required
def phrases_settext():
    index = int(request.form.get("index"))
    text = request.form.get("text", "").strip()
    if text:
        phrases.set_phrase(index, text)
    return redirect(url_for("dashboard"))


@app.route("/phrases/toggle", methods=["POST"])
@login_required
def phrases_toggle():
    index = int(request.form.get("index"))
    enabled = request.form.get("enabled") == "true"
    phrases.set_enabled(index, enabled)
    return redirect(url_for("dashboard"))


@app.route("/phrases/setweight", methods=["POST"])
@login_required
def phrases_setweight():
    index = int(request.form.get("index"))
    try:
        weight = int(request.form.get("weight", 1))
    except ValueError:
        weight = 1
    phrases.set_weight(index, weight)
    return redirect(url_for("dashboard"))


# ---------- Пользователи панели ----------

@app.route("/users/add", methods=["POST"])
@login_required
def users_add():
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    ok, error = auth.add_user(username, password)
    if ok:
        return _flash_redirect(f"Логин «{username}» создан.")
    return _flash_redirect(error, True)


@app.route("/users/remove", methods=["POST"])
@login_required
def users_remove():
    username = request.form.get("username", "")
    auth.remove_user(username)
    return redirect(url_for("dashboard"))


def run_panel():
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
