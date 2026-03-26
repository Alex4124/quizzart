from __future__ import annotations

from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    class Role(models.TextChoices):
        TEACHER = "teacher", "Учитель"
        STUDENT = "student", "Ученик"

    class StudentStatus(models.TextChoices):
        READY = "готов учиться!", "готов учиться!"
        SLEEPY = "хочу спать...", "хочу спать..."
        HOME = "скорей бы домой!", "скорей бы домой!"
        QUIZ_MASTER = "главный решатель квизов!", "главный решатель квизов!"
        TOP_ONE = "№1 в своём классе!", "№1 в своём классе!"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(
        max_length=16,
        choices=Role.choices,
        default=Role.TEACHER,
    )
    patronymic = models.CharField(max_length=150, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True)
    teacher_subject = models.CharField(max_length=150, blank=True)
    teacher_status = models.CharField(max_length=255, blank=True)
    student_classroom = models.CharField(max_length=64, blank=True)
    student_status = models.CharField(
        max_length=64,
        choices=StudentStatus.choices,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user__username",)

    def __str__(self) -> str:
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def is_teacher(self) -> bool:
        return self.role == self.Role.TEACHER

    @property
    def is_student(self) -> bool:
        return self.role == self.Role.STUDENT
