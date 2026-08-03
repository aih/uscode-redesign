/**
 * The user guide's table of contents, read from the chapters themselves
 * (ADR-0038).
 *
 * Adding a chapter is adding a file: this globs `pages/guide/*.md` and orders
 * by the `order` in each one's frontmatter. Nothing lists the chapters a second
 * time — a hand-maintained contents page is the first thing to fall out of step
 * with the guide it fronts, which is the failure this whole design exists to
 * avoid.
 *
 * This module is the *runtime* view, used by the layout and the contents page
 * and processed by Vite. The checker in `tests/guide.test.ts` reads the same
 * files from disk instead, deliberately: a ratchet that trusted the bundler to
 * hand it the file list could not notice a chapter the bundler never saw.
 */
import { APP } from "./url";

/** What a chapter declares about itself.
 *
 * `covers` is not for the reader. It is the claim `tests/guide.test.ts`
 * enforces — that every reader route and every user-facing ADR is documented
 * somewhere in the guide — so a chapter that adds no new coverage still says so
 * with empty lists rather than by omitting the key. */
export interface GuideFrontmatter {
  title: string;
  order: number;
  summary?: string;
  covers?: { routes?: string[]; adrs?: number[] };
}

export interface Chapter {
  slug: string;
  href: string;
  title: string;
  order: number;
  summary?: string;
}

const modules = import.meta.glob<{ frontmatter: GuideFrontmatter }>(
  "../pages/guide/*.md",
  { eager: true },
);

let cache: Chapter[] | null = null;

/**
 * Every chapter, in reading order.
 *
 * A function rather than a top-level constant, and that is not a style
 * preference: each chapter imports the layout, the layout imports this module,
 * and this module's glob imports every chapter — a cycle. Reading
 * `mod.frontmatter` while that cycle is still unwinding throws "Cannot access
 * 'frontmatter' before initialization" and every guide route 500s, which is
 * exactly what the first build of this did. By the time anything *renders*, all
 * of those modules are initialised, so the read is safe here and only here.
 */
export function chapters(): Chapter[] {
  if (cache) return cache;

  cache = Object.entries(modules)
    .map(([path, mod]) => {
      const slug = path.split("/").pop()!.replace(/\.md$/, "");
      return {
        slug,
        href: `${APP}/guide/${slug}`,
        title: mod.frontmatter.title,
        order: mod.frontmatter.order,
        summary: mod.frontmatter.summary,
      };
    })
    .sort((a, b) => a.order - b.order);

  return cache;
}

/** The chapters either side of `title`, for the pager at the foot of a chapter. */
export function around(title: string): {
  previous: Chapter | null;
  next: Chapter | null;
} {
  const all = chapters();
  const index = all.findIndex((c) => c.title === title);
  return {
    previous: index > 0 ? all[index - 1] : null,
    next: index >= 0 && index < all.length - 1 ? all[index + 1] : null,
  };
}
