// Capture the screenshots used by docs/participant-guide.md and
// docs/administrator-guide.md against a running, demo-seeded instance.
//
//   npm i playwright            # not a project dependency; install anywhere
//   node scripts/capture-screenshots.mjs <frontendUrl> <outDir>
//
// Start the app on ports that do not collide with anything else first — this
// machine has unrelated containers on 8000/5173, and pointing the capture at
// those silently screenshots a DIFFERENT application:
//
//   FIPM_DB_PATH=/tmp/demo.db uv run python -m fipm import-data
//   FIPM_DB_PATH=/tmp/demo.db FIPM_BASE_URL=http://localhost:5199 \
//     uv run python -m fipm serve --port 8099
//   npx vite --config vite.config.capture.ts     # serves 5199, proxies to 8099
//
// Then confirm you are on the right service before capturing:
//   curl http://localhost:8099/api/health   # must return {"status":"ok",...}
//
// Participant shots are phone-sized because that is how participants use the
// tool; administrator shots are desktop-sized. The session forces its own
// default language, so every page explicitly switches to English first.
import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'

const BASE = process.argv[2] ?? 'http://localhost:5199'
const OUT = process.argv[3] ?? 'docs/images'
const JOIN_CODE = process.env.JOIN_CODE ?? '9EN0R0'
const SESSION_ID = process.env.SESSION_ID ?? '6X0QV0BF'
const FACIL = { email: 'facilitator@confoa2026.example.org', password: 'DemoFacil!2026' }
const ADMIN = { email: 'admin@confoa2026.example.org', password: 'DemoAdmin!2026' }

const PHONE = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: 'en' }
const DESKTOP = { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, locale: 'en' }

const ok = [], failed = []

async function shot(page, name, opts = {}) {
  try {
    const { selector, fullPage = false, clip } = opts
    const path = `${OUT}/${name}.png`
    if (selector) {
      await unstick(page)
      const el = page.locator(selector).first()
      await el.waitFor({ state: 'visible', timeout: 8000 })
      await el.screenshot({ path })
    } else await page.screenshot({ path, fullPage, ...(clip ? { clip } : {}) })
    ok.push(name); console.log(`  ok   ${name}`)
  } catch (e) { failed.push(`${name}: ${String(e).split('\n')[0]}`); console.log(`  FAIL ${name}: ${String(e).split('\n')[0]}`) }
}

const english = async (p) => { try { await p.locator('.language-select').first().selectOption('en'); await p.waitForTimeout(400) } catch {} }

// Element screenshots of tall cards otherwise render the sticky page header
// through the middle of the image; pin everything static for the capture.
const unstick = async (p) => {
  try {
    await p.addStyleTag({ content: `
      *, *::before, *::after { position: static !important; }
      .app-header, header, nav, [class*="sticky"], [class*="fixed"] { position: static !important; }
      html, body { scroll-behavior: auto !important; }
    ` })
    await p.waitForTimeout(250)
  } catch {}
}
async function go(p, path) { await p.goto(`${BASE}${path}`, { waitUntil: 'networkidle', timeout: 25000 }); await p.waitForTimeout(500); await english(p) }
async function login(p, who) {
  await go(p, '/login')
  await p.locator('input[type=email], input[name=email]').first().fill(who.email)
  await p.locator('input[type=password]').first().fill(who.password)
  await p.locator('button[type=submit]').first().click()
  await p.waitForTimeout(1800)
}

const browser = await chromium.launch()
await mkdir(OUT, { recursive: true })

// ---------------- participant (phone) ----------------
{
  const ctx = await browser.newContext(PHONE); const p = await ctx.newPage()
  await go(p, '/'); await shot(p, 'home-join-code')

  await go(p, `/join/${JOIN_CODE}`)
  await shot(p, 'join-area-choice', { fullPage: true })
  await p.locator('input[type=radio]').first().check()
  await p.locator('input[type=text]').first().fill('Laboratório de Ecologia Molecular, UFRJ')
  await shot(p, 'join-community-name', { fullPage: true })
  await p.locator('button[type=submit]').first().click()
  await p.waitForTimeout(2500); await english(p)

  await shot(p, 'editor-overview')
  const card = p.locator('.question-card').first()
  await shot(p, 'question-card', { selector: '.question-card' })
  await card.locator('.question-help summary').first().click(); await p.waitForTimeout(400)
  await shot(p, 'question-help', { selector: '.question-card' })
  await card.locator('.question-help summary').first().click(); await p.waitForTimeout(300)

  // tick an option, then open the free-text/"Other (specify)" path
  const boxes = card.locator('input[type=checkbox]')
  if (await boxes.count() > 2) { await boxes.nth(1).check(); await p.waitForTimeout(700) }
  await shot(p, 'options-list', { selector: '.question-card' })

  await card.locator('.toggle-mode').first().click(); await p.waitForTimeout(500)
  await card.locator('input[type=text]').first().fill('planilha interna do laboratório')
  await shot(p, 'other-specify', { selector: '.question-card' })

  await card.locator('.more-summary').first().click(); await p.waitForTimeout(500)
  await shot(p, 'status-control', { selector: '.question-card' })

  await shot(p, 'save-indicator', { selector: 'header, .editor-header, .community-name' })

  // share + exports live further down the editor
  for (const [name, sel] of [['share-panel', '.share, .share-box, [class*=share]'], ['export-buttons', '.export-buttons, [class*=export]']]) {
    try { await p.locator(sel).first().scrollIntoViewIfNeeded(); await p.waitForTimeout(400) } catch {}
    await shot(p, name, { selector: sel })
  }

  await go(p, '/'); await shot(p, 'home-device-fips', { fullPage: true })
  await ctx.close()
}

// ---------------- administrator (desktop) ----------------
{
  const ctx = await browser.newContext(DESKTOP); const p = await ctx.newPage()
  await login(p, FACIL)
  await go(p, '/workspace'); await shot(p, 'workspace')
  await go(p, '/sessions/new'); await shot(p, 'session-new', { fullPage: true })
  await go(p, `/sessions/${SESSION_ID}`); await shot(p, 'session-detail')
  await shot(p, 'session-fip-list', { selector: '.fip-list, [class*=fip-list], table' })
  try { await p.getByRole('button', { name: /projector/i }).first().click(); await p.waitForTimeout(900); await shot(p, 'projector-mode') } catch (e) { failed.push('projector-mode: ' + String(e).split('\n')[0]) }
  await go(p, `/sessions/${SESSION_ID}/matrix`); await shot(p, 'comparison-matrix')
  await go(p, '/knowledge-models'); await shot(p, 'knowledge-model-catalogue')
  await go(p, '/knowledge-models/gofair-fip-mini/1.0.0'); await shot(p, 'knowledge-model-read')
  await go(p, '/knowledge-models/gofair-fip-mini/1.0.0/print'); await shot(p, 'questionnaire-print')
  await ctx.close()
}

// ---------------- admin + dashboard (desktop, last) ----------------
{
  const ctx = await browser.newContext(DESKTOP); const p = await ctx.newPage()
  await login(p, ADMIN)
  await go(p, '/admin'); await shot(p, 'admin-page', { fullPage: true })
  await go(p, '/dashboard'); await shot(p, 'dashboard-home')
  await go(p, `/dashboard/coverage?pop=session:${SESSION_ID}`); await shot(p, 'dashboard-coverage')
  await go(p, `/dashboard/similarity?pop=session:${SESSION_ID}`); await shot(p, 'dashboard-similarity')
  await ctx.close()
}

await browser.close()
console.log(`\ncaptured ${ok.length}, failed ${failed.length}`)
if (failed.length) console.log(failed.join('\n'))
