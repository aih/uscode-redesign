"""The proxy's crawler block refuses crawlers and nothing else (ADR-0073).

`deploy/Caddyfile` matches declared crawlers on User-Agent and answers 403
before either backend or the database is reached. The list is maintained by
hand and will always be behind, which is why it carries generic `bot`,
`crawler` and `spider` markers as well as named agents — and those markers are
exactly what could start refusing a reader.

The guide says "scripted use of the API is unaffected" and the ADR says only
self-declared crawling is refused. This is the test that keeps both true.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CADDYFILE = Path(__file__).resolve().parent.parent / "deploy" / "Caddyfile"

# Real agents that must reach the site: browsers, and the clients someone would
# use against /api/v1, which is a public API and meant to be called.
ALLOWED = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    # Playwright's browser, which is what make test-e2e and the axe matrix use.
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/140.0.0.0 Safari/537.36",
    "curl/8.7.1",
    "python-requests/2.32.3",
    # The api container's own healthcheck.
    "Python-urllib/3.12",
    "Wget/1.21.4",
    "PostmanRuntime/7.42.0",
    "Go-http-client/2.0",
    "node-fetch/3.3.2",
    "uscode-research-script/1.0 (contact: someone@example.org)",
    # "Abbott" contains "bot" — the trap the generic markers have to avoid.
    "Mozilla/5.0 (compatible; Abbott/1.0)",
]

BLOCKED = [
    # The agent that took the site down on 2026-08-19.
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 (compatible; meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler))",
    # The two ADR-0037 measured, which did stop when asked.
    "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; +https://openai.com/gptbot",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
    "Mozilla/5.0 (compatible; Bytespider; spider-feedback@bytedance.com)",
    "Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)",
    "Mozilla/5.0 (compatible; SemrushBot/7~bl; +http://www.semrush.com/bot.html)",
    "CCBot/2.0 (https://commoncrawl.org/faq/)",
    "facebookexternalhit/1.1",
    "Scrapy/2.11 (+https://scrapy.org)",
]


def crawler_pattern() -> re.Pattern[str]:
    """The live pattern, read out of the Caddyfile rather than copied here.

    Copied, this test would go on passing after someone narrowed the rule in
    the file it is meant to be about.
    """
    source = CADDYFILE.read_text()
    match = re.search(r'@crawlers header_regexp User-Agent "\(\?i\)\((.*)\)"', source)
    assert match, "no @crawlers matcher in deploy/Caddyfile"
    # Caddy reads the file's `\b` as a literal backslash-b in the regex; Python
    # gets the same two characters out of the file and needs no unescaping.
    return re.compile(match.group(1), re.IGNORECASE)


@pytest.mark.parametrize("agent", ALLOWED)
def test_a_reader_or_a_script_is_not_refused(agent: str) -> None:
    assert not crawler_pattern().search(agent), f"would 403 a legitimate client: {agent}"


@pytest.mark.parametrize("agent", BLOCKED)
def test_a_declared_crawler_is_refused(agent: str) -> None:
    assert crawler_pattern().search(agent), f"would serve a declared crawler: {agent}"
