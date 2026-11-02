"""Age rules for enrollment: 4 months to 10 years (inclusive)."""
import calendar
from datetime import date
from django.core.exceptions import ValidationError
from django.utils import timezone


def months_before(day, months):
    # Subtract calendar months and handle short months (like February).
    year = day.year
    month = day.month - months
    while month <= 0:
        month += 12
        year -= 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))


def check_child_age(birth_date):
    today = timezone.localdate()
    if birth_date > today:
        raise ValidationError("Birth date cannot be in the future.")
    if birth_date > months_before(today, 4):
        raise ValidationError("Child must be at least 4 months old.")
    if birth_date < months_before(today, 120):
        raise ValidationError("Child cannot be older than 10 years.")
