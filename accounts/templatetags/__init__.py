from django import template

from accounts.document_tracking import format_duration

register = template.Library()


@register.filter(name="duration")
def duration_filter(seconds):
    return format_duration(seconds)
