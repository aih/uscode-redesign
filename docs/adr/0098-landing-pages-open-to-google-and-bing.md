# ADR-0098 — Landing pages open to Google and Bing

**Status:** accepted (2026-11-09)

**Related:** ADR-0037 (`Disallow: /`), ADR-0073 (the crawler 403), ADR-0088 (the cookie gate),
the same change in the statutes repository (its ADR-0039) and in reintroductions-us.

## Context

The site is to be added to Google Search Console. Three things kept every search engine out:
`robots.txt` was `Disallow: /` for every agent, the crawler pattern in `deploy/Caddyfile` matches
`Googlebot/2.1` and `bingbot/2.0` (its generic `bot/` marker), and the cookie gate answers 403 to
any `/app` request without `usc_h`, which a crawler does not keep. A sitemap alone would have
listed pages that answered 403.

## Decision

1. `robots.txt` gains a group for `Googlebot` and `Bingbot` that allows `/`, `/app/`, `/app/about`,
   `/app/guide` and its chapters, `/app/us/usc`, `/sitemap.xml`, and the static assets a page needs
   to render (`/app/_astro/`, `/app/fonts/`, `/app/uswds/`, `/app/icons/`, `/favicon.svg`,
   `/app/manifest.webmanifest`), and disallows the rest. Rules on page paths end in `$`, so a page
   with a query string (`/app/?release=…`) stays disallowed. The group for `*` is still
   `Disallow: /`. The file ends with `Sitemap: https://uscode.linkedlegislation.org/sitemap.xml`
   (`USC_SITE_ORIGIN` overrides the origin).
2. `/sitemap.xml` is served by the proxy and lists `/app/`, `/app/about`, `/app/us/usc`,
   `/app/guide` and every chapter. `tests/test_search_engines.py` fails when a chapter is missing
   from it, or when a listed page is not allowed by `robots.txt` or not in the exemption below.
3. The snippet `(search_engine_landing)` matches a request from Google's or Bing's published
   crawler ranges, for one of the paths in (1), with no query string. The crawler 403 and the
   cookie gate each carry `not { import search_engine_landing }`.
4. The ranges are `client_ip` lines in `deploy/searchbots/ranges.caddy`, which is not committed.
   `deploy/searchbot-ranges.sh` writes it from
   `developers.google.com/static/search/apis/ipranges/googlebot.json` and
   `www.bing.com/toolbox/bingbot.json`, refusing a list that does not parse or holds fewer than
   ten prefixes and keeping the previous file on any failure. `deploy-on-box.sh` runs it on every
   deploy and recreates the proxy when the file changed. The proxy mounts the directory at
   `/etc/caddy/searchbots`.
5. The snippet always carries `client_ip 192.0.2.255/32`, a documentation address. Without a
   ranges file (the dev stack, CI, a box whose fetch has never succeeded) the import is a glob
   matching nothing and the matcher matches no request.

## Consequences

- A crawler that sends a Googlebot User-Agent from any other address is still refused, at the
  proxy, as before.
- Google and Bing can index the five page types in (1) and nothing under `/app/us/usc/…`, the
  version axis or `/api/v1`.
- The ranges are as current as the last deploy. Google and Bing change them rarely; an address
  added between deploys is refused until the next one.
- Google's user-triggered fetchers (Search Console's URL inspection uses `Google-InspectionTool`,
  from the `googlebot.json` ranges) are covered. Fetchers in Google's other range lists
  (`special-crawlers.json`, `user-triggered-fetchers.json`) are not.
