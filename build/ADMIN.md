# vDefend-Avi-Tools: contributor and admin guide

This guide is for people who maintain the index. The public landing page is the repository's [README](../README.md).

Run every command below from the repository root.

A GitHub Pages index of scripts and utilities for VMware vDefend and Avi Load Balancer, built with [Clarity](https://clarity.design) (CSS from CDN) and plain JavaScript. The only build step is a small standard-library Python script.

## Layout

| Path | Purpose |
| --- | --- |
| `build/catalog/**/<slug>.json` | One file per tool. Organise them in any subfolders you like (for example `avi/`). The filename (lowercase letters, digits and hyphens) is the tool's ID and must be unique across all folders. Folders whose name starts with `.` are ignored by the build and by `check_updates.py` (`.example/sample.json` is a blank template to copy). |
| `build/config/config.json` | Site settings: allowed products, types and sources, `site_url`, `new_days` and `latest_count` (see [Configuration](#configuration)). |
| `build/config/tags.json` | The controlled list of tags, as `{"tags": {"tag-name": "description"}}`. |
| `build/config/added.json` | **Generated, but commit it.** Records the date each tool was first seen (see below). |
| `tools/` | Tool code and scripts hosted in this repository, one folder per tool. Not part of the index; add an entry under `build/catalog/` to list a tool. |
| `build/` | Everything that generates the website and README (this guide, the build script, update checker, schema, config, README template, Docker files). |
| `build/check_updates.py` | Optional helper that looks up when each tool was last updated (see [Checking for updates](#checking-for-updates)). Not run by the build or CI. |
| `.githooks/pre-commit` | Optional hook that rebuilds and stages the generated files (see [Adding a tool](#adding-a-tool)). |
| `.github/workflows/pages.yml` | CI: validates and publishes the site (see [Publishing](#publishing)). |
| `push_to_dev.sh` | Maintainer convenience script: builds, rsyncs the repo to a dev host and restarts the Docker stack there. The host is hard-coded at the top of the script; edit it before use. |
| `site/` | The static website (`index.html`, `assets/`) that GitHub Pages publishes. Only this folder is published. |
| `site/data/index.json` | **Generated.** The combined file the website loads. Don't edit it by hand. |
| `README.md` | **Generated.** The public list of tools shown on the repository home page. Don't edit it by hand. |
| `build/README.template.md` | The intro and footer text of the generated `README.md`. Edit this to change the wording. |
| `build/build.py` | Validates everything, then generates `site/data/index.json` and `README.md`. |
| `build/schema/tool.schema.json` | JSON Schema for editor autocomplete and hints. |

## Adding a tool

1. Create `build/catalog/my-tool.json`:

   ```json
   {
     "$schema": "../schema/tool.schema.json",
     "name": "My Tool",
     "description": "One or two sentences.",
     "product": ["vdefend"],
     "type": "script",
     "source": "community",
     "tags": ["distributed-firewall", "python"],
     "url": "https://github.com/org/repo",
     "version": "1.0.0",
     "maintainer": "Name",
     "updated": "2026-01-01"
   }
   ```

   - **Required:** `name`, `description`, `product`, `type`, `tags`, `url`.
   - **Optional:** `source` (`broadcom` or `community`; defaults to `community`), `version` (shown as a badge), `maintainer`, `updated` (`YYYY-MM-DD`), `added` (`YYYY-MM-DD`, see [New tools](#new-tools)), `archived`, `archived_reason`, `featured`, and `update_source` (`release` or `commit`) and `release_tag_prefix` (both only used by `check_updates.py`). Any other field is rejected.
   - If the file is in a subfolder, adjust the `$schema` path (for example `../../schema/tool.schema.json` one level down). `$schema` is only an editor hint and is dropped from the generated index.
   - To retire a tool (for example its product is end of life), add `"archived": true` and, ideally, `"archived_reason": "..."`. Archived tools stay in the catalogue but are hidden from the website by default and listed under "Archived" at the bottom of the README. Visitors can reveal them with the website's **Archived** filter (Hide / Include / Only archived). They never show the NEW badge. `archived_reason` is shown as a tooltip on the ARCHIVED badge and is only allowed when `archived` is true.
   - To highlight a tool, add `"featured": true`. Featured tools appear in a **Featured** band at the top of the website's default view (cards and table), in name order, and carry a small FEATURED badge in the main list. The band is hidden whenever a search, filter, the Starred filter or a page other than 1 is active, or when archived tools are shown. An archived tool cannot be featured.
   - Only set `"source": "broadcom"` for tools that are Broadcom-owned or supported. Anything else is shown as Community.
   - `product` can list `vdefend`, `avi`, or both.
   - `url` can be a GitHub repo or any external link.
   - `type` must be a key in `build/config/config.json`, and each tag must be in `build/config/tags.json`.
2. Run `python3 build/build.py`. It reports every problem it finds, or writes `build/config/added.json`, `site/data/index.json` and `README.md`. Besides the field rules above, it rejects a filename that isn't a valid slug, a filename or tool `name` (case-insensitive) used twice, duplicate tags, and unparseable JSON.
3. Commit the new tool file **and** the regenerated `build/config/added.json`, `site/data/index.json` and `README.md`.

To avoid forgetting step 2, enable the pre-commit hook once per clone:

    git config core.hooksPath .githooks

It rebuilds and stages `build/config/added.json`, `site/data/index.json` and `README.md` on every commit, and blocks the commit if validation fails. `python3 build/build.py --check` validates and fails if any of those three generated files is out of date; CI runs it on every pull request and before every deploy.

New tags, products or types: add them to `build/config/tags.json` or `build/config/config.json` first. Unknown values are rejected, which keeps tags consistent. A new product needs `label`, `color` (a Clarity label colour such as `purple` or `blue`) and `short` (used in the README's latest additions list and the table view).

Note: `tool.schema.json` is only an editor hint. It checks structure, not the allowed product, type or tag names; `build.py` is authoritative for those.

## Configuration

`build/config/config.json` keys:

| Key | Purpose |
| --- | --- |
| `site_url` | Website address shown at the top of the README. Empty omits the line. |
| `products` | Allowed products: `label`, `color`, `short`. Order here is the order of the README sections and the website's Product filter. |
| `types` | Allowed types, as `key: display name`. The website's Type filter lists only types that are in use. |
| `sources` | Allowed sources (`broadcom`, `community`) with display `label` and badge `color`. |
| `new_days` | Days a tool shows the NEW badge (positive whole number, default 30). |
| `latest_count` | Length of the README's "Latest additions" list (positive whole number, default 5). |

## The generated README

`README.md` lists every non-archived tool in a table per product, with name, version, URL, description, tags, source, maintainer and last-updated date. A tool that targets both products appears under both. Archived tools are listed in a separate "Archived" table at the end. The total, the "most recent tool update" date and the "Latest additions" list all exclude archived tools. The update date comes from the tools' `updated` fields rather than the build time, so rebuilding without changes never alters the file.

The intro and footer text come from `build/README.template.md`, which uses the placeholders `{{SITE_LINE}}`, `{{TOTAL}}`, `{{UPDATED}}`, `{{LATEST}}`, `{{TOC}}` and `{{SECTIONS}}`. Keep them if you edit the template.

To show a link to the website at the top of the README, set `site_url` in `build/config/config.json` (for example your GitHub Pages address). It's empty by default, which omits the line.

## New tools

The build records the date it first sees each tool in `build/config/added.json` (a map of tool ID to date). Tools added within the last `new_days` days (default 30, set in `build/config/config.json`) get a red **NEW** badge on cards and in the table, and you can sort by "Recently added". The badge is worked out in the browser, so it expires on its own without a rebuild.

- The README's "Latest additions" list shows the newest `latest_count` tools (default 5, also in `build/config/config.json`).
- Always commit `build/config/added.json` with the new tool. If it's lost, every tool is re-seeded from its `updated` date (or today, if it has none).
- Entries for tools that no longer exist in the catalogue are dropped from `added.json` on the next build.
- To correct a date, edit `build/config/added.json`, or set `"added": "YYYY-MM-DD"` in the tool's own file, which takes precedence.
- The first build seeded the existing tools from their `updated` dates, so only genuinely recent ones show as new.

## Starred tools

Visitors can star a tool (the star on each card or table row) and then tick **Starred only** in the filters to see just those. Stars are stored in the visitor's own browser (`localStorage`, key `starred`), so they are per browser, don't sync between devices, and are deliberately not part of the shareable URL. Stars for tools that no longer exist are dropped automatically. No build step is involved.

Other per-browser preferences in `localStorage`: `theme` (light/dark toggle in the header), `filtersCollapsed` (the Show/Hide filters button; on first visit the sidebar starts collapsed on screens narrower than 768px) and `featuredCollapsed` (the Featured band's collapse toggle).

## Filtering

- **Search** matches name, description, maintainer and tags. Every space-separated word must match somewhere (AND).
- **Product** and **Type** are OR within a group. The Type list only shows types that at least one tool uses.
- **Tags** are AND, so each one narrows the results. Counts update to match the current results.
- **Archived:** Hide (default), Include or Only archived. When archived tools are hidden but would have matched, the empty-results message says so.
- **Starred only:** see above.
- **View:** switch between cards and a compact table. In the table, click the Name, Type or Updated headers to sort.
- **Sort and paging:** the Sort menu offers Name (A–Z / Z–A), Recently added, Recently updated, Least recently updated and Type. Tools with no value for the sort field (for example no `updated`) always sort last. Choose 12, 24, 48 or 96 results per page.
- Search, product, type, tag, archived, view, sort, page size and page number are kept in the URL hash, so any view can be shared as a link. (Starred-only is not.) Clicking the site title clears the hash and reloads.

## Checking for updates

`python3 build/check_updates.py` looks up each tool's `url` and reports when it was last updated. It changes nothing by default. Nothing here is run by the build or CI. It uses only the Python standard library and needs network access to `api.github.com` (and to any non-GitHub tool URLs). It exits non-zero only if every lookup failed.

- **Plain GitHub repo:** latest release, else latest tag, else latest commit.
- **`/tree/` or `/blob/` URL:** latest commit touching that path (a release date says nothing about one file).
- **Other hosts:** the `Last-Modified` header, or `?` if there isn't one.
- The `source` column shows which of these was used (`release`, `tag`, `commit`, `path-commit`, `last-modified`). `ARCHIVED` flags archived repos; set `archived` yourself if you agree.
- `--write` updates `updated`, and `version` when a real release was found (leading `v` stripped). Dates only move forward unless you add `--allow-older`. `--no-version` leaves `version` alone. `--no-build` skips the automatic rebuild. `--json PATH` saves the results.
- Add `"update_source": "commit"` to an entry to date it by its latest commit and ignore releases/tags (and never touch `version`). Use it for a monorepo root, where releases belong to individual components. `"update_source": "release"` does the opposite for a folder URL (`/tree/...`): it uses the repo's latest release instead of the folder's last commit. Without the field, a plain repo URL uses release → tag → commit and a folder URL uses the folder's last commit.
- Add `"release_tag_prefix": "tool-a/v"` to version one component of a monorepo: only releases whose tag starts with the prefix are considered (drafts and pre-releases skipped), the prefix is removed from the stored `version` (`tool-a/v1.2.0` → `1.2.0`), and it works for both repo-root and folder URLs. It implies `update_source: release` and can't be combined with `commit`. If no release matches, the entry is reported as failed and left unchanged.
- `check_updates.py` and `build.py` share one catalogue-discovery function (`build.iter_catalog()`), so both ignore folders whose name starts with `.`. `check_updates.py` imports `build.py` (keep them in the same folder) and calls it directly after `--write`.
- Pass one or more entry ids (the filename without `.json`) to check only those, e.g. `python3 build/check_updates.py vmflowgen`. This works with `--write` too.
- An `HTTP 403` note includes GitHub's reason. With a token, the usual cause is that the token isn't authorised for an org that enforces SAML SSO (token settings, "Configure SSO"), or a fine-grained token doesn't cover that org's repos.
- With `--write`, the script then runs `build/build.py` itself, so the generated files are never left stale. Add `--no-build` to skip that (then run `python3 build/build.py` yourself before committing).
- Each GitHub lookup takes 2-4 API calls (more with `release_tag_prefix`, which pages through releases), so a full run can exceed the 60 requests an hour allowed without a token. Set `GITHUB_TOKEN` to avoid hitting the limit. Non-GitHub URLs make no API calls.
- `--write` edits the JSON text in place, preserving formatting; if `updated` or `version` is missing it is inserted after the `url` line.
- A release date can lag far behind recent commits (some entries' latest release is years old), so review the report before using `--write`.

## Local preview

    python3 build/build.py
    python3 -m http.server 8000 --directory site

Then open http://localhost:8000. (`fetch` doesn't work from `file://`.)

Or with Docker: `docker compose -f build/docker-compose.yml up --build`, then open http://localhost (the compose file maps host port 80 to the container's 8000; change the left-hand number to use another port). The image copies the repo in, so rerun with `--build` after editing files. The container rebuilds `site/data/index.json` and `README.md` on every start.

The page loads the Clarity CSS from the unpkg CDN, so the preview needs internet access.

## Publishing

Repo **Settings → Pages → Source → GitHub Actions**. The workflow in `.github/workflows/pages.yml` runs `python3 build/build.py --check` on every pull request to `main` and on every push to `main`, and publishes only the `site/` folder after a push to `main` (it can also be started manually with "Run workflow"). If a generated file (`build/config/added.json`, `site/data/index.json` or `README.md`) is stale, the check fails and nothing is deployed, so commit them with your change.

The header's GitHub and "Report an issue" links are hard-coded to `https://github.com/vmware/vdefend-avi-tools` in `site/index.html`; update them if the repository moves.

The workflow also writes `site/data/meta.json` (commit SHA, UTC deploy date, repo) just before upload. It is published but never committed, so `--check` is unaffected. The page footer reads it and shows e.g. `Updated 2026-11-17 · a1b2c3d` (SHA links to the commit). Locally and in Docker the file doesn't exist, so the footer shows `Updated: dev build`. The local server log will therefore show `code 404` for `GET /data/meta.json` on every page load; this is expected and harmless. Ask people reporting a problem to quote the footer text.
