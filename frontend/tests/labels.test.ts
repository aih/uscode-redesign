/**
 * `fetchLabels` — the batching, which is the whole of what it does beyond one
 * `fetch`.
 *
 * This exists because of a live 500. `/api/v1/labels` bounds its list at 100
 * identifiers (ADR-0029: the list fans into one `IN (...)`), the reader asked
 * for all of a page's citations in one request, and 3 U.S.C. § 301 makes 242
 * distinct ones — so the API answered 422 and the section page, which already
 * had the statute's text in memory, rendered nothing at all. Measured over the
 * corpus, 4,221 of 489,738 stored versions are over that bound.
 *
 * `fetch` is stubbed rather than run: what is being tested is how the request
 * is *shaped*, and a network round trip would answer a different question.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LABELS_MAX, LABELS_PER_REQUEST, fetchLabels } from "../src/lib/api";

/** Every `identifier=` on a call, in the order it was sent. */
function identifiersOf(url: string): string[] {
  return [...new URL(url, "http://x").searchParams.getAll("identifier")];
}

function calls(): string[] {
  return vi.mocked(globalThis.fetch).mock.calls.map(([url]) => String(url));
}

/** n identifiers shaped like the real ones. */
function many(n: number): string[] {
  return Array.from({ length: n }, (_, i) => `/us/usc/t3/s${i + 1}`);
}

beforeEach(() => {
  globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
    // Answer each identifier asked for, so the merge across batches is visible.
    const asked = identifiersOf(String(url));
    const body = Object.fromEntries(
      asked.map((id) => [id, { identifier: id, num: `§ ${id.split("/s")[1]}.`, heading: "H" }]),
    );
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as unknown as typeof fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("fetchLabels", () => {
  it("asks for nothing when there is nothing to ask about", async () => {
    expect(await fetchLabels([])).toEqual({});
    expect(calls()).toHaveLength(0);
  });

  it("sends one request when the list fits", async () => {
    await fetchLabels(many(LABELS_PER_REQUEST));
    expect(calls()).toHaveLength(1);
    expect(identifiersOf(calls()[0])).toHaveLength(LABELS_PER_REQUEST);
  });

  it("never puts more than the bound in one request", async () => {
    // 242 is 3 U.S.C. § 301, the section that found this.
    await fetchLabels(many(242));
    const sent = calls();
    expect(sent).toHaveLength(3);
    for (const url of sent) {
      expect(identifiersOf(url).length).toBeLessThanOrEqual(LABELS_PER_REQUEST);
    }
  });

  it("asks about every identifier exactly once, and answers for all of them", async () => {
    const wanted = many(242);
    const labels = await fetchLabels(wanted);

    const asked = calls().flatMap(identifiersOf);
    expect(asked).toEqual(wanted);
    expect(new Set(asked).size).toBe(wanted.length);
    // The merge across batches is the point: a caller sees one answer.
    expect(Object.keys(labels)).toHaveLength(wanted.length);
    expect(labels["/us/usc/t3/s242"]).toMatchObject({ identifier: "/us/usc/t3/s242" });
  });

  it("carries the release point on every batch, not just the first", async () => {
    await fetchLabels(many(242), "114-139");
    for (const url of calls()) {
      expect(new URL(url, "http://x").searchParams.get("release")).toBe("114-139");
    }
  });

  it("stops at a bound, because the input is a document", async () => {
    // The densest version in the corpus carries 1,011 refs; this clears that
    // and still refuses to let a page's contents decide how many requests the
    // reader makes.
    await fetchLabels(many(LABELS_MAX + 500));
    expect(calls()).toHaveLength(LABELS_MAX / LABELS_PER_REQUEST);
    expect(calls().flatMap(identifiersOf)).toHaveLength(LABELS_MAX);
  });

  it("matches the bound the API actually enforces", async () => {
    // `api/routes.py` declares `max_length=100` on the same parameter. If that
    // ever moves, this batching is wrong in a way only a 422 would reveal.
    expect(LABELS_PER_REQUEST).toBe(100);
  });
});
