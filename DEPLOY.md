# Deploying the tracker as a website (GitHub Pages)

This turns the local script into a real website that updates itself
automatically every day, lives at **phd.placeonus.com**, and requires signing
in with your email before anyone can see it. Here's how the pieces fit
together:

1. A GitHub Actions workflow (`.github/workflows/daily-phd-check.yml`) runs
   on GitHub's servers once a day.
2. It runs `phd_checker.py` with `config.web.json`, which reloads the curated
   list, re-checks jobs.ac.uk and AcademicTransfer.com, and updates
   `data/phd_positions_found.csv` and `docs/index.html`.
3. It commits and pushes those changes back to your repo.
4. GitHub Pages serves whatever is in `docs/` at your custom domain.
5. Visiting the site shows a sign-in screen (Firebase email-link, no
   password). Once signed in, you see the full tracker and can set your own
   status per position ("To Research" → "Contacted Advisor" → "Applied" →
   "Interview" → "Offer"/"Waitlisted"/"Rejected").
6. Each signed-in user can also paste their CV / research-statement text and,
   optionally, tailor it to a specific program with their own OpenAI key
   (Cloud Functions) — both per-account and private to that user.

> **I built the code, but I can't deploy it for you.** Creating the GitHub
> repo, the Firebase project, and the DNS record all require *your*
> accounts/credentials, which I don't have access to. Everything below is
> written so you (or anyone) can do it in about 30–40 minutes without needing
> to know Firebase or GitHub Pages beforehand.

## One-time setup

### 1. Create the repository

1. Go to https://github.com/new
2. Name it something like `phd-tracker` (**must be public** — free GitHub
   accounts can only use Pages on public repos; the login screen is what
   keeps it from being usable by randoms who stumble on the URL).
3. Create it empty (no README/gitignore from GitHub's side, we already have those).

### 2. Push this folder to the repo

```
git init
git add .
git commit -m "Initial PhD application tracker site"
git branch -M main
git remote add origin https://github.com/<your-username>/phd-tracker.git
git push -u origin main
```

### 3. Set up Firebase (email login + shared tracking)

**Already have a Firebase project for the job tracker? Reuse it — don't create
a second one.** A Firebase project can host multiple sites/apps and its
Firestore database can hold as many collections as you want; you don't need
(and on the free Spark plan, typically can't easily run) a second project just
for this. This tracker's Firestore collections are all prefixed `phd_`
(`phd_position_status`, `phd_professor_status`, `phd_user_resumes`,
`phd_user_notes`) specifically so they can't collide with whatever
collections your job tracker already uses in that same database — add the
rules below *alongside* your existing job-tracker rules, don't replace them.

If you're starting fresh instead, go to https://console.firebase.google.com →
**Add project** first, then follow the same steps.

1. **Enable email-link sign-in** (skip if the job tracker already has this
   on): left sidebar → **Build → Authentication** → **Get started** → under
   "Sign-in method", choose **Email/Password** → toggle it on → also toggle on
   **Email link (passwordless sign-in)** → Save.
2. **Add authorized domains:** still in Authentication → **Settings** tab →
   **Authorized domains** → **Add domain** → add `phd.placeonus.com` (this is
   additive — your existing job-tracker domain stays in the list too).
3. **Firestore database:** if the job tracker already created one, you're
   reusing it — nothing to do here. If not: left sidebar → **Build →
   Firestore Database** → **Create database** → choose a region → start in
   **production mode**.
4. **Update security rules:** in Firestore, go to the **Rules** tab. Don't
   overwrite what's there for your job tracker — **add** these four `match`
   blocks inside the existing `service cloud.firestore { match
   /databases/{database}/documents { ... } }` wrapper, next to whatever rules
   already exist for the job tracker's collections:
   ```
   match /phd_position_status/{docId} {
     allow read: if request.auth != null;
     allow write: if request.auth != null
                   && request.auth.token.email == request.resource.data.email;
   }
   match /phd_professor_status/{docId} {
     allow read: if request.auth != null;
     allow write: if request.auth != null
                   && request.auth.token.email == request.resource.data.email;
   }
   match /phd_user_resumes/{uid} {
     allow read: if request.auth != null && request.auth.uid == uid;
     allow write: if request.auth != null && request.auth.uid == uid;
   }
   match /phd_user_notes/{uid} {
     allow read: if request.auth != null && request.auth.uid == uid;
     allow write: if request.auth != null && request.auth.uid == uid;
   }
   ```
   This lets any signed-in user see everyone's PhD-tracker status, but only
   ever write their *own* status — nobody can edit someone else's entry. The
   `phd_user_resumes` and `phd_user_notes` rules keep each person's CV text
   and journal private to just them, same as before. Click **Publish**.
5. **Get your web config:** gear icon → **Project settings** → scroll to
   "Your apps". If you already registered a web app for the job tracker, you
   can reuse that exact same `firebaseConfig` object (same project = same
   config works for both sites) — just copy it again into this repo. Or click
   the **</>** icon to register a second app under a different nickname if
   you'd rather keep them listed separately in the console (functionally
   identical either way). Copy the `firebaseConfig` values into
   `docs/firebase-config.js` in *this* repo, replacing the `REPLACE_ME`
   placeholders. Commit and push that change.

`docs/firebase-config.js` is intentionally separate from `docs/index.html` —
the daily workflow only ever rewrites `index.html`, so your real Firebase
config never gets overwritten by the automated run.

### 4. Set up Firebase Storage (optional — not required for the tracker itself)

The tracker's core status-tracking works with just Firestore (step 3). This
project's Storage rules (`storage.rules`) are included in case you want to
extend it later to let users upload a CV file directly (not just paste text)
— it's not wired into the UI by default, so you can skip this step.

### 5. Set up AI tailoring (optional — requires a paid Firebase plan)

This adds the "Tailor" button next to each program, which rewrites a user's
CV/research-statement text to better match that specific program using
OpenAI's API. You can skip this section entirely — everything else on the
site works fine without it; the Tailor button will just show a message
saying it isn't set up yet.

**Why this needs a Cloud Function:** OpenAI's API doesn't allow direct calls
from a browser (no CORS support), so a small server-side relay is required.
That relay is already written for you in `functions/index.js` — you just
need to deploy it.

**This step requires upgrading your Firebase project to the "Blaze"
(pay-as-you-go) plan.** Cloud Functions cannot run on the free "Spark" plan.
Firebase's free tier of 2 million function invocations/month still applies
on Blaze — you only pay if you exceed it. Any actual OpenAI usage is billed
separately to your own OpenAI account, using the API key each user enters
themselves.

1. In the Firebase console, click **Upgrade** (bottom-left) → choose
   **Blaze** → attach a billing account.
2. Install the Firebase CLI (one-time): `npm install -g firebase-tools`
3. Log in and select your project (run from inside this repo folder, since
   `firebase.json` / `.firebaserc` point at the project you set below):
   ```
   firebase login
   firebase use --add
   ```
   (Pick your Firebase project and give it the alias `default` when prompted
   — or manually replace `REPLACE_ME_WITH_YOUR_FIREBASE_PROJECT_ID` in
   `.firebaserc` with your real project ID first.)
4. Deploy the function: `firebase deploy --only functions`
5. The CLI output ends with a line like:
   ```
   Function URL (tailorApplication(us-central1)): https://us-central1-YOUR-PROJECT-ID.cloudfunctions.net/tailorApplication
   ```
   Copy everything **before** `/tailorApplication` and paste it into
   `docs/firebase-config.js` as the `cloudFunctionsBaseUrl` value. Commit and push.
6. On the site, each user opens **Settings**, pastes their own OpenAI API key
   (from https://platform.openai.com/api-keys) and their CV/statement text,
   then clicks **Tailor** on any program. The key is stored only in that
   person's own browser (`localStorage`) and sent directly to your Cloud
   Function per-request — never written to Firestore or logged.

### 6. Point phd.placeonus.com at GitHub Pages

1. In your DNS provider for `placeonus.com`, add a **CNAME record**:
   - Host/name: `phd`
   - Value/target: `<your-username>.github.io`
   - TTL: default is fine
2. In your repo: **Settings → Pages**.
   - Under "Build and deployment", set **Source** to `Deploy from a branch`.
   - Set **Branch** to `main`, folder to `/docs`, **Save**.
   - Under "Custom domain", enter `phd.placeonus.com` → **Save**. (A
     `docs/CNAME` file with that domain is already in this repo, so GitHub
     should pick it up automatically, but entering it here too makes sure
     HTTPS gets provisioned.)
   - Once GitHub verifies the DNS (can take a few minutes to a few hours),
     check **Enforce HTTPS**.

Until DNS propagates you can still preview the site at
`https://<your-username>.github.io/phd-tracker/`.

### 7. Trigger the first run

1. Go to the **Actions** tab in your repo.
2. Click **Daily PhD Position Check** in the left sidebar.
3. Click **Run workflow** (manual trigger — `workflow_dispatch`) to confirm
   everything works before waiting for the schedule.
4. Once it finishes (green checkmark), visit `https://phd.placeonus.com` (or
   the github.io URL if DNS hasn't propagated yet) — you should see the
   sign-in screen. Enter your email, check your inbox for the link, click
   it, and you'll land back on the site signed in.

From here on, it runs automatically every day at 13:00 UTC with no action
needed from you. Change the time by editing the `cron:` line in
`.github/workflows/daily-phd-check.yml` — https://crontab.guru is handy for the syntax.

## How the login + tracking actually works

- Sign-in is passwordless: you type your email, Firebase emails you a
  one-time link, clicking it signs you in on that device/browser.
- Every position's status dropdown is saved to a shared Firestore database,
  tagged with your email — so if a study partner or mentor also signs in,
  you'll each see your own status per position, plus a small "Also:
  their-email (their-status)" note under each row.
- Anyone can sign in with any email by default (no invite-only allowlist).
  If you want to restrict who can sign in, the simplest option is adding an
  `allowedEmails` check to the Firestore rules.

## What's scraped live vs. curated

- **Curated (19 entries):** specific programs, labs, advisors, and
  industry-friendly tracks researched by hand for your background — see
  README.md for the full list and reasoning. These don't change day to day.
- **jobs.ac.uk (UK):** live, filtered server-side to the "PhDs" job-type
  facet, so results are individually-funded PhD studentships by
  construction — refreshed daily.
- **AcademicTransfer.com (Netherlands/Europe):** live, filtered client-side
  to titles containing "phd" — refreshed daily.
- **Not scraped:** findaphd.com and academicpositions.com both block
  automated requests (HTTP 403, even with a browser User-Agent) — check
  those manually; links are in README.md.

## Keeping a local-only version too

`config.json` (writes to `local_preview.html`, no login) and
`config.web.json` (writes to `docs/index.html`, Firebase-gated) are separate
files, so you can run `python3 phd_checker.py config.json` any time for a
quick local look, independent of the deployed site.

## Files specific to the website

| File | Purpose |
|---|---|
| `docs/index.html` | Generated automatically each run — the login-gated tracker page |
| `docs/firebase-config.js` | Your Firebase project config — edit once by hand, never auto-generated |
| `docs/CNAME` | Tells GitHub Pages to serve at `phd.placeonus.com` |
| `storage.rules` | Firebase Storage security rules (optional feature, see step 4) |
| `firebase.json` / `.firebaserc` | Tell the Firebase CLI where your Cloud Functions code lives and which project to deploy to |
| `functions/index.js` | The `tailorApplication` Cloud Function — relays AI tailoring requests to OpenAI |

## Troubleshooting

- **Workflow fails on the "Run PhD position checker" step:** check the
  Actions log — most likely jobs.ac.uk or AcademicTransfer changed their page
  markup. Each source is wrapped in try/except so one failing doesn't stop
  the run or wipe existing data.
- **Site shows old data:** GitHub Pages can take a minute to update after a
  push. Hard-refresh (Cmd+Shift+R) if it looks stale.
- **Nothing shows up at all:** double check Pages is set to serve from
  `main` / `/docs`, not `/ (root)`.
- **"Tailor" button says AI tailoring isn't set up:** you skipped or haven't
  finished step 5 (Cloud Functions) — either deploy it, or ignore the
  button, everything else on the site works without it.
- **"Sign-in failed" or the link doesn't work:** confirm `phd.placeonus.com`
  is in Firebase Auth's Authorized domains list, and that
  `docs/firebase-config.js` has your real project values, not the
  `REPLACE_ME` placeholders.
- **You see your own status but not others':** double-check the Firestore
  rules were published (step 3.5).
