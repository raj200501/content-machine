"""Hand-checked material for the tip formats.

Each entry is specific and usable as-is (the "slop must stop" lesson from this
niche): exact words to say, an exact bullet to rewrite, an exact link to use.
Resume examples are clearly example resumes, not claims about real people.
"""

from __future__ import annotations

# Resume redlines: weak bullet -> strong bullet, and why it works.
REDLINES = [
    {
        "hook": "This resume bullet is costing you interviews.",
        "weak": "Worked on a team to build a web app.",
        "strong": "Built a React and Flask app 300 students use to swap textbooks.",
        "why": "Say what you built, who uses it, and how many.",
    },
    {
        "hook": "Recruiters skip bullets that start like this.",
        "weak": "Responsible for testing the backend.",
        "strong": "Wrote 120 API tests that caught 9 bugs before launch.",
        "why": "Responsible for is a job description. Show the result instead.",
    },
    {
        "hook": "Fix this bullet before you apply anywhere.",
        "weak": "Helped improve website performance.",
        "strong": "Cut page load from 4.1 to 1.3 seconds by lazy-loading images.",
        "why": "A before and after number beats the word improve every time.",
    },
    {
        "hook": "Your class project bullet probably looks like this.",
        "weak": "Made a Java project for my data structures class.",
        "strong": "Built a Java route planner using Dijkstra on 50,000 map nodes.",
        "why": "Name the hard part. The class name tells them nothing.",
    },
    {
        "hook": "Stop listing tools. Do this instead.",
        "weak": "Used Python, Pandas, and SQL.",
        "strong": "Automated a weekly sales report in Python and SQL, saving 6 hours a week.",
        "why": "Tools only count when they're attached to an outcome.",
    },
    {
        "hook": "This hackathon bullet sells you short.",
        "weak": "Participated in a 24-hour hackathon.",
        "strong": "Won 2nd of 80 teams with a voice app that books campus study rooms.",
        "why": "Participated means nothing. Placement, scale, and what it does.",
    },
    {
        "hook": "Rewrite your internship bullet like this.",
        "weak": "Interned at a startup and did various engineering tasks.",
        "strong": "Shipped 3 features to 20,000 users, including CSV export in Go.",
        "why": "Various tasks hides your best work. Lead with what shipped.",
    },
    {
        "hook": "The weakest word on most student resumes.",
        "weak": "Assisted with machine learning research.",
        "strong": "Trained a CNN that lifted defect detection accuracy from 81% to 93%.",
        "why": "Assisted makes you invisible. Own the piece you actually did.",
    },
    {
        "hook": "Your TA bullet can sound like leadership.",
        "weak": "Teaching assistant for intro to programming.",
        "strong": "Ran weekly labs for 45 students and built an autograder used by 600.",
        "why": "Numbers turn a title into proof you can lead and build.",
    },
    {
        "hook": "This is how a good project bullet reads.",
        "weak": "Created a chatbot using AI.",
        "strong": "Built a course Q&A bot over 400 lecture pages; it answers in 2 seconds.",
        "why": "Using AI is vague. Say the data, the speed, and the use.",
    },
    {
        "hook": "Delete this from your resume today.",
        "weak": "Hardworking team player with strong communication skills.",
        "strong": "Led a 4-person capstone team to ship an app on time for 200 users.",
        "why": "Never claim a trait. Show the moment that proves it.",
    },
    {
        "hook": "Make your club role count on your resume.",
        "weak": "Member of the coding club.",
        "strong": "Organized 6 coding workshops attended by 250 students.",
        "why": "Member is passive. Show what you started or ran.",
    },
]

# Interview dialogues: question, the answer people give, the answer that works.
CHATS = [
    {
        "hook": "Never answer 'tell me about yourself' like this.",
        "question": "So, tell me about yourself.",
        "bad": "Well, I was born in Ohio and I've always liked computers...",
        "good": "I'm a junior in CS. I build backend tools; last summer I cut a report job from 6 hours to 20 minutes.",
        "why": "Present, proof, then why this role. Under 60 seconds.",
    },
    {
        "hook": "When they ask your salary expectations, say this.",
        "question": "What are your salary expectations?",
        "bad": "Um, I'd be happy with anything really.",
        "good": "I'm focused on the right fit. What range did you budget for this role?",
        "why": "Let them name the number first. Many states require the range on the posting anyway.",
    },
    {
        "hook": "The best answer to 'what's your biggest weakness'.",
        "question": "What's your biggest weakness?",
        "bad": "I'm a perfectionist. I just work too hard.",
        "good": "I used to over-polish code. Now I timebox and ship a first version for review.",
        "why": "Real weakness, what you changed, and the result.",
    },
    {
        "hook": "When you don't know the answer in an interview.",
        "question": "How would you design a URL shortener?",
        "bad": "Uh... I'm not sure. I haven't done that before.",
        "good": "Let me start simple: one service, a hash of the URL, and a key value store. Then let's scale it.",
        "why": "Silence fails you. Thinking out loud is what they're grading.",
    },
    {
        "hook": "Say this at the end of every interview.",
        "question": "Do you have any questions for us?",
        "bad": "No, I think you covered everything.",
        "good": "What would make someone a standout intern on this team by week four?",
        "why": "It shows you plan to win, and tells you how they'll grade you.",
    },
    {
        "hook": "Answer 'why this company' like this.",
        "question": "Why do you want to work here?",
        "bad": "You're a big company and the pay is great.",
        "good": "Your payments API is what I used in my side project, and I want to work on the team behind it.",
        "why": "Tie one real thing you used or built to their product.",
    },
    {
        "hook": "How to answer 'tell me about a conflict'.",
        "question": "Tell me about a time you disagreed with a teammate.",
        "bad": "I don't really have conflicts. I get along with everyone.",
        "good": "We split on SQL versus NoSQL. I prototyped both in a day and we picked on real query times.",
        "why": "Disagree, use data, keep the relationship. That's the whole story.",
    },
    {
        "hook": "The recruiter call question most students fumble.",
        "question": "What other companies are you interviewing with?",
        "bad": "Just you guys right now, honestly.",
        "good": "I'm in process with a couple of teams, but this role is my top choice.",
        "why": "Never sound like you have zero options. Stay vague and positive.",
    },
    {
        "hook": "Stuck on a coding question? Say this sentence.",
        "question": "Find the longest substring without repeating characters.",
        "bad": "...",
        "good": "Let me walk a small example first: a, b, c, a. Okay, I'll slide a window and track the last index I saw each letter.",
        "why": "A tiny example out loud buys time and usually reveals the pattern.",
    },
    {
        "hook": "When they ask 'what's your greatest achievement'.",
        "question": "What's the achievement you're most proud of?",
        "bad": "Probably getting good grades.",
        "good": "I built a study room bot my school now runs, 1,200 bookings a month.",
        "why": "Pick something others use. Usage beats GPA.",
    },
]

# Job-search tricks that are true and checkable. "url" pairs show the edit.
HACKS = [
    {
        "hook": "Stop scrolling LinkedIn jobs. Edit the link like this.",
        "site": "linkedin.com/jobs/search",
        "before": "linkedin.com/jobs/search?keywords=software%20intern",
        "after": "linkedin.com/jobs/search?keywords=software%20intern&f_TPR=r3600",
        "explain": "That one bit at the end shows only jobs posted in the last hour.",
        "why": "Applying in the first few hours beats being applicant number 900.",
    },
    {
        "hook": "This LinkedIn filter hides senior roles for you.",
        "site": "linkedin.com/jobs/search",
        "before": "linkedin.com/jobs/search?keywords=software%20engineer",
        "after": "linkedin.com/jobs/search?keywords=software%20engineer&f_E=1%2C2",
        "explain": "That filter keeps only internship and entry level roles.",
        "why": "No more scrolling past jobs that want five years of experience.",
    },
    {
        "hook": "Google can search every Greenhouse job board at once.",
        "site": "google.com",
        "before": "software engineering intern 2027",
        "after": 'site:job-boards.greenhouse.io "software engineer" intern 2027',
        "explain": "The site operator searches thousands of company job boards together.",
        "why": "You find roles at smaller companies that never trend on LinkedIn.",
    },
    {
        "hook": "Search every Lever job board with one line.",
        "site": "google.com",
        "before": "new grad software engineer",
        "after": 'site:jobs.lever.co "new grad" software engineer',
        "explain": "Lever hosts job pages for hundreds of startups. This searches all of them.",
        "why": "Startups often post here first and get far fewer applicants.",
    },
    {
        "hook": "Find only fresh postings on Indeed.",
        "site": "indeed.com/jobs",
        "before": "indeed.com/jobs?q=software+intern",
        "after": "indeed.com/jobs?q=software+intern&fromage=1",
        "explain": "That one bit shows only jobs posted in the last day.",
        "why": "Fresh postings get read by a human more often. Old ones are buried.",
    },
    {
        "hook": "Use Google's date filter for job hunting.",
        "site": "google.com",
        "before": 'site:jobs.ashbyhq.com "software engineer" intern',
        "after": 'site:jobs.ashbyhq.com "software engineer" intern after:2026-10-01',
        "explain": "The after operator only returns pages Google found after that date.",
        "why": "Ashby is what a lot of AI startups use. This surfaces their newest roles.",
    },
]

# One specific application tip per role family, for job reels.
ROLE_TIPS = {
    "ml": "Lead your resume with one model you trained and the metric it hit.",
    "data": "Put one SQL or pandas project with a real dataset at the top.",
    "security": "List a CTF or a vulnerability you reported. It's proof, not a claim.",
    "mobile": "Link an app people can actually download. It beats any bullet.",
    "frontend": "Put a live demo link in your first project bullet.",
    "infra": "Mention something you deployed and kept running, with uptime or users.",
    "hardware": "Show a project with real hardware: a board, a sensor, a robot.",
    "default": "Apply in the first week. Early applicants get read by a human more often.",
}


def role_family(title: str) -> str:
    lowered = title.lower()
    for family, words in (
        ("ml", ("machine learning", " ml", "ai ", "artificial intelligence", "research")),
        ("data", ("data",)),
        ("security", ("security",)),
        ("mobile", ("ios", "android", "mobile")),
        ("frontend", ("frontend", "front-end", "front end", "web")),
        ("infra", ("infrastructure", "platform", "site reliability", "sre", "devops", "cloud")),
        ("hardware", ("hardware", "firmware", "embedded", "electrical", "robotics", "vehicle")),
    ):
        if any(word in f" {lowered} " for word in words):
            return family
    return "default"
