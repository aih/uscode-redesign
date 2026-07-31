import { describe, expect, it } from "vitest";

import {
  derefSchema,
  endpointSlug,
  groupByTag,
  refName,
  renderMarkdown,
  requestBodyType,
  slugify,
  sortedParameters,
  successSchema,
  tagLabel,
  typeName,
} from "../src/lib/openapi";
import type { OpenApiSchema } from "../src/lib/types";

/** A miniature of what FastAPI actually emits for this project's routes. */
const schema: OpenApiSchema = {
  openapi: "3.1.0",
  info: { title: "US Code", version: "0.1.0" },
  paths: {
    "/api/v1/us/usc/{identifier}": {
      get: {
        tags: ["lookup"],
        summary: "Resolve an identifier",
        parameters: [
          { name: "release", in: "query", schema: { type: "string" } },
          { name: "identifier", in: "path", required: true, schema: { type: "string" } },
        ],
        responses: {
          "200": {
            content: { "application/json": { schema: { $ref: "#/components/schemas/Section" } } },
          },
        },
      },
      // A path item can carry keys that are not operations; they must not be
      // rendered as endpoints.
      parameters: [],
    } as never,
    "/api/v1/watchlist/items": {
      post: {
        tags: ["watchlist"],
        summary: "Add an item",
        requestBody: {
          content: { "application/json": { schema: { $ref: "#/components/schemas/ItemIn" } } },
        },
        responses: { "201": { content: { "application/json": { schema: { type: "object" } } } } },
      },
      delete: {
        tags: ["watchlist"],
        summary: "Remove an item",
        responses: { "204": { description: "gone" } },
      },
    },
  },
  components: { schemas: { Section: { type: "object", title: "Section" } } },
};

describe("groupByTag", () => {
  const groups = groupByTag(schema);

  it("keeps the schema's own tag order rather than sorting", () => {
    // `main.py` mounts routers in the order a reader meets them, which is a
    // better contents list than alphabetical — `auth` should not lead.
    expect(groups.map((group) => group.tag)).toEqual(["lookup", "watchlist"]);
  });

  it("collects every operation under a path", () => {
    expect(groups[1].endpoints.map((e) => e.method)).toEqual(["post", "delete"]);
  });

  it("ignores path-item keys that are not HTTP methods", () => {
    expect(groups[0].endpoints).toHaveLength(1);
  });
});

describe("typeName", () => {
  it("names a $ref by its model", () => {
    expect(typeName({ $ref: "#/components/schemas/Section" })).toBe("Section");
  });

  it("folds an OpenAPI 3.1 nullable back into `| null`", () => {
    // Every optional FastAPI field is `anyOf: [T, null]`; printed literally the
    // whole reference page reads "anyOf".
    expect(typeName({ anyOf: [{ type: "string" }, { type: "null" }] })).toBe("string | null");
  });

  it("renders arrays and enums readably", () => {
    expect(typeName({ type: "array", items: { type: "string" } })).toBe("string[]");
    expect(typeName({ enum: ["json", "xml"] })).toBe('"json" | "xml"');
  });

  it("falls back to `any` rather than throwing on an unknown node", () => {
    expect(typeName(undefined)).toBe("any");
    expect(typeName({})).toBe("any");
  });
});

describe("derefSchema", () => {
  it("resolves a local component ref", () => {
    expect(derefSchema({ $ref: "#/components/schemas/Section" }, schema)?.title).toBe("Section");
  });

  it("returns the node unchanged when the ref does not resolve", () => {
    // A docs page must render something for a route it does not fully
    // understand, not 500.
    const missing = { $ref: "#/components/schemas/Nope" };
    expect(derefSchema(missing, schema)).toBe(missing);
  });

  it("passes an inline schema straight through", () => {
    expect(derefSchema({ type: "string" }, schema)).toEqual({ type: "string" });
  });
});

describe("responses and bodies", () => {
  it("reports the first 2xx and its model", () => {
    const get = schema.paths["/api/v1/us/usc/{identifier}"].get;
    expect(successSchema(get)).toEqual({ status: "200", type: "Section" });
  });

  it("reports a bodiless success as such", () => {
    const del = schema.paths["/api/v1/watchlist/items"].delete;
    expect(successSchema(del)).toEqual({ status: "204", type: "no content" });
  });

  it("names the request body model", () => {
    const post = schema.paths["/api/v1/watchlist/items"].post;
    expect(requestBodyType(post)).toBe("ItemIn");
    expect(requestBodyType(schema.paths["/api/v1/watchlist/items"].delete)).toBeNull();
  });
});

describe("parameters", () => {
  it("puts path parameters before query ones", () => {
    // They are part of the URL, so they come before the optional refinements.
    const get = schema.paths["/api/v1/us/usc/{identifier}"].get;
    expect(sortedParameters(get).map((p) => p.name)).toEqual(["identifier", "release"]);
  });
});

describe("anchors", () => {
  it("slugifies a tag", () => {
    expect(slugify("Release points")).toBe("release-points");
  });

  it("never returns an empty anchor", () => {
    expect(slugify("///")).toBe("untagged");
  });

  it("makes an endpoint anchor from its method and path", () => {
    expect(endpointSlug("get", "/api/v1/sections/{id}/diff")).toBe(
      "get-api-v1-sections-id-diff",
    );
  });

  it("gives two methods on one path different anchors", () => {
    expect(endpointSlug("post", "/x")).not.toBe(endpointSlug("delete", "/x"));
  });
});

describe("refName", () => {
  it("returns null for an inline schema", () => {
    expect(refName({ type: "string" })).toBeNull();
  });
});

describe("renderMarkdown", () => {
  it("renders a bulleted list as a list", () => {
    // `main.py`'s DESCRIPTION is mostly bullets. Split on blank lines alone
    // they collapsed into one run-on paragraph.
    const html = renderMarkdown("* one\n* two");
    expect(html).toContain("<ul");
    expect(html.match(/<li>/gu)).toHaveLength(2);
  });

  it("keeps a wrapped bullet as one item", () => {
    // Docstrings hard-wrap; a continuation line is not a new bullet.
    const html = renderMarkdown("* a bullet that\n  wraps onto a second line\n* second");
    expect(html.match(/<li>/gu)).toHaveLength(2);
    expect(html).toContain("a bullet that wraps onto a second line");
  });

  it("renders code spans, bold and italic", () => {
    expect(renderMarkdown("the `@identifier` field")).toContain("<code>@identifier</code>");
    expect(renderMarkdown("a **307 redirect**")).toContain("<strong>307 redirect</strong>");
    expect(renderMarkdown("a law that was *skipped*")).toContain("<em>skipped</em>");
  });

  it("leaves asterisks inside a code span alone", () => {
    const html = renderMarkdown("write `a * b * c` here");
    expect(html).toContain("<code>a * b * c</code>");
    expect(html).not.toContain("<em>");
  });

  it("escapes HTML before adding any of its own", () => {
    // The output goes through `set:html`, so nothing in a docstring may
    // introduce markup.
    const html = renderMarkdown('<img src=x onerror="alert(1)">');
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });

  it("joins hard-wrapped paragraph lines rather than breaking them", () => {
    expect(renderMarkdown("one line\nwrapped here")).toBe("<p>one line wrapped here</p>");
  });

  it("splits paragraphs on blank lines", () => {
    expect(renderMarkdown("first\n\nsecond").match(/<p>/gu)).toHaveLength(2);
  });

  it("is empty for empty input", () => {
    expect(renderMarkdown("")).toBe("");
    expect(renderMarkdown("   \n\n  ")).toBe("");
  });
});

describe("tagLabel", () => {
  it("gives FastAPI's lowercase route tags a heading a reader would write", () => {
    expect(tagLabel("api")).toBe("Provisions");
    expect(tagLabel("auth")).toBe("Accounts");
  });

  it("capitalises anything it does not know rather than dropping it", () => {
    expect(tagLabel("releases")).toBe("Releases");
  });
});
