from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from .api import Detail, LawAPIError, Version


@dataclass
class Analysis:
    version: Version
    detail: Detail | None = None
    previous: Version | None = None
    changes: list[dict[str, str]] = field(default_factory=list)
    error: str = ""
    comparison_note: str = ""


@dataclass
class Report:
    today: date
    start: date
    end: date
    horizon: date
    statuses: dict[str, str]
    weekly: list[Version]
    upcoming: list[Version]
    analyses: list[Analysis]
    manual_checks: list[str]
    title: str
    organization: str = "한영기술사사무소"
    demo: bool = False
    core_laws: list[str] = field(default_factory=list)
    volume: int = 2

    @property
    def failures(self) -> int:
        return sum(value != "확인 완료" for value in self.statuses.values())

    @property
    def incomplete(self) -> bool:
        return bool(self.failures or any(item.error for item in self.analyses))

    def as_dict(self) -> dict:
        return asdict(self)


def compare(old: Detail, new: Detail) -> list[dict[str, str]]:
    # 조문 키 기준으로 전체 조문을 비교한다. 항 이동은 원문 그대로 보여 준다.
    return [{"article": key, "before": old.articles.get(key, "<신설>"),
             "after": new.articles.get(key, "<삭제>")}
            for key in dict.fromkeys([*old.articles, *new.articles])
            if old.articles.get(key) != new.articles.get(key)]


def collect(client, config: dict, today: date) -> Report:
    start = today - timedelta(days=int(config.get("lookback_days", 7)))
    end = today - timedelta(days=1)
    horizon = today + relativedelta(months=int(config.get("future_months", 6)))
    statuses, weekly, upcoming, analyses = {}, [], [], []
    for name in config["laws"]:
        try:
            versions = client.versions(name)
        except LawAPIError as exc:
            statuses[name] = str(exc)
            continue
        statuses[name] = "확인 완료"
        # 보고일 이후 공포되는 데이터는 해당 보고서에서 확정 사실로 사용하지 않는다.
        versions = [v for v in versions if v.announced and v.announced <= today]
        if not versions:
            statuses[name] = "보고일 기준으로 확인할 수 있는 공포 버전 없음"
            continue
        recent = [v for v in versions if
                  (v.announced and start <= v.announced <= end) or
                  (v.effective and start <= v.effective <= end)]
        future = [v for v in versions if v.effective and today <= v.effective <= horizon]
        weekly.extend(recent)
        upcoming.extend(future)
        selected = {v.serial: v for v in recent + future}
        change_targets = set(selected)
        if name in config.get("core_laws", []):
            current = [v for v in versions if v.effective and v.effective <= today]
            if current:
                latest = max(current, key=lambda v: (v.effective, v.announced, v.serial))
                selected[latest.serial] = latest
        for version in selected.values():
            analysis = Analysis(version)
            try:
                analysis.detail = client.detail(version)
                if not (analysis.detail.reason or analysis.detail.amendment_text):
                    analysis.error = "개정이유·개정문 미제공: 주요 개정 내용은 원문 확인 필요"
                if name in config.get("core_laws", []) and version.serial not in change_targets:
                    analysis.comparison_note = "현행 기준본: 이번 점검 기간의 공포·시행 또는 시행 예정 대상이 아니므로 이전 버전 대비 대상에서 제외"
                elif name in config.get("core_laws", []):
                    previous = [v for v in versions if v.serial != version.serial and
                                v.effective and version.effective and v.effective < version.effective
                                and v.announced <= version.announced]
                    if previous:
                        baseline = max(previous, key=lambda v: (v.effective, v.announced, v.serial))
                        old = client.detail(baseline)
                        if not old.articles or not analysis.detail.articles:
                            raise LawAPIError("조문 본문 누락: 신·구조문 비교 불가")
                        analysis.changes = compare(old, analysis.detail)
                        analysis.previous = baseline
                    elif version.amendment != "제정":
                        analysis.comparison_note = "API에서 비교할 이전 시행 버전을 확인하지 못했습니다. 현재 개정의 공식 요약·본문·부칙은 법령 원문 링크에서 확인하세요."
            except LawAPIError as exc:
                analysis.error = str(exc)
            analyses.append(analysis)
    return Report(today, start, end, horizon, statuses,
                  sorted(weekly, key=lambda v: (v.effective or date.min, v.name)),
                  sorted(upcoming, key=lambda v: (v.effective or date.max, v.name)),
                  analyses, config.get("manual_checks", []), config["title"],
                  organization=config.get("organization", "한영기술사사무소"),
                  core_laws=config.get("core_laws", []),
                  volume=int(config.get("volume_base_number", 2)) + max(0, (today - date.fromisoformat(str(config.get("volume_base_date", today)))).days // 7))
