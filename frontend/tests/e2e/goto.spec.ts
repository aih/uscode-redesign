/**
 * The site's one search box, end to end.
 *
 * The parser's accepted forms are unit-tested without a database
 * (`tests/test_citeparse.py`, 79 cases) — this is the wiring: that a form typed
 * into the header survives the query string, the API round trip, the existence
 * lookup and the redirect, and lands on the provision.
 *
 * Since the header's two boxes merged into one, it also covers the routing that
 * merge required: a citation goes to the provision, `cites …` goes to a marked
 * search, and anything else goes to a plain one.
 */
import { expect, test } from "@playwright/test";

const BOX = ".sitesearch--header .sitesearch__input";

/** One representative of each parser shape, all naming the same provision, so a
 * failure says which *form* broke rather than which section is missing. */
const FORMS: Array<[string, string]> = [
  ["16 usc 45f", "/app/us/usc/t16/s45f"],
  ["16 U.S.C. § 45f", "/app/us/usc/t16/s45f"],
  ["16 usc 45f(c)(5)", "/app/us/usc/t16/s45f/c/5"],
  ["section 45f of title 16", "/app/us/usc/t16/s45f"],
  ["16/45f", "/app/us/usc/t16/s45f"],
  ["/us/usc/t16/s45f", "/app/us/usc/t16/s45f"],
  ["16 usc ch. 1", "/app/us/usc/t16/ch1"],
  ["title 16", "/app/us/usc/t16"],
];

for (const [typed, destination] of FORMS) {
  test(`"${typed}" lands on ${destination}`, async ({ page }) => {
    await page.goto("/app/");
    await page.fill(BOX, typed);
    await page.press(BOX, "Enter");

    await expect(page).toHaveURL(new RegExp(`${destination.replace(/\//gu, "\\/")}(\\?|$)`));
  });
}

test("the box needs no JavaScript", async ({ browser }) => {
  // It is a plain GET form, like the release picker. The whole feature has to
  // work with scripting off, which is the reason it is not an autocomplete.
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();

  await page.goto("/app/");
  await page.fill(BOX, "16 usc 45f");
  await page.press(BOX, "Enter");

  await expect(page).toHaveURL(/\/app\/us\/usc\/t16\/s45f/u);
  await context.close();
});

test("text that is not a citation is searched instead of refused", async ({ page }) => {
  // The header carries one box now, so `/app/goto` is a router: what it cannot
  // read as a citation was words, and words get searched. This used to be an
  // error page listing the citation forms, which was the right answer for a box
  // labelled "go to a citation" and the wrong one for a box that also searches.
  await page.goto("/app/goto?q=navigable%20waters");

  await expect(page).toHaveURL(/\/app\/search\?q=navigable\+waters/u);
});

test("a bare section number is searched rather than guessed at", async ({ page }) => {
  // `523` names a section of *some* title, and picking one would be a guess
  // presented as an answer. It is still refused as a citation — it now falls
  // through to a search rather than to an error.
  await page.goto("/app/goto?q=523");

  await expect(page).toHaveURL(/\/app\/search\?q=523/u);
});

test("a cites query searches the subject and says that is what it did", async ({ page }) => {
  // The reverse lookup does not exist yet (docs/citation-index-plan.md). The
  // interim answer must not be mistaken for the real one.
  await page.goto("/app/");
  await page.fill(BOX, "cites 16 usc 45f");
  await page.press(BOX, "Enter");

  await expect(page).toHaveURL(/\/app\/search\?q=16\+usc\+45f&cites=1/u);
  await expect(page.locator(".usa-alert--info").first()).toContainText(/keyword search/iu);
});

test("a citation naming nothing loaded says which part is missing", async ({ page }) => {
  await page.goto("/app/goto?q=99%20usc%201");

  const alert = page.locator(".usa-alert--warning");
  await expect(alert).toContainText("/us/usc/t99/s1");
  // And offers the title as somewhere to go from.
  await expect(alert.locator("a")).toHaveAttribute("href", /\/app\/us\/usc\/t99/u);
});

test("an appendix citation explains why it cannot resolve", async ({ page }) => {
  // OLRC publishes appendix titles under the enacting instrument, so
  // `/us/usc/t5a/s3` is well-formed and empty. A bare "not found" would read as
  // a bug in the parser.
  await page.goto("/app/goto?q=5%20U.S.C.%20App.%203");

  await expect(page.locator(".usa-alert--warning")).toContainText(/enacted/iu);
});

test("the box is reachable from a section page, not just the front page", async ({
  page,
}) => {
  await page.goto("/app/us/usc/t16/s45f");
  await page.fill(BOX, "16 usc 45f");
  await page.press(BOX, "Enter");

  await expect(page).toHaveURL(/\/app\/us\/usc\/t16\/s45f/u);
});

test("a hyphen typed on a keyboard finds OLRC's en dash", async ({ page }) => {
  // `/us/usc/t16/s45a–1` is spelled with U+2013, as are 5,697 of the corpus's
  // 65,938 sections — and none with a plain hyphen. The redirect has to land on
  // the identifier that exists, not the one that was typed.
  await page.goto("/app/");
  await page.fill(BOX, "16 usc 45a-1");
  await page.press(BOX, "Enter");

  await expect(page).toHaveURL(/s45a%E2%80%931|s45a–1/u);
  await expect(page.locator("h1.doc-title")).toContainText("45a");
});
