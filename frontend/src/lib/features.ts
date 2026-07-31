/**
 * What this build of the reader offers, and what it only describes.
 *
 * Two features are finished, working, tested — and deliberately switched off:
 * accounts and bulk downloads. Switching a thing off is easy; the reason this
 * file exists is that there are three wrong ways to do it and all three were
 * available:
 *
 *   * **Delete the code.** Then re-enabling means rewriting it, and the ADRs
 *     describing it (0017, 0019) describe nothing.
 *   * **Leave the controls and let them fail.** A "Sign up" that 500s or that
 *     silently does nothing is worse than no sign-up.
 *   * **Remove the controls silently.** Then a reader who used the watchlist
 *     last month finds it simply gone, with nowhere to ask why.
 *
 * So the controls stay visible, say plainly that they are not live yet and what
 * they will do, and the flag is one constant per feature. `ACCOUNTS_ENABLED =
 * true` restores the login form, the signup form, the navbar's account menu and
 * the Watch button, all at once, and every server route behind them is
 * untouched and still tested (`tests/test_auth.py`, `tests/test_watchlists.py`).
 *
 * These are build-time constants rather than environment variables on purpose.
 * A reader page is served from a *shared* cache (ADR-0018); a value that could
 * differ per request would have to be varied on, and there is nothing here that
 * varies per reader — the site either offers accounts or it does not.
 */

/**
 * Email + password accounts: sign-up, sign-in, watchlists, per-account
 * settings. Everything behind `/api/v1/auth` and `/api/v1/watchlist`.
 *
 * Off because the account layer has two named gaps that make an account a
 * liability rather than a feature: **no email verification and no password
 * reset** (ADR-0019 decided this deliberately rather than leaving it a
 * surprise), so an account is unrecoverable the moment its password is
 * forgotten. Turning it on is a decision about email infrastructure, not about
 * this line.
 */
export const ACCOUNTS_ENABLED = false;

/**
 * Bulk download of the corpus — the release-point zips, or a derived export.
 *
 * Off because nothing serves it yet. The corpus exists (9.7 GB of OLRC zips,
 * mirrored to S3 under ADR-0013) and the ingest side already tracks provenance
 * per file, so this is a route and a budget away rather than a research
 * project. What it is *not* is free: it is the one feature that would put real
 * egress on a $35/month single box (ADR-0020).
 */
export const DOWNLOADS_ENABLED = false;

/**
 * What the account control says when someone asks why it is greyed out.
 *
 * Kept here, next to the flag, rather than in each of the four places that show
 * it — the navbar, the sign-in page, the sign-up page and My Provisions. Four
 * copies of a promise drift into four different promises.
 */
export const ACCOUNTS_NOTICE = {
  heading: "Accounts are coming, but are not switched on yet",
  lead:
    "A later version will let you sign in and keep track of things: watch " +
    "provisions and whole titles, get alerted when a release point changes " +
    "text you care about, and keep a set of favourites to come back to.",
  detail:
    "Everything else works without an account and will keep working without " +
    "one. The reading, the search, the version history, the redlines and the " +
    "API are all open.",
} as const;

/** The same, for the downloads control. */
export const DOWNLOADS_NOTICE = {
  heading: "Bulk downloads are planned",
  lead:
    "A later version will serve the corpus in bulk through the API: whole " +
    "titles, whole release points, and the differences between them, " +
    "refreshed from the Office of the Law Revision Counsel as each new " +
    "release point is published.",
  detail:
    "Until then the official downloads are the place to get the source XML, " +
    "and every page here links to the exact file its text came from.",
} as const;
