import time
import json
import requests
import os

from pathlib import Path

RAW_URL = "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md"



BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


CHECK_EVERY_SECONDS = 900  # 15 minutes
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

        # Must look like a markdown table row
        if not (line.startswith("|") and line.endswith("|")):
            continue

        # Skip separator rows like: | --- | --- |
        stripped = line.replace("|", "").replace("-", "").replace(" ", "")
        if stripped == "":
            continue

        # Skip header rows (usually contain Company/Role)
        lower = line.lower()
        if "company" in lower and "role" in lower:
            continue

        rows.append(line)
    rows.append("| Microsoft | Software Engineer Intern https://www.microsoft.com |")
    return rows


def row_to_columns(row: str) -> list[str]:
    # Split by |, remove empty ends, trim whitespace
    return [p.strip() for p in row.strip("|").split("|")]


def format_row_message(row: str) -> str:
    parts = row_to_columns(row)

    # Most tables are: Company | Role | Location | Link | ...
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
    send_telegram("A cloud-run bot that monitors GitHub internship listings, filters for new software engineering roles, and sends real-time notifications when opportunities are added.\nBuilt by: Harry Ducu");


    seen_ids = load_seen_ids()

    while True:
        try:
            readme = fetch_readme_text()
            rows = extract_listing_rows(readme)

            # Filter rows down to SWE-ish roles
            swe_rows = []
            for row in rows:
                cols = row_to_columns(row)
                if len(cols) < 2:
                    continue
                role = cols[1]
                if is_swe_role(role):
                    swe_rows.append(row)

            # Normalize row whitespace to create stable IDs
            current_ids = set(" ".join(r.split()) for r in swe_rows)

            if not seen_ids:
                # Baseline: don't alert on first run
                save_seen_ids(current_ids)
                seen_ids = current_ids
                print("Baseline saved (SWE only). Watching for NEW SWE internships...")
            else:
                new_ids = current_ids - seen_ids

                if new_ids:
                    print(f"Found {len(new_ids)} new SWE internship(s). Sending alerts...")
                    send_telegram(f"🚨 {len(new_ids)} new SWE internship listing(s) added!")

                    # Send details (cap to avoid spam)
                    max_to_send = 5
                    for i, row_id in enumerate(sorted(new_ids)):
                        if i >= max_to_send:
                            send_telegram(f"(Showing first {max_to_send}. Check README for more.)")
                            break
                        send_telegram(format_row_message(row_id))

                    # Update state
                    seen_ids = current_ids
                    save_seen_ids(seen_ids)
                else:
                    print("No new SWE internships.")

        except Exception as e:
            print("Error:", e)

        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
