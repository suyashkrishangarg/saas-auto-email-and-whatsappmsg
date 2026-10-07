"""Single-call LLM notice analysis.

One request extracts everything: official-ness, GSTIN, notice form, FY, period,
demand amount, due date and a 2-sentence summary. Provider is whatever the
super-admin picked in the dynamic settings (no hard-coded default).

Providers: openai | gemini | anthropic | groq - each uses its own HTTP endpoint
via httpx to keep the dependency surface small.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

import httpx

DEFAULT_SYSTEM_PROMPT = (
    "You are an expert Indian GST compliance assistant working for Chartered "
    "Accountants. You are given the raw text of an email (and its PDF attachment "
    "content, if any) received by a tax consultant. Extract the requested fields "
    "with strict JSON output. Rules: 1) GSTIN is exactly 15 characters, uppercase, "
    "state code first 2 digits. 2) notice_form is one of DRC-01, DRC-01A, ASMT-10, "
    "GSTR-3A, REG-17, DRC-03, SCN, or the form named in the text; null if absent. "
    "3) demand_amount is a positive number (no commas) or null. 4) due_date is "
    "YYYY-MM-DD or null. 5) summary is exactly 2 plain sentences. 6) If the content "
    "is not an official government notice, set is_official_notice=false and null "
    "out the other fields."
)

SCHEMA_HINT = """{
  "is_official_notice": true,
  "gstin": "29ABCDE1234F1Z5",
  "notice_form": "DRC-01",
  "financial_year": "2024-25",
  "tax_period": "Mar-2024",
  "demand_amount": 125000.00,
  "due_date": "2024-11-30",
  "summary": "Two sentence plain summary."
}"""

LLM_TIMEOUT = 60.0


class LLMError(Exception):
    pass


def _coerce(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise provider output into the canonical notice analysis shape."""
    amount = payload.get("demand_amount")
    try:
        amount = float(Decimal(str(amount))) if amount not in (None, "", "null") else None
    except (InvalidOperation, ValueError, TypeError):
        amount = None

    due = payload.get("due_date")
    if isinstance(due, str) and due:
        try:
            due = date.fromisoformat(due[:10]).isoformat()
        except ValueError:
            due = None
    else:
        due = None

    gstin = (payload.get("gstin") or "").strip().upper() or None
    if gstin and (len(gstin) != 15 or not gstin.isalnum()):
        gstin = None

    return {
        "is_official_notice": bool(payload.get("is_official_notice", False)),
        "gstin": gstin,
        "notice_form": (payload.get("notice_form") or None),
        "financial_year": (payload.get("financial_year") or None),
        "tax_period": (payload.get("tax_period") or None),
        "demand_amount": amount,
        "due_date": due,
        "summary": (payload.get("summary") or "").strip(),
    }


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError(f"No JSON object in LLM response: {text[:200]}")
    return json.loads(text[start : end + 1])


async def _chat_completions(provider: str, cfg: Dict[str, str], system: str, user: str) -> str:
    """Generic OpenAI-compatible /chat/completions endpoint (openai + groq)."""
    base = "https://api.openai.com/v1" if provider == "openai" else "https://api.groq.com/openai/v1"
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        resp = await client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {cfg['api_key']}"},
            json={
                "model": cfg["model"],
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )
        if resp.status_code >= 400:
            raise LLMError(f"{provider} HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _gemini(cfg: Dict[str, str], system: str, user: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{cfg['model']}:generateContent"
    )
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        resp = await client.post(
            url,
            params={"key": cfg["api_key"]},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
            },
        )
        if resp.status_code >= 400:
            raise LLMError(f"gemini HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def _anthropic(cfg: Dict[str, str], system: str, user: str) -> str:
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": cfg["api_key"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": cfg["model"],
                "max_tokens": 1024,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "temperature": 0,
            },
        )
        if resp.status_code >= 400:
            raise LLMError(f"anthropic HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return "".join(b.get("text", "") for b in data.get("content", []))


async def analyse_notice(
    *,
    subject: str,
    body_text: str,
    attachment_text: str = "",
    cfg: Dict[str, Any],
    system_prompt_override: str = "",
) -> Dict[str, Any]:
    """One call -> full structured notice analysis (including GSTIN extraction)."""
    provider = (cfg.get("provider") or "").strip().lower()
    model = (cfg.get("model") or "").strip()
    api_key = (cfg.get("api_key") or "").strip()

    if not provider or not model or not api_key:
        raise LLMError(
            "LLM is not configured. Super-admin must set provider, model and API key "
            "in Admin > Settings."
        )

    system = system_prompt_override or cfg.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
    user = (
        f"SUBJECT:\n{subject}\n\nBODY:\n{body_text[:12000]}"
        + (f"\n\nATTACHMENT:\n{attachment_text[:12000]}" if attachment_text else "")
        + f"\n\nReturn ONLY a JSON object matching exactly this shape:\n{SCHEMA_HINT}"
    )
    cfg = dict(cfg)
    cfg["model"] = model

    if provider in ("openai", "groq"):
        raw = await _chat_completions(provider, cfg, system, user)
    elif provider == "gemini":
        raw = await _gemini(cfg, system, user)
    elif provider == "anthropic":
        raw = await _anthropic(cfg, system, user)
    else:
        raise LLMError(f"Unsupported LLM provider: {provider}")

    return _coerce(_extract_json(raw))


async def analyse_notice_vision(
    *,
    subject: str,
    page_images_base64: List[str],
    cfg: Dict[str, Any],
    system_prompt_override: str = "",
) -> Dict[str, Any]:
    """Fallback when a scanned PDF has no extractable text layer.

    Sends PNG pages to a vision-capable model (still one structured call).
    Only OpenAI and Gemini are supported; other providers raise a clear error.
    """
    provider = (cfg.get("provider") or "").strip().lower()
    if provider not in ("openai", "gemini"):
        raise LLMError(
            f"Scanned PDF detected but provider '{provider}' has no vision fallback. "
            "Configure OpenAI or Gemini in Admin > Settings."
        )
    if not page_images_base64:
        raise LLMError("Scanned PDF produced no renderable pages for vision analysis.")

    system = system_prompt_override or cfg.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
    parts: List[Dict[str, Any]] = [
        {"type": "text", "text": f"SUBJECT: {subject}\nExtract per instructions."}
    ]
    for b64 in page_images_base64[:5]:
        if provider == "openai":
            parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
        else:
            parts.append({"inline_data": {"mime_type": "image/png", "data": b64}})

    if provider == "openai":
        raw = await _openai_vision(cfg, system, parts)
    else:
        raw = await _gemini_vision(cfg, system, parts)
    return _coerce(_extract_json(raw))


async def _openai_vision(cfg, system, parts):
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {cfg['api_key']}"},
            json={
                "model": cfg["model"],
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": parts},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )
        if resp.status_code >= 400:
            raise LLMError(f"openai vision HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]["content"]


async def _gemini_vision(cfg, system, parts):
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        resp = await client.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{cfg['model']}:generateContent",
            params={"key": cfg["api_key"]},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
            },
        )
        if resp.status_code >= 400:
            raise LLMError(f"gemini vision HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
