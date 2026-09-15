"""Gmail SMTP 발송. 앱 비밀번호(2단계 인증 필수)를 사용한다."""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate

log = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # implicit TLS


class MailConfigError(RuntimeError):
    pass


def send(subject: str, html_body: str, text_body: str) -> None:
    user = os.environ.get("GMAIL_USER", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    to_addr = os.environ.get("MAIL_TO", "").strip() or user

    if not user or not password:
        raise MailConfigError(
            "GMAIL_USER / GMAIL_APP_PASSWORD 시크릿이 설정되지 않았습니다. "
            "README의 '설정' 절을 참고하세요."
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("기술사 채용 브리핑", user))
    msg["To"] = to_addr
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=40) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    log.info("메일 발송 완료 → %s", to_addr)
