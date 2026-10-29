<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Language

Everything committed to this repository is in English: code comments, commit messages, README, docs, CHANGELOG
entries and the in-app guide. The UI keeps its `tr(en, pt, es)` translations, and an optional Portuguese guide lives
under `public/guides/pt-BR/` and `docs/pt-BR/`. Do not write new documentation in another language.

## Public repository: no private details

This repository is public. Never commit anything that identifies a contributor's own machines or accounts: IP
addresses, private hostnames (Tailscale `*.ts.net`, LAN names), hosted instance URLs, RunPod endpoint/worker/volume
ids, API keys, absolute local paths, e-mail addresses or private job ids. Defaults use `127.0.0.1`/`localhost`;
anything machine-specific comes from environment variables in `.env.local` (ignored by Git) and is documented in
`.env.example` and `docs/RUN_LOCAL.md`. Before committing, search the diff for such values. The public Henge pod
template id and the published image names are fine.

## Project update history

For user-facing features, fixes, workflow changes or deployment changes, update `CHANGELOG.md` with
its date, affected component, validation and known limitations. Distinguish code pushed to main,
published Docker images, actual deployment and completed tests. Update pending results when they
finish. Do not put credentials or private job data in the changelog.
