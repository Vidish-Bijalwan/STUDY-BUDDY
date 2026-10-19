"""TEST-09: load and soak test scenario (Locust).

Simulates the roadmap's target mix:
  * ~50 concurrent users browsing public pages + public JSON APIs
  * ~10 concurrent users uploading resumes (authenticated)

NOT run here — see docs/testing/load.md for how to run the 30s smoke
config and the 10-minute soak on a staging instance.

Run:
    locust -f locustfile.py --host http://127.0.0.1:5000
Headless 30s smoke:
    locust -f locustfile.py --headless -u 5 -r 2 -t 30s \
        --host http://127.0.0.1:5000 --csv /tmp/locust-smoke
Full 10-minute soak (staging, production worker config):
    locust -f locustfile.py --headless -u 60 -r 5 -t 10m \
        --host https://staging.example.com --csv /tmp/locust-soak
"""
import io
import re
import uuid

from locust import HttpUser, between, task

# Tiny valid PDF (~1 page) used for the upload task — no fixture files.
_PDF_LINES = [
    b"Aarav Sharma",
    b"aarav.sharma@example.com | +91-9876543210",
    b"SKILLS",
    b"Python, Java, SQL, Machine Learning, Flask, Git",
]


def _minimal_pdf() -> bytes:
    content = b"BT /F1 12 Tf 72 740 Td 14 TL\n"
    for line in _PDF_LINES:
        content += b"(" + line + b") Tj T*\n"
    content += b"ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(pdf)
    pdf += b"xref\n0 %d\n" % (len(objects) + 1)
    pdf += b"0000000000 65535 f \n"
    for off in offsets:
        pdf += b"%010d 00000 n \n" % off
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (
        len(objects) + 1, xref)
    return pdf


_CSRF_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


def _csrf_token(html: str) -> str:
    m = _CSRF_RE.search(html)
    return m.group(1) if m else ""


class StudyBuddyUser(HttpUser):
    """One virtual user: registers once, then browses + uploads."""
    wait_time = between(1.0, 3.0)

    def on_start(self):
        # Register a fresh user (CSRF token scraped from the real form).
        email = f"load-{uuid.uuid4().hex[:10]}@example.com"
        page = self.client.get("/register")
        token = _csrf_token(page.text)
        self.client.post("/register", data={
            "csrf_token": token,
            "name": "Load Test",
            "email": email,
            "password": "<redacted>",
            "age_confirm": "1",
        }, name="/register")

    @task(10)
    def browse_home(self):
        self.client.get("/")

    @task(6)
    def browse_resume_page(self):
        self.client.get("/resume")

    @task(6)
    def public_apis(self):
        self.client.get("/api/companies", name="/api/companies")
        self.client.get("/api/topics", name="/api/topics")
        self.client.get("/api/dsa/problems", name="/api/dsa/problems")
        self.client.get("/api/star/examples", name="/api/star/examples")

    @task(4)
    def tracker_board(self):
        self.client.get("/tracker", name="/tracker")

    @task(2)
    def upload_resume_preview(self):
        # Authenticated upload path (parse only — no persistence).
        files = {"file": ("resume.pdf", io.BytesIO(_minimal_pdf()),
                          "application/pdf")}
        with self.client.post("/api/parse_preview", files=files,
                              catch_response=True,
                              name="/api/parse_preview") as resp:
            if resp.status_code == 429:
                resp.success()  # rate limit is expected behavior under load
            elif resp.status_code != 200:
                resp.failure(f"unexpected {resp.status_code}: "
                             f"{resp.text[:120]}")

    @task(1)
    def healthz(self):
        self.client.get("/healthz")
