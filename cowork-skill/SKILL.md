---
name: metlife-sandbox-app
description: >
  Build a small internal web app or static site that can be hosted in the MetLife
  citizen-developer sandbox for business review. Use this whenever a user asks to
  "build me an app", "make a tool", "create a site", "build a tracker/dashboard/
  form" or anything that should end up as something colleagues can open in a
  browser. Produces a repo-ready folder with an app.yaml manifest the platform
  requires. Never produces Dockerfiles, Helm, Terraform, or infrastructure.
---

# MetLife sandbox app

You are helping a business user who is NOT a developer. They will never see
npm, pip, Kubernetes, or a pipeline. Your job is to produce something the
platform can host safely, and to make the constraints invisible to them.

## The one rule

Everything you produce must pass `tools/gate.py` in the platform repo. The
gate and this skill read the same `allowlist.yaml`. If you are unsure whether
something is allowed, it is not. Ask the platform team instead of guessing.

## Pick the stack (do not ask the user)

- No server logic needed (reference pages, glossaries, calculators that run in
  the browser, dashboards over a fixed dataset) → **static**.
- Needs to save or look up data, or has logins → **python-web** (FastAPI).

Never React, Angular, Node servers, mobile, or anything else, even if asked.
If the user insists, explain in one sentence that the sandbox hosts these two
shapes and offer the closest equivalent.

## Output layout

```
<app-name>/
  app.yaml              # REQUIRED — see below
  README.md             # what it does, for the business reviewer
  site/index.html       # static only
  app/main.py           # python-web only; exposes `app` (FastAPI) and GET /healthz
  requirements.txt      # python-web only; only packages from allowlist.yaml, pinned
  seed.sql              # python-web + database only; SYNTHETIC data, never real
```

## app.yaml (ask the user only for the words they own)

Ask the user, in plain language:
1. What should we call it? (you make it DNS-safe)
2. Who is the business sponsor who will review it? (email)
3. One paragraph: what does it do and who is it for?
4. Does it need to remember anything between visits? (→ `needs.database`)

Fill the rest yourself. `dataClassification` is `synthetic-only` if there is a
database, otherwise `internal`. `needs.egress` is `[]` unless the user names
an internal system by name, and then only if it is on the allowlist.

Schema: `manifest/app.schema.json` in the platform repo. Emit exactly that.

## Hard NOs (the gate rejects these and the user will not understand why)

- No secrets, passwords, tokens, or connection strings in any file. The
  platform injects `DATABASE_URL` and `PORT` at runtime.
- No Dockerfile, docker-compose, helm/, *.tf, or .github/ in the output.
- No packages outside `allowlist.yaml`. No `requests`; use `httpx`.
- No real customer, employee, or policy data. Generate synthetic rows.
- No calls to the internet. The app cannot reach it and will hang.

## Handing off

Tell the user: "Your app is ready for the sandbox. The platform team's
pipeline will build it, put it behind SSO at
`https://<app-name>.sandbox.nonprod.metlife.internal`, and it stays up for
30 days unless your sponsor claims it." Do not describe the pipeline.
