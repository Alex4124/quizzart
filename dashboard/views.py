from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from activities.models import Activity
from attempts.models import ActivitySession


def landing(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")
    return render(request, "dashboard/landing.html")


@login_required
def home(request):
    activities = (
        Activity.objects.filter(owner=request.user)
        .annotate(
            launches=Count("sessions", distinct=True),
            completions=Count(
                "sessions",
                filter=Q(sessions__status=ActivitySession.Status.COMPLETED),
                distinct=True,
            ),
            avg_percent=Avg(
                "sessions__percent_score",
                filter=Q(sessions__status=ActivitySession.Status.COMPLETED),
            ),
        )
        .order_by("-updated_at")
    )
    return render(request, "dashboard/home.html", {"activities": activities})


@login_required
def activity_analytics(request, pk: int):
    activity = get_object_or_404(Activity, pk=pk, owner=request.user)
    sessions = activity.sessions.all()
    summary = sessions.aggregate(avg_percent=Avg("percent_score"))
    return render(
        request,
        "dashboard/analytics.html",
        {
            "activity": activity,
            "sessions": sessions,
            "launches": sessions.count(),
            "completions": sessions.filter(status=ActivitySession.Status.COMPLETED).count(),
            "average_score": summary["avg_percent"] or 0,
        },
    )
