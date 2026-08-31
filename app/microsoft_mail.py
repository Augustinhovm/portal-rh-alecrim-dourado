import base64
import json
import mimetypes
import os
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class MicrosoftMailError(RuntimeError):
    pass


def _required_env(name):
    value = (os.getenv(name) or "").strip()
    if not value:
        raise MicrosoftMailError(f"Configuração ausente: {name}.")
    return value


def outlook_mail_settings():
    sender = (os.getenv("M365_MAIL_SENDER") or "").strip()
    recipients_raw = (os.getenv("M365_CERTIFICATE_RECIPIENTS") or "").strip()
    recipients = [x.strip() for x in recipients_raw.replace(";", ",").split(",") if x.strip()]
    return {
        "configured": bool(
            (os.getenv("MICROSOFT_TENANT_ID") or "").strip()
            and (os.getenv("MICROSOFT_CLIENT_ID") or "").strip()
            and (os.getenv("MICROSOFT_CLIENT_SECRET") or "").strip()
            and sender
            and recipients
        ),
        "sender": sender,
        "recipients": recipients,
    }


def _get_access_token(timeout=12):
    tenant_id = _required_env("MICROSOFT_TENANT_ID")
    client_id = _required_env("MICROSOFT_CLIENT_ID")
    client_secret = _required_env("MICROSOFT_CLIENT_SECRET")

    endpoint = f"https://login.microsoftonline.com/{quote(tenant_id)}/oauth2/v2.0/token"
    body = urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": GRAPH_SCOPE,
        "grant_type": "client_credentials",
    }).encode("utf-8")

    req = Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise MicrosoftMailError(f"Falha de autenticação Microsoft ({exc.code}): {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise MicrosoftMailError(f"Não foi possível conectar ao Microsoft 365: {exc}") from exc

    token = payload.get("access_token")
    if not token:
        raise MicrosoftMailError("A Microsoft não retornou um token de acesso.")
    return token


def send_certificate_email(*, employee_name, start_date, days, original_name, file_path, timeout=18):
    settings = outlook_mail_settings()
    if not settings["configured"]:
        raise MicrosoftMailError(
            "Integração Microsoft 365 ainda não configurada nas variáveis de ambiente."
        )

    if not os.path.isfile(file_path):
        raise MicrosoftMailError("O arquivo do atestado não foi localizado no armazenamento do Portal.")

    file_size = os.path.getsize(file_path)
    # O sendMail simples usa JSON/base64. Mantemos margem abaixo do limite de requisição do Graph.
    if file_size > 2_500_000:
        raise MicrosoftMailError(
            "O atestado excede 2,5 MB e não pode ser encaminhado pelo envio simples configurado."
        )

    with open(file_path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")

    mime_type = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    sender = settings["sender"]
    recipients = settings["recipients"]
    formatted_date = start_date.strftime("%d/%m/%Y")

    subject = f"Atestado médico - {employee_name} - {formatted_date}"
    body = (
        "Prezados,\n\n"
        "Encaminhamos, em anexo, o atestado recebido e conferido pelo RH no Portal RH "
        "da Associação Alecrim Dourado.\n\n"
        f"Colaborador(a): {employee_name}\n"
        f"Início do atestado: {formatted_date}\n"
        f"Período informado: {int(days or 1)} dia(s)\n\n"
        "Este e-mail foi gerado automaticamente pelo Portal RH.\n"
    )

    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [
                {"emailAddress": {"address": address}} for address in recipients
            ],
            "attachments": [{
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": original_name,
                "contentType": mime_type,
                "contentBytes": encoded,
            }],
        },
        "saveToSentItems": True,
    }

    token = _get_access_token()
    endpoint = f"{GRAPH_BASE}/users/{quote(sender)}/sendMail"
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        endpoint,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            status = getattr(response, "status", 202)
            if status not in (200, 202):
                raise MicrosoftMailError(f"Microsoft Graph retornou HTTP {status}.")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1500]
        raise MicrosoftMailError(f"Falha ao enviar pelo Outlook ({exc.code}): {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise MicrosoftMailError(f"Falha de conexão durante o envio pelo Outlook: {exc}") from exc

    return {
        "sender": sender,
        "recipients": recipients,
        "subject": subject,
    }
