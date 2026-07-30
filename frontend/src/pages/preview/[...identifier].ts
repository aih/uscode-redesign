/**
 * `/app/preview/us/usc/t11/s523?release=…` — a cited provision as an HTML
 * fragment, for the hover card to drop straight into the page (ADR-0024).
 *
 * **This route is why the preview needs no client-side USLM renderer.** The
 * statutory text is USLM XML, and the one module allowed to know USLM element
 * names outside the parsers is `lib/uslm.ts` (architecture rule 5) — which runs
 * on the server, on `@xmldom/xmldom`, and could not be bundled into a browser
 * script without moving presentation into the client. So the server renders what
 * it already knows how to render, and the browser receives HTML it can insert.
 *
 * That also means no new API endpoint: this is the section page's own pipeline,
 * truncated.
 *
 * **An endpoint, not a page.** A `.astro` page is a document — Astro prepends
 * `<!DOCTYPE html>` to it, which is exactly wrong inside a `<div>`. An endpoint
 * returns the bytes asked for and nothing else.
 *
 * A miss returns **200 with an explanatory fragment**, not a 404. The island has
 * nothing useful to do with an error status except swallow it, and "not
 * published at this release point" is worth showing to someone who just asked.
 */

import type { APIRoute } from "astro";

import { ApiError, fetchIdentifier, fetchLabels, releaseParams } from "../../lib/api";
import { REVALIDATE, cacheControl } from "../../lib/cache";
import { truncateFragment } from "../../lib/preview";
import { citedIdentifiers } from "../../lib/refs";
import type { Section } from "../../lib/types";
import { isToc } from "../../lib/types";
import { appHref, trimNum } from "../../lib/url";
import { escapeHtml, hrefs, parseFragment, render } from "../../lib/uslm";

export const prerender = false;

function attr(value: string): string {
  return escapeHtml(value).replace(/"/gu, "&quot;");
}

function foot(identifier: string, release: string | null): string {
  return (
    `<p class="cite-preview__foot"><a href="${attr(appHref(identifier, release))}">` +
    `Open full section${release ? ` at ${escapeHtml(release)}` : ""} →</a></p>`
  );
}

function note(text: string): string {
  return `<p class="cite-preview__note">${escapeHtml(text)}</p>`;
}

export const GET: APIRoute = async ({ params, url }) => {
  // The route lives at `pages/preview/[...identifier]`, so the catch-all already
  // holds `us/usc/t16/s45f` — only the leading slash is missing. (The section
  // page sits at `pages/us/usc/[...]` and has to prepend the whole prefix; the
  // difference cost one round of double-`/us/usc` 404s.)
  const identifier = `/${params.identifier ?? ""}`.replace(/\/+$/u, "");
  const search = releaseParams(url);

  let body: string;
  let cache = REVALIDATE;
  let servedFrom: string | null = null;

  try {
    const found = await fetchIdentifier(identifier, search);
    servedFrom = found.served_from.label;

    if (isToc(found)) {
      // A structural node has no text of its own; say how big it is and let the
      // link do the rest. `structure_nodes` is unversioned (ADR-0006), so this
      // revalidates even when the URL pinned a release.
      const count = found.children.length + found.sections.length;
      const heading = `${trimNum(found.node.num)} ${found.node.heading ?? ""}`.trim();
      body =
        `<p class="cite-preview__head">${escapeHtml(heading)}</p>` +
        note(`${count} subdivision${count === 1 ? "" : "s"}`);
    } else {
      const section = found as Section;
      const heading = `${trimNum(section.num)} ${section.heading ?? ""}`.trim();

      // The preview's own citations get labelled too, so hover text inside a
      // hover card is not blank. One batched call, exactly as the section page
      // does it — worth the request, because a cross reference is often
      // precisely what a reader is chasing when they open one of these.
      const fragment = parseFragment(section.xml);
      const labels = await fetchLabels(
        citedIdentifiers(hrefs(fragment)),
        section.served_from.label,
      );
      const cut = truncateFragment(
        render(fragment, { target: null, release: section.served_from.label, labels }),
      );

      body =
        `<p class="cite-preview__head">` +
        `<span class="cite-preview__heading">${escapeHtml(heading)}</span>` +
        (section.status
          ? `<span class="cite-preview__status">${escapeHtml(section.status)}</span>`
          : "") +
        `</p>` +
        `<div class="cite-preview__body">${cut.html}</div>` +
        (cut.truncated ? note("… continues") : "");

      // Same rule as everywhere else (ADR-0018): pinned and exact, or revalidate.
      cache = cacheControl(search.release, section.is_exact);
    }
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    body = note(error.detail);
  }

  return new Response(body + foot(identifier, search.release ?? servedFrom), {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": cache,
    },
  });
};
