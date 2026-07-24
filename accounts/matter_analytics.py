"""Visual analytics for the Matter Management module hub."""

from __future__ import annotations

from calendar import month_abbr, monthrange
from collections import Counter
from datetime import date, timedelta

from django.db.models import Count
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.utils import timezone

from .models import LitigationCase, NonLitigationMatter

FILTER_MODES = ("day", "period", "month", "year")
FOCUS_OPTIONS = ("all", "litigation", "non_litigation")


def _parse_date(raw: str | None) -> date | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_month(raw: str | None) -> date | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        year_s, month_s = value.split("-", 1)
        year, month = int(year_s), int(month_s)
        if month < 1 or month > 12:
            return None
        return date(year, month, 1)
    except (TypeError, ValueError):
        return None


def _parse_year(raw: str | None, *, fallback: int) -> int:
    try:
        year = int((raw or "").strip())
    except (TypeError, ValueError):
        return fallback
    today = timezone.localdate()
    if year < 1990 or year > today.year + 1:
        return fallback
    return year


def resolve_matter_date_filter(params=None) -> dict:
    """
    Resolve calendar filter mode and inclusive start/end dates.

    Modes:
    - day: single calendar date
    - period: inclusive from/to dates
    - month: YYYY-MM month picker
    - year: calendar year
    """
    today = timezone.localdate()
    data = params or {}
    mode = (data.get("mode") or "month").strip().lower()
    if mode not in FILTER_MODES:
        mode = "month"

    day_value = _parse_date(data.get("date")) or today
    period_start = _parse_date(data.get("start")) or (today - timedelta(days=29))
    period_end = _parse_date(data.get("end")) or today
    if period_end < period_start:
        period_start, period_end = period_end, period_start
    # Cap extreme custom ranges to keep charts readable.
    if (period_end - period_start).days > 366 * 3:
        period_start = period_end - timedelta(days=366 * 3)

    month_value = _parse_month(data.get("month")) or today.replace(day=1)
    year_value = _parse_year(data.get("year"), fallback=today.year)

    if mode == "day":
        start = end = day_value
        label = day_value.strftime("%d %b %Y")
        grain = "day"
    elif mode == "period":
        start, end = period_start, period_end
        if start == end:
            label = start.strftime("%d %b %Y")
            grain = "day"
        else:
            label = f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}"
            span = (end - start).days + 1
            if span <= 45:
                grain = "day"
            elif span <= 180:
                grain = "week"
            else:
                grain = "month"
    elif mode == "year":
        start = date(year_value, 1, 1)
        end = date(year_value, 12, 31)
        if end > today:
            end = today
        label = str(year_value)
        grain = "month"
    else:  # month
        start = month_value.replace(day=1)
        last_day = monthrange(start.year, start.month)[1]
        end = date(start.year, start.month, last_day)
        if end > today:
            end = today
        label = f"{month_abbr[start.month]} {start.year}"
        grain = "day"

    if month_value.month == 1:
        prev_month = date(month_value.year - 1, 12, 1)
    else:
        prev_month = date(month_value.year, month_value.month - 1, 1)
    if month_value.month == 12:
        next_month = date(month_value.year + 1, 1, 1)
    else:
        next_month = date(month_value.year, month_value.month + 1, 1)
    current_month = today.replace(day=1)

    return {
        "mode": mode,
        "start": start,
        "end": end,
        "label": label,
        "grain": grain,
        "modes": [
            {"value": "day", "label": "Day"},
            {"value": "period", "label": "Period"},
            {"value": "month", "label": "Month"},
            {"value": "year", "label": "Year"},
        ],
        "values": {
            "date": day_value.isoformat(),
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
            "month": f"{month_value.year:04d}-{month_value.month:02d}",
            "year": str(year_value),
        },
        "month_nav": {
            "prev": f"{prev_month.year:04d}-{prev_month.month:02d}",
            "next": f"{next_month.year:04d}-{next_month.month:02d}",
            "can_next": next_month <= current_month,
        },
        "max_date": today.isoformat(),
        "max_month": f"{today.year:04d}-{today.month:02d}",
        "year_options": list(range(today.year, max(today.year - 14, 1990) - 1, -1)),
    }


def _in_range(queryset, date_field: str, start: date, end: date):
    return queryset.filter(
        **{
            f"{date_field}__gte": start,
            f"{date_field}__lte": end,
        }
    )


def _status_bars(queryset, status_enum) -> list[dict]:
    counts = {
        row["status"]: row["count"]
        for row in queryset.values("status").annotate(count=Count("id"))
    }
    bars = [
        {
            "key": key,
            "label": label,
            "value": counts.get(key, 0),
        }
        for key, label in status_enum.choices
    ]
    total = sum(bar["value"] for bar in bars) or 1
    maximum = max((bar["value"] for bar in bars), default=0) or 1
    for bar in bars:
        bar["max"] = maximum
        bar["pct"] = round((bar["value"] / total) * 100)
    return bars


def _merge_status_bars(*bar_lists: list[dict]) -> list[dict]:
    totals: Counter = Counter()
    labels: dict[str, str] = {}
    order: list[str] = []
    for bars in bar_lists:
        for bar in bars:
            key = bar["key"]
            if key not in labels:
                labels[key] = bar["label"]
                order.append(key)
            totals[key] += int(bar.get("value") or 0)
    merged = [
        {"key": key, "label": labels[key], "value": totals[key]} for key in order
    ]
    total = sum(bar["value"] for bar in merged) or 1
    maximum = max((bar["value"] for bar in merged), default=0) or 1
    for bar in merged:
        bar["max"] = maximum
        bar["pct"] = round((bar["value"] / total) * 100)
    return merged


def _normalize_bucket(value, grain: str) -> date | None:
    if not value:
        return None
    if hasattr(value, "date"):
        value = value.date()
    if grain == "month":
        return value.replace(day=1)
    if grain == "week":
        return value - timedelta(days=value.weekday())
    return value


def _bucket_label(bucket: date, grain: str) -> str:
    if grain == "month":
        return f"{month_abbr[bucket.month]} {str(bucket.year)[2:]}"
    if grain == "week":
        return f"{bucket.day} {month_abbr[bucket.month]}"
    return f"{bucket.day} {month_abbr[bucket.month]}"


def _iter_buckets(start: date, end: date, grain: str) -> list[date]:
    buckets: list[date] = []
    if grain == "month":
        cursor = start.replace(day=1)
        end_month = end.replace(day=1)
        while cursor <= end_month:
            buckets.append(cursor)
            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)
        return buckets

    if grain == "week":
        cursor = start - timedelta(days=start.weekday())
        while cursor <= end:
            buckets.append(cursor)
            cursor += timedelta(days=7)
        return buckets

    cursor = start
    while cursor <= end:
        buckets.append(cursor)
        cursor += timedelta(days=1)
    return buckets


def _period_counts(model, date_field: str, start: date, end: date, grain: str) -> Counter:
    trunc = {"day": TruncDay, "week": TruncWeek, "month": TruncMonth}[grain]
    rows = (
        _in_range(model.objects.all(), date_field, start, end)
        .annotate(bucket=trunc(date_field))
        .values("bucket")
        .annotate(count=Count("id"))
    )
    counts: Counter = Counter()
    for row in rows:
        bucket = _normalize_bucket(row["bucket"], grain)
        if bucket is not None:
            counts[bucket] = row["count"]
    return counts


def _build_trend(start: date, end: date, grain: str) -> list[dict]:
    buckets = _iter_buckets(start, end, grain)
    lit_counts = _period_counts(LitigationCase, "filing_date", start, end, grain)
    mat_counts = _period_counts(NonLitigationMatter, "date_opened", start, end, grain)
    return [
        {
            "key": bucket.isoformat(),
            "label": _bucket_label(bucket, grain),
            "litigation": lit_counts.get(bucket, 0),
            "non_litigation": mat_counts.get(bucket, 0),
            "total": lit_counts.get(bucket, 0) + mat_counts.get(bucket, 0),
        }
        for bucket in buckets
    ]


def _trend_title(filter_state: dict) -> str:
    grain = filter_state["grain"]
    mode = filter_state["mode"]
    if mode == "day":
        return "Openings on selected day"
    if grain == "day":
        return "Daily openings"
    if grain == "week":
        return "Weekly openings"
    return "Monthly openings"


def _workload_rows(queryset) -> list[dict]:
    rows = list(
        queryset.exclude(assigned_to__isnull=True)
        .values(
            "assigned_to_id",
            "assigned_to__first_name",
            "assigned_to__last_name",
        )
        .annotate(count=Count("id"))
        .order_by("-count")[:8]
    )
    workload = []
    for row in rows:
        first = (row.get("assigned_to__first_name") or "").strip()
        last = (row.get("assigned_to__last_name") or "").strip()
        name = f"{first} {last}".strip() or "Team member"
        workload.append(
            {
                "id": row["assigned_to_id"],
                "label": name,
                "value": row["count"],
            }
        )
    return workload


def _merge_workload(*row_lists: list[dict], limit: int = 5) -> list[dict]:
    totals: Counter = Counter()
    labels: dict[int, str] = {}
    for rows in row_lists:
        for row in rows:
            key = row["id"]
            labels[key] = row["label"]
            totals[key] += int(row.get("value") or 0)
    merged = [
        {"label": labels[key], "value": totals[key]}
        for key, _ in totals.most_common(limit)
    ]
    maximum = max((item["value"] for item in merged), default=0) or 1
    for item in merged:
        item["max"] = maximum
        item["width"] = round((item["value"] / maximum) * 100)
    return merged


def _finalize_workload(rows: list[dict], *, limit: int = 5) -> list[dict]:
    trimmed = [
        {"label": row["label"], "value": int(row.get("value") or 0)}
        for row in rows[:limit]
    ]
    maximum = max((item["value"] for item in trimmed), default=0) or 1
    for item in trimmed:
        item["max"] = maximum
        item["width"] = round((item["value"] / maximum) * 100)
    return trimmed


def _resolve_focus(params=None) -> str:
    data = params or {}
    raw = (data.get("focus") or data.get("tab") or "all").strip().lower()
    if raw in {"non_litigation", "non-litigation", "non"}:
        return "non_litigation"
    if raw in {"litigation", "lit"}:
        return "litigation"
    if raw in FOCUS_OPTIONS:
        return raw
    return "all"


def _glance_for(*, opened, active, pending, closed, unassigned):
    return [
        {
            "key": "opened",
            "label": "Opened",
            "value": opened,
            "hint": "in this period",
            "tone": "neutral",
        },
        {
            "key": "active",
            "label": "Active",
            "value": active,
            "hint": f"{unassigned} unassigned" if unassigned else "all assigned",
            "tone": "warning" if unassigned else "good",
        },
        {
            "key": "pending",
            "label": "Pending",
            "value": pending,
            "hint": "awaiting approval",
            "tone": "critical" if pending else "neutral",
        },
        {
            "key": "closed",
            "label": "Closed",
            "value": closed,
            "hint": "in this period",
            "tone": "neutral",
        },
    ]


def build_matter_management_analytics(params=None) -> dict:
    """Aggregate litigation and non-litigation matter stats for dashboard charts."""
    filter_state = resolve_matter_date_filter(params)
    start = filter_state["start"]
    end = filter_state["end"]
    focus = _resolve_focus(params)

    lit_qs = _in_range(LitigationCase.objects.all(), "filing_date", start, end)
    mat_qs = _in_range(NonLitigationMatter.objects.all(), "date_opened", start, end)

    lit_active = lit_qs.filter(status=LitigationCase.Status.ACTIVE)
    mat_active = mat_qs.filter(status=NonLitigationMatter.Status.ACTIVE)

    lit_total = lit_qs.count()
    mat_total = mat_qs.count()
    lit_active_count = lit_active.count()
    mat_active_count = mat_active.count()
    lit_pending = lit_qs.filter(
        status=LitigationCase.Status.PENDING_APPROVAL
    ).count()
    mat_pending = mat_qs.filter(
        status=NonLitigationMatter.Status.PENDING_APPROVAL
    ).count()
    lit_closed = lit_qs.filter(status=LitigationCase.Status.CLOSED).count()
    mat_closed = mat_qs.filter(status=NonLitigationMatter.Status.CLOSED).count()
    lit_unassigned = lit_active.filter(assigned_to__isnull=True).count()
    mat_unassigned = mat_active.filter(assigned_to__isnull=True).count()

    total_matters = lit_total + mat_total
    active_total = lit_active_count + mat_active_count
    pending_total = lit_pending + mat_pending
    closed_total = lit_closed + mat_closed
    unassigned_total = lit_unassigned + mat_unassigned

    trend = _build_trend(start, end, filter_state["grain"])
    lit_status = _status_bars(lit_qs, LitigationCase.Status)
    mat_status = _status_bars(mat_qs, NonLitigationMatter.Status)
    lit_workload = _workload_rows(lit_active)
    mat_workload = _workload_rows(mat_active)

    if focus == "litigation":
        glance = _glance_for(
            opened=lit_total,
            active=lit_active_count,
            pending=lit_pending,
            closed=lit_closed,
            unassigned=lit_unassigned,
        )
        status = lit_status
        workload = _finalize_workload(lit_workload)
        workload_empty = "No assigned active cases in this range."
        accent = "litigation"
        focus_label = "Litigation"
        opened_for_chart = lit_total
    elif focus == "non_litigation":
        glance = _glance_for(
            opened=mat_total,
            active=mat_active_count,
            pending=mat_pending,
            closed=mat_closed,
            unassigned=mat_unassigned,
        )
        status = mat_status
        workload = _finalize_workload(mat_workload)
        workload_empty = "No assigned active matters in this range."
        accent = "non"
        focus_label = "Non-litigation"
        opened_for_chart = mat_total
    else:
        glance = _glance_for(
            opened=total_matters,
            active=active_total,
            pending=pending_total,
            closed=closed_total,
            unassigned=unassigned_total,
        )
        status = _merge_status_bars(lit_status, mat_status)
        workload = _merge_workload(lit_workload, mat_workload)
        workload_empty = "No assigned active matters in this range."
        accent = "all"
        focus_label = "All matters"
        opened_for_chart = total_matters

    def _share(count: int) -> int:
        return round((count / total_matters) * 100) if total_matters else 0

    return {
        "generated_at": timezone.now(),
        "filter": filter_state,
        "focus": focus,
        "focus_label": focus_label,
        "accent": accent,
        "focus_items": [
            {
                "id": "all",
                "label": "All",
                "count": total_matters,
                "active": focus == "all",
            },
            {
                "id": "litigation",
                "label": "Litigation",
                "count": lit_total,
                "share_pct": _share(lit_total),
                "active": focus == "litigation",
            },
            {
                "id": "non_litigation",
                "label": "Non-litigation",
                "count": mat_total,
                "share_pct": _share(mat_total),
                "active": focus == "non_litigation",
            },
        ],
        "glance": glance,
        "trend_title": _trend_title(filter_state),
        "opened": opened_for_chart,
        "status": status,
        "workload": workload,
        "workload_empty": workload_empty,
        "active_count": (
            lit_active_count
            if focus == "litigation"
            else mat_active_count
            if focus == "non_litigation"
            else active_total
        ),
        "unassigned": (
            lit_unassigned
            if focus == "litigation"
            else mat_unassigned
            if focus == "non_litigation"
            else unassigned_total
        ),
        "totals": {
            "all": total_matters,
            "active": active_total,
            "pending": pending_total,
            "closed": closed_total,
            "litigation": lit_total,
            "non_litigation": mat_total,
            "litigation_active": lit_active_count,
            "non_litigation_active": mat_active_count,
            "litigation_pending": lit_pending,
            "non_litigation_pending": mat_pending,
            "litigation_unassigned": lit_unassigned,
            "non_litigation_unassigned": mat_unassigned,
        },
        "charts": {
            "trend": trend,
            "focus": focus,
        },
    }
