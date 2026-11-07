"""Local writing templates."""

from __future__ import annotations

# Sends (DM shares) are the strongest signal for reaching new people, then saves.
SCRIPT_CTAS = [
    "Save this for your next application, and send it to a friend who needs it.",
    "Send this to a friend who's recruiting right now.",
    "Save this before your next interview.",
    "Follow for one fix like this every day.",
]

CATEGORY_CTAS = {
    "application_strategy": [
        "Send this to a friend who's recruiting right now.",
        "Save this for your next application, and send it to a friend who needs it.",
    ],
    "interview_prep": [
        "Save this before your next interview.",
        "Send this to the friend with an interview this week.",
    ],
    "resume_portfolio": [
        "Save this for your next resume edit, and send it to a friend who needs it.",
        "Send this to a friend still fixing their resume.",
    ],
    "market_context": ["Send this to a friend who's recruiting right now."],
    "motivational_community": ["Send this to a friend who needs it today."],
}

JOB_ALERT_CTAS = [
    "Send this to a friend who's applying, and follow for tomorrow's drop.",
    "Send this to the friend who still needs an internship. New roles drop here daily.",
    "Send this to your group chat before these fill up.",
]

JOB_ALERT_TIPS = [
    "Search the exact title on each careers page and apply this week.",
    "Tailor your top resume bullet to each role before you hit submit.",
    "Early applications get read first, so don't sit on these.",
    "After you apply, send one short note to an engineer on that team.",
]

CATEGORY_SUBS = {
    "application_strategy": "Applications that get replies",
    "interview_prep": "Interview prep for students",
    "resume_portfolio": "Resume fixes that work",
    "market_context": "What's happening in hiring",
    "motivational_community": "For anyone recruiting right now",
}

CATEGORY_INTROS = {
    "openings_job_alert": "Quick hiring check",
    "application_strategy": "Quick application reset",
    "interview_prep": "Quick interview reset",
    "resume_portfolio": "Quick resume and portfolio fix",
    "market_context": "Quick market update",
    "motivational_community": "Quick reminder",
}
