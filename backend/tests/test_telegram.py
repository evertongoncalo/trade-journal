import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import config, db, settings
from app.alerts import store, telegram, watcher
from app.alerts.telegram import TelegramError
from app.main import app

TOKEN = "123456:SECRET-TOKEN-ABC"
T0 = datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)
NOW = T0 + timedelta(minutes=10)


class FakeTelegram:
    """Imita a API do Bot do Telegram por HTTP de verdade (em outra thread)."""

    def __init__(self):
        self.sent: list[dict] = []
        self.updates: list[dict] = []
        self.fail_send: tuple[int, dict] | None = None
        self.fail_updates: tuple[int, dict] | None = None
        self.raw: bytes | None = None  # resposta não-JSON
        self.calls: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code, payload):
                body = outer.raw if outer.raw is not None else json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                params = json.loads(self.rfile.read(length) or b"{}")
                prefix = f"/bot{TOKEN}/"
                if not self.path.startswith(prefix):
                    return self._reply(404, {"ok": False, "error_code": 404, "description": "Not Found"})
                method = self.path[len(prefix):]
                outer.calls.append(method)
                if method == "getMe":
                    return self._reply(200, {"ok": True, "result": {"id": 1, "username": "meu_bot", "first_name": "Meu Bot"}})
                if method == "getUpdates":
                    if outer.fail_updates:
                        code, body = outer.fail_updates
                        return self._reply(code, {"ok": False, "error_code": code, **body})
                    return self._reply(200, {"ok": True, "result": outer.updates})
                if method == "sendMessage":
                    if outer.fail_send:
                        code, body = outer.fail_send
                        return self._reply(code, {"ok": False, "error_code": code, **body})
                    outer.sent.append(params)
                    return self._reply(200, {"ok": True, "result": {"message_id": len(outer.sent)}})
                return self._reply(404, {"ok": False, "error_code": 404, "description": "Not Found"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def say(self, chat_id, text, *, kind="private", first="Ana", last="", username=None, title=None, when=1_800_000_000):
        chat = {"id": chat_id, "type": kind}
        if kind == "private":
            chat.update(first_name=first, last_name=last or None, username=username)
        else:
            chat["title"] = title
        self.updates.append({"update_id": len(self.updates) + 1, "message": {"chat": chat, "text": text, "date": when}})


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    db.init_db()


@pytest.fixture
def tg(monkeypatch):
    fake = FakeTelegram()
    monkeypatch.setattr(config, "TELEGRAM_API_URL", fake.url)
    yield fake
    fake.close()


def linked(tg, chat_id=777, label="Ana"):
    telegram.link(chat_id, label)
    return chat_id


# ---------- cliente ----------


def test_no_token_means_a_clear_error_and_nothing_is_sent(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    with pytest.raises(TelegramError) as e:
        telegram.get_me()
    assert e.value.kind == "sem_token" and ".env" in e.value.message
    assert telegram.ready() is False and telegram.notify_alert({}, {}) is None


def test_get_me_and_send_text_use_the_real_http_path(tg):
    assert telegram.get_me() == {"username": "meu_bot", "name": "Meu Bot"}
    linked(tg)
    assert telegram.send_text("oi <b>x</b>") == 1
    sent = tg.sent[0]
    assert sent["chat_id"] == "777" and sent["parse_mode"] == "HTML" and sent["disable_web_page_preview"] is True
    assert sent["text"] == "oi <b>x</b>"


def test_sending_without_a_linked_chat_is_a_clear_error_and_calls_nothing(tg):
    with pytest.raises(TelegramError) as e:
        telegram.send_text("x")
    assert e.value.kind == "sem_chat" and "vincule" in e.value.message and tg.calls == []


@pytest.mark.parametrize(
    "code,body,kind",
    [
        (401, {"description": "Unauthorized"}, "token_recusado"),
        (404, {"description": "Not Found"}, "token_recusado"),
        (400, {"description": "Bad Request: chat not found"}, "chat_nao_encontrado"),
        (403, {"description": "Forbidden: bot was blocked by the user"}, "bloqueado"),
        (409, {"description": "Conflict: terminated by other getUpdates request"}, "conflito"),
        (429, {"description": "Too Many Requests", "parameters": {"retry_after": 7}}, "limite"),
        (500, {"description": "Internal Server Error"}, "pedido"),
    ],
)
def test_api_errors_are_classified_in_portuguese(tg, code, body, kind):
    linked(tg)
    tg.fail_send = (code, body)
    with pytest.raises(TelegramError) as e:
        telegram.send_text("x")
    assert e.value.kind == kind and e.value.message
    if kind == "limite":
        assert "7 s" in e.value.message


def test_the_token_never_appears_in_error_messages(tg, monkeypatch):
    linked(tg)
    tg.fail_send = (400, {"description": f"Bad Request: something about {TOKEN} in the text"})
    with pytest.raises(TelegramError) as e:
        telegram.send_text("x")
    assert "SECRET" not in e.value.message and "SECRET" not in str(e.value)
    # servidor fora do ar: o erro do urllib cita a URL, e a URL tem o token
    monkeypatch.setattr(config, "TELEGRAM_API_URL", "http://127.0.0.1:1")
    with pytest.raises(TelegramError) as e:
        telegram.get_me()
    assert e.value.kind == "rede" and "SECRET" not in e.value.message and e.value.__cause__ is None and e.value.__suppress_context__
    assert telegram.scrub(f"https://x/bot{TOKEN}/getMe") == "https://x/bot***/getMe"


def test_a_non_json_answer_is_reported(tg):
    tg.raw = b"<html>bad gateway</html>"
    with pytest.raises(TelegramError) as e:
        telegram.get_me()
    assert e.value.kind == "resposta_invalida"


def test_a_wrong_token_is_refused_by_the_server(tg, monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "999:OUTRO")
    with pytest.raises(TelegramError) as e:
        telegram.get_me()
    assert e.value.kind == "token_recusado" and "OUTRO" not in e.value.message


# ---------- descoberta e vínculo ----------


def test_discover_lists_private_chats_and_groups_by_recency_and_ignores_the_rest(tg):
    tg.say(1, "oi", first="Ana", last="Silva", username="ana", when=1_800_000_100)
    tg.say(2, "/start", first="Beto", when=1_800_000_300)
    tg.say(3, "alerta aqui", kind="group", title="Meu grupo", when=1_800_000_200)
    tg.say(4, "post", kind="channel", title="Canal", when=1_800_000_400)  # canal: ignorado
    tg.say(1, "x" * 200, first="Ana", last="Silva", username="ana", when=1_800_000_500)  # a mais nova de Ana sobrescreve
    chats = telegram.discover_chats()
    assert [c["chat_id"] for c in chats] == [1, 2, 3]
    ana = chats[0]
    assert ana["rotulo"] == "Ana Silva (@ana)" and ana["tipo"] == "privado" and len(ana["ultima_mensagem"]) == 80
    assert chats[1]["rotulo"] == "Beto" and chats[2]["rotulo"] == "Meu grupo" and chats[2]["tipo"] == "grupo"
    tg.updates.clear()
    assert telegram.discover_chats() == []


def test_link_state_ready_env_override_and_options(tg, monkeypatch):
    assert telegram.ready() is False and telegram.linked_chat() == (None, None, None)
    telegram.link(777, "Ana")
    assert telegram.ready() is True and telegram.linked_chat() == ("777", "Ana", "app")
    telegram.set_options(enabled=False)
    assert telegram.ready() is False and telegram.is_enabled() is False
    telegram.set_options(enabled=True, include_note_=False)
    assert telegram.ready() is True and telegram.include_note() is False
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "-1001")  # o .env manda mais do que o vínculo da tela
    assert telegram.linked_chat() == ("-1001", "definido no .env", "env")
    telegram.send_text("x")
    assert tg.sent[-1]["chat_id"] == "-1001"
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    telegram.unlink()
    assert telegram.ready() is False and settings.get(telegram.CHAT_ID) is None


# ---------- mensagem ----------


def alert(**kw):
    base = {
        "symbol": "NVDA", "kind": "alvo", "direction": "acima", "price": 213.2, "note": "Plano #3: Alvo", "triggered_at": None,
    }
    return {**base, **kw}


HIT = {"bar": T0, "extreme": 213.45}


def test_format_alert_reads_like_the_toast_and_escapes_free_text():
    text = telegram.format_alert(alert(), HIT)
    assert "<b>Alvo atingido</b>" in text and "<b>NVDA</b> subiu até 213.2" in text
    assert "Máxima de 213.45 na barra de" in text and "Plano #3: Alvo" in text and "aba Alertas" in text
    down = telegram.format_alert(alert(kind="invalidacao", direction="abaixo"), {"bar": T0, "extreme": 99.5})
    assert "Invalidação tocada" in down and "caiu até" in down and "Mínima de 99.5" in down
    assert "Alerta de preço" in telegram.format_alert(alert(kind="avulso"), HIT)
    evil = telegram.format_alert(alert(symbol="A<B>&C", note="<script>alert(1)</script> & mais"), HIT)
    assert "<script>" not in evil and "&lt;script&gt;" in evil and "A&lt;B&gt;&amp;C" in evil
    assert "Plano #3" not in telegram.format_alert(alert(), HIT, note=False)
    assert "Reenviada" in telegram.format_alert(alert(), HIT, resent=True) and "Reenviada" not in telegram.format_alert(alert(), HIT)


def test_format_alert_flags_a_late_detection_only_when_the_lag_is_large():
    quick = telegram.format_alert(alert(triggered_at=(T0 + timedelta(minutes=2)).isoformat()), HIT)
    late = telegram.format_alert(alert(triggered_at=(T0 + timedelta(hours=3)).isoformat()), HIT)
    assert "Detectado" not in quick and "Detectado às" in late and "desligado" in late
    naive = telegram.format_alert(alert(triggered_at=(T0 + timedelta(hours=3)).replace(tzinfo=None).isoformat()), HIT)
    assert "Detectado às" in naive  # sem fuso no banco: tratado como UTC


def test_notify_alert_sends_returns_the_outcome_and_never_raises(tg, monkeypatch):
    assert telegram.notify_alert(alert(), HIT) is None  # nada vinculado: não tenta
    linked(tg)
    assert telegram.notify_alert(alert(), HIT) == (True, "enviada")
    assert "NVDA" in tg.sent[0]["text"]
    tg.fail_send = (403, {"description": "Forbidden"})
    ok, detail = telegram.notify_alert(alert(), HIT)
    assert ok is False and "bloqueado" in detail
    monkeypatch.setattr(telegram, "send_text", lambda *a, **k: (_ for _ in ()).throw(RuntimeError(f"boom {TOKEN}")))
    ok, detail = telegram.notify_alert(alert(), HIT)
    assert ok is False and "SECRET" not in detail and "inesperada" in detail


# ---------- vigilância ----------


def bars(rows, start=T0):
    idx = pd.date_range(start, periods=len(rows), freq="min", tz="UTC")
    return pd.DataFrame([(c, h, lo, c, 0.0) for h, lo, c in rows], columns=["Open", "High", "Low", "Close", "Volume"], index=idx)


WICK = bars([(99.0, 98.0, 98.5), (100.4, 98.5, 99.0), (99.5, 98.8, 99.2)])


def fetcher(market, symbol, since, now):
    return WICK, "1m"


def make_alert(**kw):
    a = store.create("cripto", "BTCUSDT", 100.0, "acima", note="olhar o BTC", **kw)
    with db.connect() as con:
        con.execute("UPDATE alerts SET created_at = ? WHERE id = ?", ((T0 - timedelta(seconds=30)).isoformat(), a["id"]))
    return a


class Toast:
    def __init__(self, ok=True):
        self.ok, self.calls = ok, []

    def __call__(self, title, body, url):
        self.calls.append(title)
        return self.ok, "enviada" if self.ok else "sem permissão"


def test_a_fired_alert_also_goes_to_telegram_and_the_result_is_stored(tg):
    linked(tg)
    a = make_alert()
    (fired,) = watcher.check_once(now=NOW, fetch=fetcher, notifier=Toast())
    assert fired["id"] == a["id"] and fired["telegram_ok"] is True and fired["telegram_tries"] == 1 and fired["telegram_detail"] == "enviada"
    assert len(tg.sent) == 1 and "BTCUSDT" in tg.sent[0]["text"] and "olhar o BTC" in tg.sent[0]["text"]
    assert watcher.check_once(now=NOW, fetch=fetcher, notifier=Toast()) == []  # cada alerta dispara uma vez
    assert len(tg.sent) == 1


def test_the_note_can_be_left_out_of_the_message(tg):
    linked(tg)
    telegram.set_options(include_note_=False)
    make_alert()
    watcher.check_once(now=NOW, fetch=fetcher, notifier=Toast())
    assert "olhar o BTC" not in tg.sent[0]["text"]


def test_toast_and_telegram_are_independent(tg):
    linked(tg)
    make_alert()
    tg.fail_send = (403, {"description": "Forbidden"})
    (fired,) = watcher.check_once(now=NOW, fetch=fetcher, notifier=Toast(ok=True))
    assert fired["status"] == "disparado" and fired["notify_ok"] is True and fired["telegram_ok"] is False
    assert "bloqueado" in fired["telegram_detail"]

    tg.fail_send = None
    make_alert()
    (second,) = watcher.check_once(now=NOW, fetch=fetcher, notifier=Toast(ok=False))
    assert second["notify_ok"] is False and second["telegram_ok"] is True  # o toast falhar não impede o Telegram


def test_without_telegram_nothing_is_attempted_and_the_alert_works_as_before(tg):
    a = make_alert()  # token existe, mas nenhum chat vinculado
    (fired,) = watcher.check_once(now=NOW, fetch=fetcher, notifier=Toast())
    assert fired["id"] == a["id"] and fired["telegram_ok"] is None and fired["telegram_tries"] == 0 and tg.sent == []
    telegram.link(1, "x")
    telegram.set_options(enabled=False)
    b = make_alert()
    (again,) = watcher.check_once(now=NOW, fetch=fetcher, notifier=Toast())
    assert again["id"] == b["id"] and again["telegram_ok"] is None and tg.calls == []  # desligado: nem chama a API


def test_failed_messages_are_retried_on_the_next_cycles_and_marked_as_resent(tg):
    linked(tg)
    make_alert()
    tg.fail_send = (500, {"description": "oops"})
    (first,) = watcher.check_once(now=NOW, fetch=fetcher, notifier=Toast())
    assert first["telegram_ok"] is False and first["telegram_tries"] == 1

    assert store.get(first["id"])["telegram_tries"] == 1  # o ciclo que falhou não repete na hora

    watcher.check_once(now=NOW + timedelta(seconds=30), fetch=fetcher, notifier=Toast())  # cedo demais: espera 60 s
    assert store.get(first["id"])["telegram_tries"] == 1
    watcher.check_once(now=NOW + timedelta(seconds=61), fetch=fetcher, notifier=Toast())  # ainda falha: 2ª tentativa
    assert store.get(first["id"])["telegram_tries"] == 2 and store.get(first["id"])["telegram_ok"] is False

    tg.fail_send = None
    watcher.check_once(now=NOW + timedelta(seconds=61 + 100), fetch=fetcher, notifier=Toast())  # depois da 2ª espera são 120 s
    assert store.get(first["id"])["telegram_tries"] == 2 and tg.sent == []
    watcher.check_once(now=NOW + timedelta(seconds=61 + 121), fetch=fetcher, notifier=Toast())
    done = store.get(first["id"])
    assert done["telegram_ok"] is True and done["telegram_tries"] == 3
    assert len(tg.sent) == 1 and "Reenviada" in tg.sent[0]["text"] and "BTCUSDT" in tg.sent[0]["text"]
    watcher.check_once(now=NOW + timedelta(hours=3), fetch=fetcher, notifier=Toast())
    assert len(tg.sent) == 1  # enviada: não repete


def test_retries_stop_after_the_limit_and_after_the_window(tg):
    linked(tg)
    a = make_alert()
    tg.fail_send = (500, {"description": "oops"})
    watcher.check_once(now=NOW, fetch=fetcher, notifier=Toast())
    for i in range(1, 12):
        watcher.check_once(now=NOW + timedelta(hours=i), fetch=fetcher, notifier=Toast())  # sempre depois da espera
    assert store.get(a["id"])["telegram_tries"] == telegram.MAX_TRIES  # parou de insistir

    old = make_alert()
    watcher.check_once(now=NOW, fetch=fetcher, notifier=Toast())  # falha 1
    with db.connect() as con:
        con.execute("UPDATE alerts SET triggered_at = ? WHERE id = ?", ((NOW - timedelta(hours=30)).isoformat(), old["id"]))
    tg.fail_send = None
    watcher.check_once(now=NOW + timedelta(hours=2), fetch=fetcher, notifier=Toast())
    assert store.get(old["id"])["telegram_ok"] is False and tg.sent == []  # disparado há mais de 24 h: não reenvia


def test_turning_telegram_on_later_does_not_resend_old_alerts(tg):
    a = make_alert()
    watcher.check_once(now=NOW, fetch=fetcher, notifier=Toast())  # disparou sem Telegram
    linked(tg)
    watcher.check_once(now=NOW + timedelta(minutes=1), fetch=fetcher, notifier=Toast())
    assert store.get(a["id"])["telegram_ok"] is None and tg.sent == []


def test_a_crash_in_the_retry_step_does_not_break_the_cycle(tg):
    make_alert()

    def boom(now, exclude):
        raise RuntimeError(f"falha com {TOKEN}")

    fired = watcher.check_once(now=NOW, fetch=fetcher, notifier=Toast(), telegram_retry=boom)
    assert len(fired) == 1
    assert "SECRET" not in str(watcher.status()["errors"]) and "telegram" in watcher.status()["errors"]


def test_old_databases_gain_the_telegram_columns_and_the_settings_table(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript(
        """CREATE TABLE alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, market TEXT NOT NULL,
            symbol TEXT NOT NULL, price REAL NOT NULL, direction TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'avulso', entry_id INTEGER, status TEXT NOT NULL DEFAULT 'ativo', base_price REAL,
            checked_until TEXT, last_price REAL, last_checked_at TEXT, triggered_at TEXT, trigger_bar TEXT,
            triggered_price REAL, notified_at TEXT, notify_ok INTEGER, notify_detail TEXT, response TEXT, response_note TEXT,
            response_at TEXT, cancel_reason TEXT);
        INSERT INTO alerts (created_at, market, symbol, price, direction) VALUES ('x', 'cripto', 'BTCUSDT', 1, 'acima');"""
    )
    con.commit()
    con.close()
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db()
    db.init_db()
    old = store.get(1)
    assert old["telegram_ok"] is None and old["telegram_tries"] == 0
    settings.set("k", "v")
    assert settings.get("k") == "v" and settings.get("nada", "padrão") == "padrão"
    settings.set("k", "w")
    assert settings.get("k") == "w"
    settings.delete("k")
    assert settings.get("k") is None


# ---------- API ----------


@pytest.fixture
def client(tg):
    with TestClient(app) as c:
        yield c


def test_api_status_without_and_with_token(tg, monkeypatch):
    with TestClient(app) as c:
        s = c.get("/api/telegram/status").json()
        assert s["token_configured"] is True and s["bot"] == {"username": "meu_bot", "name": "Meu Bot"} and s["chat"] is None
        assert s["ready"] is False and s["enabled"] is True and s["error"] is None
        monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
        off = c.get("/api/telegram/status").json()
        assert off["token_configured"] is False and off["bot"] is None and off["ready"] is False
        monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "999:ERRADO")
        bad = c.get("/api/telegram/status").json()  # token recusado: o status mostra o erro em vez de quebrar
        assert bad["bot"] is None and "recusou" in bad["error"] and "ERRADO" not in bad["error"]


def test_api_link_flow_confirms_in_the_chat_and_only_accepts_chats_the_bot_saw(client, tg):
    assert client.post("/api/telegram/discover").json() == {"chats": []}
    tg.say(10, "/start", first="Ana", username="ana")
    tg.say(11, "oi", first="Intruso")
    chats = client.post("/api/telegram/discover").json()["chats"]
    assert {c["chat_id"] for c in chats} == {10, 11}

    assert client.post("/api/telegram/link", json={"chat_id": 999}).status_code == 404  # não é uma conversa do bot
    assert tg.sent == []
    linked_status = client.post("/api/telegram/link", json={"chat_id": 10}).json()
    assert linked_status["ready"] is True and linked_status["chat"] == {"id": "10", "label": "Ana (@ana)", "source": "app"}
    assert tg.sent[0]["chat_id"] == "10" and "vinculado" in tg.sent[0]["text"]
    assert client.post("/api/telegram/link", json={"chat_id": "11"}).status_code == 200  # string também vale

    assert client.post("/api/telegram/test").json() == {"ok": True}
    assert "Teste do Trade Journal" in tg.sent[-1]["text"]
    opts = client.post("/api/telegram/options", json={"enabled": False, "include_note": False}).json()
    assert opts["enabled"] is False and opts["include_note"] is False and opts["ready"] is False
    assert client.post("/api/telegram/test").json() == {"ok": True}  # o teste vale mesmo com o envio desligado
    gone = client.delete("/api/telegram/link").json()
    assert gone["chat"] is None and gone["ready"] is False


def test_api_errors_map_to_http_codes_without_the_token(client, tg):
    tg.say(10, "oi")
    assert client.post("/api/telegram/test").status_code == 400  # sem chat vinculado
    tg.fail_send = (403, {"description": "Forbidden"})
    r = client.post("/api/telegram/link", json={"chat_id": 10})
    assert r.status_code == 400 and "bloqueado" in r.json()["detail"]
    assert client.get("/api/telegram/status").json()["chat"] is None  # falhou ao confirmar: nada foi vinculado
    tg.fail_updates = (409, {"description": "Conflict"})
    assert client.post("/api/telegram/discover").status_code == 409
    tg.fail_updates = (429, {"description": "slow down", "parameters": {"retry_after": 3}})
    assert client.post("/api/telegram/discover").status_code == 429


def test_the_token_is_never_in_any_api_response(client, tg):
    tg.say(10, "oi", first="Ana")
    bodies = [
        client.get("/api/telegram/status").text,
        client.post("/api/telegram/discover").text,
        client.post("/api/telegram/link", json={"chat_id": 10}).text,
        client.post("/api/telegram/test").text,
        client.post("/api/telegram/options", json={"enabled": True}).text,
        client.get("/api/alerts/status").text,
        client.get("/api/alerts").text,
    ]
    tg.fail_send = (400, {"description": f"leak {TOKEN}"})
    bodies.append(client.post("/api/telegram/test").text)
    assert all("SECRET" not in b and TOKEN not in b for b in bodies)


def test_alerts_status_tells_whether_telegram_is_ready_without_calling_the_network(client, tg):
    s = client.get("/api/alerts/status").json()["telegram"]
    assert s == {"configured": True, "ready": False}
    calls_before = len(tg.calls)
    telegram.link(5, "x")
    assert client.get("/api/alerts/status").json()["telegram"] == {"configured": True, "ready": True}
    assert len(tg.calls) == calls_before  # só lê a configuração


def test_prices_keep_their_decimals_without_scientific_notation():
    assert telegram.fmt_price(81180.23) == "81180.23" and telegram.fmt_price(1.12345) == "1.12345"
    assert telegram.fmt_price(100.0) == "100" and telegram.fmt_price(213.45) == "213.45"
    assert telegram.fmt_price(0.00001234) == "0.00001234" and "e" not in telegram.fmt_price(0.000000012)
    assert "81180.23" in telegram.format_alert(alert(price=81180.23), {"bar": T0, "extreme": 81166.0})
    title, body = watcher.toast_text(alert(price=81180.23), {"bar": T0, "extreme": 81166.0})
    assert "81180.23" in title and "81166" in body  # o toast usa o mesmo formato
