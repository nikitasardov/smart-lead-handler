"""Тесты Webhook «Умный обработчик лидов»."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

VALID_TEMPERATURES = frozenset({"hot", "warm", "cold"})

BRANCH_BY_TEMPERATURE = {
    "hot": "hot_output",
    "warm": "warm_output",
    "cold": "cold_log",
}

SUCCESS_RESPONSE_KEYS = frozenset(
    {
        "ok",
        "branch",
        "temperature",
        "contact_found",
        "name",
        "product",
        "client_interest",
        "draft_reply",
        "contact",
    }
)

CONTACT_KEYS = frozenset({"email", "phone"})


@dataclass(frozen=True)
class LeadCase:
    id: str
    filename: str
    contact_found: bool
    branch: str | None = None
    temperature: str | None = None
    require_contact_email: bool = False
    require_contact_filled: bool = False


LEAD_CASES = [
    LeadCase("structured_phone", "01_structured_phone.json", contact_found=True),
    LeadCase(
        "structured_email",
        "02_structured_email.json",
        contact_found=True,
        require_contact_email=True,
    ),
    LeadCase("unstructured_garbage", "03_unstructured_garbage.json", contact_found=True),
    LeadCase(
        "hot",
        "04_hot_lead.json",
        contact_found=True,
        branch="hot_output",
        temperature="hot",
        require_contact_filled=True,
    ),
    LeadCase(
        "cold",
        "05_cold_lead.json",
        contact_found=True,
        branch="cold_log",
        temperature="cold",
    ),
    LeadCase(
        "warm",
        "06_warm_lead.json",
        contact_found=True,
        branch="warm_output",
        temperature="warm",
    ),
    LeadCase(
        "no_contact",
        "07_no_contact.json",
        contact_found=False,
        branch="no_contact",
    ),
    LeadCase(
        "empty_body",
        "08_empty.json",
        contact_found=False,
        branch="no_contact",
    ),
]


def _assert_response_schema(body: dict) -> None:
    missing = SUCCESS_RESPONSE_KEYS - body.keys()
    assert not missing, f"Нет ключей: {missing}, body={body}"
    contact = body.get("contact")
    assert isinstance(contact, dict), body
    assert CONTACT_KEYS <= contact.keys(), body


def _assert_lead_body(body: dict, case: LeadCase) -> None:
    assert body.get("ok") is True, body
    assert body.get("contact_found") is case.contact_found, body
    _assert_response_schema(body)

    if case.branch is not None:
        assert body.get("branch") == case.branch, body
    if case.temperature is not None:
        assert body.get("temperature") == case.temperature, body
        assert body.get("branch") == BRANCH_BY_TEMPERATURE[case.temperature], body
    elif case.contact_found:
        temp = body.get("temperature")
        assert temp in VALID_TEMPERATURES, body
        assert body.get("branch") == BRANCH_BY_TEMPERATURE[temp], body

    contact = body.get("contact") or {}
    if case.require_contact_email:
        assert contact.get("email"), body
    if case.require_contact_filled:
        assert contact.get("email") or contact.get("phone"), body


@pytest.mark.parametrize("case", LEAD_CASES, ids=lambda c: c.id)
def test_lead_scenario(lead_client, case: LeadCase) -> None:
    response = lead_client.post_file(case.filename)
    body = lead_client.parse(response)

    assert response.status_code == 200, body
    _assert_lead_body(body, case)


@pytest.mark.parametrize(
    ("send_token", "token"),
    [
        (True, "invalid-token-for-test"),
        (False, None),
    ],
    ids=["wrong_token", "missing_token"],
)
def test_webhook_unauthorized(
    lead_client, send_token: bool, token: str | None
) -> None:
    """HTTP 403, тело не JSON."""
    payload = lead_client.load("01_structured_phone.json")
    response = lead_client.post(payload, token=token, send_token=send_token)

    assert response.status_code == 403, response.text
    assert "Authorization data is wrong" in response.text
    assert not response.text.strip().startswith("{")


def test_invalid_json_rejected(lead_client) -> None:
    """HTTP 422 при невалидном JSON."""
    response = lead_client.post_raw("not-json{")

    assert response.status_code == 422, response.text
    body = lead_client.parse(response)
    assert body.get("code") == 422, body
    assert "parse" in str(body.get("message", "")).lower(), body
