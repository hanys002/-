"""법령 보고서 HTML 본문 + PDF 첨부 발송. 비밀번호를 저장하거나 기록하지 않는다."""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, parseaddr
from pathlib import Path


class DeliveryError(RuntimeError):
    pass


def send_report(recipient: str, subject: str, html: str, pdf: Path,
                *, organization: str = "한영기술사사무소") -> None:
    user = os.environ.get("GMAIL_USER", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not user or not password:
        raise DeliveryError("GMAIL_USER / GMAIL_APP_PASSWORD 미설정: GitHub Actions 시크릿에 등록하세요")
    for address in (recipient, user):
        if any(c in address for c in "\r\n") or parseaddr(address)[1] != address or "@" not in address:
            raise DeliveryError("발신 또는 수신 이메일 주소가 유효하지 않습니다")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((organization, user))
    msg["To"] = recipient
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(f"{organization}\n{subject}\n\n정보통신 법령 모니터링 보고서를 첨부합니다.\n"
                    "조회 상태와 미확인 항목을 포함한 전체 내용은 첨부 PDF 또는 HTML 본문에서 확인하세요.")
    msg.add_alternative(html, subtype="html")
    msg.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename=pdf.name)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=40) as smtp:
            smtp.login(user, password)
            refused = smtp.send_message(msg)
            if refused:
                raise DeliveryError("수신자가 SMTP 서버에서 거부되었습니다")
    except (smtplib.SMTPException, OSError):
        raise DeliveryError("Gmail SMTP 발송 실패: 앱 비밀번호·SMTP 연결을 확인하세요. 중복 발송 방지를 위해 자동 재시도하지 않습니다") from None
