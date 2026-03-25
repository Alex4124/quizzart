from __future__ import annotations

from copy import deepcopy

from activities.models import Activity, ShareLink


def ensure_share_link(activity: Activity) -> ShareLink:
    existing = activity.share_links.filter(is_active=True).first()
    if existing:
        return existing
    return ShareLink.objects.create(activity=activity)


def duplicate_activity(activity: Activity) -> Activity:
    return Activity.objects.create(
        owner=activity.owner,
        title=f"{activity.title} (Копия)",
        description=activity.description,
        template_key=activity.template_key,
        config_json=deepcopy(activity.config_json),
        status=Activity.Status.DRAFT,
    )
