#!/usr/bin/env python3
"""Validate build/catalog/**/*.json (any subdirectory depth) and build site/data/index.json (standard library only).

Also generates build/config/added.json and README.md (from build/README.template.md).

Usage:  python3 build/build.py          # validate, then write site/data/index.json and README.md
        python3 build/build.py --check  # validate only, and fail if either generated file is stale
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

BUILD = Path(__file__).resolve().parent
ROOT = BUILD.parent
TOOLS_DIR = BUILD / "catalog"
OUT = ROOT / "site" / "data" / "index.json"
ADDED_OUT = BUILD / "config" / "added.json"
README_OUT = ROOT / "README.md"
README_TEMPLATE = BUILD / "README.template.md"

REQUIRED = {"name", "description", "product", "type", "tags", "url"}
OPTIONAL = {"source", "version", "maintainer", "updated", "added", "archived", "archived_reason", "featured", "update_source", "release_tag_prefix", "$schema"}
UPDATE_SOURCES = ("release", "commit")  # how check_updates.py dates a GitHub tool
DEFAULT_SOURCE = "community"  # Broadcom must be stated explicitly
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def load(path):
    """Read and parse a UTF-8 JSON file, returning the decoded data."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate(path, tool, config, tags, errors):
    """Check one tool definition against the schema rules.

    Any problems found are appended to ``errors`` as strings prefixed with the
    file's path relative to the repo root.
    """
    def err(msg):
        """Record a validation error for the current file."""
        errors.append(f"{path.relative_to(ROOT)}: {msg}")

    if not SLUG.match(path.stem):
        err("filename must be lowercase letters, digits and hyphens (e.g. my-tool.json)")
    if not isinstance(tool, dict):
        err("top level must be an object")
        return
    for k in sorted(REQUIRED - tool.keys()):
        err(f"missing required field '{k}'")
    for k in sorted(tool.keys() - REQUIRED - OPTIONAL):
        err(f"unknown field '{k}'")

    for k in ("name", "description"):
        if k in tool and not (isinstance(tool[k], str) and tool[k].strip()):
            err(f"'{k}' must be a non-empty string")

    prods = tool.get("product")
    if "product" in tool:
        if not (isinstance(prods, list) and prods and all(isinstance(p, str) for p in prods)):
            err("'product' must be a non-empty list of strings")
        else:
            for p in prods:
                if p not in config["products"]:
                    err(f"unknown product '{p}' (allowed: {', '.join(config['products'])})")

    if "source" in tool and tool["source"] not in config["sources"]:
        err(f"unknown source '{tool['source']}' (allowed: {', '.join(config['sources'])})")

    if "type" in tool and tool["type"] not in config["types"]:
        err(f"unknown type '{tool['type']}' (allowed: {', '.join(config['types'])})")

    tg = tool.get("tags")
    if "tags" in tool:
        if not (isinstance(tg, list) and all(isinstance(t, str) for t in tg)):
            err("'tags' must be a list of strings")
        else:
            if len(set(tg)) != len(tg):
                err("'tags' contains duplicates")
            for t in tg:
                if t not in tags:
                    err(f"unknown tag '{t}' - add it to build/config/tags.json if it is genuinely new")

    if "url" in tool and not (isinstance(tool["url"], str) and re.match(r"^https?://\S+$", tool["url"])):
        err("'url' must start with http:// or https://")

    for k in ("version", "maintainer"):
        if k in tool and not (isinstance(tool[k], str) and tool[k].strip()):
            err(f"'{k}' must be a non-empty string")

    if "update_source" in tool and tool["update_source"] not in UPDATE_SOURCES:
        err(f"'update_source' must be one of: {', '.join(UPDATE_SOURCES)}")

    if "release_tag_prefix" in tool:
        if not (isinstance(tool["release_tag_prefix"], str) and tool["release_tag_prefix"]):
            err("'release_tag_prefix' must be a non-empty string")
        if tool.get("update_source") == "commit":
            err("'release_tag_prefix' cannot be combined with update_source 'commit'")

    if "archived" in tool and not isinstance(tool["archived"], bool):
        err("'archived' must be true or false")
    if "archived_reason" in tool:
        if not (isinstance(tool["archived_reason"], str) and tool["archived_reason"].strip()):
            err("'archived_reason' must be a non-empty string")
        if tool.get("archived") is not True:
            err("'archived_reason' is only allowed when 'archived' is true")

    if "featured" in tool:
        if not isinstance(tool["featured"], bool):
            err("'featured' must be true or false")
        elif tool["featured"] and tool.get("archived") is True:
            err("an archived tool cannot be 'featured'")

    for k in ("updated", "added"):
        if k in tool:
            try:
                date.fromisoformat(tool[k])
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", tool[k]):
                    raise ValueError
            except (ValueError, TypeError):
                err(f"'{k}' must be a date like 2026-01-31")


# ---- README generation ------------------------------------------------------

def esc(text):
    """Escape text so it renders literally inside a Markdown table cell."""
    text = " ".join(str(text).split())  # no newlines inside a table cell
    return re.sub(r"([\\`*_\[\]<>|])", r"\\\1", text)


def md_url(url):
    """Percent-encode spaces and parentheses so a URL is safe in a Markdown link."""
    return url.replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def short_url(url):
    """Return a URL without its https:// prefix or trailing slash, for display."""
    return re.sub(r"^https://", "", url).rstrip("/")


def slug(text):
    """GitHub's heading anchor: lowercase, punctuation removed, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")


TABLE_HEADER = ["| Tool | Description | Updated |", "| --- | --- | --- |"]


def tool_row(t, sources):
    """Render one tool as a Markdown table row for the README."""
    name = f"[{esc(t['name'])}]({md_url(t['url'])})"
    cells = [name, esc(t["description"]), t.get("updated", "").replace("-", "\u2011")]  # non-breaking hyphens keep the date on one line
    return "| " + " | ".join(cells) + " |"


def render_readme(index, config):
    """Build the README text by filling build/README.template.md from the index."""
    all_tools = index["tools"]
    tools = [t for t in all_tools if not t["archived"]]
    archived = [t for t in all_tools if t["archived"]]
    sections, toc = [], []
    for key, info in index["products"].items():
        group = [t for t in tools if key in t["product"]]  # a tool can appear under both products
        if not group:
            continue
        title = info["label"]
        toc.append(f"- [{title}](#{slug(title)}) ({len(group)})")
        lines = [f"## {title}", "", *TABLE_HEADER]
        lines += [tool_row(t, index["sources"]) for t in group]
        sections.append("\n".join(lines))

    if archived:
        toc.append(f"- [Archived](#archived) ({len(archived)})")
        lines = ["## Archived", "", "End-of-life or superseded tools, kept for reference.", "",
                 *TABLE_HEADER]
        lines += [tool_row(t, index["sources"]) for t in archived]
        sections.append("\n".join(lines))

    latest = sorted(tools, key=lambda t: t["name"].lower())
    latest = sorted(latest, key=lambda t: t["added"], reverse=True)[: config["latest_count"]]
    latest_lines = []
    for t in latest:
        prods = ", ".join(index["products"][p].get("short") or index["products"][p]["label"] for p in t["product"])
        latest_lines.append(f"- [{esc(t['name'])}]({md_url(t['url'])}) · {esc(prods)} · added {t['added']}")

    featured = [t for t in tools if t.get("featured")]  # already in name order
    featured_text = ""
    if featured:
        flines = ["## Featured", "", *TABLE_HEADER]
        flines += [tool_row(t, index["sources"]) for t in featured]
        featured_text = "\n".join(flines) + "\n\n"

    dates = [t["updated"] for t in tools if t.get("updated")]
    site = config.get("site_url", "").strip()
    site_line = f"\n**Browse, search and filter these tools on the website: {site}**\n" if site else ""
    out = README_TEMPLATE.read_text(encoding="utf-8")
    for token, value in {
        "{{SITE_LINE}}": site_line,
        "{{TOTAL}}": str(len(tools)),
        "{{UPDATED}}": max(dates) if dates else "n/a",
        "{{FEATURED}}": featured_text,
        "{{LATEST}}": "\n".join(latest_lines),
        "{{TOC}}": "\n".join(toc),
        "{{SECTIONS}}": "\n\n".join(sections),
    }.items():
        out = out.replace(token, value)
    banner = "<!-- GENERATED FILE: do not edit. Edit build/README.template.md or build/catalog/*.json, then run build/build.py -->\n"
    return banner + out


def resolve_added(tools):
    """Work out each tool's 'added' date and return the id -> date map to persist.

    A tool's own "added" field wins. Otherwise the first build that sees a new ID
    records today's date in build/config/added.json. On the very first run (no added.json
    yet) existing tools are seeded from their "updated" date so they don't all
    look brand new.
    """
    first_run = not ADDED_OUT.exists()
    known = {} if first_run else load(ADDED_OUT)
    today = date.today().isoformat()
    result = {}
    for t in tools:
        if t.get("added"):
            result[t["id"]] = t["added"]
        elif t["id"] in known:
            result[t["id"]] = known[t["id"]]
        else:
            result[t["id"]] = (t.get("updated") or today) if first_run else today
        t["added"] = result[t["id"]]
    return dict(sorted(result.items()))


def main():
    """Validate all tools, then write (or with --check, verify) generated files."""
    check_only = "--check" in sys.argv
    errors = []
    try:
        config = load(BUILD / "config" / "config.json")
        tags = load(BUILD / "config" / "tags.json")["tags"]
    except (OSError, ValueError, KeyError) as e:
        sys.exit(f"Cannot read build/config/config.json or build/config/tags.json: {e}")

    for key, default in (("new_days", 30), ("latest_count", 5)):
        config.setdefault(key, default)
        if not (isinstance(config[key], int) and not isinstance(config[key], bool) and config[key] > 0):
            sys.exit(f"build/config/config.json: '{key}' must be a positive whole number")

    tools = []
    seen_names = {}
    seen_ids = {}
    for path in sorted(TOOLS_DIR.rglob("*.json")):
        rel_parts = path.relative_to(TOOLS_DIR).parts[:-1]
        if any(part.startswith(".") for part in rel_parts):
            continue  # ignore hidden directories
        try:
            tool = load(path)
        except ValueError as e:
            errors.append(f"{path.relative_to(ROOT)}: invalid JSON ({e})")
            continue
        validate(path, tool, config, tags, errors)
        # The filename is the tool's ID, so it must be unique across all folders.
        if path.stem in seen_ids:
            errors.append(f"{path.relative_to(ROOT)}: duplicate filename '{path.name}' (also at {seen_ids[path.stem]})")
        seen_ids[path.stem] = str(path.relative_to(ROOT))
        if isinstance(tool, dict):
            name = str(tool.get("name", "")).strip().lower()
            if name in seen_names:
                errors.append(f"{path.relative_to(ROOT)}: duplicate name (also used by {seen_names[name]})")
            seen_names[name] = path.name
            entry = {k: v for k, v in tool.items() if k != "$schema"}
            entry.setdefault("source", DEFAULT_SOURCE)
            entry.setdefault("archived", False)
            tools.append({"id": path.stem, **entry})

    if errors:
        print(f"{len(errors)} problem(s) found:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    tools.sort(key=lambda t: t["name"].lower())
    added_map = resolve_added(tools)
    added_text = json.dumps(added_map, indent=2, ensure_ascii=False) + "\n"
    index = {"products": config["products"], "types": config["types"], "sources": config["sources"],
             "new_days": config["new_days"], "tools": tools}
    text = json.dumps(index, indent=2, ensure_ascii=False) + "\n"

    readme = render_readme(index, config)

    if check_only:
        stale = [p.relative_to(ROOT) for p, new in ((ADDED_OUT, added_text), (OUT, text), (README_OUT, readme))
                 if not p.exists() or p.read_text(encoding="utf-8") != new]
        if stale:
            sys.exit(f"Out of date: {', '.join(map(str, stale))}. Run: python3 build/build.py")
        print(f"OK: {len(tools)} tools, generated files are up to date.")
        return

    ADDED_OUT.write_text(added_text, encoding="utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    README_OUT.write_text(readme, encoding="utf-8")
    print(f"Wrote build/config/added.json, site/data/index.json and README.md with {len(tools)} tools.")


if __name__ == "__main__":
    main()
