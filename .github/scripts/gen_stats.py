#!/usr/bin/env python3
"""Render self-hosted GitHub stat cards as SVG.

Replaces github-readme-stats (whose public instance is frequently rate-limited
or paused) with cards we generate ourselves and commit into the repo, styled to
match assets/hero.svg.

Usage:  GITHUB_TOKEN=... GH_USER=kasra-nikshabani python3 gen_stats.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

API = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    login
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar { totalContributions }
    }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

# ── palette (mirrors assets/hero.svg) ────────────────────────────────────────
BG_FROM, BG_MID, BG_TO = "#05070f", "#0d1226", "#05070f"
CYAN, INDIGO, PINK = "#22d3ee", "#818cf8", "#f472b6"
TEXT, MUTED, FAINT = "#dbe4f0", "#7c8aa5", "#4b5b75"

W, H = 470, 210

# GitHub's linguist colours — only needed for seed mode, since the GraphQL API
# returns the colour alongside each language.
LANG_COLORS = {
    "HTML": "#e34c26", "CSS": "#563d7c", "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6", "Python": "#3572A5", "Java": "#b07219",
    "Go": "#00ADD8", "Shell": "#89e051", "C": "#555555", "C++": "#f34b7d",
    "C#": "#178600", "PHP": "#4F5D95", "Ruby": "#701516", "Rust": "#dea584",
    "Kotlin": "#A97BFF", "Swift": "#F05138", "Dart": "#00B4AB",
    "Vue": "#41b883", "SCSS": "#c6538c", "Dockerfile": "#384d54",
}

FONT_SANS = ('ui-sans-serif, -apple-system, "Segoe UI", Inter, Roboto, '
             '"Helvetica Neue", Arial, sans-serif')
FONT_MONO = ('ui-monospace, "SFMono-Regular", "SF Mono", Menlo, Consolas, '
             '"Liberation Mono", monospace')


def with_retry(call, attempts: int = 4):
    """Retry transient network failures with a short backoff."""
    for attempt in range(attempts):
        try:
            return call()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code < 500:
                raise                      # 4xx is our fault; don't hammer it
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)


def fetch(login: str, token: str) -> dict:
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{login}-profile-cards",
        },
    )
    payload = with_retry(lambda: json.load(urllib.request.urlopen(req, timeout=30)))
    if "errors" in payload:
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def fetch_public(login: str) -> dict:
    """Token-free seed data from the REST API.

    Used to commit honest starter cards: everything the anonymous API can
    confirm is real, and anything requiring a token renders as an em dash
    until the workflow runs. Never invent numbers here.
    """
    def rest(path: str):
        req = urllib.request.Request(
            f"https://api.github.com{path}", headers={"User-Agent": f"{login}-cards"}
        )
        return with_retry(lambda: json.load(urllib.request.urlopen(req, timeout=30)))

    nodes = []
    for repo in rest(f"/users/{login}/repos?per_page=100"):
        if repo["fork"]:
            continue
        langs = rest(f"/repos/{login}/{repo['name']}/languages")
        nodes.append({
            "stargazerCount": repo["stargazers_count"],
            "languages": {"edges": [
                {"size": size, "node": {"name": name, "color": LANG_COLORS.get(name)}}
                for name, size in langs.items()
            ]},
        })

    return {
        "contributionsCollection": {
            "totalCommitContributions": None,
            "restrictedContributionsCount": 0,
            "contributionCalendar": {"totalContributions": None},
        },
        "pullRequests": {"totalCount": None},
        "issues": {"totalCount": None},
        "repositories": {"totalCount": len(nodes), "nodes": nodes},
    }


def human(n: int | None) -> str:
    if n is None:          # seed mode: unknown until the workflow runs
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + "m"
    if n >= 1_000:
        return f"{n / 1_000:.1f}".rstrip("0").rstrip(".") + "k"
    return str(n)


def shell(title: str, body: str, uid: str) -> str:
    """Common card chrome: gradient background, grid, border, title."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{escape(title)}">
  <title>{escape(title)}</title>
  <defs>
    <linearGradient id="bg{uid}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{BG_FROM}"/>
      <stop offset="45%" stop-color="{BG_MID}"/>
      <stop offset="100%" stop-color="{BG_TO}"/>
    </linearGradient>
    <linearGradient id="ac{uid}" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{W}" y2="0">
      <stop offset="0%" stop-color="{CYAN}"/>
      <stop offset="55%" stop-color="{INDIGO}"/>
      <stop offset="100%" stop-color="{PINK}"/>
    </linearGradient>
    <linearGradient id="rl{uid}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{CYAN}" stop-opacity=".55"/>
      <stop offset="100%" stop-color="{PINK}" stop-opacity="0"/>
    </linearGradient>
    <pattern id="gr{uid}" width="28" height="28" patternUnits="userSpaceOnUse">
      <path d="M28 0H0V28" fill="none" stroke="#93c5fd" stroke-opacity=".07"/>
    </pattern>
    <clipPath id="cd{uid}"><rect width="{W}" height="{H}" rx="14"/></clipPath>
    <style>
      .s{uid} {{ font-family: {FONT_SANS}; }}
      .m{uid} {{ font-family: {FONT_MONO}; }}
    </style>
  </defs>
  <g clip-path="url(#cd{uid})">
    <rect width="{W}" height="{H}" fill="url(#bg{uid})"/>
    <rect width="{W}" height="{H}" fill="url(#gr{uid})"/>
    <text class="s{uid}" x="24" y="40" font-size="16" font-weight="700" fill="url(#ac{uid})">{escape(title)}</text>
    <rect x="24" y="54" width="{W - 48}" height="1.5" rx="1" fill="url(#rl{uid})"/>
{body}
  </g>
  <rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="#ffffff" stroke-opacity=".10"/>
</svg>
"""


def stats_card(u: dict) -> str:
    c = u["contributionsCollection"]
    stars = sum(r["stargazerCount"] for r in u["repositories"]["nodes"])
    own = c["totalCommitContributions"]
    commits = None if own is None else own + c["restrictedContributionsCount"]

    items = [
        ("Contributions", c["contributionCalendar"]["totalContributions"], CYAN),
        ("Total Commits", commits, INDIGO),
        ("Public Repos", u["repositories"]["totalCount"], PINK),
        ("Pull Requests", u["pullRequests"]["totalCount"], CYAN),
        ("Issues", u["issues"]["totalCount"], INDIGO),
        ("Total Stars", stars, PINK),
    ]

    rows = []
    for i, (label, value, color) in enumerate(items):
        x = 24 + (i % 2) * 224
        y = 92 + (i // 2) * 40
        rows.append(
            f'    <g>\n'
            f'      <circle cx="{x + 5}" cy="{y - 5}" r="3.5" fill="{color}"/>\n'
            f'      <text class="mS" x="{x + 18}" y="{y}" font-size="12" fill="{MUTED}">{escape(label)}</text>\n'
            f'      <text class="sS" x="{x + 200}" y="{y + 1}" font-size="17" font-weight="700" '
            f'fill="{TEXT}" text-anchor="end">{human(value)}</text>\n'
            f'      <rect x="{x + 18}" y="{y + 8}" width="182" height="1" fill="#ffffff" fill-opacity=".05"/>\n'
            f'    </g>'
        )
    return shell("⚡ GitHub Stats", "\n".join(rows), "S")


def langs_card(u: dict) -> str:
    totals: dict[str, int] = {}
    colors: dict[str, str] = {}
    for repo in u["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + edge["size"]
            colors[name] = edge["node"]["color"] or INDIGO

    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:8]
    grand = sum(v for _, v in ranked) or 1

    bar_x, bar_y, bar_w, bar_h = 24, 76, W - 48, 12
    segments, legend = [], []
    cursor = 0.0

    for i, (name, size) in enumerate(ranked):
        pct = size / grand * 100
        seg_w = max(bar_w * size / grand, 1.5)
        # Base width is the final width so the bar is correct even if the
        # renderer ignores SMIL; the animation is a progressive enhancement.
        segments.append(
            f'      <rect x="{cursor + bar_x:.1f}" y="{bar_y}" width="{seg_w:.1f}" height="{bar_h}" fill="{colors[name]}">\n'
            f'        <animate attributeName="width" from="0" to="{seg_w:.1f}" dur=".8s" '
            f'begin="{i * 0.08:.2f}s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.4 0 0.2 1"/>\n'
            f'      </rect>'
        )
        cursor += seg_w

        lx = 24 + (i % 2) * 224
        ly = 122 + (i // 2) * 22
        legend.append(
            f'    <g>\n'
            f'      <circle cx="{lx + 5}" cy="{ly - 4}" r="4.5" fill="{colors[name]}"/>\n'
            f'      <text class="mL" x="{lx + 18}" y="{ly}" font-size="12" fill="{TEXT}">{escape(name)}</text>\n'
            f'      <text class="mL" x="{lx + 196}" y="{ly}" font-size="11" fill="{MUTED}" '
            f'text-anchor="end">{pct:.1f}%</text>\n'
            f'    </g>'
        )

    body = (
        f'    <clipPath id="barL"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="6"/></clipPath>\n'
        f'    <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="6" fill="#ffffff" fill-opacity=".05"/>\n'
        f'    <g clip-path="url(#barL)">\n' + "\n".join(segments) + "\n    </g>\n"
        + "\n".join(legend)
    )
    return shell("◆ Most Used Languages", body, "L")


def main() -> int:
    seed = "--seed" in sys.argv
    token = os.environ.get("GITHUB_TOKEN")
    login = os.environ.get("GH_USER")

    if not login:
        print("GH_USER must be set", file=sys.stderr)
        return 1
    if not seed and not token:
        print("GITHUB_TOKEN must be set (or pass --seed)", file=sys.stderr)
        return 1

    try:
        user = fetch_public(login) if seed else fetch(login, token)
    except urllib.error.HTTPError as exc:
        print(f"GitHub API {exc.code}: {exc.read().decode()[:200]}", file=sys.stderr)
        return 1

    out = os.path.join(os.path.dirname(__file__), "..", "..", "assets")
    os.makedirs(out, exist_ok=True)

    for filename, svg in (("stats.svg", stats_card(user)), ("langs.svg", langs_card(user))):
        path = os.path.join(out, filename)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(svg)
        print(f"wrote {os.path.normpath(path)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
