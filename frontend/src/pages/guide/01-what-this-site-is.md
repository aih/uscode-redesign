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

**It is not an official publication of the United States government.** Nothing here amends,
replaces or interprets what the OLRC publishes. If you need the official text, or the official
currency of a title, go to [uscode.house.gov](https://uscode.house.gov/). Every page on this site
names the release point its text came from and links to the source file it was parsed from.

## The idea

Every provision of the United States Code has an address, at every point in time it has existed.

The address is the citation you already know. Section 45f of Title 16 is at `/us/usc/t16/s45f`,
and subsection (c)(5) of it is at `/us/usc/t16/s45f/c/5`. That path is not a scheme invented for
this site — it is the `@identifier` the OLRC puts on the element in its own XML, so the URL and the
official markup say the same thing.

The second half — *at every point in time* — is what the rest of this guide is mostly about. The
Code is republished in full at each **release point**, named for the last public law it includes.
Add `?release=` or `?date=` to any address and you get that provision as it stood then, rather than
as it stands now.

## What is here

The front page lists the titles that are loaded, and how many release points each one is held at.

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

## What it is not

Two things this guide describes are built but switched off: **accounts** and **bulk downloads**.
Their controls are still on the page and explain themselves rather than failing — see
[Accounts and watchlists](/app/guide/07-accounts).

The site is also **not indexed by search engines**. It serves `robots.txt` disallowing every
crawler, because the addressable space — 65,938 sections across 382 release points, plus a diff
between any two of them — is effectively unbounded, and two AI crawlers walking it drove 43,068
requests in an hour against roughly 48 from human browsers. That is a decision about a demo, and it
is written down with the traffic that prompted it in ADR-0037.

## Watch it instead

There is a [three-minute demo](/app/demo) of the site — a citation, a release point, a version
history, a redline, the search box, the copy control and a hover preview. It is recorded from this
guide: every scene is one of the walkthroughs below, and the captions are the guide's own sentences,
so the video cannot show you something the guide does not describe.

```scenario
id: demo-page
title: The demo video is on the site
steps:
  - goto: /app/demo
  - expect: { selector: "video", visible: true }
```

## About this guide

Every behavioural claim in these chapters carries a **“How this is verified”** box listing the
steps that demonstrate it. Those steps run as Playwright tests on every push, and the ones marked
*in the demo video* are also the script the demo recording follows. A claim here that stopped being
true would turn the build red.

That is not documentation zeal for its own sake. The site's own search guide spent a fortnight
telling readers it could only search current text, months after the full index was built — a true
sentence that quietly became a false one because nothing was checking it. ADR-0038 records the
design that followed.

```scenario
id: about-disclaimer
title: The site says plainly that it is not official
steps:
  - goto: /app/about
  - expect:
      selector: main
      contains: not an official publication of the United States government
```
