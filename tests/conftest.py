"""Фикстуры и хелперы для тестов Webhook n8n."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PAYLOADS_DIR = Path(__file__).resolve().parent / "payloads"

load_dotenv(PROJECT_ROOT / ".env")

PLACEHOLDER_MARKERS = ("your-n8n", "example.com/webhook/smart-lead-handler")


def load_payload(filename: str) -> dict[str, Any]:
    """Загрузить JSON из tests/payloads/."""
    path = PAYLOADS_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Payload not found: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def post_lead(
    webhook_url: str,
    payload: dict[str, Any],
    *,
    token: str | None,
    send_token: bool = True,
    timeout: float,
) -> requests.Response:
    """POST на Webhook n8n с JSON и опциональным заголовком X-Webhook-Token."""
    headers = {"Content-Type": "application/json"}
    if send_token and token is not None:
        headers["X-Webhook-Token"] = token
    return requests.post(
        webhook_url,
        json=payload,
        headers=headers,
        timeout=timeout,
    )


def post_raw(
    webhook_url: str,
    body: str,
    *,
    token: str | None,
    send_token: bool = True,
    content_type: str = "application/json",
    timeout: float,
) -> requests.Response:
    """POST с сырым телом (для проверки невалидного JSON)."""
    headers = {"Content-Type": content_type}
    if send_token and token is not None:
        headers["X-Webhook-Token"] = token
    return requests.post(
        webhook_url,
        data=body,
        headers=headers,
        timeout=timeout,
    )


def parse_webhook_json(response: requests.Response) -> dict[str, Any]:
    """Разобрать JSON-ответ webhook; понятная ошибка при не-JSON."""
    try:
        data = response.json()
    except ValueError as exc:
        raise AssertionError(
            f"Ответ не JSON (status={response.status_code}): {response.text[:500]}"
        ) from exc
    if not isinstance(data, dict):
        raise AssertionError(f"Ожидался объект JSON, получено: {type(data)!r}")
    return data


@pytest.fixture(scope="session")
def webhook_url() -> str:
    url = os.getenv("N8N_WEBHOOK_URL", "").strip()
    if not url or any(marker in url for marker in PLACEHOLDER_MARKERS):
        pytest.skip("Задайте N8N_WEBHOOK_URL в .env")
    return url


@pytest.fixture(scope="session")
def webhook_token() -> str:
    token = os.getenv("X_WEBHOOK_TOKEN", "").strip()
    if not token or token == "your-secret-token":
        pytest.skip("Задайте X_WEBHOOK_TOKEN в .env")
    return token


@pytest.fixture(scope="session")
def http_timeout() -> float:
    return float(os.getenv("HTTP_TIMEOUT", "120"))


@pytest.fixture
def lead_client(webhook_url: str, webhook_token: str, http_timeout: float):
    """Клиент для отправки лидов на webhook."""

    class LeadClient:
        url = webhook_url
        token = webhook_token
        timeout = http_timeout

        def post(
            self,
            payload: dict[str, Any],
            *,
            token: str | None = None,
            send_token: bool = True,
        ) -> requests.Response:
            return post_lead(
                self.url,
                payload,
                token=self.token if token is None else token,
                send_token=send_token,
                timeout=self.timeout,
            )

        def post_raw(
            self,
            body: str,
            *,
            token: str | None = None,
            send_token: bool = True,
        ) -> requests.Response:
            return post_raw(
                self.url,
                body,
                token=self.token if token is None else token,
                send_token=send_token,
                timeout=self.timeout,
            )

        def load(self, filename: str) -> dict[str, Any]:
            return load_payload(filename)

        def post_file(
            self,
            filename: str,
            *,
            token: str | None = None,
            send_token: bool = True,
        ) -> requests.Response:
            return self.post(self.load(filename), token=token, send_token=send_token)

        @staticmethod
        def parse(response: requests.Response) -> dict[str, Any]:
            return parse_webhook_json(response)

    return LeadClient()
