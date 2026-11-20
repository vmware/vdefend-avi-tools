#!/usr/bin/env python3
"""Work out when each catalogue tool was last updated (standard library only).

For every build/catalog/**/*.json entry the script looks at the tool's `url`:

  github.com/<org>/<repo>                latest release, else latest tag, else latest commit
  github.com/<org>/<repo>/(tree|blob)/<branch>/<path>
                                         latest commit that touched <path>
  The optional `update_source` field overrides this: "commit" always uses the latest
  commit (use it for a monorepo root, where releases belong to individual components);
  "release" uses the repo's latest release (for a folder URL in a repo that releases as one unit).
  `release_tag_prefix` (e.g. "tool-a/v") limits releases to tags starting with it, so one
  component of a monorepo can be versioned; it implies "release" and is stripped from `version`.
  any other host                         the `Last-Modified` response header, if any

It prints a report and changes nothing unless --write is given, in which case it
updates the `updated` field (and `version`, when a real release was found). A stored date
is never replaced by an older one unless --allow-older is given, because a release date can lag
well behind recent commits.
Run `python3 build/build.py` afterwards to regenerate site/data/index.json and README.md.

Usage:  python3 build/check_updates.py
        python3 build/check_updates.py terraform-provider-nsxt   # just one (or more) entries
        python3 build/check_updates.py --json report.json
        python3 build/check_updates.py --write [--no-version] [--allow-older]

Set GITHUB_TOKEN to avoid the unauthenticated GitHub rate limit (60 requests/hour).
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

BUILD = Path(__file__).resolve().parent
CATALOG = BUILD / "catalog"
API = "https://api.github.com"
TIMEOUT = 20

GH_REPO = re.compile(r"^https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+?)(?:\.git)?/?$")
GH_PATH = re.compile(r"^https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s]+)/(tree|blob)/([^/\s]+)/(\S+?)/?$")


class LookupError_(Exception):
    """A lookup failed in a way worth reporting (message is shown in the note column)."""


def http(url, method="GET", github=False):
    """Fetch ``url`` and return (parsed JSON or None, response headers)."""
    headers = {"User-Agent": "catalogue-update-checker"}
    if github:
        headers["Accept"] = "application/vnd.github+json"
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read() if method == "GET" else b""
            data = json.loads(body) if github and body else None
            return data, resp.headers
    except urllib.error.HTTPError as e:
        if e.code in (403, 429) and e.headers.get("X-RateLimit-Remaining") == "0":
            reset = e.headers.get("X-RateLimit-Reset")
            when = datetime.fromtimestamp(int(reset)).strftime("%H:%M") if reset else "later"
            raise LookupError_(f"GitHub rate limit hit (resets {when}); set GITHUB_TOKEN")
        if e.code == 404:
            raise LookupError_("404 not found")
        # Include GitHub's own explanation, which says why a 403 happened.
        detail = ""
        try:
            detail = json.loads(e.read()).get("message", "")
        except (ValueError, OSError):
            pass
        if e.headers.get("X-GitHub-SSO"):
            detail = "token not authorised for this org's SSO (Configure SSO on the token)"
        raise LookupError_(f"HTTP {e.code}: {detail}" if detail else f"HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LookupError_(f"network error: {getattr(e, 'reason', e)}")


def gh(path):
    """GET a GitHub API path and return the decoded JSON."""
    return http(API + path, github=True)[0]


def day(iso):
    """Reduce an ISO-8601 timestamp (as GitHub returns) to YYYY-MM-DD."""
    return iso[:10]


def commit_date(c):
    """Date of a commit object from the commits API."""
    return day(c["commit"]["committer"]["date"])


def latest_release(org, repo, prefix=None):
    """Return (date, version, "release") for the repo's latest release.

    With ``prefix``, only releases whose tag starts with it count (monorepos that tag
    each component, e.g. "tool-a/v1.2.0"); the prefix is removed from the version.
    Drafts and pre-releases are skipped, matching /releases/latest.
    """
    if not prefix:
        rel = gh(f"/repos/{org}/{repo}/releases/latest")
        return day(rel["published_at"] or rel["created_at"]), rel["tag_name"], "release"
    for page in range(1, 6):  # newest first; 5 x 100 releases is plenty
        rels = gh(f"/repos/{org}/{repo}/releases?per_page=100&page={page}")
        for rel in rels:
            tag = rel["tag_name"]
            if tag.startswith(prefix) and not rel["draft"] and not rel["prerelease"]:
                return day(rel["published_at"] or rel["created_at"]), tag[len(prefix):], "release"
        if len(rels) < 100:
            break
    raise LookupError_(f"no release with tag prefix '{prefix}'")


def check_github_repo(org, repo, mode=None, prefix=None):
    """Return (date, version, source) for a plain repo URL.

    ``mode`` "commit" skips releases and tags (monorepos, where a release belongs
    to one component) and uses the latest commit on the default branch.
    """
    base = f"/repos/{org}/{repo}"
    if mode == "commit":
        commits = gh(f"{base}/commits?per_page=1")
        if commits:
            return commit_date(commits[0]), None, "commit"
        raise LookupError_("repo has no commits")
    if prefix:
        return latest_release(org, repo, prefix)
    try:
        return latest_release(org, repo)
    except LookupError_ as e:
        if "404" not in str(e):
            raise  # rate limit / network: a fallback would fail the same way
    tags = gh(f"{base}/tags?per_page=1")
    if tags:
        return commit_date(gh(f"{base}/commits/{tags[0]['commit']['sha']}")), None, "tag"
    commits = gh(f"{base}/commits?per_page=1")
    if commits:
        return commit_date(commits[0]), None, "commit"
    raise LookupError_("repo has no commits")


def check_github_path(org, repo, branch, path, mode=None, prefix=None):
    """Return (date, version, source) for a folder/file URL.

    Default is the latest commit touching ``path``. ``mode`` "release" uses the
    repo's latest release instead; ``prefix`` narrows that to one component's tags.
    """
    if mode == "release" or (prefix and mode != "commit"):
        return latest_release(org, repo, prefix)
    q = urllib.parse.urlencode({"path": urllib.parse.unquote(path), "sha": urllib.parse.unquote(branch), "per_page": 1})
    commits = gh(f"/repos/{org}/{repo}/commits?{q}")
    if not commits:
        raise LookupError_("no commits found for that path")
    return commit_date(commits[0]), None, "path-commit"


def check_other(url):
    """Return (date, None, source) from the Last-Modified header, trying HEAD then GET."""
    last = None
    for method in ("HEAD", "GET"):
        try:
            _, hdrs = http(url, method=method)
        except LookupError_ as e:
            last = e
            continue
        lm = hdrs.get("Last-Modified")
        if lm:
            return parsedate_to_datetime(lm).strftime("%Y-%m-%d"), None, "last-modified"
        last = LookupError_("no Last-Modified header")
    raise last


def check_archived(org, repo):
    """True/False from the repo API, or None if it can't be determined."""
    try:
        return bool(gh(f"/repos/{org}/{repo}").get("archived"))
    except LookupError_:
        return None


def check(url, mode=None, prefix=None):
    """Resolve one URL; ``mode`` is the entry's update_source. Returns a dict with date/version/source/archived/note."""
    res = {"date": None, "version": None, "source": None, "archived": None, "note": ""}
    try:
        m = GH_PATH.match(url)
        if m:
            org, repo, _kind, branch, path = m.groups()
            res["date"], res["version"], res["source"] = check_github_path(org, repo, branch, path, mode, prefix)
            res["archived"] = check_archived(org, repo)
            return res
        m = GH_REPO.match(url)
        if m:
            org, repo = m.groups()
            res["date"], res["version"], res["source"] = check_github_repo(org, repo, mode, prefix)
            res["archived"] = check_archived(org, repo)
            return res
        res["date"], res["version"], res["source"] = check_other(url)
    except LookupError_ as e:
        res["note"] = str(e)
    return res


def clean_version(tag):
    """Strip a leading 'v' from a release tag (v1.2.3 -> 1.2.3)."""
    return re.sub(r"^[vV](?=\d)", "", tag) if tag else None


# ---- writing ----------------------------------------------------------------

def set_field(text, key, value):
    """Set ``key`` to ``value`` in raw JSON text, preserving formatting. Returns new text."""
    new = json.dumps(value)
    pat = re.compile(rf'^(\s*"{re.escape(key)}"\s*:\s*)"(?:[^"\\]|\\.)*"', re.M)
    if pat.search(text):
        return pat.sub(lambda m: m.group(1) + new, text, count=1)
    # Key missing: insert on a new line after the "url" line (always present).
    m = re.search(r'^(\s*)"url"\s*:.*$', text, re.M)
    if not m:
        raise ValueError("no url line to anchor on")
    line = m.group(0)
    indent = m.group(1)
    if line.rstrip().endswith(","):
        return text.replace(line, f'{line}\n{indent}"{key}": {new},', 1)
    return text.replace(line, f'{line.rstrip()},\n{indent}"{key}": {new}', 1)


# ---- main -------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true", help="update `updated` (and `version`) in the catalogue files")
    ap.add_argument("--no-version", action="store_true", help="with --write, leave `version` alone")
    ap.add_argument("--allow-older", action="store_true",
                    help="with --write, also replace a stored date with an older found date (default: dates only move forward)")
    ap.add_argument("--json", metavar="PATH", help="also write the results as JSON")
    ap.add_argument("ids", nargs="*", metavar="ID",
                    help="only check these catalogue entries (filename without .json); default: all")
    args = ap.parse_args()

    files = sorted(p for p in CATALOG.rglob("*.json") if ".example" not in p.parts)
    if args.ids:
        known = {p.stem for p in files}
        unknown = [i for i in args.ids if i not in known]
        if unknown:
            ap.error(f"unknown id(s): {', '.join(unknown)}")
        files = [p for p in files if p.stem in set(args.ids)]
    rows = []
    for path in files:
        try:
            tool = json.loads(path.read_text(encoding="utf-8"))
            url = tool["url"]
        except (ValueError, KeyError) as e:
            rows.append({"id": path.stem, "path": path, "cur_date": None, "cur_version": None,
                         "date": None, "version": None, "source": None, "archived": None,
                         "note": f"bad entry: {e}"})
            continue
        r = check(url, tool.get("update_source"), tool.get("release_tag_prefix"))
        r["version"] = clean_version(r["version"])
        rows.append({"id": path.stem, "path": path, "cur_date": tool.get("updated"),
                     "cur_version": tool.get("version"), **r})
        print(f"  checked {path.stem}", file=sys.stderr)

    rows.sort(key=lambda r: (r["date"] or "0000", r["id"]))

    cols = ["id", "updated", "found", "version", "found ver", "source", "archived", "note"]
    table = []
    for r in rows:
        note = r["note"]
        if r["date"] and r["cur_date"] and r["date"] != r["cur_date"]:
            note = (note + " " if note else "") + ("date differs" if r["date"] > r["cur_date"] else "stored date is newer")
        if r["version"] and r["cur_version"] and r["version"] != r["cur_version"]:
            note = (note + "; " if note else "") + "version differs"
        arch = "" if r["archived"] is None else ("ARCHIVED" if r["archived"] else "no")
        table.append([r["id"], r["cur_date"] or "-", r["date"] or "?", r["cur_version"] or "-",
                      r["version"] or "-", r["source"] or "-", arch, note])
    widths = [max(len(c), *(len(row[i]) for row in table)) for i, c in enumerate(cols)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*cols))
    print(fmt.format(*("-" * w for w in widths)))
    for row in table:
        print(fmt.format(*row).rstrip())

    failed = sum(1 for r in rows if not r["date"])
    print(f"\n{len(rows) - failed} of {len(rows)} resolved, {failed} unknown/failed.")

    if args.json:
        out = [{k: (str(v) if isinstance(v, Path) else v) for k, v in r.items()} for r in rows]
        Path(args.json).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.json}")

    if args.write:
        changed = 0
        for r in rows:
            if not r["date"]:
                continue
            text = orig = r["path"].read_text(encoding="utf-8")
            msgs = []
            older = bool(r["cur_date"]) and r["date"] < r["cur_date"] and not args.allow_older
            if r["date"] != r["cur_date"] and not older:
                text = set_field(text, "updated", r["date"])
                msgs.append(f"updated {r['cur_date'] or '-'} -> {r['date']}")
            if not args.no_version and r["source"] == "release" and r["version"] and r["version"] != r["cur_version"]:
                text = set_field(text, "version", r["version"])
                msgs.append(f"version {r['cur_version'] or '-'} -> {r['version']}")
            if text != orig:
                json.loads(text)  # never leave a broken file behind
                r["path"].write_text(text, encoding="utf-8")
                changed += 1
                print(f"  {r['path'].relative_to(BUILD.parent)}: {', '.join(msgs)}")
        print(f"\nUpdated {changed} file(s)." + (" Now run: python3 build/build.py" if changed else ""))
    elif any(r["date"] and r["date"] != r["cur_date"] for r in rows):
        print("Dry run: re-run with --write to apply these dates" + ("" if args.no_version else " and release versions") + ".")

    return 1 if rows and failed == len(rows) else 0


if __name__ == "__main__":
    sys.exit(main())
