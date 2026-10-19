from __future__ import annotations

import json
import os
import smtplib
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

import requests
import yaml

from src.law_monitor.__main__ import FixtureClient, main
from src.law_monitor.api import Detail, LawAPIError, LawClient, Version, parse_detail
from src.law_monitor.delivery import DeliveryError, send_report
from src.law_monitor.pipeline import collect, compare
from src.law_monitor.report import ReportValidationError, excerpt, render, write_pdf

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / 'tests/fixtures/law'
TODAY = date(2026, 10, 19)
CONFIG = yaml.safe_load((FIXTURE / 'config.yaml').read_text())


def law_row(serial='123', title='정보통신공사업법', effective='20261022'):
    return f'''<law><법령일련번호>{serial}</법령일련번호><법령ID>001</법령ID>
    <법령명한글>{title}</법령명한글><공포일자>20261015</공포일자>
    <시행일자>{effective}</시행일자><공포번호>12345</공포번호>
    <법령구분명>법률</법령구분명><제개정구분명>일부개정</제개정구분명></law>'''


def listing(rows, total=None):
    return ET.fromstring(f'<LawSearch><totalCnt>{len(rows) if total is None else total}</totalCnt>{"".join(rows)}</LawSearch>')


class APIAndPipelineTests(unittest.TestCase):
    def test_missing_oc_is_explicit(self):
        with self.assertRaisesRegex(LawAPIError, 'LAW_API_OC'):
            LawClient('')

    def test_pagination_exact_name_and_dedupe(self):
        client = LawClient('test', delay=0)
        client.xml = MagicMock(side_effect=[
            listing([law_row('1'), law_row('2', '정보통신공사업법 시행령')], 3),
            listing([law_row('3')], 3), listing([law_row('1')]), listing([law_row('1')])])
        rows = client.versions('정보통신공사업법')
        self.assertEqual({r.serial for r in rows}, {'1', '3'})
        self.assertEqual(client.xml.call_args_list[1].kwargs['page'], 2)

    def test_repeated_page_fails_instead_of_truncating(self):
        client = LawClient('test', delay=0)
        client.xml = MagicMock(return_value=listing([law_row()], 200))
        with self.assertRaisesRegex(LawAPIError, '반복'):
            client.versions('정보통신공사업법')

    def test_empty_search_is_not_no_changes(self):
        client = LawClient('test', delay=0)
        client.xml = MagicMock(return_value=listing([]))
        with self.assertRaisesRegex(LawAPIError, '정확히'):
            client.versions('정보통신공사업법')

    def test_bad_dates_fail(self):
        client = LawClient('test', delay=0)
        client.xml = MagicMock(return_value=listing([law_row(effective='20261340')]))
        with self.assertRaises(LawAPIError):
            client.versions('정보통신공사업법')

    def test_api_error_is_not_zero_results(self):
        client = LawClient('test', delay=0)
        client.xml = MagicMock(return_value=ET.fromstring('<error>unauthorized</error>'))
        with self.assertRaises(LawAPIError):
            client.versions('정보통신공사업법')

    @patch('src.law_monitor.api.time.sleep')
    def test_connection_error_does_not_leak_oc(self, _):
        session = MagicMock()
        session.get.side_effect = requests.ConnectionError('URL?OC=private-value')
        with self.assertRaises(LawAPIError) as caught:
            LawClient('private-value', session=session, delay=0).xml('lawSearch.do')
        self.assertNotIn('private-value', str(caught.exception))
        self.assertEqual(session.get.call_count, 3)

    def test_html_and_entity_responses_rejected(self):
        for content in (b'<html>Login</html>', b'<!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>'):
            session = MagicMock()
            session.get.return_value.status_code = 200
            session.get.return_value.content = content
            client = LawClient('test', session=session, delay=0)
            with self.assertRaises(LawAPIError):
                client.versions('정보통신공사업법')

    def test_detail_keeps_paragraphs_and_all_articles(self):
        root = ET.fromstring('''<법령><기본정보/><조문><조문단위><조문번호>24</조문번호>
          <조문가지번호>2</조문가지번호><조문여부>조문</조문여부><조문내용>제24조의2</조문내용>
          <항><항내용>① 본문</항내용><호><호내용>1. 하위 항목</호내용></호></항></조문단위></조문>
          <제개정이유><제개정이유내용>공식 이유</제개정이유내용></제개정이유>
          <개정문><개정문내용>개정 원문</개정문내용></개정문>
          <부칙><부칙단위><부칙내용>적용례</부칙내용></부칙단위></부칙></법령>''')
        detail = parse_detail(root)
        self.assertIn('1. 하위 항목', detail.articles['제24조의2'])
        self.assertEqual(detail.reason, '공식 이유')
        self.assertEqual(detail.supplements, '적용례')
        old = Detail(articles={f'제{i}조': '이전' for i in range(1, 63)})
        new = Detail(articles={f'제{i}조': '이후' for i in range(1, 63)})
        self.assertEqual(len(compare(old, new)), 62)

    def test_weekly_upcoming_and_core_diff(self):
        report = collect(FixtureClient(FIXTURE / 'example.json'), CONFIG, TODAY)
        self.assertFalse(report.incomplete)
        self.assertEqual(report.start, date(2026, 10, 12))
        self.assertEqual(report.end, date(2026, 10, 18))
        self.assertEqual(len(report.weekly), 1)
        self.assertEqual(len(report.upcoming), 1)
        changes = report.analyses[0].changes
        self.assertEqual(len(changes), 2)
        self.assertEqual(changes[1]['before'], '<신설>')

    def test_current_baseline_does_not_require_older_version(self):
        client = FixtureClient(FIXTURE / 'example.json')
        versions = client.versions('정보통신공사업법')
        client.versions = MagicMock(return_value=[replace(versions[0], amendment='일부개정'), versions[1]])
        report = collect(client, CONFIG, TODAY)
        self.assertFalse(report.incomplete)
        self.assertTrue(any('현행 기준본' in item.comparison_note for item in report.analyses))
        self.assertEqual(len(report.analyses[0].changes), 2)

    def test_calendar_six_month_boundary_and_today(self):
        sample = FixtureClient(FIXTURE / 'example.json').versions('정보통신공사업법')[0]
        client = MagicMock()
        client.versions.return_value = [replace(sample, serial=str(i), effective=d) for i, d in enumerate([
            TODAY, date(2026, 11, 18), date(2027, 4, 19), date(2027, 4, 20)])]
        client.detail.return_value = Detail(reason='내용')
        report = collect(client, {**CONFIG, 'core_laws': []}, TODAY)
        self.assertEqual(len(report.upcoming), 3)
        self.assertIn('D-day', render(report))
        self.assertIn('30일 내 시행 2개', render(report))

    def test_future_announcements_not_asserted_as_known(self):
        sample = FixtureClient(FIXTURE / 'example.json').versions('정보통신공사업법')[0]
        client = MagicMock()
        client.versions.return_value = [replace(sample, announced=date(2026, 10, 20))]
        report = collect(client, CONFIG, TODAY)
        self.assertTrue(report.incomplete)
        self.assertEqual(report.weekly, [])

    def test_partial_and_total_failure_visible(self):
        client = MagicMock()
        client.versions.side_effect = LawAPIError('접근 차단')
        report = collect(client, CONFIG, TODAY)
        self.assertEqual(report.failures, 1)
        self.assertTrue(report.incomplete)
        self.assertIn('변경 없음으로 판단하지', render(report))

    def test_detail_failure_preserves_listing_but_marks_incomplete(self):
        client = FixtureClient(FIXTURE / 'example.json')
        client.detail = MagicMock(side_effect=LawAPIError('본문 조회 실패'))
        report = collect(client, CONFIG, TODAY)
        self.assertEqual(len(report.upcoming), 1)
        self.assertTrue(report.incomplete)
        self.assertIn('본문 조회 실패', render(report))

    def test_html_escapes_remote_content(self):
        report = collect(FixtureClient(FIXTURE / 'example.json'), CONFIG, TODAY)
        report.analyses[0].detail.reason = '<script>alert(1)</script>'
        self.assertNotIn('<script>', render(report))
        self.assertIn('&lt;script&gt;', render(report))

    def test_long_originals_become_bounded_summary_and_links(self):
        report = collect(FixtureClient(FIXTURE / 'example.json'), CONFIG, TODAY)
        item = report.analyses[0]
        item.detail.reason = '◇ 주요내용\n교육 기준을 정비함. ' + '공식 설명 추가 문장. ' * 10000
        item.detail.supplements = 'SUPPLEMENT_FULL_TEXT ' * 10000
        item.detail.amendment_text = 'AMENDMENT_FULL_TEXT ' * 10000
        item.changes = [{'article': f'제{i}조', 'before': 'OLD_FULL_TEXT ' * 1000,
                         'after': 'NEW_FULL_TEXT ' * 1000} for i in range(1, 63)]
        html = render(report)
        self.assertLess(len(html), 15000)
        self.assertIn('교육 기준을 정비함.', html)
        self.assertIn('일부 발췌', html)
        self.assertIn('변경 조문 62개', html)
        self.assertIn('외 54개', html)
        self.assertIn(item.version.url, html)
        self.assertNotIn('SUPPLEMENT_FULL_TEXT', html)
        self.assertNotIn('OLD_FULL_TEXT', html)
        self.assertEqual(len(report.as_dict()['analyses'][0]['changes']), 62)

    def test_excerpt_prefers_official_main_content(self):
        result = excerpt('◇ 개정이유\n배경 설명\n◇ 주요내용\n가. 교육 기준을 정비함. 나. 기록 보관을 명확히 함.')
        self.assertIn('교육 기준', result)
        self.assertNotIn('배경 설명', result)
        combined = excerpt('[일부개정]\n◇ 개정이유 및 주요내용\n감리관리시스템 근거를 마련함.')
        self.assertEqual(combined, '감리관리시스템 근거를 마련함.')

    def test_failed_baseline_does_not_claim_zero_changed_articles(self):
        client = FixtureClient(FIXTURE / 'example.json')
        original = client.detail
        def detail(version):
            if version.serial == '900001':
                raise LawAPIError('이전 조문 조회 실패')
            return original(version)
        client.detail = detail
        report = collect(client, CONFIG, TODAY)
        self.assertIsNone(report.analyses[0].previous)
        self.assertNotIn('변경 조문 0개', render(report))


class DeliveryAndCLITests(unittest.TestCase):
    def test_pdf_over_ten_pages_is_rejected(self):
        html = '<html><body>' + '<p style="page-break-after:always">page</p>' * 11 + '</body></html>'
        with tempfile.TemporaryDirectory() as folder:
            pdf = Path(folder) / 'too-long.pdf'
            with self.assertRaisesRegex(ReportValidationError, '최대 10페이지'):
                write_pdf(html, pdf)
            self.assertFalse(pdf.exists())
    @patch.dict(os.environ, {'GMAIL_USER': 'sender@example.com', 'GMAIL_APP_PASSWORD': 'test-password'})
    @patch('src.law_monitor.delivery.smtplib.SMTP_SSL')
    def test_mail_recipient_html_and_pdf(self, smtp):
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        with tempfile.TemporaryDirectory() as folder:
            pdf = Path(folder) / '법령보고.pdf'
            pdf.write_bytes(b'%PDF-test')
            send_report('hanys002@gmail.com', '주간 보고서', '<p>정보통신</p>', pdf)
        msg = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
        self.assertEqual(msg['To'], 'hanys002@gmail.com')
        self.assertIn('정보통신', msg.get_body(preferencelist=('html',)).get_content())
        attachment = next(msg.iter_attachments())
        self.assertEqual(attachment.get_content_type(), 'application/pdf')
        self.assertEqual(attachment.get_filename(), '법령보고.pdf')
        self.assertEqual(attachment.get_payload(decode=True), b'%PDF-test')

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_smtp_credentials(self):
        with self.assertRaises(DeliveryError):
            send_report('hanys002@gmail.com', '제목', '본문', Path('absent.pdf'))

    @patch.dict(os.environ, {'GMAIL_USER': 'sender@example.com', 'GMAIL_APP_PASSWORD': 'private-value'})
    @patch('src.law_monitor.delivery.smtplib.SMTP_SSL')
    def test_smtp_error_sanitized_and_not_retried(self, smtp):
        smtp.return_value.__enter__.return_value.login.side_effect = smtplib.SMTPAuthenticationError(535, b'private-value')
        with tempfile.TemporaryDirectory() as folder:
            pdf = Path(folder) / 'report.pdf'
            pdf.write_bytes(b'%PDF-test')
            with self.assertRaises(DeliveryError) as caught:
                send_report('hanys002@gmail.com', 'report', 'body', pdf)
        self.assertNotIn('private-value', str(caught.exception))
        self.assertEqual(smtp.call_count, 1)

    def test_fixture_send_forbidden(self):
        with self.assertRaises(SystemExit) as caught:
            main(['--send', '--fixture', str(FIXTURE / 'example.json')])
        self.assertEqual(caught.exception.code, 2)

    @patch.dict(os.environ, {}, clear=True)
    def test_cli_missing_oc_fails(self):
        self.assertEqual(main(['--dry-run']), 2)

    @patch('src.law_monitor.__main__.send_report')
    def test_end_to_end_fixture_creates_pdf_and_json_without_sending(self, send):
        with tempfile.TemporaryDirectory() as folder:
            code = main(['--config', str(FIXTURE / 'config.yaml'), '--fixture', str(FIXTURE / 'example.json'),
                         '--date', TODAY.isoformat(), '--output', folder])
            self.assertEqual(code, 0)
            pdf = next(Path(folder).glob('*.pdf'))
            self.assertTrue(pdf.read_bytes().startswith(b'%PDF-'))
            self.assertGreater(pdf.stat().st_size, 5000)
            from pypdf import PdfReader
            reader = PdfReader(pdf)
            self.assertLessEqual(len(reader.pages), 10)
            self.assertIn('한영기술사사무소', ''.join(page.extract_text() for page in reader.pages))
            self.assertTrue(any(page.get('/Annots') for page in reader.pages))
            data = json.loads(next(Path(folder).glob('*.json')).read_text())
            self.assertTrue(data['demo'])
            self.assertEqual(len(data['upcoming']), 1)
            self.assertIn('실제 조회 아님', next(Path(folder).glob('*.html')).read_text())
        send.assert_not_called()

    @patch('src.law_monitor.__main__.write_pdf')
    @patch('src.law_monitor.__main__.send_report')
    @patch('src.law_monitor.__main__.LawClient')
    def test_all_sources_failed_never_sends(self, client, send, pdf):
        client.return_value.versions.side_effect = LawAPIError('네트워크 차단')
        with tempfile.TemporaryDirectory() as folder:
            code = main(['--send', '--config', str(FIXTURE / 'config.yaml'), '--output', folder])
        self.assertEqual(code, 2)
        send.assert_not_called()

    @patch('src.law_monitor.__main__.write_pdf')
    @patch('src.law_monitor.__main__.send_report')
    @patch('src.law_monitor.__main__.LawClient')
    def test_partial_detail_failure_blocks_sending_and_exits_one(self, client, send, pdf):
        source = FixtureClient(FIXTURE / 'example.json')
        source.detail = MagicMock(side_effect=LawAPIError('상세 미확인'))
        client.return_value = source
        with tempfile.TemporaryDirectory() as folder:
            code = main(['--send', '--date', TODAY.isoformat(), '--config', str(FIXTURE / 'config.yaml'), '--output', folder])
        self.assertEqual(code, 1)
        send.assert_not_called()

    @patch('src.law_monitor.__main__.write_pdf', side_effect=RuntimeError('PDF failed'))
    @patch('src.law_monitor.__main__.send_report')
    @patch('src.law_monitor.__main__.LawClient')
    def test_pdf_failure_never_sends(self, client, send, pdf):
        client.return_value = FixtureClient(FIXTURE / 'example.json')
        with tempfile.TemporaryDirectory() as folder:
            code = main(['--send', '--date', TODAY.isoformat(), '--config', str(FIXTURE / 'config.yaml'), '--output', folder])
        self.assertEqual(code, 2)
        send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
