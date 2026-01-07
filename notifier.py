import json
import os
from pathlib import Path

import requests

# This repo's README is NOT a pipe table anymore.
# We parse the "## Software Engineering Internship Roles" section.
RAW_URL = "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

STATE_FILE = Path("seen_swe_internships.json")


def send_telegram(message: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message, "disable_web_page_preview": True}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()


def fetch_readme_text() -> str:
    r = requests.get(RAW_URL, headers={"User-Agent": "internship-notifier/1.0"}, timeout=20)
    r.raise_for_status()
    return r.text


def extract_swe_section_lines(readme_text: str) -> list[str]:
    """
    Extract listing lines from:
      ## Software Engineering Internship Roles
    until the next ## header.

    The lines in this section are markdown-ish, often like:
      [Company](link) | Role | Location | ...
    or sometimes continuation lines starting with "↳".
    """
    lines = readme_text.splitlines()

    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("## Software Engineering Internship Roles"):
            start = i + 1
            break

    if start is None:
        return []

    end = len(lines)
    for j in range(start, len(lines)):
        s = lines[j].strip()
        if s.startswith("## "):
            end = j
            break

    section = lines[start:end]

    rows: list[str] = []
    for line in section:
        s = line.strip()
        if not s:
            continue

        # Skip the section header row if present
        if s.lower().startswith("company role location"):
            continue

        # Most real listings start with a markdown link or a continuation arrow
        if s.startswith("[") or s.startswith("↳"):
            rows.append(s)

    return rows


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


def format_row_message(line: str) -> str:
    # Keep it simple: send the raw line (it usually includes company + role + location)
    # Telegram will show it nicely; disable_web_page_preview is enabled.
    return f"🚨 New SWE Internship\n{line}"


def main() -> None:
    seen_ids = load_seen_ids()
    print("Loaded seen_ids:", len(seen_ids))

    readme = fetch_readme_text()
    swe_lines = extract_swe_section_lines(readme)

    # Normalize whitespace so minor spacing changes don't cause false positives
    current_ids = set(" ".join(line.split()) for line in swe_lines)

    print("SWE section lines:", len(swe_lines))
    print("Current SWE ids:", len(current_ids))

    # First run: save baseline only
    if not seen_ids:
        save_seen_ids(current_ids)
        print("Baseline saved.")
        return

    new_ids = current_ids - seen_ids

    if new_ids:
        send_telegram(f"🚨 {len(new_ids)} new SWE internship listing(s) added!")
        for line in list(sorted(new_ids))[:5]:
            send_telegram(format_row_message(line))
    else:
        print("No new listings.")

    # Always update state to latest
    save_seen_ids(current_ids)


if __name__ == "__main__":
    main()
