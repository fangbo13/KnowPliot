"""User models."""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model for EY employees."""

    SERVICE_LINE_CHOICES = [
        ("assurance", "Assurance"),
        ("consulting", "Consulting"),
        ("tax", "Tax"),
        ("strategy_transactions", "Strategy & Transactions"),
        ("core", "Core Business Services"),
    ]

    ROLE_LEVEL_CHOICES = [
        ("staff", "Staff"),
        ("senior", "Senior"),
        ("manager", "Manager"),
        ("senior_manager", "Senior Manager"),
        ("partner", "Partner"),
    ]

    LANGUAGE_CHOICES = [
        ("en", "English"),
        ("zh", "Chinese"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    employee_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    service_line = models.CharField(
        max_length=30, choices=SERVICE_LINE_CHOICES, null=True, blank=True
    )
    office_location = models.CharField(max_length=100, null=True, blank=True)
    role_level = models.CharField(
        max_length=20, choices=ROLE_LEVEL_CHOICES, null=True, blank=True
    )
    start_date = models.DateField(null=True, blank=True)
    language_preference = models.CharField(
        max_length=2, choices=LANGUAGE_CHOICES, default="en"
    )
    manager = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="direct_reports"
    )
    buddy = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="buddy_assignees"
    )
    is_hr_admin = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users_user"

    def __str__(self):
        return f"{self.email} ({self.employee_id or 'no-id'})"
