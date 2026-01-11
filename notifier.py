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

# IMPORTANT:
# This file must persist between runs for "new jobs" detection to work.
# If you run this on GitHub Actions, you need to restore/save this file each run
# (commit it back to the repo OR cache it). If it resets, you'll never see updates.
STATE_FILE = Path("seen_swe_internships.json")

RUN_MESSAGE = (
    "🤖 SWE Internship Notifier is running\n\n"
    "A cloud-run bot that monitors GitHub internship listings, "
    "filters for new software engineering roles, and sends notifications "
    "when opportunities are added.\n\n"
    "Built by: Harry Ducu"
)

# ---- SWE FILTER SETTINGS ----
# Categories vary over time, so we do:
# 1) category keyword match
# 2) title keyword fallback
SWE_CATEGORY_KEYWORDS = {
    "software engineering",
    "software engineer",
    "software development",
    "swe",
    "backend",
    "back-end",
    "frontend",
    "front-end",
    "full stack",
    "full-stack",
    "fullstack",
    "platform",
    "engineering",
    "developer",
}

TITLE_KEYWORDS = {
    "software engineer",
    "software engineering",
    "swe",
    "backend",
    "back-end",
    "frontend",
    "front-end",
    "full stack",
    "full-stack",
    "fullstack",
    "platform",
    "developer",
    "development",
}


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
        raise RuntimeError("Unexpected listings.json format (expected a list)")
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


def norm_text(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip().lower()


def role_category(role: dict[str, Any]) -> str:
    # Try several likely keys because schemas sometimes change
    for key in (
        "category",
        "role_category",
        "roleCategory",
        "type",
        "role_type",
        "discipline",
        "track",
    ):
        val = role.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().lower()
    return ""


def is_swe(role: dict[str, Any]) -> bool:
    cat = role_category(role)
    title = norm_text(role.get("title"))
    # Primary: category keywords
    for k in SWE_CATEGORY_KEYWORDS:
        if k in cat:
            return True
    # Fallback: title keywords
    for k in TITLE_KEYWORDS:
        if k in title:
            return True
    return False


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
    # "Bot is running" message
    send_telegram(RUN_MESSAGE)

    # Load seen state
    state = load_state()
    seen_ids = set(str(x) for x in state.get("seen_ids", []) if x)

    # Fetch all listings
    listings = fetch_listings()

    # Debug counters
    total = 0
    active_cnt = 0
    visible_cnt = 0
    swe_cnt = 0

    swe_listings: list[dict[str, Any]] = []
    cats: dict[str, int] = {}

    for role in listings:
        if not isinstance(role, dict):
            continue

        total += 1

        if not role.get("active", False):
            continue
        active_cnt += 1

        if not role.get("is_visible", False):
            continue
        visible_cnt += 1

        if not is_swe(role):
            continue
        swe_cnt += 1

        swe_listings.append(role)
        c = role_category(role) or "MISSING"
        cats[c] = cats.get(c, 0) + 1

    # Print some useful debugging info in Actions logs
    print("---- FILTER DEBUG ----")
    print("total roles:", total)
    print("active roles:", active_cnt)
    print("active + visible roles:", visible_cnt)
    print("active + visible + SWE roles:", swe_cnt)
    print("Category breakdown (SWE-filtered):", dict(sorted(cats.items(), key=lambda x: -x[1])))

    # Show a few examples (first 10) so you can see what your filter is catching
    print("---- SAMPLE (first 10 SWE roles) ----")
    for r in swe_listings[:10]:
        print(role_category(r), "|", r.get("company_name"), "|", r.get("title"))

    # Build set of current IDs (for SWE listings only)
    current_ids = set(str(role.get("id")) for role in swe_listings if role.get("id"))

    # Baseline creation only once (when no state exists)
    if not seen_ids:
        save_state(current_ids)
        send_telegram("✅ Baseline created for SWE filter. Next runs will alert on new postings.")
        return

    # Compute new IDs
    new_ids = current_ids - seen_ids

    if new_ids:
        send_telegram(f"🚨 {len(new_ids)} new SWE internship listing(s) added!")

        id_to_role = {str(r.get("id")): r for r in swe_listings if r.get("id")}

        # Limit to 10 messages to avoid spamming
        for rid in sorted(new_ids)[:10]:
            role = id_to_role.get(rid)
            if role:
                send_telegram(fmt_role(role))
            else:
                send_telegram(f"🚨 New SWE Internship (id: {rid})")
    else:
        # Optional: small message so you know it ran + found nothing new
        # Comment this out if you don't want extra pings.
        send_telegram("✅ No new SWE listings this run.")

    # Save updated state
    save_state(current_ids)


if __name__ == "__main__":
    main()
