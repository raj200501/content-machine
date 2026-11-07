"""Hand-written, specific advice packs for evergreen reel categories.

Each pack is one reel: a hook plus three concrete beats. Packs rotate by date
so the same advice does not repeat inside the recent-similarity window.
Keep every beat short enough to read on one card (roughly 8 to 16 words).
"""

from __future__ import annotations

SCRIPT_PACKS: dict[str, list[dict[str, object]]] = {
    "application_strategy": [
        {
            "hook": "This is why you're not hearing back.",
            "beats": [
                "Your resume says software engineer, but the job says data platform intern.",
                "Copy three exact phrases from the posting into your bullets, only where they're true.",
                "Recruiters skim for a match in six seconds. Make the match obvious.",
            ],
        },
        {
            "hook": "Stop sending a hundred cold applications.",
            "beats": [
                "Pick one role family this week, like backend, data, or mobile.",
                "Tailor one resume for it, then apply to twenty roles in that family.",
                "Twenty focused applications beat a hundred generic ones almost every time.",
            ],
        },
        {
            "hook": "Apply in the first week a posting goes live.",
            "beats": [
                "Big tech internship pipelines fill on a rolling basis.",
                "Set alerts on company career pages and check them twice a week.",
                "Applying early often matters more than one extra resume rewrite.",
            ],
        },
        {
            "hook": "Don't send this recruiter message.",
            "beats": [
                "Hi, I'm interested in any open roles. That gets ignored.",
                "Instead, name the exact role, one project that fits it, and one question.",
                "Three sentences, under sixty words. Specific messages get replies.",
            ],
        },
        {
            "hook": "The referral ask that actually works.",
            "beats": [
                "Don't ask a stranger for a referral in the first message.",
                "Ask one question about their team, then thank them when they reply.",
                "After that, share the job ID and your resume. Make referring you easy.",
            ],
        },
        {
            "hook": "Track your applications like a project.",
            "beats": [
                "Keep a sheet with company, role, date applied, and contact.",
                "Follow up once after ten business days if you have a contact.",
                "Your reply rate tells you whether to fix the resume or the targeting.",
            ],
        },
        {
            "hook": "Your cover letter is probably too long.",
            "beats": [
                "Most early-career recruiters read the first two lines, if anything.",
                "Line one: the role and why this team. Line two: your most relevant project.",
                "If the form says optional, a sharp short note still beats a generic page.",
            ],
        },
        {
            "hook": "Don't ignore smaller companies.",
            "beats": [
                "Everyone applies to the same ten famous names.",
                "Series B to D startups hire interns with fewer applicants per seat.",
                "You often ship more real work there, which makes your next resume stronger.",
            ],
        },
    ],
    "interview_prep": [
        {
            "hook": "Technical interview fix in twenty seconds.",
            "beats": [
                "Before writing code, repeat the problem back and ask about edge cases.",
                "Say your brute force first, then explain how you'd optimize it.",
                "Interviewers grade how you think, not just whether it compiles.",
            ],
        },
        {
            "hook": "The behavioral answer mistake students keep making.",
            "beats": [
                "They spend forty seconds on background and five on what they did.",
                "Flip it. One line of context, then your actions, then the result.",
                "End with what you learned. That's the part interviewers remember.",
            ],
        },
        {
            "hook": "Online assessment prep if you're short on time.",
            "beats": [
                "Focus on arrays, hash maps, two pointers, and sliding window first.",
                "Those patterns cover a big share of early-career assessments.",
                "Do timed sets of two problems in seventy minutes to build pace.",
            ],
        },
        {
            "hook": "Stuck in a coding interview? Say this.",
            "beats": [
                "Let me try a small example to see the pattern.",
                "Walking through an example out loud often unlocks the approach.",
                "Silence looks like stuck. Narration looks like problem solving.",
            ],
        },
        {
            "hook": "How to explain your project in an interview.",
            "beats": [
                "Start with the problem it solved, not the tech stack.",
                "Then one hard decision you made and the tradeoff behind it.",
                "Finish with what you'd change now. That shows real ownership.",
            ],
        },
        {
            "hook": "Questions to ask at the end of your interview.",
            "beats": [
                "What does a great intern accomplish in the first month here?",
                "What's the hardest problem the team is working on right now?",
                "Good questions show you're already picturing yourself on the team.",
            ],
        },
        {
            "hook": "Big O without the panic.",
            "beats": [
                "After every solution, state the time and space complexity unprompted.",
                "If you loop inside a loop, say why and whether a hash map fixes it.",
                "Doing this every time makes you sound senior, even as an intern.",
            ],
        },
        {
            "hook": "Mock interviews are the cheat code.",
            "beats": [
                "Practicing alone hides the hardest part, which is talking while coding.",
                "Trade mock interviews with a friend once a week, forty-five minutes each.",
                "Record one. Watching yourself fixes habits faster than any course.",
            ],
        },
    ],
    "resume_portfolio": [
        {
            "hook": "Three resume fixes before internship season.",
            "beats": [
                "Start every bullet with a strong verb like built, shipped, or reduced.",
                "Add a number to each one: users, speed, accuracy, or time saved.",
                "Cut coursework lists. Projects and experience earn the space.",
            ],
        },
        {
            "hook": "No internships yet? Do this instead.",
            "beats": [
                "Build one project that real people use, even ten classmates.",
                "Users, feedback, and fixes give you bullets that read like experience.",
                "Put it at the top of your resume, above coursework.",
            ],
        },
        {
            "hook": "Your GitHub is doing you no favors.",
            "beats": [
                "Pin your three best repos and archive the tutorial clones.",
                "Each pinned repo needs a README with a screenshot and how to run it.",
                "Recruiters click once. Make that one click count.",
            ],
        },
        {
            "hook": "Resume bullets that sound stronger fast.",
            "beats": [
                "Weak: worked on a web app using React.",
                "Strong: built a React dashboard used by forty students, cutting signup time in half.",
                "Same project. One shows impact, the other just lists tools.",
            ],
        },
        {
            "hook": "Your resume should be one page.",
            "beats": [
                "Early-career resumes over one page usually get skimmed less, not more.",
                "Cut anything older than high school graduation and any objective statement.",
                "Use the space for two strong projects with measurable results.",
            ],
        },
        {
            "hook": "Make your resume pass the parser.",
            "beats": [
                "Use a simple single-column layout with standard section headings.",
                "Skip icons, tables, and text inside images. Parsers can drop them.",
                "Export to PDF and paste it into a plain text editor to test it.",
            ],
        },
        {
            "hook": "The skills section most students get wrong.",
            "beats": [
                "Don't list every language you touched once in a class.",
                "Group skills by languages, frameworks, and tools you've actually shipped with.",
                "If it's on your resume, expect an interview question about it.",
            ],
        },
        {
            "hook": "A portfolio project that gets interviews.",
            "beats": [
                "Pick a problem from the industry you want, not another to-do app.",
                "Want fintech? Build a budget tracker with real bank-style data.",
                "Relevant projects give recruiters an easy reason to say yes.",
            ],
        },
    ],
    "market_context": [
        {
            "hook": "New-grad market update, minus the panic.",
            "beats": [
                "Hiring is slower and more selective, but companies are still hiring.",
                "Roles are spread wider now: data, infrastructure, AI tooling, and security.",
                "Broaden the role families you search, not just the company list.",
            ],
        },
        {
            "hook": "What AI hiring means for students.",
            "beats": [
                "Companies want engineers who can build with AI tools, not just talk about them.",
                "One project that uses a model API in a real workflow stands out right now.",
                "Show the product, the prompt design, and how you measured quality.",
            ],
        },
        {
            "hook": "Layoff headlines? Here's the context.",
            "beats": [
                "Layoffs usually hit specific teams, while other teams keep hiring.",
                "Internship and new-grad programs often run on separate budgets.",
                "Keep applying, and watch company career pages, not just headlines.",
            ],
        },
        {
            "hook": "Recruiting season timing, simplified.",
            "beats": [
                "Many big tech summer internships open in late summer and early fall.",
                "Startups and mid-size companies keep hiring well into spring.",
                "Missed the early wave? You're not out. Shift to the second wave.",
            ],
        },
    ],
    "motivational_community": [
        {
            "hook": "You're not behind. Do this next.",
            "beats": [
                "Pick one role family, fix one resume bullet, and send one application today.",
                "Small daily reps compound faster than one panicked weekend.",
                "Rejections are data about targeting, not a verdict on you.",
            ],
        },
        {
            "hook": "Job search momentum without burnout.",
            "beats": [
                "Set a daily cap: five tailored applications, then stop.",
                "Spend the rest of your time building or practicing, not refreshing email.",
                "Consistency over intensity is how most people land the offer.",
            ],
        },
        {
            "hook": "The small move that makes this week better.",
            "beats": [
                "Message one person who has the job you want and ask one question.",
                "Most people are happy to answer a short, specific message.",
                "One conversation can teach you more than ten blog posts.",
            ],
        },
    ],
}


def pick_pack(category: str, day_ordinal: int, slot_index: int, recent_hooks: set[str] | None = None) -> dict[str, object] | None:
    packs = SCRIPT_PACKS.get(category) or []
    if not packs:
        return None
    recent_hooks = {hook.lower() for hook in (recent_hooks or set())}
    start = (day_ordinal + slot_index) % len(packs)
    for offset in range(len(packs)):
        pack = packs[(start + offset) % len(packs)]
        if str(pack["hook"]).lower() not in recent_hooks:
            return pack
    return packs[start]
