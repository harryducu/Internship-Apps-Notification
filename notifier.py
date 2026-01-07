import json
import os
from pathlib import Path
from typing import Any

import requests

# Stable data source (JSON), not the README formatting.
LISTINGS_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/.github/scripts/listings.json"
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

STATE_FILE = Path("seen_swe_internships.json")


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
    r = requests.get(LISTINGS_URL, headers={"User-Agent": "internship-notifier/1.0"}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise RuntimeError("Unexpected listings.json format (expected a list)")
    return data


def is_swe_role(title: str) -> bool:
    t = (title or "").lower()

    include = [
        "software", "software engineer", "swe",
        "backend", "back end", "frontend", "front end",
        "full stack", "full-stack",
        "mobile", "ios", "android",
        "security", "cyber",
        "developer", "engineer",
    ]

    exclude = [
        "data analyst", "data analytics", "business", "product",
        "program manager", "pm",
        "designer", "design", "ux", "ui",
        "marketing", "sales", "finance", "accounting", "hr",
        "qa", "test engineer", "quality assurance",
        "sre", "site reliability", "devops",
    ]

    # If it clearly matches excluded categories, drop it.
    if any(k in t for k in exclude):
        return False

    # Otherwise require at least one include keyword.
    return any(k in t for k in include)


def load_seen_ids() -> set[str]:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            ids = data.get("seen_ids", [])
            return set(ids) if isinstance(ids, list) else set()
        except Exception:
            return set()
    return set()


def save_seen_ids(seen_ids: set[str]) -> None:
    STATE_FILE.write_text(json.dumps({"seen_ids": sorted(seen_ids)}, indent=2))


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
    seen_ids = load_seen_ids()
    print("Loaded seen_ids:", len(seen_ids))

    listings = fetch_listings()
    print("Fetched listings:", len(listings))

    swe_listings: list[dict[str, Any]] = []
    for role in listings:
        if not isinstance(role, dict):
            continue

        if not role.get("active", False):
            continue
        if not role.get("is_visible", False):
            continue

        title = str(role.get("title", ""))
        if not is_swe_role(title):
            continue

        swe_listings.append(role)

    print("Filtered SWE listings:", len(swe_listings))

    current_ids = set(str(role.get("id")) for role in swe_listings if role.get("id"))
    print("Current SWE ids:", len(current_ids))

    # First run: baseline only
    if not seen_ids:
        save_seen_ids(current_ids)
        print("Baseline saved.")
        return

    new_ids = current_ids - seen_ids

    if new_ids:
        send_telegram(f"🚨 {len(new_ids)} new SWE internship listing(s) added!")
        # Send up to 5 listings (sorted for stable order)
        id_to_role = {str(r.get("id")): r for r in swe_listings if r.get("id")}
        for rid in sorted(new_ids)[:5]:
            role = id_to_role.get(rid)
            if role:
                send_telegram(fmt_role(role))
            else:
                send_telegram(f"🚨 New SWE Internship (id: {rid})")
    else:
        print("No new listings.")

    save_seen_ids(current_ids)


if __name__ == "__main__":
    main()
