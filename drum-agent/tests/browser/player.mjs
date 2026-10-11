// Drives a chart page in headless Chromium: real-drum playback, play-along with a
// recording, and click-to-jump. Prints one JSON line. Used by tests/test_page_browser.py.
//   node player.mjs <playwright module path> <page.html> [recording.wav]
const [pw, file, audio] = process.argv.slice(2);
const { chromium } = await import(pw);
const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
const page = await browser.newPage({ viewport: { width: 1300, height: 900 } });
const errors = [];
page.on('pageerror', e => errors.push(e.message));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
await page.goto('file://' + file);
await page.waitForTimeout(400);
const out = { errors };
// every embedded drum sample decodes
out.decoded = await page.evaluate(async () => {
  const k = JSON.parse(document.getElementById('kit-data').textContent);
  const ctx = new OfflineAudioContext(1, 44100, 44100); let ok = 0, bad = 0;
  for (const id of Object.keys(k.s)) for (const l of Object.keys(k.s[id])) {
    const bin = atob(k.s[id][l]); const u = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
    try { await ctx.decodeAudioData(u.buffer); ok++; } catch (e) { bad++; }
  }
  return { ok, bad };
});
if (audio) await page.setInputFiles('#recFile', audio);
await page.click('#pPlay');
await page.waitForTimeout(2500);
out.playing = await page.evaluate(() => window.drumchartState());
const sel = '.layout.on .staff-svg .hl[data-b="6"]';
await page.evaluate(s => document.querySelector(s).scrollIntoView({ block: 'center' }), sel);
await page.waitForTimeout(300);
const box = await page.locator(sel).boundingBox();
await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
await page.waitForTimeout(800);
out.jumped = await page.evaluate(() => ({ ...window.drumchartState(),
  highlighted: (document.querySelector('.layout.on .hl.on') || { getAttribute: () => null }).getAttribute('data-b') }));
console.log(JSON.stringify(out));
await browser.close();
