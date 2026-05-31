# Hi, I'm Adam Tokár 👋

**Year 5/6 bilingual economic technikum (Hungary) · Building automation that runs while I sleep**

I ship small, focused systems that do one thing well — usually involving an LLM, a scraper, a queue, and a cron.
Most of what's here is side-revenue infra: outbound, job hunting, lead-gen for HU SMBs.

📍 Gyula, Hungary · 🌍 EU/CET · 📬 tkradam0207@gmail.com

---

## What I'm building

| Project | What it does | Stack |
|---|---|---|
| **ApexWeb cold-email infra** | 400–1000 HU SMB emails/day across 10 Rackhost SMTPs. MX-only verification, weekend + HU holiday gating, no em-dash, no "Ingyen". | Python · SQLite · launchd · smtplib · MX lookup |
| **Multi-board auto-apply (Adam lane)** | Pulls RemoteOK / Working Nomads / EU Remote Jobs / Profession.hu / LinkedIn → two-lane gate (auto vs human-review) → Gemini-tailored CV+CL per job → email submit. 08:00 Mon–Fri Hungary. | Python · Gemini 2.5 Flash · Pandoc · WeasyPrint · Supabase |
| **Chris's marketing job tracker** | Discovery-only dashboard for a US marketing director. 7 sources, Gemini fit-scoring, Boston-hybrid geofence. *Does not* apply or write cover letters — purely surfaces. | Python · JobSpy · Gemini · Flask · Netlify |
| **HU SMB lead-gen pipeline** | Scrapes Hungarian SMB directories → enriches → drops verified leads into ApexWeb's cold-email queue. | Python · Playwright · regex · MX checks |

---

## Stack

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-2.5_Flash-4285F4?logo=google&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-Sonnet_4.7-D97757?logo=anthropic&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-3FCF8E?logo=supabase&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-2EAD33?logo=playwright&logoColor=white)
![Netlify](https://img.shields.io/badge/Netlify-00C7B7?logo=netlify&logoColor=white)
![launchd](https://img.shields.io/badge/launchd-macOS-000?logo=apple&logoColor=white)

---

## How I work

- **Cost-discipline first.** Gemini 2.5 Flash over Claude where it's a remix job (~40× cheaper, perfectly capable for CV/CL tailoring).
- **Two-lane safety gates.** Any system that talks to a third party gets an AUTO lane (low blast-radius) and a MANUAL lane (human approval). No reputation damage from a bug.
- **No-paid-subs constraint.** Public APIs, RSS, scraping where ToS-allowed. If a board kills its free tier, I document the disable reason in config and move on.
- **Cron + SQLite > Kubernetes.** Side projects don't need a control plane.

---

## Open to

Remote part-time work I can run from Hungary: VA, ops, automation builds, cold-email setup, no-code/Claude/Gemini integrations. Best fit: async, EU/US time-zones welcome, ~1 hr/day cadence.

📬 **tkradam0207@gmail.com** · LinkedIn coming soon
