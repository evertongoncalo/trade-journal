"""Notificação (toast) do Windows via PowerShell, sem dependências extras.

Usa o AppUserModelID do próprio Windows PowerShell, que já é registrado no sistema; sem um ID registrado o
Windows costuma descartar o toast em silêncio. Se o Windows estiver em "Não incomodar" ou com o assistente de
foco ligado, a notificação vai direto para a central de notificações.
"""
from __future__ import annotations

import base64
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape, quoteattr

APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


def available() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Notificações do Windows só existem no Windows."
    if shutil.which("powershell") is None:
        return False, "powershell.exe não encontrado."
    return True, "ok"


def build_toast_xml(title: str, body: str, url: str | None = None) -> str:
    """XML do toast em uma linha só. Com `url`, clicar na notificação abre o app no navegador."""
    launch = f" activationType=\"protocol\" launch={quoteattr(url)}" if url else ""
    return (
        f"<toast{launch}><visual><binding template=\"ToastGeneric\">"
        f"<text>{escape(title)}</text><text>{escape(body)}</text>"
        "</binding></visual><audio src=\"ms-winsoundevent:Notification.Default\"/></toast>"
    )


def build_script(xml: str) -> str:
    if "\n" in xml or "\r" in xml:
        raise ValueError("O XML do toast precisa ficar em uma linha.")
    return "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null",
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null",
            "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument",
            "$xml.LoadXml(@'",
            xml,
            "'@)",
            "$toast = New-Object Windows.UI.Notifications.ToastNotification $xml",
            f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{APP_ID}').Show($toast)",
        ]
    )


def send(title: str, body: str, url: str | None = None) -> tuple[bool, str]:
    """Mostra a notificação. Devolve (ok, detalhe); nunca levanta exceção."""
    ok, why = available()
    if not ok:
        return False, why
    encoded = base64.b64encode(build_script(build_toast_xml(title, body, url)).encode("utf-16-le")).decode("ascii")
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        return False, f"falha ao chamar o PowerShell: {exc}"
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or f"código {proc.returncode}").strip()[:300]
    return True, "enviada"
