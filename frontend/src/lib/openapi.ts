/**
 * Turning FastAPI's OpenAPI schema into something `/app/docs` can render.
 *
 * The API reference used to be FastAPI's own `/docs` — Swagger UI, on a bare
 * page with no navbar, no footer and no way back into the site. Clicking "API
 * docs" in the header took the reader somewhere that did not look like this
 * site and did not link to it. This module is what lets the reference live
 * inside the site chrome instead.
 *
 * Rendered on the server, with no client JavaScript, for the same two reasons
 * everything else here is: the site ships no bundle (ADR-0011), and Swagger UI
 * could not be loaded anyway — the CSP names no CDN and `X-Frame-Options: DENY`
 * (ADR-0030) blocks framing `/docs` even same-origin. Deriving the page from
 * `/openapi.json` also means there is no second, hand-written description of
 * the API to fall out of date with the routes.
 *
 * Pure functions over the parsed schema, so they are testable without a server.
 */

import type {
  JsonSchema,
  OpenApiOperation,
  OpenApiParameter,
  OpenApiSchema,
} from "./types";

/** The HTTP methods a path item can carry. Anything else in a path item
 * (`parameters`, `summary`) is not an operation and must not be rendered as
 * one. */
const METHODS = ["get", "post", "put", "patch", "delete", "head", "options"] as const;

export type Method = (typeof METHODS)[number];

export interface Endpoint {
  path: string;
  method: Method;
  operation: OpenApiOperation;
  /** The tag it is grouped under — the first one FastAPI gave it. */
  tag: string;
}

export interface TagGroup {
  tag: string;
  endpoints: Endpoint[];
  /** A stable `id` for the in-page anchor and the contents list. */
  slug: string;
}

/** `Release points` → `release-points`. Anchors have to survive a tag being
 * renamed in `api/`, so this is derived rather than kept in a lookup table. */
export function slugify(value: string): string {
  return (
    value
      .toLowerCase()
      .replace(/[^a-z0-9]+/gu, "-")
      .replace(/^-+|-+$/gu, "") || "untagged"
  );
}

/** A stable anchor for one endpoint: method plus path, both flattened.
 * `get /api/v1/sections/{id}/diff` → `get-api-v1-sections-id-diff`. */
export function endpointSlug(method: string, path: string): string {
  return slugify(`${method} ${path}`);
}

/**
 * Every operation in the schema, grouped by tag, in the order the tags first
 * appear.
 *
 * Insertion order rather than alphabetical: `main.py` mounts the routers in the
 * order a reader meets them — lookup before diffs before auth — and that is a
 * better contents list than sorting `auth` to the top. Within a tag, paths keep
 * the schema's own order for the same reason.
 */
export function groupByTag(schema: OpenApiSchema): TagGroup[] {
  const groups = new Map<string, Endpoint[]>();

  for (const [path, item] of Object.entries(schema.paths ?? {})) {
    for (const method of METHODS) {
      const operation = item[method];
      if (!operation) continue;
      const tag = operation.tags?.[0] ?? "Other";
      const list = groups.get(tag) ?? [];
      list.push({ path, method, operation, tag });
      groups.set(tag, list);
    }
  }

  return [...groups.entries()].map(([tag, endpoints]) => ({
    tag,
    endpoints,
    slug: slugify(tag),
  }));
}

/** Resolve a `$ref` against `components.schemas`.
 *
 * Only local refs, because that is all FastAPI emits. A ref that does not
 * resolve returns the original node rather than throwing: a docs page must
 * render something for an endpoint it does not fully understand, not 500. */
export function derefSchema(
  node: JsonSchema | undefined,
  schema: OpenApiSchema,
): JsonSchema | undefined {
  if (!node?.$ref) return node;
  const name = node.$ref.replace(/^#\/components\/schemas\//u, "");
  return schema.components?.schemas?.[name] ?? node;
}

/** The component name a `$ref` points at, for labelling a response as the model
 * it returns (`Section`, `Toc`) rather than as "object". */
export function refName(node: JsonSchema | undefined): string | null {
  if (!node?.$ref) return null;
  return node.$ref.split("/").pop() ?? null;
}

/**
 * A short, readable type for a parameter or field: `string`, `integer`,
 * `Section`, `string[]`, `string | null`.
 *
 * The `anyOf` case is the one that matters in practice. Every optional field in
 * a FastAPI response is `anyOf: [{type: X}, {type: "null"}]` in OpenAPI 3.1, and
 * rendering that literally gives a page full of `anyOf` — so the null arm is
 * folded back into a trailing `| null`, which is how the field is actually
 * described everywhere else in this codebase.
 */
export function typeName(node: JsonSchema | undefined): string {
  if (!node) return "any";

  const ref = refName(node);
  if (ref) return ref;

  if (node.anyOf?.length) {
    const parts = node.anyOf.filter((arm) => arm.type !== "null").map(typeName);
    const nullable = node.anyOf.some((arm) => arm.type === "null");
    const joined = parts.join(" | ") || "any";
    return nullable ? `${joined} | null` : joined;
  }

  if (node.enum?.length) {
    return node.enum.map((value) => JSON.stringify(value)).join(" | ");
  }

  if (node.type === "array") return `${typeName(node.items)}[]`;
  return node.type ?? "any";
}

/** Query and path parameters, path ones first — they are part of the URL, so
 * they are what a reader needs before the optional refinements. */
export function sortedParameters(operation: OpenApiOperation): OpenApiParameter[] {
  const params = operation.parameters ?? [];
  return [...params].sort((a, b) => {
    if (a.in === b.in) return 0;
    if (a.in === "path") return -1;
    if (b.in === "path") return 1;
    return 0;
  });
}

/** The success response's schema, if the operation documents one. Looks for the
 * first 2xx with a JSON body — FastAPI writes `200` for most routes and `201`
 * for a create, and a `204` has no body at all. */
export function successSchema(
  operation: OpenApiOperation,
): { status: string; type: string } | null {
  for (const [status, response] of Object.entries(operation.responses ?? {})) {
    if (!/^2\d\d$/u.test(status)) continue;
    const json = response.content?.["application/json"]?.schema;
    if (!json) return { status, type: "no content" };
    return { status, type: typeName(json) };
  }
  return null;
}

/** The request body's model name, for the handful of POST routes. */
export function requestBodyType(operation: OpenApiOperation): string | null {
  const json = operation.requestBody?.content?.["application/json"]?.schema;
  return json ? typeName(json) : null;
}
