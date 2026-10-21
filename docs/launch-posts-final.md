# Launch Posts — FINAL (copy-paste ready)

Live: https://study-buddy-3m16.onrender.com
Try (no signup): https://study-buddy-3m16.onrender.com/try
Repo: https://github.com/Vivek492005/STUDY-BUDDY
Release v1.0.0: https://github.com/Vivek492005/STUDY-BUDDY/releases/tag/v1.0.0

---

## 1. Show HN

**Title:**
Show HN: Study Buddy – open-source AI career copilot with no-LLM/BYOK/local modes

**URL field:** https://study-buddy-3m16.onrender.com/try

**First comment (post immediately after submitting):**

Hi HN, I'm Vivek, a student, and I built Study Buddy — an open-source
(Flask, MIT) career copilot for students: resume readiness analysis, JD
matching, mock interviews, aptitude/DSA practice, and research-paper Q&A
with citations.

The part I care most about is that your resume doesn't have to go to a
third-party API. Three privacy modes:

- **No-LLM** — full rule-based functionality, zero AI calls
- **BYOK** — your own provider key, encrypted at rest, never logged
- **Local** — point it at Ollama; your text never leaves your machine

A few engineering choices HN might appreciate:

- "Resume Readiness" with evidence-backed feedback instead of a fake
  "ATS score" number
- RAG over your own documents (TF-IDF/BM25 + structure-aware chunking),
  with a published eval harness (recall/MRR/citation validity)
- Prompt-injection defense for uploaded documents — a resume is
  untrusted input
- ~2,900 automated tests, incl. real-Postgres migration tests; the
  production instance is verified end-to-end (auth, quizzes, payments
  of XP, the works)
- Self-service data export/deletion, LLM consent with withdrawal

Under the hood there's also a 91-tool "Ultimate Lab" (everything from a
JD skill-gap analyzer to a citation formatter), skill quizzes (16 skills),
312 aptitude questions, and a 354-question interview bank.

Live demo (no signup): https://study-buddy-3m16.onrender.com/try
Code: https://github.com/Vivek492005/STUDY-BUDDY

I'd love feedback — especially on the privacy-mode design and the eval
methodology. Happy to answer anything about the trade-offs.

---

## 2. Reddit — r/SideProject

**Title:**
I built a privacy-first AI career copilot for students — resume, JD matching, interviews, research Q&A (open-source, live demo, no signup needed to try)

**Body:**

Hey r/SideProject! I'm a student, and after months of building nights,
**Study Buddy v1.0.0** is live.

**What it does:**
- Resume readiness analysis (honest, evidence-backed — no fake "ATS scores")
- JD matching with skill-gap analysis
- Mock interviews with structured scoring rubrics
- Skill quizzes (16 skills), 312 aptitude questions, DSA practice
- Research-paper Q&A with real citations
- A 91-tool "Ultimate Lab" of small career/research utilities

**Why I built it differently:** every career tool I tried wanted me to
upload my resume into a black box. So Study Buddy has three privacy modes:

1. **No-LLM mode** — everything rule-based, zero AI calls
2. **BYOK** — your own API key, encrypted, never logged
3. **Local mode** — run it with Ollama, nothing leaves your machine

**Try it (no signup):** https://study-buddy-3m16.onrender.com/try
**Code (MIT):** https://github.com/Vivek492005/STUDY-BUDDY

Fun launch-week fact: the first three external PRs from contributors
were merged on release day itself — the open-source community showed up
before I did any promotion. There are still `good first issue`s open if
anyone wants in.

Feedback very welcome — what would make you trust (or ditch) a tool
like this?

*Also suitable for: r/opensource (lead with the MIT/privacy angle),
r/learnprogramming (lead with the practice tools). One subreddit at a
time, and read each sub's self-promo rules first.*

---

## 3. Product Hunt

**Name:** Study Buddy

**Tagline (45 chars):** Privacy-first AI career copilot for students

**Topics:** Education · Artificial Intelligence · Career · Open Source

**Description:**

Study Buddy takes students from resume to offer letter — without
uploading their resume to a black box.

📄 **Resume Readiness** — evidence-backed feedback instead of fake ATS
scores
🎯 **JD Matching** — paste a job description, get a skill-gap analysis
🎤 **Mock Interviews** — structured rubrics, a 354-question bank
🧠 **Practice** — 16 skill quizzes, 312 aptitude questions, DSA drills
🔬 **Research Q&A** — ask questions over papers, get cited answers
🧰 **Ultimate Lab** — 91 small tools for careers and research

🔒 **Privacy-first by design:**
- No-LLM mode (fully rule-based, zero AI calls)
- BYOK — your own key, encrypted at rest, never logged
- Local mode via Ollama — your text never leaves your machine
- One-click data export & deletion, revocable AI consent

Open-source (MIT), built by a student, verified end-to-end in
production with ~2,900 automated tests.

**Maker's first comment:**

Hi Product Hunt! 👋 I'm Vivek, a B.Tech student from India. I built
Study Buddy because every AI career tool I tried asked for my resume
and gave back a mysterious "ATS score" from a black box. I wanted the
opposite: honest feedback, real citations, and my data staying mine —
hence the no-LLM / BYOK / local modes.

It's live, free to try (no signup for the demo), and fully open-source.
Three community PRs were merged on launch day — I'd love for you to be
the next contributor, user, or friendly critic. Ask me anything!

**Gallery assets:**
1. Social preview image: `docs-site/docs/assets/social-preview.png`
   (also upload it in GitHub repo Settings → Social preview)
2. Walkthrough video (3 min): `study-buddy-walkthrough.mp4`
3. Screenshots: dashboard, quiz flow, JD match report, Ultimate Lab

**Launch checklist:**
- Schedule for 12:01 AM PT (Product Hunt day starts then)
- Post the maker's first comment immediately at launch
- Reply to every comment within the first hours
- Share the PH link on LinkedIn the same morning

---

## Posting order & timing (notes for Vivek)

1. **Product Hunt** — schedule first; it's a full-day event.
2. **Show HN** — weekday, ~5:30–7:30 PM IST (morning US). Don't post the
   same hour as PH launch; HN and PH audiences overlap.
3. **Reddit r/SideProject** — evening IST; be present for comments.
4. Engage with EVERY comment in the first 48 hours — that's where the
   real users and contributors come from.
5. All three posts link the /try page — no signup wall for first contact.
