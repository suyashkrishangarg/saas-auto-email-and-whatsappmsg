"""WhatsApp dispatch with automatic provider fallback: Meta -> Twilio -> Gupshup.

Retry policy (per requirement): one retry inside the provider, then the worker
marks FAILED so the consultant gets a manual-alert entry. Message body = full AI
summary + demand amount + due date.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

import httpx

logger = logging.getLogger("whatsapp")
HTTP_TIMEOUT = 30.0


class WhatsAppError(Exception):
    def __init__(self, message: str, provider: str = ""):
        super().__init__(message)
        self.provider = provider


def build_message(
    *,
    recipient_kind: str,  # CONSULTANT | CLIENT
    client_name: str,
    gstin: Optional[str],
    notice_form: Optional[str],
    demand_amount: Optional[Decimal],
    due_date: Optional[str],
    summary: Optional[str],
    is_unmapped: bool = False,
) -> str:
    if is_unmapped:
        return (
            "⚠️ *GST Notice detected - no client mapped*\n\n"
            f"GSTIN on notice: *{gstin or 'Not found'}*\n"
            f"Form: {notice_form or 'N/A'}\n"
            f"Summary: {summary or 'N/A'}\n\n"
            "Open your dashboard to map this GSTIN to a client and dispatch the client alert."
        )
    who = "Client" if recipient_kind == "CLIENT" else "CA"
    lines = [
        f"📄 *GST Notice Alert ({who})*",
        f"Client: *{client_name}*",
        f"GSTIN: {gstin or 'N/A'}",
        f"Form: {notice_form or 'N/A'}",
    ]
    if demand_amount is not None:
        lines.append(f"Demand: *₹{Decimal(demand_amount):,.2f}*")
    if due_date:
        lines.append(f"Due: *{due_date}*")
    if summary:
        lines.append(f"\n_{summary}_")
    return "\n".join(lines)


# ------------------------------- providers ---------------------------------

async def _send_meta(token: str, phone_number_id: str, to: str, body: str) -> str:
    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=payload)
        if resp.status_code >= 400:
            raise WhatsAppError(f"Meta {resp.status_code}: {resp.text[:300]}", "meta")
        data = resp.json()
        return data.get("messages", [{}])[0].get("id", "")


async def _send_twilio(sid: str, token: str, from_: str, to: str, body: str) -> str:
    import base64

    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Basic {auth}"},
            data={"To": f"whatsapp:{to}", "From": f"whatsapp:{from_}", "Body": body},
        )
        if resp.status_code >= 400:
            raise WhatsAppError(f"Twilio {resp.status_code}: {resp.text[:300]}", "twilio")
        return resp.json().get("sid", "")


async def _send_gupshup(api_key: str, sender: str, to: str, body: str) -> str:
    url = "https://api.gupshup.ai/wa/api/v1/msg"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(
            url,
            headers={"apikey": api_key},
            data={
                "channel": "whatsapp",
                "source": sender,
                "destination": to,
                "type": "text",
                "text": body,
            },
        )
        if resp.status_code >= 400:
            raise WhatsAppError(f"Gupshup {resp.status_code}: {resp.text[:300]}", "gupshup")
        data = resp.json()
        return data.get("messageId", "") or data.get("jobId", "")


# ------------------------------- dispatcher --------------------------------

async def send_whatsapp(wa_cfg: Dict[str, Any], to: str, body: str) -> Tuple[str, str, str]:
    """Returns (provider, message_id, "") on success.

    Walks the configured fallback chain (default meta -> twilio -> gupshup).
    Each provider gets ONE retry (immediate) before moving to the next.
    On total failure raises WhatsAppError carrying the last error.
    """
    to = to.replace("+", "").replace(" ", "")
    if not to.isdigit():
        raise WhatsAppError(f"Invalid destination number: {to}", "validation")
    to = "91" + to if len(to) == 10 else to

    order = wa_cfg.get("provider_order") or ["meta", "twilio", "gupshup"]
    last_err: Optional[WhatsAppError] = None

    for provider in order:
        cfg = wa_cfg.get(provider) or {}
        try:
            if provider == "meta":
                if not (cfg.get("token") and cfg.get("phone_number_id")):
                    continue
                mid = await _send_meta(cfg["token"], cfg["phone_number_id"], to, body)
            elif provider == "twilio":
                if not (cfg.get("account_sid") and cfg.get("auth_token") and cfg.get("from")):
                    continue
                mid = await _send_twilio(
                    cfg["account_sid"], cfg["auth_token"], cfg["from"], to, body
                )
            elif provider == "gupshup":
                if not (cfg.get("api_key") and cfg.get("sender")):
                    continue
                mid = await _send_gupshup(cfg["api_key"], cfg["sender"], to, body)
            else:
                continue
            return (provider, mid, "")

        except WhatsAppError as exc:
            last_err = exc
            logger.warning("WhatsApp provider %s failed (%s); retrying once", provider, exc)
            try:  # ONE retry on the same provider
                if provider == "meta":
                    mid = await _send_meta(cfg["token"], cfg["phone_number_id"], to, body)
                elif provider == "twilio":
                    mid = await _send_twilio(
                        cfg["account_sid"], cfg["auth_token"], cfg["from"], to, body
                    )
                else:
                    mid = await _send_gupshup(cfg["api_key"], cfg["sender"], to, body)
                return (provider, mid, "")
            except WhatsAppError as exc2:
                last_err = exc2
                continue
        except Exception as exc:  # network/unknown - keep walking the chain
            last_err = WhatsAppError(str(exc), provider)
            continue

    raise last_err or WhatsAppError("No WhatsApp provider configured", "none")
