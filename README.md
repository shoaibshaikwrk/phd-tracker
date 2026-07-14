# PhD Application Tracker — Neural CS / ML / AI (Fall 2027)

A step-by-step tracker for your PhD applications, adapted from a job-checker
script of the same shape. It has four tabs: **Positions** (individually
funded PhD studentships, refreshed daily), **Professors** (advisors worth
contacting, whether or not they have an advertised opening — uncapped, every
qualifying US + Europe/UK faculty member is included, not a curated top-N),
**Schools** (every US + Europe/UK CS department's website, one click away),
and **Notes** (a daily log + a pinned "where I am right now" line).

## Positions tab — sources

- **19 curated entries** — specific programs, labs, advisors, and
  industry-friendly tracks in ML systems, LLM/RAG, and applied ML /
  time-series forecasting, researched against your background (7+ years
  Data/AI engineering, RAG on Azure AI Foundry, MLOps on Spark/Airflow/
  Kubernetes, completed Master's). See the full writeup and reasoning in the
  companion PhD Roadmap document.
- **jobs.ac.uk (UK)** — refreshed daily, filtered server-side to the "PhDs"
  job-type facet, so every result is an individually-funded PhD studentship
  by construction.
- **AcademicTransfer.com (Netherlands/Europe)** — refreshed daily, filtered
  to titles containing "phd".
- **THEunijobs.com (global)** — Times Higher Education's academic jobs
  board; refreshed daily via its RSS feed (`Keywords=` param), filtered to
  titles/descriptions containing "phd"/"doctoral". Broader geographic
  coverage than the other two (includes continental Europe, Asia-Pacific,
  Middle East academic postings, not just UK/NL).

Nothing is scraped from findaphd.com or academicpositions.com — both block
automated requests (HTTP 403) even with a browser User-Agent. Other places
worth checking by hand (not wired into the scraper, either because they
block bots or because they don't list PhD studentships as postings):
- https://www.findaphd.com/phds/?Keywords=machine+learning — the largest UK/EU aggregator
- https://academicpositions.com/jobs/field/machine-learning
- https://www.nature.com/naturecareers/jobs — global science jobs, JS-rendered (couldn't scrape)
- http://scholarshipdb.net/scholarships/Category-PhD/Keyword-machine-learning
- https://euraxess.ec.europa.eu/jobs/search — EU-wide, JS-rendered (couldn't scrape)
- LinkedIn/X searches for "#PhDposition" or "#AcademicTwitter" — no clean way to automate, but real postings show up there, especially from labs between grant cycles
- Individual department "prospective PhD students" pages for any professor in the Professors tab below — the single best source, since many advisors take students without ever posting an ad

## Professors tab — sources

- **6 curated entries** — hand-picked advisors (Chris Ré, Zhihao Jia, Junjie
  Hu, Laura Dietz, Isabelle Augenstein, Yarin Gal) researched specifically
  against your RAG/MLOps/LLM-infrastructure background, each with a note
  on why they're a fit.
- **~5,700 CSRankings-derived entries, uncapped** — [CSRankings](https://csrankings.org)
  publishes its full underlying dataset as open CSVs on GitHub: a faculty
  roster, an institution→region/country lookup, and per-author per-venue
  per-year publication counts. This rebuilds the same computation
  CSRankings' own site does — recent (last ~5 years) adjusted publication
  counts across AI/ML-adjacent venues (ICML, NeurIPS, ACL, EMNLP, NAACL,
  AAAI, IJCAI, KDD, CVPR/ICCV/ECCV, and ML-systems-adjacent venues like
  OSDI/SOSP/NSDI/EuroSys/SIGMOD/VLDB), restricted to US + Europe/UK
  institutions — to surface actively-publishing faculty, tagged by sub-area
  (LLM & NLP / Broad ML/AI / ML Systems / Applied ML/Vision) and sorted by
  activity. This is real open data, not a scrape of csrankings.org itself.
  **Every** US + Europe/UK faculty member with at least one qualifying
  publication in the window is included — no top-N cutoff — so use the
  search box and area filter to narrow it down rather than expecting a
  short list.

Each professor gets the same kind of status tracking as positions — but a
different workflow, since "applying" isn't the first step with a professor:
**Not Contacted → Emailed → Replied → Call Scheduled / Not a Fit.**

## Schools tab

Every US + Europe/UK institution CSRankings tracks (~460), each linking
straight to that school's official CS department homepage — the same
`homepage` field CSRankings itself publishes, not a scrape. A few curated
entries (schools not tracked by CSRankings, like Northumbria's CDT) are
added on top with the specific program page already researched. Search by
name; click through to browse each department's own PhD admissions page
from there.

## Notes tab

A personal log, separate from the structured status tracking on the other
tabs:
- **Where I am right now** — one pinned line you overwrite whenever your
  overall status changes (e.g. "Drafting SOP, waiting on 2 replies").
- **Daily log** — free-text entries you add as things happen (emails sent,
  replies received, deadlines discovered), newest first, deletable.

On the deployed site this is private to your account (Firestore, under
`phd_user_notes/{your-uid}`) — nobody else signed in can read or write it, same
protection as your CV/resume text in Settings. Locally it's saved in that
browser's storage only.

## Two ways to run this

1. **Locally** (this README) — `config.json` writes a standalone
   `local_preview.html` you can open in any browser, no login required.
2. **As a live website, updated daily automatically** — see
   **[DEPLOY.md](DEPLOY.md)**. Uses `config.web.json` + GitHub Actions +
   GitHub Pages at **phd.placeonus.com**, with Firebase email-link sign-in so
   your status per program is saved and visible across devices.

Both use the exact same `phd_checker.py` — just pointed at different config files.

## Setup

1. Make sure you have Python 3.8+ installed (`python3 --version`).
2. Install the one dependency:
   ```
   pip install -r requirements.txt
   ```
   (On some systems you may need `pip install -r requirements.txt --break-system-packages`.)
3. Run it:
   ```
   python3 phd_checker.py config.json
   ```
4. Open the generated `local_preview.html` in a browser. It has no login —
   your status choices are saved in that browser's local storage.

## config.json / config.web.json reference

| Field | What it does |
|---|---|
| `keywords` | Position titles must contain at least one of these (case-insensitive). Curated entries always pass through regardless. |
| `exclude_keywords` | Titles containing any of these are skipped. |
| `sources.curated` | Include the hand-researched shortlist (default `true`). |
| `sources.jobsacuk` | Scrape jobs.ac.uk, PhD-only (default `true`). |
| `sources.academictransfer` | Scrape AcademicTransfer.com (default `true`). |
| `sources.theunijobs` | Scrape THEunijobs.com via RSS, PhD-filtered (default `true`). |
| `sources.curated_professors` | Include the 6 hand-picked advisors on the Professors tab (default `true`). |
| `sources.csrankings` | Fetch + rank the CSRankings-derived faculty list on the Professors tab, uncapped (default `true`). |
| `sources.schools` | Fetch the Schools tab data (default `true`). |
| `output_csv` / `seen_jobs_file` / `log_file` | Where position results, dedup state, and the run log are written. |
| `professors_file` | Where the Professors tab data is written (`data/professors.json`) — always a fresh full snapshot, not append-only. |
| `schools_file` | Where the Schools tab data is written (`data/schools.json`) — always a fresh full snapshot. |
| `output_html` | Where the generated tracker page is written (`local_preview.html` locally, `docs/index.html` for the website). |

## Using the tracker

**Positions tab:** each row starts with status **To Research**. Suggested workflow, matching
the action plan in the PhD Roadmap document:

`To Research` → `Contacted Advisor` → `Applied` → `Interview` → `Offer` / `Waitlisted` / `Rejected`

The script only ever *appends* new position rows — re-running it never overwrites or
reorders a status you've already set. To start totally fresh, delete
`data/seen_positions.json` and/or `data/phd_positions_found.csv`.

**Professors tab:** each professor starts with status **Not Contacted**.
Suggested workflow: `Not Contacted` → `Emailed` → `Replied` → `Call Scheduled` / `Not a Fit`.
Unlike positions, this list is fully regenerated every run (it's a ranked
snapshot, not a "new items found" feed) — but each professor's status
persists because their ID is derived from their name, which is stable
across runs. Use the search box and research-area filter to narrow down
~140 names to the ones actually relevant to you.

## Running it automatically

### macOS / Linux — cron

```
crontab -e
```
Add a line to run it every day at 8am:
```
0 8 * * * cd /full/path/to/phd-application-tracker && /usr/bin/python3 phd_checker.py >> cron_output.log 2>&1
```

### Windows — Task Scheduler

Create a Basic Task, trigger **Daily**, action **Start a program**:
program `python`, arguments `phd_checker.py`, start-in the folder this is in.

### As a website

See [DEPLOY.md](DEPLOY.md) for the full GitHub Actions + GitHub Pages +
Firebase + custom-domain (phd.placeonus.com) setup — this runs the check
automatically once a day even if your laptop is off.

## Files

| File | Purpose |
|---|---|
| `phd_checker.py` | Main script — run this |
| `config.json` | Local run settings — writes `local_preview.html`, no login |
| `config.web.json` | Website deployment settings — writes to `data/` and `docs/` for GitHub Pages |
| `data/phd_positions_found.csv` | Growing application checklist — every position ever found, with a status column |
| `data/seen_positions.json` | Internal memory of what's already been shown (don't need to touch it) |
| `data/professors.json` | Professors tab data — fully regenerated each run (curated + CSRankings-derived) |
| `data/run_log.txt` | Simple log of each run and how many new positions it found |
| `docs/index.html` | The website version of the tracker (Firebase-gated, shared across signed-in users) |
| `.github/workflows/daily-phd-check.yml` | GitHub Actions workflow that runs the check daily and publishes the site |

## Extending it

- Want another curated position? Add a dict to `CURATED_POSITIONS` in
  `phd_checker.py` — `id`, `title`, `company` (used as "Institution / Lab /
  Advisor"), `location`, `url`.
- Want another curated professor? Add a dict to `CURATED_PROFESSORS` —
  `name`, `company`, `location`, `url`, `tags` (subset of `llm_nlp`,
  `ml_broad`, `ml_systems`, `applied_ml`), `note`.
- Want another live position source? Copy the shape of `fetch_jobsacuk()`,
  `fetch_academictransfer()`, or `fetch_theunijobs()` — each just needs to
  return a list of dicts with `id`, `title`, `company`, `location`, `url`, `source`.
- Want to change which venues count toward the Professors tab, or widen the
  region filter beyond US + Europe/UK? Edit `PROFESSOR_AREA_TAGS` and the
  region check inside `fetch_csrankings_professors()`.
- Want a desktop notification instead of/alongside the tracker? Install
  `plyer` (`pip install plyer`) and call `plyer.notification.notify(...)`
  for each new position inside the `if new_positions:` block in `phd_checker.py`.
