"""Email sender — delivers daily briefing emails via SMTP."""
import os
import ssl
import smtplib
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


class EmailSender:
    """Sends the daily briefing email using stdlib SMTP."""

    def __init__(self, config: dict | None = None):
        config = config or {}
        self.enabled = config.get("enabled", True)
        self.template_dir = config.get("template_dir", "templates")
        self.template_env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=True,
        )

        self.smtp_host = os.environ.get("SMTP_HOST", "")
        self.smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_user = os.environ.get("SMTP_USER", "")
        self.smtp_password = os.environ.get("SMTP_PASSWORD", "")
        self.from_address = os.environ.get("SMTP_FROM", self.smtp_user)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send(self, briefing, recipient: str, page_url: str) -> bool:
        """Send email with link to today's briefing.

        Returns True on success, False on failure.
        """
        if not self.enabled:
            logger.warning("Email sending is disabled in config")
            return False

        if not self.smtp_host or not self.smtp_user:
            logger.warning("SMTP not configured — skipping email")
            return False

        template = self.template_env.get_template("email.html")
        html = template.render(
            briefing=briefing,
            page_url=page_url,
            date_formatted=self._format_date(briefing.date),
            headline=briefing.headline,
            preview=self._build_preview(briefing),
        )

        subject = "Daily news coverage ready"

        try:
            self._send_smtp(recipient, subject, html)
            logger.info("Email sent to %s", recipient)
            return True
        except Exception as exc:
            logger.error("Email send failed for %s: %s", recipient, exc)
            return False

    def send_failure_notice(self, recipient: str, run_url: str) -> bool:
        """Send a pipeline failure notification email."""
        if not self.smtp_host or not self.smtp_user:
            logger.warning("SMTP not configured — skipping failure notice")
            return False

        subject = "Instinct pipeline failed"
        html = (
            "<p>The Instinct daily pipeline failed.</p>"
            f'<p>Check the run: <a href="{run_url}">{run_url}</a></p>'
        )

        try:
            self._send_smtp(recipient, subject, html)
            logger.info("Failure notice sent to %s", recipient)
            return True
        except Exception as exc:
            logger.error("Failure notice failed for %s: %s", recipient, exc)
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _send_smtp(self, recipient: str, subject: str, html: str):
        """Send an email via SMTP with STARTTLS or SSL."""
        msg = MIMEMultipart("alternative")
        msg["From"] = self.from_address
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(html, "html"))

        context = ssl.create_default_context()

        if self.smtp_port == 465:
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context) as server:
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_address, [recipient], msg.as_string())
        else:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_address, [recipient], msg.as_string())

    @staticmethod
    def _format_date(date_str: str) -> str:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%A, %B %d, %Y")
        except ValueError:
            return date_str

    @staticmethod
    def _build_preview(briefing) -> str:
        """Extract 1-2 sentence preview from the opening brief."""
        opening = briefing.sections.get("opening_brief", "")
        if not opening:
            return briefing.headline or ""
        sentences = opening.replace("\n", " ").split(". ")
        preview = ". ".join(sentences[:2])
        if len(preview) > 200:
            preview = preview[:197] + "..."
        if not preview.endswith("."):
            preview += "."
        return preview
