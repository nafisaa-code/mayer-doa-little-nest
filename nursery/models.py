from datetime import date

from django.conf import settings
from .age_rules import check_child_age
from django.db import models
from django.utils import timezone


class Classroom(models.Model):
    TONES = [("mint", "Mint"), ("sky", "Sky"), ("sand", "Sand"), ("rose", "Rose")]

    name = models.CharField(max_length=60)
    age_group = models.CharField(max_length=40, help_text="e.g. Ages 2–3")
    capacity = models.PositiveIntegerField(default=12)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="classrooms", limit_choices_to={"role": "teacher"},
    )
    tone = models.CharField(max_length=10, choices=TONES, default="mint")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def pill_tone(self):
        return {"mint": "green", "sky": "blue", "sand": "amber", "rose": "red"}[self.tone]


class Child(models.Model):
    first_name = models.CharField(max_length=60)
    last_name = models.CharField(max_length=60)
    birth_date = models.DateField()
    classroom = models.ForeignKey(Classroom, null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="children", limit_choices_to={"role": "parent"},
    )
    photo = models.ImageField(upload_to="children/", null=True, blank=True)
    health_notes = models.TextField(blank=True)
    allergies = models.CharField(max_length=200, blank=True, help_text="Comma separated")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["first_name", "last_name"]
        verbose_name_plural = "children"

    def __str__(self):
        return self.full_name

    def clean(self):
        super().clean()
        if self.birth_date:
            check_child_age(self.birth_date)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def initials(self):
        return f"{self.first_name[:1]}{self.last_name[:1]}".upper()

    @property
    def allergy_list(self):
        return [a.strip() for a in self.allergies.split(",") if a.strip()]

    @property
    def avatar_tone(self):
        return ["mint", "sky", "sand", "coral"][self.pk % 4 if self.pk else 0]

    @property
    def age_label(self):
        today = date.today()
        months = (today.year - self.birth_date.year) * 12 + today.month - self.birth_date.month
        if today.day < self.birth_date.day:
            months -= 1
        years, rem = divmod(max(months, 0), 12)
        if years == 0:
            return f"{rem} mo"
        return f"{years} yr {rem} mo" if rem else f"{years} yr"


class Attendance(models.Model):
    child = models.ForeignKey(Child, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField(default=date.today)
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    picked_up_by = models.CharField(max_length=120, blank=True)

    class Meta:
        unique_together = ["child", "date"]
        ordering = ["-date"]


class DailyRecord(models.Model):
    MOODS = [("happy", "Happy"), ("calm", "Calm"), ("tired", "Tired"), ("fussy", "Fussy"), ("upset", "Upset")]

    child = models.ForeignKey(Child, on_delete=models.CASCADE, related_name="records")
    date = models.DateField(default=date.today)
    nap_start = models.TimeField(null=True, blank=True)
    nap_end = models.TimeField(null=True, blank=True)
    nap_note = models.CharField(max_length=200, blank=True)
    mood = models.CharField(max_length=10, choices=MOODS, blank=True)
    mood_note = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    notes_updated_at = models.DateTimeField(null=True, blank=True)
    notes_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    last_activity = models.CharField(max_length=80, blank=True)

    class Meta:
        unique_together = ["child", "date"]

    @property
    def is_napping(self):
        return bool(self.nap_start and not self.nap_end)

    @property
    def nap_minutes(self):
        if not (self.nap_start and self.nap_end):
            return 0
        return (self.nap_end.hour * 60 + self.nap_end.minute) - (self.nap_start.hour * 60 + self.nap_start.minute)

    @property
    def lunch(self):
        meals = [m for m in self.meals.all() if m.meal == "lunch"]
        return meals[-1] if meals else None


class Meal(models.Model):
    KINDS = [("breakfast", "Breakfast"), ("snack", "Snack"), ("lunch", "Lunch"), ("afternoon snack", "Afternoon snack")]
    AMOUNTS = [("all", "Ate all"), ("most", "Ate most"), ("some", "Ate some"), ("none", "Didn't eat")]

    record = models.ForeignKey(DailyRecord, on_delete=models.CASCADE, related_name="meals")
    meal = models.CharField(max_length=20, choices=KINDS)
    food = models.CharField(max_length=120)
    amount = models.CharField(max_length=10, choices=AMOUNTS)
    time = models.TimeField()

    class Meta:
        ordering = ["time", "id"]

    @property
    def amount_pct(self):
        return {"all": 100, "most": 75, "some": 40, "none": 0}[self.amount]


class Activity(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="activities")
    date = models.DateField(default=date.today)
    time = models.TimeField()
    title = models.CharField(max_length=80)
    description = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["date", "time"]
        verbose_name_plural = "activities"


class MediaItem(models.Model):
    KINDS = [("image", "Photo"), ("video", "Video")]

    child = models.ForeignKey(Child, on_delete=models.CASCADE, related_name="media")
    file = models.FileField(upload_to="media/%Y/%m/")
    kind = models.CharField(max_length=10, choices=KINDS, default="image")
    caption = models.CharField(max_length=160, blank=True)
    date = models.DateField(default=date.today)
    created_at = models.DateTimeField(default=timezone.now)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class PickupCode(models.Model):
    """One active OTP per child. The code itself is stored hashed."""

    child = models.OneToOneField(Child, on_delete=models.CASCADE, related_name="pickup_code")
    CHANNELS = [("phone", "Phone"), ("email", "Email")]

    code_hash = models.CharField(max_length=128)
    channel = models.CharField(max_length=5, choices=CHANNELS, default="phone")
    phone = models.CharField(max_length=30)
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField(default=timezone.now)
    attempts = models.PositiveSmallIntegerField(default=0)


class PickupRecord(models.Model):
    child = models.ForeignKey(Child, on_delete=models.CASCADE, related_name="pickups")
    date = models.DateField(default=date.today)
    time = models.TimeField()
    picked_up_by = models.CharField(max_length=120)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=10, default="verified")

    class Meta:
        ordering = ["-date", "-time"]
