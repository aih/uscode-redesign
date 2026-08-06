import { chromium } from "playwright";
const b = await chromium.launch();
for (const w of [375, 768, 1024, 1280]) {
  const c = await b.newContext({ viewport: { width: w, height: 900 } });
  const p = await c.newPage();
  for (const [name, url] of [["section", "/app/us/usc/t16/s45f"], ["design", "/app/design"], ["search", "/app/search?q=park"]]) {
    await p.goto(`http://localhost:8000${url}`, { waitUntil: "networkidle" });
    const r = await p.evaluate(() => {
      const rw = document.querySelector(".reader-wrap");
      const sb = document.querySelector(".section-body") ?? document.querySelector("main");
      const cs = getComputedStyle(document.documentElement);
      return {
        wrap: Math.round(rw?.getBoundingClientRect().width ?? -1),
        wrapMax: getComputedStyle(rw).maxWidth,
        prose: Math.round(sb?.getBoundingClientRect().width ?? -1),
      };
    });
    console.log(w, name.padEnd(8), JSON.stringify(r));
  }
  await c.close();
}
await b.close();
