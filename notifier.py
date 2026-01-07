import json
import requests
import os
from pathlib import Path



RAW_URL = "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

STATE_FILE = Path("seen_swe_internships.json")


def send_telegram(message: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()


def fetch_readme_text() -> str:
    r = requests.get(RAW_URL, headers={"User-Agent": "internship-notifier/1.0"}, timeout=20)
    r.raise_for_status()
    return r.text


def is_swe_role(role: str) -> bool:
    r = role.lower()

    include_keywords = [
        "software", "swe", "software engineer",
        "backend", "front end", "frontend", "full stack", "full-stack",
        "mobile", "ios", "android", "web developer", "developer",
        "security", "cyber"
    ]

    exclude_keywords = [
        "data", "analytics", "business", "product",
        "pm", "program manager", "design", "ux", "ui",
        "marketing", "sales", "finance", "accounting", "hr",
        "devops", "site reliability", "sre", "qa", "test"
    ]

    if any(k in r for k in exclude_keywords):
        return False

    return any(k in r for k in include_keywords)


def extract_listing_rows(readme_text: str) -> list[str]:
    rows = []
    for line in readme_text.splitlines():
        line = line.strip()

        if not (line.startswith("|") and line.endswith("|")):
            continue

        stripped = line.replace("|", "").replace("-", "").replace(" ", "")
        if stripped == "":
            continue

        lower = line.lower()
        if "company" in lower and "role" in lower:
            continue

        rows.append(line)

    return rows


def row_to_columns(row: str) -> list[str]:
    return [p.strip() for p in row.strip("|").split("|")]


def format_row_message(row: str) -> str:
    parts = row_to_columns(row)

    company = parts[0] if len(parts) > 0 else "Unknown"
    role = parts[1] if len(parts) > 1 else "Unknown"
    location = parts[2] if len(parts) > 2 else "Unknown"
    link = parts[3] if len(parts) > 3 else ""

    msg = (
        "🚨 New SWE Internship\n"
        f"Company: {company}\n"
        f"Role: {role}\n"
        f"Location: {location}\n"
    )
    if link:
        msg += f"Link: {link}"
    return msg


def load_seen_ids() -> set[str]:
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text())
        return set(data.get("seen_ids", []))
    return set()


def save_seen_ids(seen_ids: set[str]) -> None:
    STATE_FILE.write_text(json.dumps({"seen_ids": sorted(seen_ids)}, indent=2))


def main():
    seen_ids = load_seen_ids()
    print("Loaded seen_ids:", len(seen_ids)) 

    readme = fetch_readme_text()
    rows = extract_listing_rows(readme)

    swe_rows = []
    for row in rows:
        cols = row_to_columns(row)
        if len(cols) < 2:
            continue
        if is_swe_role(cols[1]):
            swe_rows.append(row)

    current_ids = set(" ".join(r.split()) for r in swe_rows)

    if not seen_ids:
        save_seen_ids(current_ids)
        print("Baseline saved.")
        return

    new_ids = current_ids - seen_ids
    



    if new_ids:
        send_telegram(f"🚨 {len(new_ids)} new SWE internship listing(s) added!")
        for row in sorted(new_ids)[:5]:
            send_telegram(format_row_message(row))

        save_seen_ids(current_ids)


if __name__ == "__main__":
    main()
