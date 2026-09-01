"""네이버 메일(SMTP)로 채용정보 알림 메일을 전송한다."""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

import config
from scrapers.base import JobPosting

SMTP_HOST = "smtp.naver.com"
SMTP_PORT = 587


def _build_body(postings: list[JobPosting]) -> str:
    lines = []
    for i, p in enumerate(postings, 1):
        lines.append(f"{i}. [{p.source}] {p.title}")
        if p.company:
            lines.append(f"   회사: {p.company}")
        lines.append(f"   링크: {p.link}")
        lines.append("")
    return "\n".join(lines)


def send_job_digest(postings: list[JobPosting]) -> None:
    """새로 발견된 채용공고 목록을 담은 메일 1통을 전송한다."""
    if not postings:
        return
    if not config.NAVER_EMAIL or not config.NAVER_APP_PASSWORD:
        raise RuntimeError(
            ".env 에 NAVER_EMAIL / NAVER_APP_PASSWORD 가 설정되어 있지 않습니다."
        )

    msg = MIMEMultipart()
    msg["From"] = config.NAVER_EMAIL
    msg["To"] = config.MAIL_TO
    msg["Subject"] = f"[기술사 채용정보] 새 공고 {len(postings)}건"
    msg["Date"] = formatdate(localtime=True)
    msg.attach(MIMEText(_build_body(postings), "plain", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
        server.starttls()
        server.login(config.NAVER_EMAIL, config.NAVER_APP_PASSWORD)
        server.sendmail(config.NAVER_EMAIL, [config.MAIL_TO], msg.as_string())
