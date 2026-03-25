from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone

from activities.models import Activity, ShareLink


class ActivitySession(models.Model):
    class Status(models.TextChoices):
        STARTED = "started", "Начато"
        COMPLETED = "completed", "Завершено"
        ABANDONED = "abandoned", "Прервано"

    activity = models.ForeignKey(
        Activity,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    share_link = models.ForeignKey(
        ShareLink,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    participant_name = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.STARTED,
    )
    runtime_state = models.JSONField(default=dict, blank=True)
    score = models.IntegerField(default=0)
    max_score = models.IntegerField(default=0)
    percent_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-started_at",)

    def __str__(self) -> str:
        return f"{self.activity.title} / {self.token}"

    def update_scores(self, score: int, max_score: int) -> None:
        self.score = score
        self.max_score = max_score
        self.percent_score = round((score / max_score) * 100, 2) if max_score else 0

    def mark_completed(self, score: int, max_score: int) -> None:
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.update_scores(score, max_score)


class ActivityAnswer(models.Model):
    session = models.ForeignKey(
        ActivitySession,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    item_key = models.CharField(max_length=120)
    prompt = models.TextField(blank=True)
    submitted_value = models.JSONField(default=dict, blank=True)
    is_correct = models.BooleanField(default=False)
    score_awarded = models.IntegerField(default=0)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("answered_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("session", "item_key"),
                name="unique_answer_per_session_item",
            )
        ]

    def __str__(self) -> str:
        return f"{self.session_id}:{self.item_key}"
