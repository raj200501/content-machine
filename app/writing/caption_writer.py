"""Caption and hashtag generation."""

from __future__ import annotations

from app.models import CaptionPackage, PlannedTopic

BASE_HASHTAGS = [
    "techinternship",
    "newgradjobs",
    "softwareengineer",
    "csstudent",
    "internshipsearch",
    "jobsearchtips",
    "careertok",
]


def build_caption(topic: PlannedTopic, beats: list[str], evidence_items: list[dict], cta: str) -> CaptionPackage:
    companies = [item.get("company") or item.get("title", "").split(" ")[0] for item in evidence_items[:3]]
    source_lines = [f"- {item.get('title', 'Source')} :: {item.get('source_url', '')}" for item in evidence_items]
    compliance = "Original synthesized script from public sources. No raw URLs in spoken copy. Verify live details before posting."
    caption_body = "\n".join(
        [
            topic.hook_style.capitalize(),
            "",
            *[f"- {beat}" for beat in beats[:4]],
            "",
            cta,
        ]
    ).strip()
    hashtags = BASE_HASHTAGS + [tag.lower().replace("-", "") for tag in companies if tag][:3]
    return CaptionPackage(
        caption=caption_body,
        hashtags=sorted(set(f"#{tag}" for tag in hashtags if tag)),
        cta=cta,
        source_notes="\n".join(source_lines) if source_lines else "- Evergreen guidance with recent hiring context.",
        compliance_notes=compliance,
    )
