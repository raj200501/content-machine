"""Hand-written, specific advice packs for evergreen reel categories.

Each pack is one reel: a hook plus three concrete beats. Packs rotate by date
so the same advice does not repeat inside the recent-similarity window.
Keep every beat short enough to read on one card (roughly 8 to 16 words).
"""

from __future__ import annotations

SCRIPT_PACKS: dict[str, list[dict[str, object]]] = {
    "application_strategy": [
        {
            "hook": "Your resume isn't the problem. Your keywords are.",
            "beats": [
                "Your resume says software engineer, but the job says data platform intern.",
                "Copy three exact phrases from the posting into your bullets, only where they're true.",
                "Recruiters skim for a match in six seconds. Make the match obvious.",
            ],
        },
        {
            "hook": "Stop sending a hundred applications. Send twenty.",
            "beats": [
                "Pick one role family this week, like backend, data, or mobile.",
                "Tailor one resume for it, then apply to twenty roles in that family.",
                "Twenty focused applications beat a hundred generic ones almost every time.",
            ],
        },
        {
            "hook": "Applying in week three? You're already late.",
            "beats": [
                "Big tech internship pipelines fill on a rolling basis.",
                "Set alerts on company career pages and check them twice a week.",
                "Applying early often matters more than one extra resume rewrite.",
            ],
        },
        {
            "hook": "Recruiters ignore this message. Send this instead.",
            "beats": [
                "Hi, I'm interested in any open roles. That gets ignored.",
                "Instead, name the exact role, one project that fits it, and one question.",
                "Three sentences, under sixty words. Specific messages get replies.",
            ],
        },
        {
            "hook": "Never ask a stranger for a referral like this.",
            "beats": [
                "Don't ask a stranger for a referral in the first message.",
                "Ask one question about their team, then thank them when they reply.",
                "After that, share the job ID and your resume. Make referring you easy.",
            ],
        },
        {
            "hook": "Zero replies? Your tracker will tell you why.",
            "beats": [
                "Keep a sheet with company, role, date applied, and contact.",
                "Follow up once after ten business days if you have a contact.",
                "Your reply rate tells you whether to fix the resume or the targeting.",
            ],
        },
        {
            "hook": "Recruiters read two lines of your cover letter.",
            "beats": [
                "Most early-career recruiters read the first two lines, if anything.",
                "Line one: the role and why this team. Line two: your most relevant project.",
                "If the form says optional, a sharp short note still beats a generic page.",
            ],
        },
        {
            "hook": "Everyone applies to the same ten companies. Don't.",
            "beats": [
                "Everyone applies to the same ten famous names.",
                "Series B to D startups hire interns with fewer applicants per seat.",
                "You often ship more real work there, which makes your next resume stronger.",
            ],
        },
    ],
    "interview_prep": [
        {
            "hook": "Never start coding the second they stop talking.",
            "beats": [
                "Before writing code, repeat the problem back and ask about edge cases.",
                "Say your brute force first, then explain how you'd optimize it.",
                "Interviewers grade how you think, not just whether it compiles.",
            ],
        },
        {
            "hook": "You're answering behavioral questions backwards.",
            "beats": [
                "They spend forty seconds on background and five on what they did.",
                "Flip it. One line of context, then your actions, then the result.",
                "End with what you learned. That's the part interviewers remember.",
            ],
        },
        {
            "hook": "Online assessment this week? Study only these.",
            "beats": [
                "Focus on arrays, hash maps, two pointers, and sliding window first.",
                "Those patterns cover a big share of early-career assessments.",
                "Do timed sets of two problems in seventy minutes to build pace.",
            ],
        },
        {
            "hook": "Stuck in a coding interview? Say this sentence.",
            "beats": [
                "Let me try a small example to see the pattern.",
                "Walking through an example out loud often unlocks the approach.",
                "Silence looks like stuck. Narration looks like problem solving.",
            ],
        },
        {
            "hook": "Stop explaining your project with the tech stack.",
            "beats": [
                "Start with the problem it solved, not the tech stack.",
                "Then one hard decision you made and the tradeoff behind it.",
                "Finish with what you'd change now. That shows real ownership.",
            ],
        },
        {
            "hook": "Ask this when they say: any questions for us?",
            "beats": [
                "What does a great intern accomplish in the first month here?",
                "What's the hardest problem the team is working on right now?",
                "Good questions show you're already picturing yourself on the team.",
            ],
        },
        {
            "hook": "Say this after every solution. Interviewers notice.",
            "beats": [
                "After every solution, state the time and space complexity unprompted.",
                "If you loop inside a loop, say why and whether a hash map fixes it.",
                "Doing this every time makes you sound senior, even as an intern.",
            ],
        },
        {
            "hook": "Practicing LeetCode alone hides your biggest weakness.",
            "beats": [
                "Practicing alone hides the hardest part, which is talking while coding.",
                "Trade mock interviews with a friend once a week, forty-five minutes each.",
                "Record one. Watching yourself fixes habits faster than any course.",
            ],
        },
    ],
    "resume_portfolio": [
        {
            "hook": "Three resume fixes before you apply anywhere.",
            "beats": [
                "Start every bullet with a strong verb like built, shipped, or reduced.",
                "Add a number to each one: users, speed, accuracy, or time saved.",
                "Cut coursework lists. Projects and experience earn the space.",
            ],
        },
        {
            "hook": "No internships yet? Put this at the top.",
            "beats": [
                "Build one project that real people use, even ten classmates.",
                "Users, feedback, and fixes give you bullets that read like experience.",
                "Put it at the top of your resume, above coursework.",
            ],
        },
        {
            "hook": "Recruiters click your GitHub once. Fix this first.",
            "beats": [
                "Pin your three best repos and archive the tutorial clones.",
                "Each pinned repo needs a README with a screenshot and how to run it.",
                "Recruiters click once. Make that one click count.",
            ],
        },
        {
            "hook": "Turn this weak resume bullet into a strong one.",
            "beats": [
                "Weak: worked on a web app using React.",
                "Strong: built a React dashboard used by forty students, cutting signup time in half.",
                "Same project. One shows impact, the other just lists tools.",
            ],
        },
        {
            "hook": "Your two-page resume is getting skimmed. Cut it.",
            "beats": [
                "A second page doesn't get read more carefully. It gets skimmed faster.",
                "Cut high school details and any objective statement.",
                "Use the space for two strong projects with measurable results.",
            ],
        },
        {
            "hook": "Your resume might look blank to the parser.",
            "beats": [
                "Use a simple single-column layout with standard section headings.",
                "Skip icons, tables, and text inside images. Parsers can drop them.",
                "Export to PDF and paste it into a plain text editor to test it.",
            ],
        },
        {
            "hook": "If it's in your skills section, they'll ask about it.",
            "beats": [
                "Don't list every language you touched once in a class.",
                "Group skills by languages, frameworks, and tools you've actually shipped with.",
                "If it's on your resume, expect an interview question about it.",
            ],
        },
        {
            "hook": "Stop building to-do apps. Build this instead.",
            "beats": [
                "Pick a problem from the industry you want, not another to-do app.",
                "Want fintech? Build a budget tracker with real bank-style data.",
                "Relevant projects give recruiters an easy reason to say yes.",
            ],
        },
    ],
    "market_context": [
        {
            "hook": "New grad hiring isn't dead. It moved.",
            "beats": [
                "Hiring is slower and more selective, but companies are still hiring.",
                "Roles are spread wider now: data, infrastructure, AI tooling, and security.",
                "Broaden the role families you search, not just the company list.",
            ],
        },
        {
            "hook": "Companies want this from students now. Not prompts.",
            "beats": [
                "Companies want engineers who can build with AI tools, not just talk about them.",
                "One project that uses a model API in a real workflow stands out right now.",
                "Show the product, the prompt design, and how you measured quality.",
            ],
        },
        {
            "hook": "Layoff headlines don't mean internships are gone.",
            "beats": [
                "Layoffs usually hit specific teams, while other teams keep hiring.",
                "Internship and new-grad programs often run on separate budgets.",
                "Keep applying, and watch company career pages, not just headlines.",
            ],
        },
        {
            "hook": "Missed the early internship wave? You're not out.",
            "beats": [
                "Many big tech summer internships open in late summer and early fall.",
                "Startups and mid-size companies keep hiring well into spring.",
                "Missed the early wave? You're not out. Shift to the second wave.",
            ],
        },
    ],
    "motivational_community": [
        {
            "hook": "You're not behind. Do these three things today.",
            "beats": [
                "Pick one role family, fix one resume bullet, and send one application today.",
                "Small daily reps compound faster than one panicked weekend.",
                "Rejections are data about targeting, not a verdict on you.",
            ],
        },
        {
            "hook": "Applying all day is why you're burning out.",
            "beats": [
                "Set a daily cap: five tailored applications, then stop.",
                "Spend the rest of your time building or practicing, not refreshing email.",
                "Consistency over intensity is how most people land the offer.",
            ],
        },
        {
            "hook": "One message this week can beat ten blog posts.",
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
