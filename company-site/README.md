# Clever Crump — Company Site

The parent-company website for **Clever Crump**, the independent software company
behind Ask Crump, Dabblebit, and Rally.

This directory is a standalone static site (no build step, no frameworks —
pure HTML/CSS/JS), modeled on the `CRUMP-AI/dabblebit-site` pattern. It lives
inside the `CRUMP-AI/AskCrump` repo under `company-site/` so the parent brand
stays separated from any single product, exactly like the Dabblebit marketing
site is separated from the Dabblebit app.

## Contents

| File | Purpose |
|---|---|
| `index.html` | Homepage — hero, product lineup (Ask Crump, Dabblebit, Rally), philosophy, founder note, footer |
| `privacy.html` | Parent-company privacy policy |
| `terms.html` | Parent-company terms of service |
| `contact.html` | Contact page (`support@clevercrump.com`) |
| `favicon.svg` | Gold "C" + magnifying-glass monogram |
| `assets/css/style.css` | Full stylesheet (near-black / ivory / gold, editorial premium) |
| `assets/js/main.js` | Mobile nav, footer year, scroll reveals |
| `CNAME` | Custom domain for GitHub Pages: `clevercrump.com` |

## Brand

- Near-black `#070a0e`, ivory `#f1efe9`, gold `#d5b971` / `#b69855`
- Georgia serif headlines (wide-tracked eyebrow labels), system sans body
- Vibe: private-members-club, editorial, calm premium — never SaaS-startup

## Deploy (GitHub Pages)

Option A — separate repo (recommended, mirrors dabblebit-site):
1. Create a new repo (e.g. `CRUMP-AI/clevercrump-site`).
2. Copy the contents of this directory into it.
3. Repo Settings → Pages → Deploy from branch → `main` / root.
4. Add DNS: `clevercrump.com` → GitHub Pages IPs (or CNAME to `CRUMP-AI.github.io`
   for `www`). The `CNAME` file is already in place; GitHub provisions the
   TLS certificate automatically once DNS resolves.

Option B — serve from this repo:
GitHub Pages can only serve from one location per repo, so serving the company
site from `AskCrump` would displace the existing Pages setup. Prefer Option A.

## Local preview

```bash
cd company-site
python3 -m http.server 8000
# open http://localhost:8000/
```

## Notes

- Dabblebit is listed as "Coming soon to iOS and Android" — update the card
  once it's live on the App Store / Google Play.
- Rally is intentionally one restrained line ("in development") until there's
  more to say.
