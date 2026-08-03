/**
 * The demo video, recorded from the user guide (ADR-0038).
 *
 * Every scenario in `src/pages/guide/*.md` flagged `demo: true` is a scene, in
 * `demoOrder`. The captions are the ones printed in the guide beside the prose
 * they illustrate, so the video cannot say something the guide does not — and
 * a feature whose walkthrough changes changes the video with it, because there
 * is only one walkthrough.
 *
 *   make demo-video                       # against http://localhost:8000 (make dev-all)
 *   SITE=http://localhost:4321 node scripts/demovideo.mjs
 *
 * Output, in two places with two jobs:
 *
 *   static/demo/   the servable assets — `uscode-demo.mp4`, `uscode-demo.vtt`,
 *                  `poster.png`. All generated, all gitignored: a video binary
 *                  does not belong in a history meant to be read. FastAPI
 *                  mounts `static/` at `/static`, so a local run is watchable
 *                  at /static/demo/uscode-demo.mp4 immediately. In production
 *                  the same three files arrive from S3 onto a mounted volume
 *                  (`deploy/publish-demo.sh`).
 *   docs/demo/     `scenes.json`, committed — every scene, its timing and its
 *                  captions. What the video *says* stays reviewable in a diff
 *                  even though the video itself is regenerated.
 *
 * Playwright records one webm per browser context and gives no control over
 * where a frame lands in it, so a scene is a context: that is what makes the
 * per-scene durations knowable, and the caption timings with them.
 *
 * It is deliberately not a Playwright *test*. The same steps already run as
 * tests in `tests/e2e/guide.spec.ts`, on every push, where a failure means
 * something. Here a failing scene should cost you that scene and not the
 * video, so failures are caught, logged, and skipped.
 */

import { spawnSync } from "node:child_process";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { demoScenes, describeStep } from "./scenarios.mjs";

const SITE = process.env.SITE ?? "http://localhost:8000";
/** The servable assets, under the directory FastAPI mounts at `/static`. */
const OUT = fileURLToPath(new URL("../../static/demo/", import.meta.url));
/** The committed record of what the video says. */
const DOCS = fileURLToPath(new URL("../../docs/demo/", import.meta.url));
const WORK = fileURLToPath(new URL("../../static/demo/scenes/", import.meta.url));

/** 720p. Big enough to read statutory text in, small enough to attach. */
const SIZE = { width: 1280, height: 720 };

/** How long a caption stays up: a floor, plus reading time. 60ms/character is
 * about 200 words per minute, which is a comfortable read rather than a fast
 * one — the audience for this is reading legal text on screen. */
const MIN_CAPTION_MS = 2500;
const PER_CHAR_MS = 60;
const captionMs = (text) => Math.max(MIN_CAPTION_MS, text.length * PER_CHAR_MS);

/** How long the title card holds before the first scene. */
const TITLE_MS = 3500;

/**
 * The title card, rendered in the browser rather than drawn by ffmpeg.
 *
 * `drawtext` would need a font path, would not have the site's reading face,
 * and would put the one frame a viewer judges the whole video by outside the
 * design system everything after it belongs to. This is the site's own
 * typography and its own navy, screenshotted — and because it is a page, it
 * can be looked at in a browser while being worked on.
 */
const TITLE_CARD = `
<!doctype html>
<meta charset="utf-8">
<style>
  html, body { margin: 0; height: 100%; }
  body {
    background: #ffffff;
    color: #1b1b1b;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    text-align: center;
  }
  .rule { width: 4rem; height: 4px; background: #005ea2; margin: 0 0 2rem; }
  h1 {
    font-family: Georgia, 'Iowan Old Style', 'Times New Roman', serif;
    font-size: 54px; line-height: 1.15; font-weight: 700;
    margin: 0 0 1rem; max-width: 22ch;
  }
  p { font-size: 24px; color: #565c65; margin: 0; max-width: 40ch; line-height: 1.4; }
  .foot {
    position: absolute; bottom: 48px;
    font-size: 17px; color: #71767a;
    max-width: none; /* the prose measure above would break this onto two lines */
  }
  code { font-size: 0.95em; }
</style>
<div class="rule"></div>
<h1>The United States Code, at any release point</h1>
<p>Every provision has an address — at every point in time it has existed.</p>
<p class="foot">uscode.linkedlegislation.org · a conceptual redesign, not an official publication</p>
`;

/** The caption bar, installed via `addInitScript` so it survives navigation —
 * every scene navigates at least once, and a bar injected per page would blink
 * out on each one. */
const OVERLAY = `
(() => {
  if (window.__uscCaption) return;
  const install = () => {
    if (document.getElementById("usc-caption")) return;
    const bar = document.createElement("div");
    bar.id = "usc-caption";
    bar.setAttribute("aria-hidden", "true");
    bar.style.cssText = [
      "position:fixed", "left:0", "right:0", "bottom:0", "z-index:2147483647",
      "background:rgba(16,16,20,0.92)", "color:#fff",
      "font:500 22px/1.4 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif",
      "padding:18px 32px", "text-align:center", "pointer-events:none",
      "opacity:0", "transition:opacity 220ms ease",
      "text-shadow:0 1px 2px rgba(0,0,0,0.6)",
    ].join(";");
    document.documentElement.appendChild(bar);
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", install);
  } else {
    install();
  }
  window.__uscCaption = (text) => {
    install();
    const bar = document.getElementById("usc-caption");
    if (!bar) return;
    bar.textContent = text ?? "";
    bar.style.opacity = text ? "1" : "0";
  };
})();
`;

async function caption(page, text) {
  try {
    await page.evaluate((value) => window.__uscCaption?.(value), text);
  } catch {
    // A caption is narration. Losing one to a navigation racing the evaluate
    // is not a reason to lose the scene.
  }
}

/** Run one step, with its caption up while it happens. */
async function runStep(page, step) {
  if (step.caption) await caption(page, step.caption);

  switch (step.verb) {
    case "goto":
      await page.goto(`${SITE}${step.value}`, { waitUntil: "load" });
      // The caption is installed by `addInitScript`, so it is there after the
      // navigation too — but the text went with the old document.
      if (step.caption) await caption(page, step.caption);
      break;
    case "click":
      await page.locator(step.value).first().click();
      break;
    case "fill":
      // Typed rather than filled: the video is the one place where watching
      // the text appear is worth more than setting it in one go.
      await page.locator(step.value.selector).first().click();
      await page.locator(step.value.selector).first().type(step.value.value, { delay: 55 });
      break;
    case "press":
      await page.locator("body").press(step.value);
      break;
    case "hover":
      await page.locator(step.value).first().hover();
      break;
    case "focus":
      await page.locator(step.value).first().focus();
      break;
    case "scroll":
      await page.locator(step.value).first().scrollIntoViewIfNeeded();
      break;
    case "pause":
      await page.waitForTimeout(step.value);
      break;
    case "expect":
      // In the video an assertion is a beat, not a check — the tests already
      // hold it to account. Waiting for the thing to appear is what keeps the
      // recording in step with the page.
      if (step.value.selector) {
        try {
          await page.locator(step.value.selector).first().waitFor({ timeout: 5000 });
        } catch {
          // Fall through: the caption still gets its time on screen.
        }
      }
      break;
    default:
      break;
  }

  await page.waitForTimeout(step.caption ? captionMs(step.caption) : 400);
}

function ffmpeg(args) {
  const result = spawnSync("ffmpeg", args, { stdio: ["ignore", "ignore", "pipe"] });
  if (result.status !== 0) {
    throw new Error(`ffmpeg failed: ${result.stderr?.toString().split("\n").slice(-6).join("\n")}`);
  }
}

function vttTimestamp(ms) {
  const total = Math.max(0, ms) / 1000;
  const hours = String(Math.floor(total / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const seconds = String((total % 60).toFixed(3)).padStart(6, "0");
  return `${hours}:${minutes}:${seconds}`;
}

// ---------------------------------------------------------------- preflight

if (spawnSync("ffmpeg", ["-version"], { stdio: "ignore" }).status !== 0) {
  console.error("ffmpeg is not on PATH. `brew install ffmpeg`, then try again.");
  process.exit(1);
}

const health = await fetch(`${SITE}/health`).catch(() => null);
if (!health?.ok) {
  console.error(`${SITE} is not answering. Run \`make dev-all\` first.`);
  process.exit(1);
}

const scenes = demoScenes();
if (scenes.length === 0) {
  console.error("No scenario is flagged `demo: true`, so there is nothing to record.");
  process.exit(1);
}

const wantsCorpus = scenes.some((scene) => scene.data === "corpus");
if (wantsCorpus && process.env.GUIDE_CORPUS !== "1") {
  console.log(
    "Note: some scenes need the full corpus and GUIDE_CORPUS is not 1 — recording them anyway,\n" +
      "      which is fine against a fully loaded site and will look wrong against fixture data.",
  );
}

// ------------------------------------------------------------------ record

await rm(WORK, { recursive: true, force: true });
await mkdir(WORK, { recursive: true });
await mkdir(OUT, { recursive: true });

const browser = await chromium.launch();
const recorded = [];

// The title card first, as a still. It is a screenshot held for a few seconds
// rather than a recorded scene, because there is nothing in it that moves and
// a recording of a static page is a much larger file saying the same thing.
const titlePng = `${WORK}00-title.png`;
{
  const context = await browser.newContext({ viewport: SIZE, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.setContent(TITLE_CARD, { waitUntil: "load" });
  await page.screenshot({ path: titlePng });
  // The same still is the poster the player shows before you press play.
  await page.screenshot({ path: `${OUT}poster.png` });
  await context.close();
  console.log("▶ 00-title: The United States Code, at any release point");
}

try {
  for (const [index, scene] of scenes.entries()) {
    const label = `${String(index + 1).padStart(2, "0")}-${scene.id}`;
    console.log(`▶ ${label}: ${scene.title}`);

    const context = await browser.newContext({
      viewport: SIZE,
      deviceScaleFactor: 1,
      recordVideo: { dir: WORK, size: SIZE },
      ...(scene.needs.clipboard ? { permissions: ["clipboard-read", "clipboard-write"] } : {}),
      ...(scene.needs.colorScheme ? { colorScheme: scene.needs.colorScheme } : {}),
    });
    await context.addInitScript(OVERLAY);

    const page = await context.newPage();
    const captions = [];
    let elapsed = 0;
    let failed = null;

    try {
      for (const step of scene.steps) {
        const started = elapsed;
        await runStep(page, step);
        const duration = step.caption ? captionMs(step.caption) : 400;
        elapsed = started + duration;
        if (step.caption) {
          captions.push({ text: step.caption, start: started, end: elapsed });
        }
        console.log(`   · ${describeStep(step)}`);
      }
    } catch (error) {
      // A scene that breaks costs its own footage and nothing else.
      failed = error.message.split("\n")[0];
      console.log(`   ! skipped: ${failed}`);
    }

    const video = page.video();
    await context.close(); // flushes the webm
    const path = video ? await video.path() : null;

    if (path && !failed) {
      recorded.push({ id: scene.id, title: scene.title, path, captions, duration: elapsed });
    } else if (path) {
      await rm(path, { force: true });
    }
  }
} finally {
  await browser.close();
}

if (recorded.length === 0) {
  console.error("Every scene failed; nothing to stitch.");
  process.exit(1);
}

// ------------------------------------------------------------------ stitch

console.log(`\nNormalising a title card and ${recorded.length} scene(s)…`);

const parts = [];

// The still, encoded to the same format as everything else so the concat
// demuxer will take it.
const titleMp4 = `${WORK}00-title.mp4`;
ffmpeg([
  "-y", "-loop", "1", "-i", titlePng,
  "-t", String(TITLE_MS / 1000),
  "-r", "30",
  "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
  "-pix_fmt", "yuv420p",
  "-vf", `scale=${SIZE.width}:${SIZE.height}`,
  "-an", titleMp4,
]);
parts.push({
  id: "title-card",
  title: "The United States Code, at any release point",
  mp4: titleMp4,
  captions: [],
  duration: TITLE_MS,
});

for (const [index, scene] of recorded.entries()) {
  const mp4 = `${WORK}${String(index + 1).padStart(2, "0")}-${scene.id}.mp4`;
  // Re-encoded to a common format rather than concatenated as-is: the webm
  // Playwright writes is VP8 at a variable frame rate, and the concat demuxer
  // needs every part to agree on codec, rate and timebase.
  ffmpeg([
    "-y", "-i", scene.path,
    "-r", "30",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
    "-pix_fmt", "yuv420p",
    "-vf", `scale=${SIZE.width}:${SIZE.height}:force_original_aspect_ratio=decrease,pad=${SIZE.width}:${SIZE.height}:(ow-iw)/2:(oh-ih)/2`,
    "-an", mp4,
  ]);
  parts.push({ ...scene, mp4 });
}

const listPath = `${WORK}concat.txt`;
await writeFile(listPath, parts.map((part) => `file '${part.mp4}'`).join("\n"), "utf8");

const finalPath = `${OUT}uscode-demo.mp4`;
ffmpeg(["-y", "-f", "concat", "-safe", "0", "-i", listPath, "-c", "copy", finalPath]);

// ----------------------------------------------------- captions and manifest
//
// The timings are the ones the recording was paced by, accumulated across
// scenes. They are the script's own arithmetic rather than a measurement of
// the file, which is why the manifest records both and the .vtt is honest
// about being derived.

let offset = 0;
const cues = [];
const manifest = [];

for (const part of parts) {
  const probe = spawnSync(
    "ffprobe",
    ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", part.mp4],
    { encoding: "utf8" },
  );
  const measured = Number(probe.stdout?.trim());
  const duration = Number.isFinite(measured) && measured > 0 ? measured * 1000 : part.duration;

  manifest.push({
    id: part.id,
    title: part.title,
    startMs: Math.round(offset),
    durationMs: Math.round(duration),
    captions: part.captions.map((caption) => caption.text),
  });

  for (const caption of part.captions) {
    // Scaled onto the measured length: ffmpeg's re-encode is close to, but not
    // exactly, the wall clock the steps were paced by.
    const scale = duration / (part.duration || duration);
    cues.push({
      start: offset + caption.start * scale,
      end: offset + Math.min(caption.end * scale, duration),
      text: caption.text,
    });
  }

  offset += duration;
}

const vtt = [
  "WEBVTT",
  "",
  ...cues.flatMap((cue, index) => [
    String(index + 1),
    `${vttTimestamp(cue.start)} --> ${vttTimestamp(cue.end)}`,
    cue.text,
    "",
  ]),
].join("\n");

await writeFile(`${OUT}uscode-demo.vtt`, vtt, "utf8");
await mkdir(DOCS, { recursive: true });
await writeFile(
  `${DOCS}scenes.json`,
  `${JSON.stringify(
    {
      note:
        "Generated by `make demo-video` from the scenario blocks in " +
        "frontend/src/pages/guide/*.md (ADR-0038). The mp4 is gitignored; this file " +
        "and the .vtt are committed so the video's content is reviewable in a diff.",
      site: SITE,
      scenes: manifest,
      totalMs: Math.round(offset),
    },
    null,
    2,
  )}\n`,
  "utf8",
);

// Everything in here was an intermediate: Playwright's webm originals, the
// per-scene mp4s and the concat list. The stitched file is the artifact.
await rm(WORK, { recursive: true, force: true });

console.log(
  `\n${finalPath}\n${Math.round(offset / 1000)}s, ${parts.length} scene(s), ${cues.length} captions` +
    `\n${OUT}uscode-demo.vtt\n${OUT}poster.png\n${DOCS}scenes.json`,
);
