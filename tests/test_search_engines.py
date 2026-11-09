"""Google and Bing may fetch the landing pages and nothing else (ADR-0098).

Three parts of `deploy/Caddyfile` have to agree: the robots.txt it serves, the
sitemap it serves, and the paths in `(search_engine_landing)`, which exempts
Google's and Bing's published address ranges from the crawler 403 and the
cookie gate. Each is read out of the file here.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parent.parent
CADDYFILE = (ROOT / "deploy" / "Caddyfile").read_text()
GUIDE = ROOT / "frontend" / "src" / "pages" / "guide"


def heredoc(name: str) -> str:
    match = re.search(rf"<<{name}\n(.*?)\n\s*{name} 200", CADDYFILE, re.S)
    assert match, f"no {name} heredoc in deploy/Caddyfile"
    return "\n".join(line.strip() for line in match.group(1).splitlines())


def groups() -> dict[str, list[tuple[str, str]]]:
    """robots.txt as {agent: [(directive, pattern)]}."""
    out: dict[str, list[tuple[str, str]]] = {}
    agents: list[str] = []
    rules: list[tuple[str, str]] = []
    for line in heredoc("ROBOTS").splitlines() + [""]:
        if not line:
            for agent in agents:
                out[agent.lower()] = rules
            agents, rules = [], []
            continue
        key, _, value = line.partition(":")
        if key.lower() == "user-agent":
            agents.append(value.strip())
        elif key.lower() in ("allow", "disallow"):
            rules.append((key.lower(), value.strip()))
    return out


def allowed(rules: list[tuple[str, str]], path: str) -> bool:
    """Google's reading: the longest matching rule wins, Allow on a tie."""
    best: tuple[int, bool] = (-1, True)
    for directive, pattern in rules:
        regex = "".join(".*" if c == "*" else re.escape(c) for c in pattern.rstrip("$"))
        regex += "$" if pattern.endswith("$") else ""
        if re.match(regex, path):
            candidate = (len(pattern), directive == "allow")
            if candidate[0] > best[0] or (candidate[0] == best[0] and candidate[1]):
                best = candidate
    return best[1]


def sitemap_paths() -> list[str]:
    locs = re.findall(r"<loc>(.*?)</loc>", heredoc("SITEMAP"))
    assert locs
    return [urlsplit(loc.split("}", 1)[-1] if "}" in loc else loc).path for loc in locs]


def landing_paths() -> list[str]:
    match = re.search(r"\(search_engine_landing\) \{(.*?)\n\}", CADDYFILE, re.S)
    assert match, "no (search_engine_landing) snippet"
    body = match.group(1)
    assert "client_ip 192.0.2.255/32" in body, "the sentinel range keeps the matcher closed without a ranges file"
    path_line = re.search(r"^\s*path (.*)$", body, re.M)
    assert path_line
    return path_line.group(1).split()


def in_landing(path: str) -> bool:
    return any(p == path or (p.endswith("*") and path.startswith(p[:-1])) for p in landing_paths())


@pytest.mark.parametrize("agent", ["googlebot", "bingbot"])
def test_every_sitemap_page_is_allowed_to_the_search_engines(agent: str) -> None:
    rules = groups()[agent]
    for path in sitemap_paths():
        assert allowed(rules, path), f"robots.txt disallows {path} to {agent}"
        assert in_landing(path), f"{path} is in the sitemap and not in (search_engine_landing)"


def test_every_guide_chapter_is_in_the_sitemap() -> None:
    chapters = {f"/app/guide/{p.stem}" for p in GUIDE.glob("*.md")}
    assert chapters and chapters <= set(sitemap_paths())


@pytest.mark.parametrize(
    "path",
    ["/app/us/usc/t16/s45f", "/app/?release=119-99", "/app/search", "/app/diff/us/usc/t16/s1", "/api/v1/status", "/us/usc/t16/s1"],
)
def test_the_rest_stays_disallowed(path: str) -> None:
    for agent in ("googlebot", "bingbot"):
        assert not allowed(groups()[agent], path), f"{path} allowed to {agent}"
        assert not (in_landing(path.split("?")[0]) and "?" not in path), f"{path} exempted from the crawler block"


def test_every_other_agent_is_disallowed_everything() -> None:
    assert groups()["*"] == [("disallow", "/")]


def test_robots_names_the_sitemap() -> None:
    assert re.search(r"^Sitemap: \{\$USC_SITE_ORIGIN:https://uscode\.linkedlegislation\.org\}/sitemap\.xml$",
                     heredoc("ROBOTS"), re.M)
