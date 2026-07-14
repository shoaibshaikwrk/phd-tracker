#!/usr/bin/env python3
"""
phd_checker.py

A PhD-application tracker script, adapted from a job-checker script of the
same shape. It combines two things into one running checklist:

  1. A CURATED seed list of ~18 specific PhD programs / labs / advisors /
     industry-friendly tracks in ML systems, LLM & RAG, and applied ML /
     time-series forecasting, hand-researched (US + UK/Europe, Fall 2027
     cycle). These don't change day to day, so they're hardcoded below
     rather than scraped.

  2. LIVE scraped sources for individually-advertised, funded PhD studentship
     postings (the UK/Europe model, where a PhD position is posted like a
     job listing with a close date) — refreshed on every run:
       - jobs.ac.uk    — UK academic jobs board; filtered server-side to the
                         "PhDs" job-type facet, so every result is a PhD
                         studentship by construction.
       - AcademicTransfer.com — Dutch/European academic jobs aggregator;
                         filtered client-side to titles containing "phd"
                         since it has no PhD-only server-side filter.

     Both sites are plain server-rendered HTML (no JS execution needed) but
     have no public JSON API, so this uses light, documented regex parsing
     against their current page structure — the same trade-off the original
     job-checker made for Google/Apple job pages. If either site changes its
     markup, that one fetcher may start returning 0 results; it's wrapped in
     try/except so it won't take down the rest of the run.

     NOTE: findaphd.com and academicpositions.com — the two biggest PhD
     listing aggregators — both return HTTP 403 (bot-blocked, Cloudflare)
     even with a browser User-Agent, so they are NOT scraped here. They're
     still worth checking manually; links are in README.md.

Usage:
    python3 phd_checker.py [path/to/config.json]

Designed to be run manually, via cron, or on a daily GitHub Actions schedule
(see .github/workflows/daily-phd-check.yml).
"""

import csv
import json
import os
import re
import sys
from datetime import datetime, timezone

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

CSV_FIELDNAMES = ["id", "found_at", "status", "title", "company", "location", "source", "url"]
DEFAULT_STATUS = "To Research"


def log(msg, log_path=None):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {msg}"
    print(line)
    if log_path:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def load_config(config_path):
    if not os.path.exists(config_path):
        print(f"ERROR: config.json not found at {config_path}")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_seen(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return set(json.load(f))
            except json.JSONDecodeError:
                return set()
    return set()


def save_seen(path, seen_ids):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(seen_ids), f, indent=2)


def matches_keywords(title, keywords, exclude_keywords):
    title_lower = title.lower()
    if any(ex.lower() in title_lower for ex in exclude_keywords):
        return False
    return any(kw.lower() in title_lower for kw in keywords)


# ---------------------------------------------------------------------------
# 1. Curated seed list — hand-researched, not scraped. See README.md for the
#    full research writeup these are drawn from. "company" field is reused
#    here to mean "Institution / Lab / Advisor" — the field is displayed
#    under that label in the UI, kept as "company" internally to match the
#    existing CSV/JS schema.
# ---------------------------------------------------------------------------

CURATED_POSITIONS = [
    {
        "id": "curated_cmu_ml_phd",
        "title": "PhD in Machine Learning — home of the Catalyst ML-systems group. Early deadline Nov 18, 2026; final Dec 9, 2026. Fully funded, GRE optional.",
        "company": "Carnegie Mellon University — Machine Learning Dept.",
        "location": "Pittsburgh, PA, USA",
        "url": "https://www.ml.cmu.edu/academics/machine-learning-phd",
    },
    {
        "id": "curated_cmu_catalyst",
        "title": "Catalyst research group — ML systems, LLM serving/inference optimization (Zhihao Jia et al.). Apply via the CMU ML PhD program above and reference this group.",
        "company": "Carnegie Mellon University — Catalyst Group",
        "location": "Pittsburgh, PA, USA",
        "url": "https://catalyst.cs.cmu.edu/",
    },
    {
        "id": "curated_cmu_zhihao_jia",
        "title": "Prof. Zhihao Jia — LLM serving systems & inference efficiency. Strong fit for Azure AI Foundry / AI-infrastructure background. Email before applying.",
        "company": "Carnegie Mellon University — Zhihao Jia's lab",
        "location": "Pittsburgh, PA, USA",
        "url": "https://www.cs.cmu.edu/~zhihaoj2/",
    },
    {
        "id": "curated_northeastern_khoury_phd",
        "title": "PhD in Computer Science — deadline Dec 15, 2026. Test-optional; “advanced entry” petition available for Master's holders; rolling review.",
        "company": "Northeastern University — Khoury College",
        "location": "Boston, MA, USA",
        "url": "https://www.khoury.northeastern.edu/programs/computer-science-phd/",
    },
    {
        "id": "curated_northeastern_industry_phd",
        "title": "Industry/Experiential PhD — continue working while doing the PhD, paired with a faculty advisor + a company mentor. Confirm which departments currently participate.",
        "company": "Northeastern University — Industry PhD track",
        "location": "Boston, MA, USA (hybrid with employer)",
        "url": "https://phd.northeastern.edu/industry-and-experiential-phd-program/",
    },
    {
        "id": "curated_columbia_cs_phd",
        "title": "PhD in Computer Science — deadline Dec 15, 2026 for Fall admission.",
        "company": "Columbia University — Dept. of Computer Science",
        "location": "New York, NY, USA",
        "url": "https://www.cs.columbia.edu/education/admissions8/",
    },
    {
        "id": "curated_uiuc_vision_ml",
        "title": "Computer Vision & Machine Learning Group — actively seeking PhD students, deadline Dec 1, 2026, 5-year TA/RA funding guarantee.",
        "company": "University of Illinois Urbana-Champaign — Siebel School",
        "location": "Urbana-Champaign, IL, USA",
        "url": "https://vision.ischool.illinois.edu/openings/",
    },
    {
        "id": "curated_stanford_cs_phd",
        "title": "PhD in Computer Science — one admissions cycle/year; check exact Fall 2027 date on this page closer to the cycle.",
        "company": "Stanford University — Dept. of Computer Science",
        "location": "Stanford, CA, USA",
        "url": "https://www.cs.stanford.edu/admissions-graduate-application-deadlines",
    },
    {
        "id": "curated_stanford_hazy",
        "title": "Hazy Research (Chris Ré) — foundation-model systems, data-centric AI, weak supervision. Directly adjacent to production RAG/LLM-systems work.",
        "company": "Stanford University — Hazy Research",
        "location": "Stanford, CA, USA",
        "url": "https://hazyresearch.stanford.edu/",
    },
    {
        "id": "curated_gatech_ml_phd",
        "title": "ML PhD — cross-school program; faculty can advise regardless of home department. Browse core/affiliated faculty here before applying.",
        "company": "Georgia Institute of Technology — ML @ GT",
        "location": "Atlanta, GA, USA",
        "url": "https://ml.gatech.edu/people/faculty/phdprogramfaculty",
    },
    {
        "id": "curated_berkeley_sky",
        "title": "Sky Computing Lab (successor to RISELab) — distributed systems for ML/cloud infrastructure; has produced Amazon AI PhD Fellows. Apply via UC Berkeley EECS PhD.",
        "company": "UC Berkeley — Sky Computing Lab",
        "location": "Berkeley, CA, USA",
        "url": "https://sky.cs.berkeley.edu/",
    },
    {
        "id": "curated_unh_trema",
        "title": "TREMA Lab (Laura Dietz) — RAG evaluation, works directly with companies deploying GenAI/RAG/search in production. Unusually direct fit for applied-RAG backgrounds.",
        "company": "University of New Hampshire — TREMA Lab",
        "location": "Durham, NH, USA",
        "url": "https://www.cs.unh.edu/~dietz/",
    },
    {
        "id": "curated_copenlu",
        "title": "CopeNLU (Isabelle Augenstein & Pepa Atanasova) — actively recruiting PhD + postdoc on RAG robustness / LLM susceptibility to false information.",
        "company": "University of Copenhagen — CopeNLU",
        "location": "Copenhagen, Denmark",
        "url": "https://copenlu.github.io/",
    },
    {
        "id": "curated_oxford_oatml",
        "title": "OATML (Yarin Gal) — applied/theoretical ML via the Oxford DPhil route. Most Oxford scholarship-linked deadlines land around Dec 2, noon UK time.",
        "company": "University of Oxford — OATML",
        "location": "Oxford, UK",
        "url": "https://oatml.cs.ox.ac.uk/apply.html",
    },
    {
        "id": "curated_ukri_cdt_overview",
        "title": "UKRI Centres for Doctoral Training in AI — 4-year, fully funded (fees + ~£21,805/yr 2026-27 stipend), co-funded with ~370 industry partners. Full current list of centres here.",
        "company": "UKRI — AI Centres for Doctoral Training (multiple UK universities)",
        "location": "Various UK universities",
        "url": "https://www.ukri.org/opportunity/ukri-centres-for-doctoral-training-in-artificial-intelligence/",
    },
    {
        "id": "curated_bristol_cdt",
        "title": "CDT in Practice-Oriented AI — applications open for Sept 2026 entry.",
        "company": "University of Bristol — UKRI CDT",
        "location": "Bristol, UK",
        "url": "https://www.bristol.ac.uk/cdt/practice-oriented-ai/",
    },
    {
        "id": "curated_northumbria_cdt",
        "title": "CDT in Citizen-Centred AI — next cohort applications open Dec 2025; verify current window.",
        "company": "Northumbria University — UKRI CDT",
        "location": "Newcastle, UK",
        "url": "https://www.northumbria.ac.uk/about-us/our-schools/school-of-computer-science/citizen-centred-artificial-intelligence/apply-for-a-phd/",
    },
    {
        "id": "curated_fau_professional_phd",
        "title": "Professional PhD in Computer Science — evenings/weekends/hybrid, built for working professionals in research/technical-leadership roles.",
        "company": "Florida Atlantic University",
        "location": "Boca Raton, FL, USA",
        "url": "https://www.fau.edu/engineering/eecs/graduate/professional-programs/professional-phd/",
    },
    {
        "id": "curated_nova_se_cs_phd",
        "title": "PhD in Computer Science — structured for working professionals, no residency requirement.",
        "company": "Nova Southeastern University",
        "location": "Fort Lauderdale, FL, USA (online-hybrid)",
        "url": "https://computing.nova.edu/degrees/doctoral/computer-science.html",
    },
]

for _row in CURATED_POSITIONS:
    _row["source"] = "Curated"
    _row["us_confirmed"] = True


# ---------------------------------------------------------------------------
# 2. Live sources. Each returns a list of dicts:
#    {id, title, company, location, url, source, us_confirmed}
# ---------------------------------------------------------------------------

def fetch_jobsacuk(keyword, max_results=40):
    """jobs.ac.uk, filtered server-side to the "PhDs" job-type facet
    (jobTypeFacet[]=phds), so every result returned is a PhD studentship by
    construction — no title-based PhD filtering needed for this source.
    """
    positions = []
    try:
        resp = requests.get(
            "https://www.jobs.ac.uk/search/",
            params={"keywords": keyword, "jobTypeFacet[]": "phds"},
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        html = resp.text
        chunks = html.split('data-advert-id="')[1:]
        for chunk in chunks[:max_results]:
            m_id = re.match(r'(\d+)"', chunk)
            m_link = re.search(r'<a href="(/job/[^"]+)">\s*([^<]+?)\s*</a>', chunk, re.S)
            if not m_id or not m_link:
                continue
            m_emp = re.search(r'j-search-result__employer">\s*<b>([^<]+)</b>', chunk, re.S)
            m_loc = re.search(r'>Location:\s*([^<]+?)\s*</div>', chunk, re.S)
            m_close = re.search(
                r'j-search-result__date-span j-search-result__date--blue[^>]*>\s*([^<]+?)\s*</span>',
                chunk, re.S,
            )
            title = m_link.group(2).strip()
            # A handful of listings on jobs.ac.uk leak a CMS placeholder like
            # "PhD Opportunity Title" into the visible title text itself —
            # strip that boilerplate and collapse any resulting whitespace/tabs.
            title = re.sub(r"\bPhD Opportunity Title\b", "", title, flags=re.I)
            title = re.sub(r"\s+", " ", title).strip(" :-")
            closes = m_close.group(1).strip() if m_close else ""
            if closes:
                title = f"{title} (closes {closes})"
            positions.append({
                "id": f"jobsacuk_{m_id.group(1)}",
                "title": title,
                "company": (m_emp.group(1).strip() if m_emp else "See listing"),
                "location": (m_loc.group(1).strip() if m_loc else "UK"),
                "url": "https://www.jobs.ac.uk" + m_link.group(1),
                "source": "jobs.ac.uk",
                "us_confirmed": True,
            })
    except Exception as e:
        print(f"  [jobsacuk:{keyword}] fetch failed: {e}")
    return positions


def fetch_academictransfer(keyword, max_results=25):
    """AcademicTransfer.com (Netherlands/Europe academic jobs aggregator).
    No server-side PhD-only filter exists here, so results are filtered to
    titles containing "phd" client-side after fetching.
    """
    positions = []
    try:
        resp = requests.get(
            "https://www.academictransfer.com/en/jobs/",
            params={"q": keyword},
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        html = resp.text
        pattern = re.compile(r'href="(/en/jobs/(\d+)/[^"]+/)"[^>]*>.*?<h3[^>]*>([^<]+)</h3>', re.S)
        for href, job_id, title in pattern.findall(html)[:max_results]:
            title_clean = re.sub(r"&amp;", "&", title).strip()
            if "phd" not in title_clean.lower():
                continue
            positions.append({
                "id": f"academictransfer_{job_id}",
                "title": title_clean,
                "company": "See listing (AcademicTransfer)",
                "location": "Netherlands / Europe",
                "url": "https://www.academictransfer.com" + href,
                "source": "AcademicTransfer",
                "us_confirmed": True,
            })
    except Exception as e:
        print(f"  [academictransfer:{keyword}] fetch failed: {e}")
    return positions


def fetch_theunijobs(keyword, max_results=40):
    """Times Higher Education Unijobs — global academic jobs board (not just
    UK), covering Europe, Asia-Pacific, Middle East, etc. Has a clean RSS
    feed with a working keyword filter (param is "Keywords", case-sensitive)
    — no HTML scraping needed for this one. No PhD-only server-side filter,
    so results are filtered client-side to titles/descriptions that look
    like a PhD/doctoral position.
    """
    positions = []
    try:
        resp = requests.get(
            "https://www.timeshighereducation.com/unijobs/jobsrss/",
            params={"Keywords": keyword},
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        xml = resp.text
        items = re.findall(r"<item>(.*?)</item>", xml, re.S)
        phd_pattern = re.compile(r"\b(phd|doctoral)\b", re.I)
        for item in items[:max_results]:
            m_title = re.search(r"<title>(.*?)</title>", item, re.S)
            m_link = re.search(r"<link>(.*?)</link>", item, re.S)
            m_desc = re.search(r"<description>(.*?)</description>", item, re.S)
            m_guid = re.search(r'<guid[^>]*>(.*?)</guid>', item, re.S)
            if not m_title or not m_link:
                continue
            title_raw = m_title.group(1).strip()
            desc = (m_desc.group(1) if m_desc else "").strip()
            if not phd_pattern.search(title_raw) and not phd_pattern.search(desc):
                continue
            # Titles are formatted "INSTITUTION: Role" — split those apart.
            if ":" in title_raw:
                institution, role = title_raw.split(":", 1)
                institution = institution.strip().title()
                role = role.strip()
            else:
                institution, role = "See listing", title_raw
            # Location is typically the last non-empty line of the description.
            desc_lines = [ln.strip() for ln in desc.splitlines() if ln.strip()]
            location = desc_lines[-1] if desc_lines else "See listing"
            job_id = re.search(r"/listing/(\d+)/", m_link.group(1))
            positions.append({
                "id": f"theunijobs_{job_id.group(1) if job_id else abs(hash(m_link.group(1)))}",
                "title": role,
                "company": institution,
                "location": location,
                "url": m_link.group(1).strip(),
                "source": "THEunijobs",
                "us_confirmed": True,
            })
    except Exception as e:
        print(f"  [theunijobs:{keyword}] fetch failed: {e}")
    return positions


# ---------------------------------------------------------------------------
# 3. Professors tab data. Two sources merged together:
#
#    a) CURATED_PROFESSORS — hand-picked advisors specifically researched
#       against your background (see the PhD Roadmap document), each with a
#       "note" explaining the fit.
#
#    b) CSRankings-derived — CSRankings (csrankings.org) publishes its full
#       underlying dataset as open CSVs on GitHub: a faculty roster
#       (name/affiliation/homepage), an institution->region/country lookup,
#       and per-author per-venue per-year publication counts (DBLP-derived,
#       "adjustedcount" already divides credit among co-authors the same way
#       CSRankings' own site does). This rebuilds the same computation
#       CSRankings' website does — sum adjusted publication counts across
#       target AI/ML-adjacent venues over the last few years, restricted to
#       US + Europe/UK institutions — to surface actively-publishing faculty
#       who are typically the ones taking PhD students, well beyond what
#       could reasonably be hand-curated. This is real, open, and doesn't
#       require scraping — it's the same data CSRankings itself publishes.
# ---------------------------------------------------------------------------

CURATED_PROFESSORS = [
    {
        "name": "Chris Ré",
        "company": "Stanford University — Hazy Research",
        "location": "Stanford, CA, USA",
        "url": "https://hazyresearch.stanford.edu/",
        "tags": ["llm_nlp", "ml_systems"],
        "note": "Foundation-model systems, data-centric AI, weak supervision — directly adjacent to production RAG/LLM-systems work.",
    },
    {
        "name": "Zhihao Jia",
        "company": "Carnegie Mellon University — Catalyst Group",
        "location": "Pittsburgh, PA, USA",
        "url": "https://www.cs.cmu.edu/~zhihaoj2/",
        "tags": ["ml_systems"],
        "note": "LLM serving systems & inference efficiency. Strong fit for Azure AI Foundry / AI-infrastructure background.",
    },
    {
        "name": "Junjie Hu",
        "company": "University of Wisconsin–Madison",
        "location": "Madison, WI, USA",
        "url": "https://junjiehu.github.io/",
        "tags": ["llm_nlp"],
        "note": "Actively recruits 1–3 PhD students most cycles; LLM interpretability, multilingual NLP, language agents. Asks applicants to name him in their research statement.",
    },
    {
        "name": "Laura Dietz",
        "company": "University of New Hampshire — TREMA Lab",
        "location": "Durham, NH, USA",
        "url": "https://www.cs.unh.edu/~dietz/",
        "tags": ["llm_nlp"],
        "note": "RAG evaluation, works directly with companies deploying GenAI/RAG/search in production — unusually direct fit for applied-RAG backgrounds.",
    },
    {
        "name": "Isabelle Augenstein",
        "company": "University of Copenhagen — CopeNLU",
        "location": "Copenhagen, Denmark",
        "url": "https://copenlu.github.io/",
        "tags": ["llm_nlp"],
        "note": "Actively recruiting PhD + postdoc on RAG robustness / LLM susceptibility to false information.",
    },
    {
        "name": "Yarin Gal",
        "company": "University of Oxford — OATML",
        "location": "Oxford, UK",
        "url": "https://oatml.cs.ox.ac.uk/apply.html",
        "tags": ["ml_broad"],
        "note": "Applied/theoretical ML via the Oxford DPhil route. Most Oxford scholarship-linked deadlines land around Dec 2, noon UK time.",
    },
]

for _p in CURATED_PROFESSORS:
    _p["source"] = "Curated"
    _p["score"] = None
    _p["id"] = "prof_curated_" + re.sub(r"[^a-z0-9]+", "_", _p["name"].lower()).strip("_")

CSRANKINGS_BASE = "https://raw.githubusercontent.com/emeryberger/CSrankings/gh-pages/"

# CSRankings venue codes grouped into the sub-areas shown as filterable tags.
# MLOps/"ML systems" has no dedicated CSRankings venue, so systems + database
# venues (where ML-infrastructure work is typically published) are used as
# the closest available proxy.
PROFESSOR_AREA_TAGS = {
    "llm_nlp": {"acl", "emnlp", "naacl"},
    "ml_broad": {"icml", "nips", "iclr", "aaai", "ijcai"},
    "ml_systems": {"osdi", "sosp", "nsdi", "eurosys", "sigmod", "vldb"},
    "applied_ml": {"kdd", "cvpr", "iccv", "eccv"},
}
PROFESSOR_ALL_VENUES = set().union(*PROFESSOR_AREA_TAGS.values())


def fetch_csrankings_professors(recent_years=5):
    """See module docstring section 3(b) above. Returns a list of dicts in
    the same shape as CURATED_PROFESSORS (minus "note"). Network calls hit
    raw.githubusercontent.com (CSRankings' own published data export), not
    csrankings.org itself — no HTML scraping involved.

    No cap on how many are returned — every US + Europe/UK faculty member
    in the CSRankings roster with at least one publication in a target venue
    in the last `recent_years` years is included, by design (maximize
    coverage rather than showing a curated top-N). Use the search box and
    tag filter in the UI to narrow this down, not a smaller server-side list.
    """
    professors = []
    try:
        fac = {}
        resp = requests.get(CSRANKINGS_BASE + "csrankings.csv", headers=HEADERS, timeout=30)
        resp.raise_for_status()
        for row in csv.DictReader(resp.text.splitlines()):
            fac[row["name"]] = row

        inst = {}
        resp = requests.get(CSRANKINGS_BASE + "institutions.csv", headers=HEADERS, timeout=30)
        resp.raise_for_status()
        for row in csv.DictReader(resp.text.splitlines()):
            inst[row["institution"]] = row

        resp = requests.get(CSRANKINGS_BASE + "generated-author-info.csv", headers=HEADERS, timeout=60)
        resp.raise_for_status()

        year_min = datetime.now(timezone.utc).year - recent_years
        totals = {}
        tag_totals = {}
        for row in csv.DictReader(resp.text.splitlines()):
            area = row.get("area", "")
            if area not in PROFESSOR_ALL_VENUES:
                continue
            try:
                year = int(row["year"])
                adj = float(row["adjustedcount"])
            except (ValueError, TypeError):
                continue
            if year < year_min:
                continue
            name = row["name"]
            totals[name] = totals.get(name, 0.0) + adj
            per_tag = tag_totals.setdefault(name, {})
            for tag, venues in PROFESSOR_AREA_TAGS.items():
                if area in venues:
                    per_tag[tag] = per_tag.get(tag, 0.0) + adj

        # Region-filtered, faculty-roster-joined candidate pool.
        candidates = []
        for name, total in totals.items():
            facrow = fac.get(name)
            if not facrow:
                continue
            instrow = inst.get(facrow["affiliation"])
            if not instrow:
                continue
            if not (instrow["countryabbrv"] == "us" or instrow["region"] == "europe"):
                continue
            tags_for_name = tag_totals.get(name, {})
            candidates.append({
                "name": name,
                "company": facrow["affiliation"],
                "location": instrow["countryabbrv"].upper(),
                "url": facrow["homepage"],
                "tags": tags_for_name,
                "score": round(total, 1),
            })

        for c in candidates:
            professors.append({
                "id": "prof_csr_" + re.sub(r"[^a-z0-9]+", "_", c["name"].lower()).strip("_"),
                "name": c["name"],
                "company": c["company"],
                "location": c["location"],
                "url": c["url"],
                "tags": sorted(c["tags"].keys(), key=lambda t: -c["tags"][t]),
                "score": c["score"],
                "source": "CSRankings",
                "note": "",
            })
    except Exception as e:
        print(f"  [csrankings] fetch failed: {e}")
    return professors


# ---------------------------------------------------------------------------
# 4. Schools tab data. Every US + Europe/UK institution in CSRankings'
#    institutions.csv, each with its official CS department homepage link
#    (that's literally what CSRankings calls "homepage" for that entry — not
#    a scrape, it's the field this open dataset publishes). A small override
#    dict points a handful of curated institutions at a more specific page
#    (e.g. a program's own PhD-apply page) where one was already researched,
#    or fills in a school CSRankings doesn't track at all (e.g. Northumbria).
# ---------------------------------------------------------------------------

SCHOOL_LINKS = {
    "Northumbria University": "https://www.northumbria.ac.uk/about-us/our-schools/school-of-computer-science/citizen-centred-artificial-intelligence/apply-for-a-phd/",
}


def fetch_schools():
    """All US + Europe/UK institutions from CSRankings' institutions.csv,
    each with its CS department homepage. See section 4 docstring above.
    """
    schools = []
    try:
        resp = requests.get(CSRANKINGS_BASE + "institutions.csv", headers=HEADERS, timeout=30)
        resp.raise_for_status()
        for row in csv.DictReader(resp.text.splitlines()):
            if not (row["countryabbrv"] == "us" or row["region"] == "europe"):
                continue
            name = row["institution"]
            schools.append({
                "id": "school_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"),
                "name": name,
                "url": SCHOOL_LINKS.get(name, row["homepage"]),
                "location": row["countryabbrv"].upper(),
            })
        for name, url in SCHOOL_LINKS.items():
            if not any(s["name"] == name for s in schools):
                schools.append({
                    "id": "school_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"),
                    "name": name,
                    "url": url,
                    "location": "UK",
                })
    except Exception as e:
        print(f"  [schools] fetch failed: {e}")
    schools.sort(key=lambda s: s["name"])
    return schools


def build_professors(sources_cfg):
    professors = []
    if sources_cfg.get("curated_professors", True):
        professors.extend(CURATED_PROFESSORS)
    if sources_cfg.get("csrankings", True):
        print("Fetching CSRankings faculty + publication data (this pulls a ~17MB dataset, may take a bit)...")
        csr = fetch_csrankings_professors()
        print(f"  CSRankings candidates after region + recency filtering: {len(csr)}")
        curated_names = {p["name"].lower() for p in professors}
        for p in csr:
            if p["name"].lower() in curated_names:
                continue  # already represented via the hand-curated entry
            professors.append(p)
    # Curated entries first (score=None sorts last numerically, so give them
    # a high sentinel instead), then by score descending.
    professors.sort(key=lambda p: -(p["score"] if p["score"] is not None else 1e9))
    return professors


TAG_LABELS = {
    "llm_nlp": "LLM & NLP",
    "ml_broad": "Broad ML/AI",
    "ml_systems": "ML Systems",
    "applied_ml": "Applied ML/Vision",
}

# Shared CSS + tab/professors JS used by both generate_html() and
# generate_html_auth() so the two don't drift out of sync.
_SHARED_CSS = """
  .tabs { display: flex; gap: 4px; margin-bottom: 14px; border-bottom: 1px solid #ccc; }
  .tab-btn { padding: 8px 18px; border: 1px solid #ccc; border-bottom: none; border-radius: 6px 6px 0 0;
             background: transparent; color: inherit; cursor: pointer; font-size: 0.9rem; margin-bottom: -1px; }
  .tab-btn.active { background: rgba(37,99,235,0.1); border-color: #2563eb; color: #2563eb; font-weight: 600; }
  .panel.hidden { display: none; }
  .prof-link { text-decoration: none; font-weight: 600; }
  .prof-link:hover { text-decoration: underline; }
  .tag-pill { display: inline-block; font-size: 0.7rem; padding: 1px 7px; border-radius: 999px;
              border: 1px solid #999; margin: 1px 3px 1px 0; }
  .prof-note { font-size: 0.8rem; color: #666; margin-top: 3px; max-width: 360px; }
  .score-cell { font-variant-numeric: tabular-nums; color: #555; }
  .school-link { text-decoration: none; font-weight: 600; }
  .school-link:hover { text-decoration: underline; }
  .notes-current { width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid #ccc;
                    border-radius: 8px; font-family: inherit; font-size: 0.95rem; resize: vertical;
                    margin-bottom: 10px; min-height: 2.4em; }
  .notes-add-row { display: flex; gap: 8px; margin-bottom: 20px; align-items: flex-start; }
  .notes-add-row textarea { flex: 1; box-sizing: border-box; padding: 8px 10px; border: 1px solid #ccc;
                             border-radius: 6px; font-family: inherit; font-size: 0.9rem; resize: vertical; min-height: 4.5em; }
  .note-entry { border: 1px solid #e2e2e2; border-radius: 8px; padding: 10px 14px; margin-bottom: 10px; }
  .note-entry-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; }
  .note-entry-date { font-size: 0.78rem; color: #888; font-weight: 600; }
  .note-entry-text { white-space: pre-wrap; font-size: 0.9rem; }
  .note-delete { background: none; border: none; color: #999; cursor: pointer; font-size: 0.8rem; }
  .note-delete:hover { color: #dc2626; }
  .section-label { font-size: 0.85rem; font-weight: 600; margin: 4px 0 6px; color: #555; }
"""

_TAG_LABELS_JS = "const TAG_LABELS = " + json.dumps(TAG_LABELS) + ";"

_PROFESSORS_PANEL_HTML = """
<div id="professorsPanel" class="panel hidden">
  <div class="controls">
    <input type="text" id="profSearch" placeholder="Search name or institution...">
    <select class="filter" id="profTagFilter">
      <option value="">All research areas</option>
    </select>
    <select class="filter" id="profStatusFilter">
      <option value="">All statuses</option>
      <option>Not Contacted</option>
      <option>Emailed</option>
      <option>Replied</option>
      <option>Call Scheduled</option>
      <option>Not a Fit</option>
    </select>
  </div>
  <table>
    <thead>
      <tr>
        <th>__PROF_STATUS_HEADER__</th>
        <th>Name</th>
        <th>Institution</th>
        <th>Location</th>
        <th>Research Areas</th>
        <th>Recent Activity</th>
      </tr>
    </thead>
    <tbody id="profRows"></tbody>
  </table>
</div>
"""

_SCHOOLS_PANEL_HTML = """
<div id="schoolsPanel" class="panel hidden">
  <div class="controls">
    <input type="text" id="schoolSearch" placeholder="Search school name...">
  </div>
  <table>
    <thead>
      <tr>
        <th>School</th>
        <th>Location</th>
        <th>Website</th>
      </tr>
    </thead>
    <tbody id="schoolRows"></tbody>
  </table>
</div>
"""

_NOTES_PANEL_HTML = """
<div id="notesPanel" class="panel hidden">
  <div class="section-label">Where I am right now</div>
  <textarea id="notesCurrent" class="notes-current" placeholder="e.g. Drafting research statement, contacted 3 advisors, waiting to hear back from CopeNLU..." rows="2"></textarea>

  <div class="section-label">Add a daily log entry</div>
  <div class="notes-add-row">
    <textarea id="notesNewEntry" placeholder="What happened today? Emails sent, replies received, deadlines you found, decisions made..."></textarea>
    <button class="btn btn-primary" id="notesAddBtn">Add entry</button>
  </div>

  <div class="section-label">Log</div>
  <div id="notesLog"></div>
</div>
"""


def generate_html(rows, professors, schools, output_path):
    """Simple, login-free tracker page for local use: a single self-contained
    HTML file with all position, professor, AND school data embedded as
    inline JSON. Status/notes are saved in that browser's localStorage
    (per-device, not shared) — no Firebase project needed. Good for a quick
    local look; use generate_html_auth() (config.web.json / the deployed
    site) for a shared, cross-device tracker.
    """
    rows_sorted = sorted(rows, key=lambda r: r.get("found_at", ""), reverse=True)
    positions_json = json.dumps(rows_sorted, ensure_ascii=False)
    professors_json = json.dumps(professors, ensure_ascii=False)
    schools_json = json.dumps(schools, ensure_ascii=False)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PhD Application Tracker (local preview)</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         max-width: 1150px; margin: 0 auto; padding: 24px 16px 64px; line-height: 1.4; }
  h1 { font-size: 1.5rem; margin-bottom: 4px; }
  .meta { color: #666; font-size: 0.85rem; margin-bottom: 20px; }
  .stats { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
  .stat { border: 1px solid #ccc; border-radius: 8px; padding: 8px 14px; font-size: 0.85rem; }
  .stat b { display: block; font-size: 1.2rem; }
  .controls { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; align-items: center; }
  input[type=text] { padding: 7px 10px; border: 1px solid #ccc; border-radius: 6px; min-width: 220px; }
  select.filter { padding: 7px 10px; border: 1px solid #ccc; border-radius: 6px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e2e2e2; vertical-align: top; }
  th { position: sticky; top: 0; background: Canvas; cursor: default; }
  tr:hover { background: rgba(127,127,127,0.08); }
  a.pos-link { text-decoration: none; font-weight: 600; }
  a.pos-link:hover { text-decoration: underline; }
  .institution { color: #555; font-size: 0.85rem; }
  select.status { padding: 5px 6px; border-radius: 6px; border: 1px solid #ccc; font-size: 0.85rem; }
  .found-at, .source { color: #777; font-size: 0.8rem; white-space: nowrap; }
  .badge-curated { display: inline-block; font-size: 0.7rem; padding: 1px 6px; border-radius: 999px; border: 1px solid #888; margin-left: 6px; }
""" + _SHARED_CSS + """
</style>
</head>
<body>
<h1>PhD Application Tracker (local preview)</h1>
<div class="meta">Last updated __GENERATED_AT__ &middot; status saved in this browser only (no login) &middot; use the deployed site for a shared, cross-device tracker</div>

<div class="stats" id="stats"></div>

<div class="tabs">
  <button class="tab-btn active" id="tabBtnPositions">Positions</button>
  <button class="tab-btn" id="tabBtnProfessors">Professors</button>
  <button class="tab-btn" id="tabBtnSchools">Schools</button>
  <button class="tab-btn" id="tabBtnNotes">Notes</button>
</div>

<div id="positionsPanel" class="panel">
<div class="controls">
  <input type="text" id="search" placeholder="Search program, advisor, or institution...">
  <select class="filter" id="statusFilter">
    <option value="">All statuses</option>
    <option>To Research</option>
    <option>Contacted Advisor</option>
    <option>Applied</option>
    <option>Interview</option>
    <option>Offer</option>
    <option>Waitlisted</option>
    <option>Rejected</option>
  </select>
  <select class="filter" id="sourceFilter">
    <option value="">All sources</option>
  </select>
</div>

<table>
  <thead>
    <tr>
      <th>Status</th>
      <th>Program / Position</th>
      <th>Institution</th>
      <th>Location</th>
      <th>Source</th>
      <th>Found</th>
    </tr>
  </thead>
  <tbody id="posRows"></tbody>
</table>
</div>

""" + _PROFESSORS_PANEL_HTML.replace("__PROF_STATUS_HEADER__", "Status") + _SCHOOLS_PANEL_HTML + _NOTES_PANEL_HTML + """

<script>
""" + _TAG_LABELS_JS + """
const POSITIONS = __POSITIONS_JSON__;
const PROFESSORS = __PROFESSORS_JSON__;
const SCHOOLS = __SCHOOLS_JSON__;
const STATUS_OPTIONS = ["To Research", "Contacted Advisor", "Applied", "Interview", "Offer", "Waitlisted", "Rejected"];
const PROF_STATUS_OPTIONS = ["Not Contacted", "Emailed", "Replied", "Call Scheduled", "Not a Fit"];
const STORAGE_PREFIX = "phdtracker_status_";
const PROF_STORAGE_PREFIX = "phdtracker_profstatus_";
const NOTES_CURRENT_KEY = "phdtracker_notes_current";
const NOTES_LOG_KEY = "phdtracker_notes_log";

function getStatus(pos) {
  return localStorage.getItem(STORAGE_PREFIX + pos.id) || pos.status || "To Research";
}
function setStatus(posId, status) {
  localStorage.setItem(STORAGE_PREFIX + posId, status);
}
function getProfStatus(prof) {
  return localStorage.getItem(PROF_STORAGE_PREFIX + prof.id) || "Not Contacted";
}
function setProfStatus(profId, status) {
  localStorage.setItem(PROF_STORAGE_PREFIX + profId, status);
}

const TABS = ["positions", "professors", "schools", "notes"];
document.getElementById("tabBtnPositions").addEventListener("click", () => switchTab("positions"));
document.getElementById("tabBtnProfessors").addEventListener("click", () => switchTab("professors"));
document.getElementById("tabBtnSchools").addEventListener("click", () => switchTab("schools"));
document.getElementById("tabBtnNotes").addEventListener("click", () => switchTab("notes"));
function switchTab(which) {
  TABS.forEach(t => {
    document.getElementById(t + "Panel").classList.toggle("hidden", t !== which);
    document.getElementById("tabBtn" + t[0].toUpperCase() + t.slice(1)).classList.toggle("active", t === which);
  });
}

function renderStats(positions) {
  const counts = {};
  STATUS_OPTIONS.forEach(s => counts[s] = 0);
  positions.forEach(p => { const s = getStatus(p); counts[s] = (counts[s] || 0) + 1; });
  const statsEl = document.getElementById("stats");
  statsEl.innerHTML = `<div class="stat"><b>${positions.length}</b>Positions</div>` +
    STATUS_OPTIONS.map(s => `<div class="stat"><b>${counts[s] || 0}</b>${s}</div>`).join("") +
    `<div class="stat"><b>${PROFESSORS.length}</b>Professors</div>`;
}

function populateSourceFilter(positions) {
  const sources = [...new Set(positions.map(p => p.source))].sort();
  const sel = document.getElementById("sourceFilter");
  sources.forEach(s => {
    const opt = document.createElement("option");
    opt.value = s; opt.textContent = s;
    sel.appendChild(opt);
  });
}

function populateTagFilter() {
  const sel = document.getElementById("profTagFilter");
  Object.keys(TAG_LABELS).forEach(tag => {
    const opt = document.createElement("option");
    opt.value = tag; opt.textContent = TAG_LABELS[tag];
    sel.appendChild(opt);
  });
}

function render() {
  const search = document.getElementById("search").value.toLowerCase();
  const statusFilter = document.getElementById("statusFilter").value;
  const sourceFilter = document.getElementById("sourceFilter").value;
  const tbody = document.getElementById("posRows");
  tbody.innerHTML = "";

  POSITIONS.forEach(pos => {
    const status = getStatus(pos);
    if (statusFilter && status !== statusFilter) return;
    if (sourceFilter && pos.source !== sourceFilter) return;
    const haystack = (pos.title + " " + pos.company).toLowerCase();
    if (search && !haystack.includes(search)) return;

    const tr = document.createElement("tr");

    const statusTd = document.createElement("td");
    const select = document.createElement("select");
    select.className = "status";
    STATUS_OPTIONS.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s; opt.textContent = s;
      if (s === status) opt.selected = true;
      select.appendChild(opt);
    });
    select.addEventListener("change", () => {
      setStatus(pos.id, select.value);
      renderStats(POSITIONS);
    });
    statusTd.appendChild(select);
    tr.appendChild(statusTd);

    const posTd = document.createElement("td");
    const link = document.createElement("a");
    link.href = pos.url; link.target = "_blank"; link.rel = "noopener";
    link.className = "pos-link"; link.textContent = pos.title;
    posTd.appendChild(link);
    if (pos.source === "Curated") {
      const badge = document.createElement("span");
      badge.className = "badge-curated"; badge.textContent = "researched";
      posTd.appendChild(badge);
    }
    tr.appendChild(posTd);

    const instTd = document.createElement("td");
    instTd.className = "institution"; instTd.textContent = pos.company;
    tr.appendChild(instTd);

    const locTd = document.createElement("td");
    locTd.textContent = pos.location || "";
    tr.appendChild(locTd);

    const sourceTd = document.createElement("td");
    sourceTd.className = "source"; sourceTd.textContent = pos.source;
    tr.appendChild(sourceTd);

    const foundTd = document.createElement("td");
    foundTd.className = "found-at"; foundTd.textContent = (pos.found_at || "").replace(" UTC", "");
    tr.appendChild(foundTd);

    tbody.appendChild(tr);
  });

  renderStats(POSITIONS);
}

function renderProfessors() {
  const search = document.getElementById("profSearch").value.toLowerCase();
  const tagFilter = document.getElementById("profTagFilter").value;
  const statusFilter = document.getElementById("profStatusFilter").value;
  const tbody = document.getElementById("profRows");
  tbody.innerHTML = "";

  PROFESSORS.forEach(prof => {
    const status = getProfStatus(prof);
    if (statusFilter && status !== statusFilter) return;
    if (tagFilter && !(prof.tags || []).includes(tagFilter)) return;
    const haystack = (prof.name + " " + prof.company).toLowerCase();
    if (search && !haystack.includes(search)) return;

    const tr = document.createElement("tr");

    const statusTd = document.createElement("td");
    const select = document.createElement("select");
    select.className = "status";
    PROF_STATUS_OPTIONS.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s; opt.textContent = s;
      if (s === status) opt.selected = true;
      select.appendChild(opt);
    });
    select.addEventListener("change", () => {
      setProfStatus(prof.id, select.value);
    });
    statusTd.appendChild(select);
    tr.appendChild(statusTd);

    const nameTd = document.createElement("td");
    const link = document.createElement("a");
    link.href = prof.url; link.target = "_blank"; link.rel = "noopener";
    link.className = "prof-link"; link.textContent = prof.name;
    nameTd.appendChild(link);
    if (prof.source === "Curated") {
      const badge = document.createElement("span");
      badge.className = "badge-curated"; badge.textContent = "researched";
      nameTd.appendChild(badge);
    }
    if (prof.note) {
      const noteDiv = document.createElement("div");
      noteDiv.className = "prof-note"; noteDiv.textContent = prof.note;
      nameTd.appendChild(noteDiv);
    }
    tr.appendChild(nameTd);

    const instTd = document.createElement("td");
    instTd.className = "institution"; instTd.textContent = prof.company;
    tr.appendChild(instTd);

    const locTd = document.createElement("td");
    locTd.textContent = prof.location || "";
    tr.appendChild(locTd);

    const tagsTd = document.createElement("td");
    (prof.tags || []).forEach(t => {
      const pill = document.createElement("span");
      pill.className = "tag-pill"; pill.textContent = TAG_LABELS[t] || t;
      tagsTd.appendChild(pill);
    });
    tr.appendChild(tagsTd);

    const scoreTd = document.createElement("td");
    scoreTd.className = "score-cell";
    scoreTd.textContent = prof.score != null ? prof.score : "—";
    scoreTd.title = "Adjusted publication count across target venues, last ~5 years (CSRankings methodology)";
    tr.appendChild(scoreTd);

    tbody.appendChild(tr);
  });
}

function renderSchools() {
  const search = document.getElementById("schoolSearch").value.toLowerCase();
  const tbody = document.getElementById("schoolRows");
  tbody.innerHTML = "";
  SCHOOLS.forEach(school => {
    if (search && !school.name.toLowerCase().includes(search)) return;
    const tr = document.createElement("tr");

    const nameTd = document.createElement("td");
    const link = document.createElement("a");
    link.href = school.url; link.target = "_blank"; link.rel = "noopener";
    link.className = "school-link"; link.textContent = school.name;
    nameTd.appendChild(link);
    tr.appendChild(nameTd);

    const locTd = document.createElement("td");
    locTd.textContent = school.location || "";
    tr.appendChild(locTd);

    const linkTd = document.createElement("td");
    const link2 = document.createElement("a");
    link2.href = school.url; link2.target = "_blank"; link2.rel = "noopener";
    link2.textContent = school.url.replace(/^https?:\\/\\//, "").replace(/\\/$/, "");
    linkTd.appendChild(link2);
    tr.appendChild(linkTd);

    tbody.appendChild(tr);
  });
}

function loadNotes() {
  document.getElementById("notesCurrent").value = localStorage.getItem(NOTES_CURRENT_KEY) || "";
}
function saveCurrentNote() {
  localStorage.setItem(NOTES_CURRENT_KEY, document.getElementById("notesCurrent").value);
}
function getNotesLog() {
  try { return JSON.parse(localStorage.getItem(NOTES_LOG_KEY) || "[]"); }
  catch (e) { return []; }
}
function saveNotesLog(log) {
  localStorage.setItem(NOTES_LOG_KEY, JSON.stringify(log));
}
function renderNotesLog() {
  const log = getNotesLog();
  const container = document.getElementById("notesLog");
  container.innerHTML = "";
  if (log.length === 0) {
    container.innerHTML = '<p class="modal-hint">No entries yet — add your first one above.</p>';
    return;
  }
  log.slice().reverse().forEach(entry => {
    const div = document.createElement("div");
    div.className = "note-entry";
    const head = document.createElement("div");
    head.className = "note-entry-head";
    const dateSpan = document.createElement("span");
    dateSpan.className = "note-entry-date";
    dateSpan.textContent = entry.date;
    head.appendChild(dateSpan);
    const delBtn = document.createElement("button");
    delBtn.className = "note-delete";
    delBtn.textContent = "Delete";
    delBtn.addEventListener("click", () => {
      const updated = getNotesLog().filter(e => e.id !== entry.id);
      saveNotesLog(updated);
      renderNotesLog();
    });
    head.appendChild(delBtn);
    div.appendChild(head);
    const textDiv = document.createElement("div");
    textDiv.className = "note-entry-text";
    textDiv.textContent = entry.text;
    div.appendChild(textDiv);
    container.appendChild(div);
  });
}
document.getElementById("notesCurrent").addEventListener("input", saveCurrentNote);
document.getElementById("notesAddBtn").addEventListener("click", () => {
  const ta = document.getElementById("notesNewEntry");
  const text = ta.value.trim();
  if (!text) return;
  const now = new Date();
  const log = getNotesLog();
  log.push({
    id: now.getTime() + "_" + Math.random().toString(36).slice(2, 8),
    date: now.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }),
    text: text,
  });
  saveNotesLog(log);
  ta.value = "";
  renderNotesLog();
});

populateSourceFilter(POSITIONS);
populateTagFilter();
document.getElementById("search").addEventListener("input", render);
document.getElementById("statusFilter").addEventListener("change", render);
document.getElementById("sourceFilter").addEventListener("change", render);
document.getElementById("profSearch").addEventListener("input", renderProfessors);
document.getElementById("profTagFilter").addEventListener("change", renderProfessors);
document.getElementById("profStatusFilter").addEventListener("change", renderProfessors);
document.getElementById("schoolSearch").addEventListener("input", renderSchools);
render();
renderProfessors();
renderSchools();
loadNotes();
renderNotesLog();
</script>
</body>
</html>
"""
    html = html.replace("__GENERATED_AT__", generated_at)
    html = html.replace("__POSITIONS_JSON__", positions_json)
    html = html.replace("__PROFESSORS_JSON__", professors_json)
    html = html.replace("__SCHOOLS_JSON__", schools_json)

    folder = os.path.dirname(output_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def generate_html_auth(rows, professors, schools, output_path):
    """Firebase-authenticated PhD application tracker. Every signed-in user
    sees the same list of positions AND professors, and can set their OWN
    status per row (Firestore, keyed by row id + email) — "Also: X (Applied)"
    shows what others signed in have marked, same pattern as the original
    job-checker's shared checklist.
    """
    rows_sorted = sorted(rows, key=lambda r: r.get("found_at", ""), reverse=True)
    positions_json = json.dumps(rows_sorted, ensure_ascii=False)
    professors_json = json.dumps(professors, ensure_ascii=False)
    schools_json = json.dumps(schools, ensure_ascii=False)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PhD Application Tracker</title>
<script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-auth-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-storage-compat.js"></script>
<script src="firebase-config.js"></script>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         max-width: 1150px; margin: 0 auto; padding: 24px 16px 64px; line-height: 1.4; }
  h1 { font-size: 1.5rem; margin-bottom: 4px; }
  .meta { color: #666; font-size: 0.85rem; margin-bottom: 20px; }
  .stats { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
  .stat { border: 1px solid #ccc; border-radius: 8px; padding: 8px 14px; font-size: 0.85rem; }
  .stat b { display: block; font-size: 1.2rem; }
  .controls { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; align-items: center; }
  input[type=text], input[type=email] { padding: 7px 10px; border: 1px solid #ccc; border-radius: 6px; min-width: 220px; }
  select.filter { padding: 7px 10px; border: 1px solid #ccc; border-radius: 6px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e2e2e2; vertical-align: top; }
  th { position: sticky; top: 0; background: Canvas; cursor: default; }
  tr:hover { background: rgba(127,127,127,0.08); }
  a.pos-link { text-decoration: none; font-weight: 600; }
  a.pos-link:hover { text-decoration: underline; }
  .institution { color: #555; font-size: 0.85rem; }
  select.status { padding: 5px 6px; border-radius: 6px; border: 1px solid #ccc; font-size: 0.85rem; }
  .applied-by { font-size: 0.75rem; color: #888; margin-top: 4px; max-width: 240px; }
  .found-at, .source { color: #777; font-size: 0.8rem; white-space: nowrap; }
  .badge-curated { display: inline-block; font-size: 0.7rem; padding: 1px 6px; border-radius: 999px; border: 1px solid #888; margin-left: 6px; }
  .topbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }
  .topbar-right { display: flex; align-items: center; gap: 10px; font-size: 0.85rem; }
  .btn { display: inline-block; padding: 8px 16px; border-radius: 6px; border: 1px solid #888;
         background: transparent; cursor: pointer; font-size: 0.9rem; text-decoration: none; color: inherit; }
  .btn:hover { background: rgba(127,127,127,0.12); }
  .btn-primary { border-color: #2563eb; color: #2563eb; font-weight: 600; }
  #loginScreen { max-width: 420px; margin: 15vh auto 0; text-align: center; }
  #loginScreen input { width: 100%; box-sizing: border-box; margin-bottom: 10px; }
  #loginStatus { font-size: 0.85rem; color: #666; margin-top: 12px; min-height: 1.2em; }
  .hidden { display: none; }
  .btn-small { padding: 4px 10px; font-size: 0.8rem; }
  .notes-input { width: 100%; box-sizing: border-box; padding: 5px 6px; border: 1px solid #ccc;
                 border-radius: 6px; font-size: 0.8rem; margin-top: 4px; }
  .drawer-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 99; }
  .drawer { position: fixed; top: 0; right: 0; bottom: 0; width: min(440px, 100vw);
            background: Canvas; color: CanvasText; z-index: 100; box-shadow: -6px 0 24px rgba(0,0,0,0.25);
            padding: 24px; overflow-y: auto; box-sizing: border-box; }
  .drawer h2 { margin-top: 0; font-size: 1.2rem; }
  .drawer-close { float: right; }
  .modal-section { margin-bottom: 16px; }
  .modal-section label { display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 6px; }
  .modal-section input[type=file], .modal-section input[type=password] { width: 100%; box-sizing: border-box;
    padding: 7px 10px; border: 1px solid #ccc; border-radius: 6px; }
  .modal-hint { font-size: 0.78rem; color: #777; margin-top: 6px; }
  .modal-subtitle { font-size: 0.9rem; color: #555; margin-bottom: 10px; }
  .modal-status { font-size: 0.85rem; color: #666; margin-top: 10px; min-height: 1.2em; }
  .modal-actions { display: flex; gap: 10px; }
  textarea { width: 100%; box-sizing: border-box; padding: 8px 10px; border: 1px solid #ccc;
             border-radius: 6px; font-family: inherit; font-size: 0.85rem; resize: vertical; }
  .optional-tag { font-size: 0.75rem; font-weight: 400; color: #888; }
""" + _SHARED_CSS + """
</style>
</head>
<body>

<div id="loginScreen">
  <h1>PhD Application Tracker</h1>
  <p>Sign in with your email to view and update your tracker.
     No password — we'll email you a one-time sign-in link.</p>
  <input type="email" id="emailInput" placeholder="you@example.com">
  <button class="btn btn-primary" id="sendLinkBtn" style="width:100%">Send me a sign-in link</button>
  <div id="loginStatus"></div>
</div>

<div id="appScreen" class="hidden">
  <div class="topbar">
    <div>
      <h1>PhD Application Tracker</h1>
      <div class="meta">Neural Computer Science / ML / AI — Fall 2027 cycle. Last updated __GENERATED_AT__ &middot; regenerated automatically once a day</div>
    </div>
    <div class="topbar-right">
      <button class="btn" id="settingsBtn" title="Upload your CV / research statement and add an OpenAI key to tailor materials per program">&#9881; Settings</button>
      <span id="whoami"></span>
      <button class="btn" id="signOutBtn">Sign out</button>
    </div>
  </div>

  <div class="stats" id="stats"></div>

  <div class="tabs">
    <button class="tab-btn active" id="tabBtnPositions">Positions</button>
    <button class="tab-btn" id="tabBtnProfessors">Professors</button>
    <button class="tab-btn" id="tabBtnSchools">Schools</button>
    <button class="tab-btn" id="tabBtnNotes">Notes</button>
  </div>

  <div id="positionsPanel" class="panel">
  <div class="controls">
    <input type="text" id="search" placeholder="Search program, advisor, or institution...">
    <select class="filter" id="statusFilter">
      <option value="">All statuses</option>
      <option>To Research</option>
      <option>Contacted Advisor</option>
      <option>Applied</option>
      <option>Interview</option>
      <option>Offer</option>
      <option>Waitlisted</option>
      <option>Rejected</option>
    </select>
    <select class="filter" id="sourceFilter">
      <option value="">All sources</option>
    </select>
  </div>

  <table>
    <thead>
      <tr>
        <th>Your Status</th>
        <th>Program / Position</th>
        <th>Institution</th>
        <th>Location</th>
        <th>Source</th>
        <th>Found</th>
        <th>AI Tailoring <span class="optional-tag">(optional)</span></th>
      </tr>
    </thead>
    <tbody id="posRows"></tbody>
  </table>
  </div>

""" + _PROFESSORS_PANEL_HTML.replace("__PROF_STATUS_HEADER__", "Your Status") + _SCHOOLS_PANEL_HTML + _NOTES_PANEL_HTML + """

</div>

<div id="settingsBackdrop" class="drawer-backdrop hidden"></div>
<div id="settingsModal" class="drawer hidden">
  <button class="btn drawer-close" id="closeSettingsBtn">Close</button>
  <h2>Settings</h2>
  <p class="modal-hint">Everything here is tied to your own signed-in account and only ever visible to you.</p>

  <div class="modal-section">
    <label for="resumeFileInput">Your CV / resume file (PDF or Word)</label>
    <input type="file" id="resumeFileInput" accept=".pdf,.doc,.docx">
    <div class="modal-hint" id="resumeFileCurrent"></div>
  </div>

  <div class="modal-section">
    <label for="resumeTextInput">CV / research-statement text (plain text — used as the starting point for AI tailoring)</label>
    <textarea id="resumeTextInput" rows="8" placeholder="Paste your CV or research statement draft here..."></textarea>
  </div>

  <div class="modal-section">
    <label for="openaiKeyInput">OpenAI API key <span class="optional-tag">(optional — only needed for the "Tailor" AI feature)</span></label>
    <input type="password" id="openaiKeyInput" placeholder="Paste your key here, e.g. sk-...">
    <div class="modal-hint">Stored only in your browser (localStorage) — never saved to Firestore
      or seen by anyone else. Get one at platform.openai.com/api-keys.</div>
  </div>

  <div class="modal-actions">
    <button class="btn btn-primary" id="saveSettingsBtn">Save</button>
  </div>
  <div id="settingsStatus" class="modal-status"></div>
</div>

<div id="tailorBackdrop" class="drawer-backdrop hidden"></div>
<div id="tailorModal" class="drawer hidden">
  <button class="btn drawer-close" id="closeTailorBtn">Close</button>
  <h2>AI-Tailored Materials <span class="optional-tag">(optional)</span></h2>
  <div id="tailorPosTitle" class="modal-subtitle"></div>
  <div id="tailorStatus" class="modal-status"></div>
  <button class="btn btn-primary hidden" id="openSettingsFromTailorBtn">Add my OpenAI API key</button>
  <textarea id="tailorOutput" rows="18" placeholder="Optional — add your OpenAI API key in Settings, then click &quot;Tailor&quot; on a program to get a version of your CV/statement rewritten toward that program. Output appears here." readonly></textarea>
  <div class="modal-actions">
    <button class="btn" id="copyTailorBtn">Copy to clipboard</button>
  </div>
</div>

<script>
""" + _TAG_LABELS_JS + """
const POSITIONS = __POSITIONS_JSON__;
const PROFESSORS = __PROFESSORS_JSON__;
const SCHOOLS = __SCHOOLS_JSON__;
const STATUS_OPTIONS = ["To Research", "Contacted Advisor", "Applied", "Interview", "Offer", "Waitlisted", "Rejected"];
const PROF_STATUS_OPTIONS = ["Not Contacted", "Emailed", "Replied", "Call Scheduled", "Not a Fit"];

firebase.initializeApp(firebaseConfig);
const auth = firebase.auth();
const db = firebase.firestore();
const storage = firebase.storage();

const loginScreen = document.getElementById("loginScreen");
const appScreen = document.getElementById("appScreen");
const loginStatus = document.getElementById("loginStatus");
const emailInput = document.getElementById("emailInput");

let currentEmail = null;
let currentUid = null;
let statusByPos = {};
let statusByProf = {};
let myResumeText = "";
let myApiKey = "";
let myNotesLog = [];
let notesSaveTimer = null;

function docIdFor(posId, email) {
  return posId + "__" + email.replace(/[^a-zA-Z0-9]/g, "_");
}

const TABS = ["positions", "professors", "schools", "notes"];
document.getElementById("tabBtnPositions").addEventListener("click", () => switchTab("positions"));
document.getElementById("tabBtnProfessors").addEventListener("click", () => switchTab("professors"));
document.getElementById("tabBtnSchools").addEventListener("click", () => switchTab("schools"));
document.getElementById("tabBtnNotes").addEventListener("click", () => switchTab("notes"));
function switchTab(which) {
  TABS.forEach(t => {
    document.getElementById(t + "Panel").classList.toggle("hidden", t !== which);
    document.getElementById("tabBtn" + t[0].toUpperCase() + t.slice(1)).classList.toggle("active", t === which);
  });
}

async function loadUserResume() {
  if (!currentUid) return;
  try {
    const doc = await db.collection("phd_user_resumes").doc(currentUid).get();
    if (doc.exists) myResumeText = doc.data().resumeText || "";
  } catch (err) {
    console.error("Failed to load your saved materials:", err);
  }
  document.getElementById("resumeTextInput").value = myResumeText;
}

function loadApiKeyFromBrowser() {
  myApiKey = window.localStorage.getItem("openaiApiKey") || "";
  document.getElementById("openaiKeyInput").value = myApiKey;
}

function openSettings(focusApiKey) {
  closeTailorDrawer();
  document.getElementById("settingsBackdrop").classList.remove("hidden");
  document.getElementById("settingsModal").classList.remove("hidden");
  if (focusApiKey) document.getElementById("openaiKeyInput").focus();
}
function closeSettings() {
  document.getElementById("settingsBackdrop").classList.add("hidden");
  document.getElementById("settingsModal").classList.add("hidden");
  document.getElementById("saveSettingsBtn").disabled = false;
  document.getElementById("settingsStatus").textContent = "";
}
document.getElementById("settingsBtn").addEventListener("click", () => openSettings(false));
document.getElementById("closeSettingsBtn").addEventListener("click", closeSettings);
document.getElementById("settingsBackdrop").addEventListener("click", closeSettings);

document.getElementById("saveSettingsBtn").addEventListener("click", async () => {
  const statusEl = document.getElementById("settingsStatus");
  const saveBtn = document.getElementById("saveSettingsBtn");
  saveBtn.disabled = true;
  statusEl.textContent = "Saving...";
  try {
    const apiKey = document.getElementById("openaiKeyInput").value.trim();
    window.localStorage.setItem("openaiApiKey", apiKey);
    myApiKey = apiKey;

    const resumeText = document.getElementById("resumeTextInput").value;
    myResumeText = resumeText;

    await db.collection("phd_user_resumes").doc(currentUid).set({
      email: currentEmail,
      resumeText: resumeText,
      updatedAt: firebase.firestore.FieldValue.serverTimestamp(),
    }, { merge: true });

    statusEl.textContent = "Saved.";
    setTimeout(() => { statusEl.textContent = ""; }, 2500);
  } catch (err) {
    statusEl.textContent = "Error: " + err.message;
  } finally {
    saveBtn.disabled = false;
  }
});

function openTailorDrawer() {
  closeSettings();
  document.getElementById("tailorBackdrop").classList.remove("hidden");
  document.getElementById("tailorModal").classList.remove("hidden");
}
function closeTailorDrawer() {
  document.getElementById("tailorBackdrop").classList.add("hidden");
  document.getElementById("tailorModal").classList.add("hidden");
}
document.getElementById("closeTailorBtn").addEventListener("click", closeTailorDrawer);
document.getElementById("tailorBackdrop").addEventListener("click", closeTailorDrawer);
document.getElementById("openSettingsFromTailorBtn").addEventListener("click", () => openSettings(true));

document.getElementById("copyTailorBtn").addEventListener("click", async () => {
  const ta = document.getElementById("tailorOutput");
  const btn = document.getElementById("copyTailorBtn");
  const text = ta.value;
  if (!text) return;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      ta.removeAttribute("readonly"); ta.select();
      document.execCommand("copy"); ta.setAttribute("readonly", "readonly");
    }
    const original = btn.textContent;
    btn.textContent = "Copied!";
    setTimeout(() => { btn.textContent = original; }, 1500);
  } catch (err) {
    btn.textContent = "Copy failed — select the text manually";
    setTimeout(() => { btn.textContent = "Copy to clipboard"; }, 2500);
  }
});

async function tailorForPosition(pos) {
  openTailorDrawer();
  document.getElementById("tailorPosTitle").textContent = pos.title + " — " + pos.company + " (" + (pos.location || "") + ")";
  const statusEl = document.getElementById("tailorStatus");
  const outEl = document.getElementById("tailorOutput");
  const apiKeyBtn = document.getElementById("openSettingsFromTailorBtn");
  outEl.value = "";
  apiKeyBtn.classList.add("hidden");

  if (!myApiKey) {
    statusEl.textContent = "This feature is optional. Add your OpenAI API key to generate tailored materials for this program.";
    apiKeyBtn.classList.remove("hidden");
    return;
  }
  if (!myResumeText) {
    statusEl.textContent = "Paste your CV/research-statement text in Settings first — it's the starting point the AI edits.";
    return;
  }
  if (!firebaseConfig.cloudFunctionsBaseUrl) {
    statusEl.textContent = "AI tailoring isn't set up on this site yet — see DEPLOY.md.";
    return;
  }

  statusEl.textContent = "Generating tailored materials (10-20 seconds)...";
  try {
    const resp = await fetch(firebaseConfig.cloudFunctionsBaseUrl + "/tailorApplication", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        apiKey: myApiKey,
        resumeText: myResumeText,
        position: { title: pos.title, company: pos.company, location: pos.location, source: pos.source },
      }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || ("Request failed (" + resp.status + ")"));
    outEl.value = data.tailoredText || "";
    statusEl.textContent = "Done — review carefully before using; AI output can be wrong.";
  } catch (err) {
    statusEl.textContent = "Error: " + err.message;
  }
}

document.getElementById("sendLinkBtn").addEventListener("click", () => {
  const email = emailInput.value.trim();
  if (!email || !email.includes("@")) {
    loginStatus.textContent = "Enter a valid email address.";
    return;
  }
  const actionCodeSettings = { url: window.location.href, handleCodeInApp: true };
  loginStatus.textContent = "Sending...";
  auth.sendSignInLinkToEmail(email, actionCodeSettings).then(() => {
    window.localStorage.setItem("emailForSignIn", email);
    loginStatus.textContent = "Check " + email + " for your sign-in link.";
  }).catch(err => {
    loginStatus.textContent = "Error: " + err.message;
  });
});

document.getElementById("signOutBtn").addEventListener("click", () => {
  auth.signOut().then(() => window.location.reload());
});

async function loadStatuses() {
  const snapshot = await db.collection("phd_position_status").get();
  statusByPos = {};
  snapshot.forEach(doc => {
    const d = doc.data();
    if (!statusByPos[d.posId]) statusByPos[d.posId] = [];
    statusByPos[d.posId].push(d);
  });
}

async function loadProfStatuses() {
  const snapshot = await db.collection("phd_professor_status").get();
  statusByProf = {};
  snapshot.forEach(doc => {
    const d = doc.data();
    if (!statusByProf[d.profId]) statusByProf[d.profId] = [];
    statusByProf[d.profId].push(d);
  });
}

function getMyStatus(posId) {
  const entries = statusByPos[posId] || [];
  const mine = entries.find(e => e.email === currentEmail);
  return mine ? mine.status : "To Research";
}

function getOthersText(posId) {
  const entries = statusByPos[posId] || [];
  const others = entries.filter(e => e.email !== currentEmail && e.status !== "To Research");
  if (others.length === 0) return "";
  return "Also: " + others.map(e => e.email + " (" + e.status + ")").join(", ");
}

function getMyProfStatus(profId) {
  const entries = statusByProf[profId] || [];
  const mine = entries.find(e => e.email === currentEmail);
  return mine ? mine.status : "Not Contacted";
}

function getOthersProfText(profId) {
  const entries = statusByProf[profId] || [];
  const others = entries.filter(e => e.email !== currentEmail && e.status !== "Not Contacted");
  if (others.length === 0) return "";
  return "Also: " + others.map(e => e.email + " (" + e.status + ")").join(", ");
}

function renderStats() {
  const counts = {};
  STATUS_OPTIONS.forEach(s => counts[s] = 0);
  POSITIONS.forEach(p => { const s = getMyStatus(p.id); counts[s] = (counts[s] || 0) + 1; });
  const statsEl = document.getElementById("stats");
  statsEl.innerHTML = `<div class="stat"><b>${POSITIONS.length}</b>Positions</div>` +
    STATUS_OPTIONS.map(s => `<div class="stat"><b>${counts[s] || 0}</b>${s}</div>`).join("") +
    `<div class="stat"><b>${PROFESSORS.length}</b>Professors</div>`;
}

function populateSourceFilter() {
  const sources = [...new Set(POSITIONS.map(p => p.source))].sort();
  const sel = document.getElementById("sourceFilter");
  sources.forEach(s => {
    const opt = document.createElement("option");
    opt.value = s; opt.textContent = s;
    sel.appendChild(opt);
  });
}

function populateTagFilter() {
  const sel = document.getElementById("profTagFilter");
  Object.keys(TAG_LABELS).forEach(tag => {
    const opt = document.createElement("option");
    opt.value = tag; opt.textContent = TAG_LABELS[tag];
    sel.appendChild(opt);
  });
}

function renderProfessors() {
  const search = document.getElementById("profSearch").value.toLowerCase();
  const tagFilter = document.getElementById("profTagFilter").value;
  const statusFilter = document.getElementById("profStatusFilter").value;
  const tbody = document.getElementById("profRows");
  tbody.innerHTML = "";

  PROFESSORS.forEach(prof => {
    const status = getMyProfStatus(prof.id);
    if (statusFilter && status !== statusFilter) return;
    if (tagFilter && !(prof.tags || []).includes(tagFilter)) return;
    const haystack = (prof.name + " " + prof.company).toLowerCase();
    if (search && !haystack.includes(search)) return;

    const tr = document.createElement("tr");

    const statusTd = document.createElement("td");
    const select = document.createElement("select");
    select.className = "status";
    PROF_STATUS_OPTIONS.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s; opt.textContent = s;
      if (s === status) opt.selected = true;
      select.appendChild(opt);
    });
    select.addEventListener("change", async () => {
      const docId = docIdFor(prof.id, currentEmail);
      await db.collection("phd_professor_status").doc(docId).set({
        profId: prof.id,
        email: currentEmail,
        status: select.value,
        updatedAt: firebase.firestore.FieldValue.serverTimestamp(),
      });
      const entries = statusByProf[prof.id] || (statusByProf[prof.id] = []);
      const existing = entries.find(e => e.email === currentEmail);
      if (existing) existing.status = select.value;
      else entries.push({ email: currentEmail, status: select.value });
      othersDiv.textContent = getOthersProfText(prof.id);
    });
    statusTd.appendChild(select);
    const othersDiv = document.createElement("div");
    othersDiv.className = "applied-by";
    othersDiv.textContent = getOthersProfText(prof.id);
    statusTd.appendChild(othersDiv);
    tr.appendChild(statusTd);

    const nameTd = document.createElement("td");
    const link = document.createElement("a");
    link.href = prof.url; link.target = "_blank"; link.rel = "noopener";
    link.className = "prof-link"; link.textContent = prof.name;
    nameTd.appendChild(link);
    if (prof.source === "Curated") {
      const badge = document.createElement("span");
      badge.className = "badge-curated"; badge.textContent = "researched";
      nameTd.appendChild(badge);
    }
    if (prof.note) {
      const noteDiv = document.createElement("div");
      noteDiv.className = "prof-note"; noteDiv.textContent = prof.note;
      nameTd.appendChild(noteDiv);
    }
    tr.appendChild(nameTd);

    const instTd = document.createElement("td");
    instTd.className = "institution"; instTd.textContent = prof.company;
    tr.appendChild(instTd);

    const locTd = document.createElement("td");
    locTd.textContent = prof.location || "";
    tr.appendChild(locTd);

    const tagsTd = document.createElement("td");
    (prof.tags || []).forEach(t => {
      const pill = document.createElement("span");
      pill.className = "tag-pill"; pill.textContent = TAG_LABELS[t] || t;
      tagsTd.appendChild(pill);
    });
    tr.appendChild(tagsTd);

    const scoreTd = document.createElement("td");
    scoreTd.className = "score-cell";
    scoreTd.textContent = prof.score != null ? prof.score : "—";
    scoreTd.title = "Adjusted publication count across target venues, last ~5 years (CSRankings methodology)";
    tr.appendChild(scoreTd);

    tbody.appendChild(tr);
  });
}

function render() {
  const search = document.getElementById("search").value.toLowerCase();
  const statusFilter = document.getElementById("statusFilter").value;
  const sourceFilter = document.getElementById("sourceFilter").value;
  const tbody = document.getElementById("posRows");
  tbody.innerHTML = "";

  POSITIONS.forEach(pos => {
    const status = getMyStatus(pos.id);
    if (statusFilter && status !== statusFilter) return;
    if (sourceFilter && pos.source !== sourceFilter) return;
    const haystack = (pos.title + " " + pos.company).toLowerCase();
    if (search && !haystack.includes(search)) return;

    const tr = document.createElement("tr");

    const statusTd = document.createElement("td");
    const select = document.createElement("select");
    select.className = "status";
    STATUS_OPTIONS.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s; opt.textContent = s;
      if (s === status) opt.selected = true;
      select.appendChild(opt);
    });
    select.addEventListener("change", async () => {
      const docId = docIdFor(pos.id, currentEmail);
      await db.collection("phd_position_status").doc(docId).set({
        posId: pos.id,
        email: currentEmail,
        status: select.value,
        updatedAt: firebase.firestore.FieldValue.serverTimestamp(),
      });
      const entries = statusByPos[pos.id] || (statusByPos[pos.id] = []);
      const existing = entries.find(e => e.email === currentEmail);
      if (existing) existing.status = select.value;
      else entries.push({ email: currentEmail, status: select.value });
      renderStats();
      othersDiv.textContent = getOthersText(pos.id);
    });
    statusTd.appendChild(select);
    const othersDiv = document.createElement("div");
    othersDiv.className = "applied-by";
    othersDiv.textContent = getOthersText(pos.id);
    statusTd.appendChild(othersDiv);
    tr.appendChild(statusTd);

    const posTd = document.createElement("td");
    const link = document.createElement("a");
    link.href = pos.url; link.target = "_blank"; link.rel = "noopener";
    link.className = "pos-link"; link.textContent = pos.title;
    posTd.appendChild(link);
    if (pos.source === "Curated") {
      const badge = document.createElement("span");
      badge.className = "badge-curated"; badge.textContent = "researched";
      posTd.appendChild(badge);
    }
    tr.appendChild(posTd);

    const instTd = document.createElement("td");
    instTd.className = "institution"; instTd.textContent = pos.company;
    tr.appendChild(instTd);

    const locTd = document.createElement("td");
    locTd.textContent = pos.location || "";
    tr.appendChild(locTd);

    const sourceTd = document.createElement("td");
    sourceTd.className = "source"; sourceTd.textContent = pos.source;
    tr.appendChild(sourceTd);

    const foundTd = document.createElement("td");
    foundTd.className = "found-at"; foundTd.textContent = (pos.found_at || "").replace(" UTC", "");
    tr.appendChild(foundTd);

    const aiTd = document.createElement("td");
    const tailorBtn = document.createElement("button");
    tailorBtn.className = "btn btn-small";
    tailorBtn.textContent = "Tailor";
    tailorBtn.title = "Generate a version of your CV/research statement tailored to this program";
    tailorBtn.addEventListener("click", () => tailorForPosition(pos));
    aiTd.appendChild(tailorBtn);
    tr.appendChild(aiTd);

    tbody.appendChild(tr);
  });

  renderStats();
}

function renderSchools() {
  const search = document.getElementById("schoolSearch").value.toLowerCase();
  const tbody = document.getElementById("schoolRows");
  tbody.innerHTML = "";
  SCHOOLS.forEach(school => {
    if (search && !school.name.toLowerCase().includes(search)) return;
    const tr = document.createElement("tr");

    const nameTd = document.createElement("td");
    const link = document.createElement("a");
    link.href = school.url; link.target = "_blank"; link.rel = "noopener";
    link.className = "school-link"; link.textContent = school.name;
    nameTd.appendChild(link);
    tr.appendChild(nameTd);

    const locTd = document.createElement("td");
    locTd.textContent = school.location || "";
    tr.appendChild(locTd);

    const linkTd = document.createElement("td");
    const link2 = document.createElement("a");
    link2.href = school.url; link2.target = "_blank"; link2.rel = "noopener";
    link2.textContent = school.url.replace(/^https?:\\/\\//, "").replace(/\\/$/, "");
    linkTd.appendChild(link2);
    tr.appendChild(linkTd);

    tbody.appendChild(tr);
  });
}

// Notes: private per-account, stored in Firestore under user_notes/{uid} as
// { current: string, log: [{id, date, text}] } — never visible to other
// signed-in users (Firestore rules restrict read/write to request.auth.uid
// matching the doc id, same pattern as user_resumes).
async function loadNotes() {
  if (!currentUid) return;
  try {
    const doc = await db.collection("phd_user_notes").doc(currentUid).get();
    if (doc.exists) {
      const d = doc.data();
      document.getElementById("notesCurrent").value = d.current || "";
      myNotesLog = d.log || [];
    }
  } catch (err) {
    console.error("Failed to load your notes:", err);
  }
  renderNotesLog();
}

async function saveNotesDoc() {
  if (!currentUid) return;
  await db.collection("phd_user_notes").doc(currentUid).set({
    email: currentEmail,
    current: document.getElementById("notesCurrent").value,
    log: myNotesLog,
    updatedAt: firebase.firestore.FieldValue.serverTimestamp(),
  }, { merge: true });
}

function scheduleNotesSave() {
  clearTimeout(notesSaveTimer);
  notesSaveTimer = setTimeout(saveNotesDoc, 800);
}

function renderNotesLog() {
  const container = document.getElementById("notesLog");
  container.innerHTML = "";
  if (myNotesLog.length === 0) {
    container.innerHTML = '<p class="modal-hint">No entries yet — add your first one above.</p>';
    return;
  }
  myNotesLog.slice().reverse().forEach(entry => {
    const div = document.createElement("div");
    div.className = "note-entry";
    const head = document.createElement("div");
    head.className = "note-entry-head";
    const dateSpan = document.createElement("span");
    dateSpan.className = "note-entry-date";
    dateSpan.textContent = entry.date;
    head.appendChild(dateSpan);
    const delBtn = document.createElement("button");
    delBtn.className = "note-delete";
    delBtn.textContent = "Delete";
    delBtn.addEventListener("click", async () => {
      myNotesLog = myNotesLog.filter(e => e.id !== entry.id);
      await saveNotesDoc();
      renderNotesLog();
    });
    head.appendChild(delBtn);
    div.appendChild(head);
    const textDiv = document.createElement("div");
    textDiv.className = "note-entry-text";
    textDiv.textContent = entry.text;
    div.appendChild(textDiv);
    container.appendChild(div);
  });
}

async function showApp() {
  loginScreen.classList.add("hidden");
  appScreen.classList.remove("hidden");
  document.getElementById("whoami").textContent = currentEmail;
  await loadStatuses();
  await loadProfStatuses();
  loadApiKeyFromBrowser();
  await loadUserResume();
  await loadNotes();
  populateSourceFilter();
  populateTagFilter();
  document.getElementById("search").addEventListener("input", render);
  document.getElementById("statusFilter").addEventListener("change", render);
  document.getElementById("sourceFilter").addEventListener("change", render);
  document.getElementById("profSearch").addEventListener("input", renderProfessors);
  document.getElementById("profTagFilter").addEventListener("change", renderProfessors);
  document.getElementById("profStatusFilter").addEventListener("change", renderProfessors);
  document.getElementById("schoolSearch").addEventListener("input", renderSchools);
  document.getElementById("notesCurrent").addEventListener("input", scheduleNotesSave);
  document.getElementById("notesAddBtn").addEventListener("click", async () => {
    const ta = document.getElementById("notesNewEntry");
    const text = ta.value.trim();
    if (!text) return;
    const now = new Date();
    myNotesLog.push({
      id: now.getTime() + "_" + Math.random().toString(36).slice(2, 8),
      date: now.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }),
      text: text,
    });
    await saveNotesDoc();
    ta.value = "";
    renderNotesLog();
  });
  render();
  renderProfessors();
  renderSchools();
}

if (auth.isSignInWithEmailLink(window.location.href)) {
  let email = window.localStorage.getItem("emailForSignIn");
  if (!email) {
    email = window.prompt("Confirm your email to complete sign-in:");
  }
  auth.signInWithEmailLink(email, window.location.href).then(result => {
    window.localStorage.removeItem("emailForSignIn");
    window.history.replaceState({}, document.title, window.location.pathname);
    currentEmail = result.user.email;
    currentUid = result.user.uid;
    showApp();
  }).catch(err => {
    loginStatus.textContent = "Sign-in failed: " + err.message;
  });
} else {
  auth.onAuthStateChanged(user => {
    if (user) {
      currentEmail = user.email;
      currentUid = user.uid;
      showApp();
    }
  });
}
</script>
</body>
</html>
"""
    html = html.replace("__GENERATED_AT__", generated_at)
    html = html.replace("__POSITIONS_JSON__", positions_json)
    html = html.replace("__PROFESSORS_JSON__", professors_json)
    html = html.replace("__SCHOOLS_JSON__", schools_json)

    folder = os.path.dirname(output_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG_PATH
    config = load_config(config_path)

    keywords = config.get("keywords", [])
    exclude_keywords = config.get("exclude_keywords", [])
    sources_cfg = config.get("sources", {})

    script_dir = os.path.dirname(os.path.abspath(config_path))

    output_csv = os.path.join(script_dir, config.get("output_csv", "phd_positions_found.csv"))
    seen_path = os.path.join(script_dir, config.get("seen_jobs_file", "seen_positions.json"))
    log_path = os.path.join(script_dir, config.get("log_file", "run_log.txt"))

    for path in (output_csv, seen_path, log_path):
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)

    log("Starting PhD position check run...", log_path)

    all_positions = []

    if sources_cfg.get("curated", True):
        print(f"Loading curated seed list ({len(CURATED_POSITIONS)} entries)...")
        all_positions.extend(CURATED_POSITIONS)

    if sources_cfg.get("jobsacuk", True):
        for kw in keywords:
            print(f"Fetching jobs.ac.uk (PhDs only): {kw}...")
            all_positions.extend(fetch_jobsacuk(kw))

    if sources_cfg.get("academictransfer", True):
        for kw in keywords:
            print(f"Fetching AcademicTransfer.com: {kw}...")
            all_positions.extend(fetch_academictransfer(kw))

    if sources_cfg.get("theunijobs", True):
        for kw in keywords:
            print(f"Fetching THEunijobs.com: {kw}...")
            all_positions.extend(fetch_theunijobs(kw))

    print(f"\nTotal positions pulled from all sources: {len(all_positions)}")

    # Filter by keyword (curated entries always pass — they're pre-vetted)
    filtered = []
    for pos in all_positions:
        if pos["source"] == "Curated":
            filtered.append(pos)
            continue
        if not matches_keywords(pos["title"], keywords, exclude_keywords):
            continue
        filtered.append(pos)

    # Dedup within this run (same position can surface for multiple keywords)
    dedup = {}
    for pos in filtered:
        dedup[pos["id"]] = pos
    filtered = list(dedup.values())

    print(f"Positions matching your keywords/filters: {len(filtered)}")

    # Dedup against previously seen positions
    seen_ids = load_seen(seen_path)
    new_positions = [p for p in filtered if p["id"] not in seen_ids]

    print(f"NEW positions since last run: {len(new_positions)}")

    if new_positions:
        file_exists = os.path.exists(output_csv)
        with open(output_csv, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            found_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            for pos in new_positions:
                writer.writerow({
                    "id": pos["id"],
                    "found_at": found_at,
                    "status": DEFAULT_STATUS,
                    "title": pos["title"],
                    "company": pos["company"],
                    "location": pos["location"],
                    "source": pos["source"],
                    "url": pos["url"],
                })
                seen_ids.add(pos["id"])
                print(f"  + {pos['title']} @ {pos['company']} ({pos['source']})")

        save_seen(seen_path, seen_ids)
        log(f"Added {len(new_positions)} new position(s) to {output_csv}", log_path)
    else:
        log("No new positions found this run.", log_path)

    # Professors tab data — always a fresh full snapshot (curated + CSRankings),
    # not append/dedup tracked like positions, since it's a ranked list rather
    # than a "new items found" feed. IDs are stable (derived from name), so a
    # user's status choice on a professor survives day-to-day score changes.
    professors = build_professors(sources_cfg)
    n_curated_profs = sum(1 for p in professors if p["source"] == "Curated")
    print(f"Professors tab: {len(professors)} total ({n_curated_profs} curated + {len(professors) - n_curated_profs} from CSRankings)")
    professors_path = os.path.join(script_dir, config.get("professors_file", "data/professors.json"))
    folder = os.path.dirname(professors_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(professors_path, "w", encoding="utf-8") as f:
        json.dump(professors, f, indent=2, ensure_ascii=False)
    log(f"Wrote {len(professors)} professors to {professors_path}", log_path)

    # Schools tab data — also a fresh full snapshot each run.
    schools = fetch_schools() if sources_cfg.get("schools", True) else []
    print(f"Schools tab: {len(schools)} US + Europe/UK institutions")
    schools_path = os.path.join(script_dir, config.get("schools_file", "data/schools.json"))
    with open(schools_path, "w", encoding="utf-8") as f:
        json.dump(schools, f, indent=2, ensure_ascii=False)
    log(f"Wrote {len(schools)} schools to {schools_path}", log_path)

    output_html = config.get("output_html")
    if output_html:
        html_path = os.path.join(script_dir, output_html)
        if os.path.exists(output_csv):
            with open(output_csv, "r", newline="", encoding="utf-8") as f:
                all_rows = list(csv.DictReader(f))
        else:
            all_rows = []
        if config.get("enable_auth"):
            generate_html_auth(all_rows, professors, schools, html_path)
        else:
            generate_html(all_rows, professors, schools, html_path)
        log(f"Regenerated tracker page at {html_path} ({len(all_rows)} total positions, {len(professors)} professors, {len(schools)} schools)", log_path)

    log("Run complete.\n", log_path)


if __name__ == "__main__":
    main()
