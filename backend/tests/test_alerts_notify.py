import base64
import subprocess
from xml.dom import minidom

import pytest

from app.alerts import notify


def test_toast_xml_is_well_formed_and_escapes_special_characters():
    xml = notify.build_toast_xml('PETR4 <subiu> & "tocou"', "Nota: a < b && c > d", "http://127.0.0.1:8765/?a=1&b=2")
    doc = minidom.parseString(xml)  # levanta erro se o XML estiver quebrado
    texts = [t.firstChild.data for t in doc.getElementsByTagName("text")]
    assert texts == ['PETR4 <subiu> & "tocou"', "Nota: a < b && c > d"]
    toast = doc.documentElement
    assert toast.getAttribute("activationType") == "protocol"
    assert toast.getAttribute("launch") == "http://127.0.0.1:8765/?a=1&b=2"
    assert "\n" not in xml


def test_toast_without_url_has_no_launch_attribute():
    doc = minidom.parseString(notify.build_toast_xml("t", "b"))
    assert not doc.documentElement.hasAttribute("launch")


def test_script_wraps_the_xml_in_a_literal_here_string():
    xml = notify.build_toast_xml("T", "B")
    script = notify.build_script(xml)
    lines = script.split("\n")
    assert lines[lines.index("$xml.LoadXml(@'") + 1] == xml
    assert "'@)" in lines
    assert notify.APP_ID in script and ".Show($toast)" in script
    with pytest.raises(ValueError):
        notify.build_script("<toast>\n</toast>")


def test_unavailable_outside_windows(monkeypatch):
    monkeypatch.setattr(notify.sys, "platform", "linux")
    ok, why = notify.available()
    assert ok is False and "Windows" in why
    assert notify.send("t", "b")[0] is False


def test_send_runs_powershell_with_an_encoded_command(monkeypatch):
    monkeypatch.setattr(notify, "available", lambda: (True, "ok"))
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(notify.subprocess, "run", fake_run)
    assert notify.send("BTCUSDT subiu até 100", "Máxima 100,4", "http://x/") == (True, "enviada")
    cmd = seen["cmd"]
    assert cmd[0] == "powershell" and "-NoProfile" in cmd and cmd[-2] == "-EncodedCommand"
    script = base64.b64decode(cmd[-1]).decode("utf-16-le")
    assert "BTCUSDT subiu até 100" in script and "Máxima 100,4" in script
    assert seen["kw"]["timeout"] == 20


def test_send_reports_powershell_errors_and_timeouts(monkeypatch):
    monkeypatch.setattr(notify, "available", lambda: (True, "ok"))
    monkeypatch.setattr(
        notify.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="falhou feio\n")
    )
    assert notify.send("t", "b") == (False, "falhou feio")

    def timeout(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 20)

    monkeypatch.setattr(notify.subprocess, "run", timeout)
    ok, detail = notify.send("t", "b")
    assert ok is False and "PowerShell" in detail
