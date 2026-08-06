---
layout: ../../layouts/GuideLayout.astro
title: What this site is
order: 1
summary: A reader for the United States Code where every provision has an address, at every point in time it has existed.
covers:
  routes: ["/app/", "/app/about", "/app/demo"]
  adrs: [37, 38]
---

This is a conceptual redesign of the [Office of the Law Revision Counsel](https://uscode.house.gov/)'s
United States Code website, built entirely from the official USLM downloads.

This site is not an official publication of the United States government. If you need the official text, or the official
currency of a title, go to [uscode.house.gov](https://uscode.house.gov/). Every page on this site
names the release point its text came from and links to the source file it was parsed from.

## The idea

Every provision of the United States Code has an address, at every point in time it has existed.

The address corresponds directly to the citation. For example, section 45f of Title 16 is at `/us/usc/t16/s45f`,
and subsection (c)(5) of it is at `/us/usc/t16/s45f/c/5`. That path follows the official `@identifier` scheme in USLM.

The site also allows you to trace the history of a provision. The
Code is republished in full at each **release point**, named for the last public law it includes.
Add `?release=` or `?date=` to any address and you get that provision as it stood then, rather than
as it stands now.

## Landing page

The landing or front page lists the titles that are loaded, and how many release points each one is held at.

```scenario
id: front-page-titles
title: Open a title from the front page
demo: true
demoOrder: 10
steps:
  - goto: /app/
    caption: Every provision of the US Code has an address — at every point in time it has existed.
  - expect: { selector: ".toc", contains: "Title 16" }
    caption: The front page lists the titles that are loaded.
```

## Inactive features and indexing

Two features described in this guide are currently inactive: **accounts** and **bulk downloads**.
Their controls are still visible on the page to explain their intended functionality — see
[Accounts and watchlists](/app/guide/07-accounts).

The site also serves a `robots.txt` disallowing search engine crawlers. The addressable space is effectively unbounded, so this prevents automated crawling from consuming excessive resources.

## Video demonstration

There is a [demo video](/app/demo) of the site — a citation, a release point, a version
history, a redline, the search box, the copy control and a hover preview. It is recorded from this
guide: every scene is one of the walkthroughs below, and the captions are the guide's own sentences, and is kept in sync with the Guide through automated CI/CD.

```scenario
id: demo-page
title: The demo video is on the site
steps:
  - goto: /app/demo
  - expect: { selector: "video", visible: true }
```

## About this guide

Every feature in these chapters carries a **“How this is verified”** box listing the
steps that demonstrate it. Those steps run as Playwright tests on every push, and the ones marked
*in the demo video* are also the script the demo recording follows. A claim here that stopped being
true would fail in testing.

This approach ensures that the documentation remains accurate as the application evolves.

```scenario
id: about-disclaimer
title: The site says plainly that it is not official
steps:
  - goto: /app/about
  - expect:
      selector: main
      contains: not an official publication of the United States government
```
