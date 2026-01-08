import json
import os
from pathlib import Path
from typing import Any

import requests

LISTINGS_URL = "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/.github/scripts/listings.json"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

STATE_FILE = Path("seen_swe_internships.json")

RUN_MESSAGE = (
    "🤖 SWE Internship Notifier is running\n\n"
    "A cloud-run bot that monitors GitHub internship listings, "
    "filters for new software engineering roles, and sends notifications "
    "when opportunities are added.\n\n"
    "Built by: Harry Ducu"
)


def send_telegram(message: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    params = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()


def fetch_listings() -> list[dict[str, Any]]:
    headers = {"User-Agent": "internship-notifier/1.0"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    r = requests.get(LISTINGS_URL, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise RuntimeError("Unexpected listings.json format")
    return data


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"seen_ids": []}
    try:
        data = json.loads(STATE_FILE.read_text())
        if not isinstance(data, dict):
            return {"seen_ids": []}
        if not isinstance(data.get("seen_ids"), list):
            return {"seen_ids": []}
        return data
    except Exception:
        return {"seen_ids": []}


def save_state(seen_ids: set[str]) -> None:
    STATE_FILE.write_text(json.dumps({"seen_ids": sorted(seen_ids)}, indent=2))


def role_category(role: dict[str, Any]) -> str:
    for key in ("category", "role_category", "roleCategory", "type", "role_type", "discipline", "track"):
        val = role.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().lower()
    return ""


def is_swe(role: dict[str, Any]) -> bool:
    cat = role_category(role)
    if not cat:
        return False
    return "software engineering" in cat or cat == "swe" or cat == "software"


def fmt_role(role: dict[str, Any]) -> str:
    company = role.get("company_name", "Unknown")
    title = role.get("title", "Unknown")
    url = role.get("url", "")
    locations = role.get("locations") or []
    terms = role.get("terms") or []
    sponsorship = role.get("sponsorship", "Unknown")

    loc_str = ", ".join(locations) if locations else "Unknown"
    term_str = ", ".join(terms) if terms else "Unknown"

    msg = (
        "🚨 New SWE Internship\n"
        f"Company: {company}\n"
        f"Role: {title}\n"
        f"Location: {loc_str}\n"
        f"Term: {term_str}\n"
        f"Sponsorship: {sponsorship}\n"
    )
    if url:
        msg += f"Link: {url}"
    return msg


def main() -> None:
    send_telegram(RUN_MESSAGE)

    state = load_state()
    seen_ids = set(str(x) for x in state.get("seen_ids", []) if x)

    listings = fetch_listings()

    swe_listings = []
    for role in listings:
        if not isinstance(role, dict):
            continue
        if not role.get("active", False):
            continue
        if not role.get("is_visible", False):
            continue
        if not is_swe(role):
            continue
        swe_listings.append(role)

    cats = {}
    for r in swe_listings:
        c = role_category(r) or "MISSING"
        cats[c] = cats.get(c, 0) + 1
    print("Category breakdown (filtered):", cats)

    sample = swe_listings[:10]
    for r in sample:
        print("Microsoft:", role_category(r), "|", r.get("company_name"), "|", r.get("title"))


    current_ids = set(str(role.get("id")) for role in swe_listings if role.get("id"))

    if not seen_ids:
        save_state(current_ids)
        send_telegram("✅ Baseline created for SWE category.")
        return

    new_ids = current_ids - seen_ids

    if new_ids:
        send_telegram(f"🚨 {len(new_ids)} new SWE internship listing(s) added!")
        id_to_role = {str(r.get("id")): r for r in swe_listings if r.get("id")}
        for rid in sorted(new_ids)[:10]:
            role = id_to_role.get(rid)
            if role:
                send_telegram(fmt_role(role))
            else:
                send_telegram(f"🚨 New SWE Internship (id: {rid})")

    save_state(current_ids)


if __name__ == "__main__":
    main()
