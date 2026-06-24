from __future__ import annotations

import csv
import json
import mimetypes
import smtplib
import threading
import time
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template
from urllib.parse import urlparse

from compliant_email_tool import (
    DEFAULT_CSV,
    DEFAULT_LOG,
    DEFAULT_SUPPRESSION,
    append_log,
    eligible_contacts,
    load_contacts,
    load_suppression,
    render_text,
    send_smtp,
)


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "email_web"
DEFAULT_RESUME = ROOT / "resume.pdf"
DEFAULT_BODY = (
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
)


state_lock = threading.Lock()
stop_event = threading.Event()
job_state = {
    "running": False,
    "sent": 0,
    "failed": 0,
    "total": 0,
    "current": "",
    "events": [],
}


def resolve_path(value: str | None, default: Path) -> Path:
    if not value:
        return default if default.is_absolute() else ROOT / default
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def json_response(handler: BaseHTTPRequestHandler, data: dict, status: int = 200) -> None:
    body = json.dumps(data, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def get_batch(payload: dict) -> tuple[list, dict]:
    csv_path = resolve_path(payload.get("csvPath"), DEFAULT_CSV)
    suppression_path = resolve_path(payload.get("suppressionPath"), DEFAULT_SUPPRESSION)
    contacts = load_contacts(csv_path)
    suppression = load_suppression(suppression_path)
    eligible, stats = eligible_contacts(contacts, suppression)
    skip = max(0, int(payload.get("skip", 0)))
    batch_size = min(50, max(1, int(payload.get("batchSize", 10))))
    return eligible[skip : skip + batch_size], stats


def env_from_payload(payload: dict) -> dict[str, str]:
    return {
        "sender_name": payload.get("senderName", "").strip(),
        "sender_company": payload.get("senderCompany", "").strip(),
        "relevant_context": "",
        "specific_offer": "",
        "description": "",
        "unsubscribe_url": "",
        "physical_address": "",
    }


def update_event(email: str, outcome: str, detail: str = "") -> None:
    with state_lock:
        if outcome == "sent":
            job_state["sent"] += 1
        else:
            job_state["failed"] += 1
        job_state["current"] = email
        job_state["events"].append(
            {
                "time": time.strftime("%H:%M:%S"),
                "email": email,
                "outcome": outcome,
                "detail": detail[:180],
            }
        )
        job_state["events"] = job_state["events"][-200:]


def send_job(payload: dict) -> None:
    batch, _ = get_batch(payload)
    env = env_from_payload(payload)
    from_email = payload.get("fromEmail", "").strip()
    smtp_host = payload.get("smtpHost", "smtp.gmail.com").strip()
    smtp_port = int(payload.get("smtpPort", 587))
    smtp_username = payload.get("smtpUsername", "").strip()
    smtp_password = payload.get("smtpPassword", "")
    delay = max(10, float(payload.get("delaySeconds", 90)))
    resume_path = resolve_path(payload.get("attachmentPath"), DEFAULT_RESUME)
    log_path = resolve_path(payload.get("logPath"), DEFAULT_LOG)
    subject_template = payload.get("subject", "Quick question about $company")
    body_template = payload.get("body", DEFAULT_BODY)

    try:
        for contact in batch:
            if stop_event.is_set():
                break
            subject = render_text(subject_template, contact, env)
            body = render_text(body_template, contact, env)
            message = EmailMessage()
            message["From"] = f"{env['sender_name']} <{from_email}>"
            message["To"] = contact.email
            message["Subject"] = subject
            message.set_content(body)
            if resume_path.exists():
                mime_type, _ = mimetypes.guess_type(resume_path.name)
                maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
                message.add_attachment(
                    resume_path.read_bytes(),
                    maintype=maintype,
                    subtype=subtype,
                    filename=resume_path.name,
                )
            try:
                status, detail = send_smtp(
                    smtp_host,
                    smtp_port,
                    smtp_username,
                    smtp_password,
                    False,
                    message,
                )
                outcome = "sent" if 200 <= status < 300 else f"failed:{status}"
            except (OSError, smtplib.SMTPException) as exc:
                outcome = "failed"
                detail = f"{type(exc).__name__}: {exc}"
            append_log(log_path, [[time.strftime("%Y-%m-%d %H:%M:%S"), contact.email, contact.company, outcome, detail[:500]]])
            update_event(contact.email, outcome, detail)
            if outcome != "sent":
                break
            time.sleep(delay)
    finally:
        with state_lock:
            job_state["running"] = False
            job_state["current"] = ""
        payload["smtpPassword"] = ""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            path = STATIC_DIR / "index.html"
        elif parsed.path == "/api/status":
            with state_lock:
                json_response(self, dict(job_state))
            return
        else:
            path = STATIC_DIR / parsed.path.lstrip("/")

        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        content = path.read_bytes()
        content_type = "text/html; charset=utf-8" if path.suffix == ".html" else "text/css; charset=utf-8"
        if path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        try:
            payload = read_json(self)
            if self.path == "/api/preview":
                batch, stats = get_batch(payload)
                if not batch:
                    json_response(self, {"ok": False, "stats": stats, "message": "No eligible contacts in this batch."}, 400)
                    return
                env = env_from_payload(payload)
                contact = batch[0]
                json_response(
                    self,
                    {
                        "ok": True,
                        "stats": stats,
                        "batchSize": len(batch),
                        "first": {
                            "email": contact.email,
                            "company": contact.company,
                            "subject": render_text(payload.get("subject", "Quick question about $company"), contact, env),
                            "body": render_text(payload.get("body", DEFAULT_BODY), contact, env),
                        },
                    },
                )
                return

            if self.path == "/api/mark-range":
                csv_path = resolve_path(payload.get("csvPath"), DEFAULT_CSV)
                start = int(payload.get("startRow", 1))
                end = int(payload.get("endRow", 1))
                if start < 1 or end < start or end - start + 1 > 100:
                    json_response(self, {"ok": False, "message": "Use a valid 1-based row range up to 100 rows."}, 400)
                    return
                rows = []
                with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle)
                    fieldnames = reader.fieldnames or []
                    rows = list(reader)
                if "lawful_basis_or_consent" not in fieldnames:
                    json_response(self, {"ok": False, "message": "CSV is missing lawful_basis_or_consent."}, 400)
                    return
                note = f"User confirmed contacts {start} to {end} are okay to email for job opportunity outreach"
                for index in range(start - 1, min(end, len(rows))):
                    rows[index]["lawful_basis_or_consent"] = note
                with csv_path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                json_response(self, {"ok": True, "message": f"Marked contacts {start}-{end}."})
                return

            if self.path == "/api/send":
                required = ["fromEmail", "senderName", "smtpHost", "smtpPort", "smtpUsername", "smtpPassword"]
                missing = [key for key in required if not str(payload.get(key, "")).strip()]
                if missing:
                    json_response(self, {"ok": False, "message": f"Missing: {', '.join(missing)}"}, 400)
                    return
                batch, _ = get_batch(payload)
                if not batch:
                    json_response(self, {"ok": False, "message": "No eligible contacts in this batch."}, 400)
                    return
                with state_lock:
                    if job_state["running"]:
                        json_response(self, {"ok": False, "message": "A send job is already running."}, 409)
                        return
                    stop_event.clear()
                    job_state.update({"running": True, "sent": 0, "failed": 0, "total": len(batch), "current": "", "events": []})
                threading.Thread(target=send_job, args=(payload,), daemon=True).start()
                json_response(self, {"ok": True, "message": "Send started.", "total": len(batch)})
                return

            if self.path == "/api/stop":
                stop_event.set()
                json_response(self, {"ok": True, "message": "Stop requested."})
                return

            json_response(self, {"ok": False, "message": "Unknown endpoint."}, 404)
        except Exception as exc:
            json_response(self, {"ok": False, "message": f"{type(exc).__name__}: {exc}"}, 500)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("Email web tool running at http://127.0.0.1:8765")
    server.serve_forever()


if __name__ == "__main__":
    main()
