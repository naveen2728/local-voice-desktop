"""Prepare and send compliant outreach batches.

Dry-run is the default. Sending requires SendGrid environment variables and
an explicit --send flag. The tool refuses rows without a lawful basis/consent
value and skips opt-outs.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import mimetypes
import os
import re
import smtplib
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from string import Template


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
DEFAULT_CSV = Path("outputs/hr_campaign/hr_outreach_cleaned_import.csv")
DEFAULT_SUPPRESSION = Path("outputs/hr_campaign/suppression_list.txt")
DEFAULT_LOG = Path("outputs/hr_campaign/send_log.csv")


@dataclass
class Contact:
    first_name: str
    company: str
    role: str
    email: str
    source: str
    lawful_basis_or_consent: str
    segment: str
    send_status: str
    opt_out: str
    notes: str


def load_suppression(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        line.strip().lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def load_contacts(path: Path) -> list[Contact]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "first_name",
            "company",
            "role",
            "email",
            "source",
            "lawful_basis_or_consent",
            "segment",
            "send_status",
            "opt_out",
            "notes",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"CSV is missing required columns: {', '.join(sorted(missing))}")
        return [Contact(**{key: (row.get(key) or "").strip() for key in required}) for row in reader]


def eligible_contacts(contacts: list[Contact], suppression: set[str]) -> tuple[list[Contact], dict[str, int]]:
    stats = {
        "total_rows": len(contacts),
        "invalid_email": 0,
        "suppressed_or_opted_out": 0,
        "missing_lawful_basis": 0,
        "eligible": 0,
    }
    eligible: list[Contact] = []
    seen: set[str] = set()
    for contact in contacts:
        email = contact.email.lower()
        if not EMAIL_RE.match(email):
            stats["invalid_email"] += 1
            continue
        if email in seen:
            continue
        seen.add(email)
        if email in suppression or contact.opt_out.lower() in {"yes", "y", "true", "1", "unsubscribe"}:
            stats["suppressed_or_opted_out"] += 1
            continue
        if not contact.lawful_basis_or_consent:
            stats["missing_lawful_basis"] += 1
            continue
        eligible.append(contact)
    stats["eligible"] = len(eligible)
    return eligible, stats


def render_text(template_text: str, contact: Contact, extra: dict[str, str]) -> str:
    values = {
        "first_name": contact.first_name or "there",
        "company": contact.company or "your team",
        "role": contact.role,
        "email": contact.email,
        "source": contact.source,
        "lawful_basis_or_consent": contact.lawful_basis_or_consent,
        "segment": contact.segment,
        **extra,
    }
    return Template(template_text).safe_substitute(values)


def send_sendgrid(api_key: str, payload: dict) -> tuple[int, str]:
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def send_smtp(
    host: str,
    port: int,
    username: str,
    password: str,
    use_ssl: bool,
    message: EmailMessage,
) -> tuple[int, str]:
    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_cls(host, port, timeout=30) as server:
        if not use_ssl:
            server.starttls()
        server.login(username, password)
        server.send_message(message)
    return 202, "accepted"


def build_attachment(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Attachment not found: {path}")
    data = path.read_bytes()
    if len(data) > 7 * 1024 * 1024:
        raise SystemExit("Attachment is larger than 7 MB. Use a smaller PDF resume.")
    mime_type, _ = mimetypes.guess_type(path.name)
    return {
        "content": base64.b64encode(data).decode("ascii"),
        "type": mime_type or "application/octet-stream",
        "filename": path.name,
        "disposition": "attachment",
    }


def append_log(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if not exists:
            writer.writerow(["timestamp", "email", "company", "status", "detail"])
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compliant outreach batch sender")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--suppression", type=Path, default=DEFAULT_SUPPRESSION)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--attachment", type=Path, help="Resume PDF/DOCX to attach")
    parser.add_argument("--provider", choices=["sendgrid", "smtp"], default="sendgrid")
    parser.add_argument("--continue-on-error", action="store_true", help="Log send errors and keep going")
    parser.add_argument("--description", default=os.environ.get("CUSTOM_DESCRIPTION", "my profile may be relevant for open roles"))
    parser.add_argument("--subject", default="Quick question about $company")
    parser.add_argument(
        "--body",
        default=(
            "Dear $first_name,\n\n"
            "I hope you are doing well. My name is $sender_name, and I am writing to express my "
            "interest in exploring suitable opportunities at $company.\n\n"
            "I am a fresher with a strong interest in learning, growing, and applying my skills in a "
            "practical, real-world environment. I am highly motivated, quick to learn, and comfortable "
            "adapting to new tools, technologies, and responsibilities based on the needs of the role.\n\n"
            "I would be grateful for an opportunity to contribute and grow under the guidance of "
            "experienced professionals. I am open to internships, trainee roles, or any suitable "
            "entry-level position where I can add value and learn continuously.\n\n"
            "I have attached my resume for your consideration. Thank you for your time and support.\n\n"
            "Warm regards,\n$sender_name\n\n"
            "If this is not relevant, no worries. Just let me know and I will not follow up."
        ),
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--skip", type=int, default=0, help="Skip this many eligible contacts before batching")
    parser.add_argument("--delay-seconds", type=float, default=2.0)
    parser.add_argument("--send", action="store_true", help="Actually send via SendGrid")
    parser.add_argument("--i-understand", action="store_true", help="Confirm this is lawful, non-spam outreach")
    args = parser.parse_args()

    if args.batch_size < 1 or args.batch_size > 100:
        raise SystemExit("--batch-size must be between 1 and 100")
    if args.skip < 0:
        raise SystemExit("--skip must be 0 or greater")

    contacts = load_contacts(args.csv)
    suppression = load_suppression(args.suppression)
    eligible, stats = eligible_contacts(contacts, suppression)
    batch = eligible[args.skip : args.skip + args.batch_size]

    print(json.dumps(stats, indent=2))
    if not batch:
        print("No eligible contacts. Fill lawful_basis_or_consent and check suppression/opt-out fields.")
        return 0

    env = {
        "sender_name": os.environ.get("SENDER_NAME", ""),
        "sender_company": os.environ.get("SENDER_COMPANY", ""),
        "relevant_context": os.environ.get("RELEVANT_CONTEXT", "your HR work appears relevant"),
        "specific_offer": os.environ.get("SPECIFIC_OFFER", "our product"),
        "description": args.description,
        "unsubscribe_url": os.environ.get("UNSUBSCRIBE_URL", ""),
        "physical_address": os.environ.get("PHYSICAL_ADDRESS", ""),
    }
    attachment = build_attachment(args.attachment) if args.attachment else None

    print("\nPreview:")
    preview = batch[0]
    print(f"To: {preview.email}")
    print(f"Subject: {render_text(args.subject, preview, env)}")
    print(render_text(args.body, preview, env))
    if attachment:
        print(f"Attachment: {attachment['filename']} ({attachment['type']})")

    if not args.send:
        print(f"\nDry run only. Eligible batch size: {len(batch)}. Add --send --i-understand to send.")
        return 0

    if not args.i_understand:
        raise SystemExit("Sending requires --i-understand.")

    required_env = ["FROM_EMAIL", "SENDER_NAME", "SENDER_COMPANY"]
    if args.provider == "sendgrid":
        required_env.append("SENDGRID_API_KEY")
    else:
        required_env.extend(["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD"])
    missing_env = [key for key in required_env if not os.environ.get(key)]
    if missing_env:
        raise SystemExit(f"Missing environment variables: {', '.join(missing_env)}")

    from_email = os.environ["FROM_EMAIL"]
    sendgrid_api_key = os.environ.get("SENDGRID_API_KEY", "")
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_username = os.environ.get("SMTP_USERNAME", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    smtp_ssl = os.environ.get("SMTP_SSL", "").lower() in {"1", "true", "yes"}
    for contact in batch:
        subject = render_text(args.subject, contact, env)
        body = render_text(args.body, contact, env)
        try:
            if args.provider == "sendgrid":
                payload = {
                    "personalizations": [{"to": [{"email": contact.email}], "subject": subject}],
                    "from": {"email": from_email, "name": env["sender_name"]},
                    "content": [{"type": "text/plain", "value": body}],
                }
                if attachment:
                    payload["attachments"] = [attachment]
                status, detail = send_sendgrid(sendgrid_api_key, payload)
            else:
                message = EmailMessage()
                message["From"] = f"{env['sender_name']} <{from_email}>"
                message["To"] = contact.email
                message["Subject"] = subject
                message.set_content(body)
                if args.attachment:
                    attachment_path = args.attachment
                    mime_type, _ = mimetypes.guess_type(attachment_path.name)
                    maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
                    message.add_attachment(
                        attachment_path.read_bytes(),
                        maintype=maintype,
                        subtype=subtype,
                        filename=attachment_path.name,
                    )
                status, detail = send_smtp(
                    smtp_host,
                    smtp_port,
                    smtp_username,
                    smtp_password,
                    smtp_ssl,
                    message,
                )
        except (OSError, smtplib.SMTPException) as exc:
            status = 0
            detail = f"{type(exc).__name__}: {exc}"
        outcome = "sent" if 200 <= status < 300 else f"failed:{status}"
        print(f"{contact.email}: {outcome}")
        append_log(args.log, [[time.strftime("%Y-%m-%d %H:%M:%S"), contact.email, contact.company, outcome, detail[:500]]])
        if status == 0 and not args.continue_on_error:
            print(f"Stopped after error: {detail}")
            print("Wait a while, then resume using --skip with the number of already-sent eligible contacts.")
            return 1
        time.sleep(args.delay_seconds)

    print(f"Logged {len(batch)} attempts to {args.log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
