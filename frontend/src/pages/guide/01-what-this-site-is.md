---
layout: ../../layouts/GuideLayout.astro
title: What this site is
order: 1
summary: A reader for the United States Code where every provision has an address, at every point in time it has existed.
covers:
  routes: ["/app/", "/app/about", "/app/demo"]
  adrs: [37, 38, 65, 69]
---

This is a conceptual redesign of the [Office of the Law Revision Counsel](https://uscode.house.gov/)'s
United States Code website, built from official USLM downloads.

This site is not an official publication of the United States government. If you need the official text, or the official
currency of a title, go to [uscode.house.gov](https://uscode.house.gov/).  Each U.S. Code section on this site links to the source and identifies the release point it came from.

## Addresses

The site is built on an API that associates a url address to each legal citation. For example, section 45f of Title 16 is at `/us/usc/t16/s45f`,
and subsection (c)(5) of it is at `/us/usc/t16/s45f/c/5`. That path follows the official `@identifier` scheme in USLM.

The site and its API also allow you to trace the history of a provision. The
Code is republished in full at each **release point**, named for the last public law it includes.
Add `?release=` or `?date=` to any address and you get that provision as it stood then, rather than
as it stands now.

## Fallbacks

A url for a provision that does not (yet?) exist in the U.S. Code returns a response showing that the provision does not exist. Below that it offers the nearest address, hierarchically — a section that is not there suggests its title; a bad subsection of a real section suggests the
parent section.

```scenario
id: notfound-offers-the-way-back
title: A section that does not exist offers the title it would be in
steps:
  - goto: /app/us/usc/t16/s99999
  - expect: { selector: ".lede", contains: "nothing at /us/usc/t16/s99999" }
  - expect: { selector: ".deadend__step--last a", contains: "Title 16" }
```

Appendix titles are an edge case. For example, `5 U.S.C. App. 3` parses to `/us/usc/t5a/s3`, and the
Office of the Law Revision Counsel does not publish these as such: appendix provisions are filed under
the law that enacted them, at addresses like `/us/usc/t5a/pl/92/463/s1` or
`/us/usc/t50a/act/1917-05-18/ch15/s212`. This site does yet translate one form into the other.

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

The **Titles** menu at the top of every page lists a few selected titles and ends
with **All titles**, which goes to this page.

```scenario
id: titles-menu-to-front-page
title: Reach the title list from any page
steps:
  - goto: /app/us/usc/t16/s45f
  - click: .navdrop--titles > summary
    caption: Titles opens a short list over the page.
  - click: .navdrop__item--all
    caption: All titles goes to the front page.
  - expect: { selector: ".toc", contains: "Title 16" }
```

## Inactive features and indexing

Two features described in this guide are currently inactive: **accounts** and **bulk downloads**.
Their controls are still visible on the page to explain their intended functionality — see
[Accounts and watchlists](/app/guide/07-accounts).

The site also serves a `robots.txt` disallowing search engine crawlers.

## The corpus as a dataset

The parsed corpus is published as a Hugging Face dataset at
[dreamproit/uscode](https://huggingface.co/datasets/dreamproit/uscode), in two configurations:
`current` — one row per section, carrying the text in force at the newest release point — and
`versions` — one row per distinct text a section has had, with the release points it was in
force. Each row carries the section's plain text, its verbatim USLM XML, its citation, its place
in the Code's hierarchy, and its release-point metadata. The dataset is refreshed when OLRC
publishes a new release point; the dataset card documents every field. The
[About page](/app/about) describes it and shows how to load it.

```scenario
id: about-names-the-dataset
title: The About page describes the Hugging Face dataset
steps:
  - goto: /app/about
  - expect: { selector: "main", contains: "dreamproit/uscode" }
```

## Video demonstration

There is a [demo video](/app/demo) of the site — a citation, a release point, a version
history, a redline, the search box, the copy control and a hover preview. It is recorded from this
guide: each scene is one of the walkthroughs below, and the captions are drawn from the guide.

```scenario
id: demo-page
title: The demo video is on the site
steps:
  - goto: /app/demo
  - expect: { selector: "video", visible: true }
```

## About this guide

Each feature in these chapters carries a **“How this is verified”** box listing the
steps that demonstrate it. Those steps run as Playwright tests on every push, and the ones marked
*in the demo video* are also the script the demo recording follows.

```scenario
id: about-disclaimer
title: The site says plainly that it is not official
steps:
  - goto: /app/about
  - expect:
      selector: main
      contains: not an official publication of the United States government
```