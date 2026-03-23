from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


def generate_share_slug() -> str:
    return uuid.uuid4().hex[:12]


class Activity(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    template_key = models.CharField(max_length=64)
    config_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-created_at")

    def __str__(self) -> str:
        return self.title

    @property
    def is_published(self) -> bool:
        return self.status == self.Status.PUBLISHED

    @property
    def active_share_link(self) -> "ShareLink | None":
        return self.share_links.filter(is_active=True).first()

    def get_absolute_url(self) -> str:
        return reverse("activities:edit", kwargs={"pk": self.pk})

    def get_preview_url(self) -> str:
        return reverse("activities:preview", kwargs={"pk": self.pk})

    def publish(self) -> None:
        self.status = self.Status.PUBLISHED
        if not self.published_at:
            self.published_at = timezone.now()

    def unpublish(self) -> None:
        self.status = self.Status.DRAFT


class ShareLink(models.Model):
    activity = models.ForeignKey(
        Activity,
        on_delete=models.CASCADE,
        related_name="share_links",
    )
    slug = models.SlugField(max_length=32, unique=True, default=generate_share_slug)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.activity.title} [{self.slug}]"

    def get_absolute_url(self) -> str:
        return reverse("attempts:play", kwargs={"slug": self.slug})
