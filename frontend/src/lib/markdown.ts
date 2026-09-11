/**
 * An escape-first Markdown -> HTML renderer, originally written for the
 * privacy notice (spec 05 §2) and extended to render the user guides
 * (docs/participant-guide.md, docs/administrator-guide.md): every
 * character is HTML-escaped before any markup is recognised, so no
 * input — however crafted — can ever produce a raw tag. Supports:
 * `#`-`###` headings, paragraphs, `-` lists, `**bold**`, `*em*`,
 * `[text](url)` links, `---` rules, GitHub-style pipe tables,
 * `> ` blockquotes, `![alt](src)` images, inline `` `code` `` spans and
 * fenced ``` code blocks (rendered verbatim, never scanned for inline
 * markup). No new dependency.
 */

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * Only `http(s)://` and same-origin `/...` targets are ever allowed. A
 * leading `//` is a protocol-relative URL (`//evil.example`, resolved by
 * the browser against whatever scheme the page is served over) — it starts
 * with `/` but is not same-origin, so it's rejected same as any other
 * off-allowlist scheme (including `javascript:` and `data:`).
 *
 * Browsers normalise `\` to `/` inside URLs for special schemes (http,
 * https, ...), so `/\evil.example/p` is *also* protocol-relative —
 * `new URL('/\\evil.example/p', 'https://app.example')` resolves to
 * `https://evil.example/p`, not the same origin. Reject that form too:
 * any same-origin path whose second character is `/` or `\` is rejected,
 * not just a literal leading `//`.
 */
function isSafeUrl(url: string): boolean {
  if (/^https?:\/\//i.test(url)) return true
  if (url.startsWith('/')) return url[1] !== '/' && url[1] !== '\\'
  return false
}

/**
 * A same-page fragment, e.g. `#3-the-editor-at-a-glance`. The guides carry
 * their own hand-written tables of contents, so rejecting these would turn
 * every entry into a dead link. Accented characters are allowed because the
 * pt-PT/pt-BR/es headings slug to anchors containing them; the character set
 * is still restricted so a fragment can never break out of the href quoting.
 */
function isFragment(url: string): boolean {
  return /^#[\w\u00C0-\u024F\u1E00-\u1EFF-]*$/.test(url)
}

function safeHref(url: string): string {
  if (isFragment(url)) return url
  return isSafeUrl(url) ? url : '#'
}

/** Same allowlist as safeHref, but an unsafe image src is dropped rather than pointing at '#'. */
function safeImageSrc(url: string): string {
  return isSafeUrl(url) ? url : ''
}

/**
 * Bold/italic/links/images/inline-code, applied to already-escaped text —
 * never raw input. Code spans are extracted first (and restored last) so
 * that `*`/`[`/`]` characters inside them are never mistaken for other
 * inline markup.
 */
function renderInline(escaped: string): string {
  // Raw (unwrapped) code-span text, keyed by placeholder index -- kept
  // separate from the `<code>...</code>`-wrapped form used in text
  // content. An attribute value must never receive the wrapped form: if a
  // placeholder inside a would-be href/src/alt were restored to
  // `<code>...</code>` *after* being embedded in `href="..."`, a code span
  // in a link target or alt text (e.g. `` [x](/a`b`c) ``) would splice a
  // raw tag straight into that attribute. So attribute values are resolved
  // to plain text immediately, before they are ever placed inside markup;
  // only placeholders left in ordinary text content are restored wrapped,
  // at the very end.
  const codeSpans: string[] = []
  let out = escaped.replace(/`([^`]+)`/g, (_match, code: string) => {
    const index = codeSpans.push(code) - 1
    return `\u0000CODE${index}\u0000`
  })
  const restoreForAttribute = (value: string): string =>
    value.replace(/\u0000CODE(\d+)\u0000/g, (_match, index: string) => codeSpans[Number(index)])
  out = out.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_match, alt: string, src: string) => {
    return `<img src="${safeImageSrc(restoreForAttribute(src))}" alt="${restoreForAttribute(alt)}">`
  })
  out = out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_match, label: string, url: string) => {
    const href = safeHref(restoreForAttribute(url))
    // Only a genuinely external link opens a new tab. Same-page fragments are
    // how the guides' own tables of contents work, and sending those to a new
    // tab means every entry spawns a duplicate page instead of scrolling.
    const external = /^https?:\/\//i.test(href)
    const attrs = external ? ' target="_blank" rel="noopener"' : ''
    return `<a href="${href}"${attrs}>${label}</a>`
  })
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  out = out.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  out = out.replace(/\u0000CODE(\d+)\u0000/g, (_match, index: string) => `<code>${codeSpans[Number(index)]}</code>`)
  return out
}

const HEADING = /^(#{1,3})\s+(.*)$/
// Captures leading indentation (for nesting), the marker (`-` or `1.`, `2.`,
// ...) and the item's text. A top-level item has zero leading spaces; an
// item indented by two or more spaces nests inside the previous item at a
// shallower indent (see `parseList` below).
const LIST_ITEM_LINE = /^(\s*)(-|\d+\.)\s+(.*)$/
const RULE = /^-{3,}\s*$/
const BLANK = /^\s*$/
const FENCE = /^```/
const BLOCKQUOTE = /^>\s?(.*)$/
const TABLE_SEPARATOR = /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/

function splitTableRow(line: string): string[] {
  let trimmed = line.trim()
  if (trimmed.startsWith('|')) trimmed = trimmed.slice(1)
  if (trimmed.endsWith('|')) trimmed = trimmed.slice(0, -1)
  return trimmed.split('|').map((cell) => cell.trim())
}

type Align = 'left' | 'right' | 'center' | null

function cellAlign(separatorCell: string): Align {
  const s = separatorCell.trim()
  const left = s.startsWith(':')
  const right = s.endsWith(':')
  if (left && right) return 'center'
  if (right) return 'right'
  if (left) return 'left'
  return null
}

function alignAttr(align: Align): string {
  return align ? ` style="text-align:${align}"` : ''
}

function isTableStart(line: string, nextLine: string | undefined): boolean {
  if (!line.includes('|') || nextLine === undefined) return false
  if (!TABLE_SEPARATOR.test(nextLine) || !nextLine.includes('-')) return false
  // A bare `---` rule also matches TABLE_SEPARATOR (it's a valid one-column
  // separator), so a plain horizontal rule following a line that merely
  // mentions "|" would otherwise be misread as a table. Require the
  // separator to describe the same number of columns as the header row.
  return splitTableRow(line).length === splitTableRow(nextLine).length
}

function isTopListItem(line: string): boolean {
  const match = LIST_ITEM_LINE.exec(line)
  return match !== null && match[1].length === 0
}

/**
 * Consumes a run of list-item lines starting at `lines[start]`, all of them
 * indented exactly `indent` spaces, and returns the rendered `<ul>`/`<ol>`
 * plus the index just past the last line it consumed. Ordered vs. unordered
 * is decided by the first item's marker. If an item is immediately followed
 * by a more-deeply-indented item, that run is parsed recursively and nested
 * inside the parent `<li>` -- this is how the guides' tables of contents
 * (a numbered top level with `   - ` sub-steps) render as a real nested
 * list instead of collapsing into one paragraph.
 */
function parseList(lines: string[], start: number, indent: number): { html: string; next: number } {
  let i = start
  let ordered: boolean | null = null
  const items: string[] = []

  while (i < lines.length) {
    const match = LIST_ITEM_LINE.exec(lines[i])
    if (!match || match[1].length !== indent) break
    const isOrdered = match[2] !== '-'
    if (ordered === null) ordered = isOrdered
    i += 1
    let itemHtml = renderInline(escapeHtml(match[3]))

    const next = i < lines.length ? LIST_ITEM_LINE.exec(lines[i]) : null
    if (next && next[1].length > indent) {
      const nested = parseList(lines, i, next[1].length)
      itemHtml += nested.html
      i = nested.next
    }

    items.push(`<li>${itemHtml}</li>`)
  }

  const tag = ordered ? 'ol' : 'ul'
  return { html: `<${tag}>${items.join('')}</${tag}>`, next: i }
}

function renderTable(headerCells: string[], aligns: Align[], bodyRows: string[][]): string {
  const cols = headerCells.length
  const thead = headerCells
    .map((cell, idx) => `<th${alignAttr(aligns[idx] ?? null)}>${renderInline(escapeHtml(cell))}</th>`)
    .join('')
  const rows = bodyRows
    .map((row) => {
      const tds: string[] = []
      for (let idx = 0; idx < cols; idx += 1) {
        const cell = row[idx] ?? ''
        tds.push(`<td${alignAttr(aligns[idx] ?? null)}>${renderInline(escapeHtml(cell))}</td>`)
      }
      return `<tr>${tds.join('')}</tr>`
    })
    .join('')
  return `<table><thead><tr>${thead}</tr></thead><tbody>${rows}</tbody></table>`
}

export function renderMarkdown(source: string): string {
  // The inline-code placeholder below uses U+0000 as its delimiter, so a NUL
  // in the input could otherwise forge a placeholder and smuggle markup past
  // the escaping. Strip them before anything else looks at the text.
  source = source.replace(/\u0000/g, '')
  const lines = source.replace(/\r\n/g, '\n').split('\n')
  const html: string[] = []
  let i = 0

  function isBlockStart(line: string, nextLine: string | undefined): boolean {
    return (
      BLANK.test(line) ||
      HEADING.test(line) ||
      isTopListItem(line) ||
      RULE.test(line) ||
      FENCE.test(line) ||
      BLOCKQUOTE.test(line) ||
      isTableStart(line, nextLine)
    )
  }

  while (i < lines.length) {
    const line = lines[i]

    if (BLANK.test(line)) {
      i += 1
      continue
    }

    if (FENCE.test(line)) {
      i += 1
      const codeLines: string[] = []
      while (i < lines.length && !FENCE.test(lines[i])) {
        codeLines.push(lines[i])
        i += 1
      }
      if (i < lines.length && FENCE.test(lines[i])) {
        i += 1 // consume closing fence; an unclosed fence just runs to EOF
      }
      html.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
      continue
    }

    if (RULE.test(line)) {
      html.push('<hr>')
      i += 1
      continue
    }

    const heading = HEADING.exec(line)
    if (heading) {
      const level = heading[1].length
      html.push(`<h${level}>${renderInline(escapeHtml(heading[2]))}</h${level}>`)
      i += 1
      continue
    }

    if (BLOCKQUOTE.test(line)) {
      const contentLines: string[] = []
      while (i < lines.length && BLOCKQUOTE.test(lines[i])) {
        contentLines.push(BLOCKQUOTE.exec(lines[i])![1])
        i += 1
      }
      html.push(`<blockquote><p>${renderInline(escapeHtml(contentLines.join(' ')))}</p></blockquote>`)
      continue
    }

    if (isTableStart(line, lines[i + 1])) {
      const headerCells = splitTableRow(line)
      const aligns = splitTableRow(lines[i + 1]).map(cellAlign)
      i += 2
      const bodyRows: string[][] = []
      while (i < lines.length && lines[i].includes('|') && !BLANK.test(lines[i])) {
        bodyRows.push(splitTableRow(lines[i]))
        i += 1
      }
      html.push(renderTable(headerCells, aligns, bodyRows))
      continue
    }

    if (isTopListItem(line)) {
      const list = parseList(lines, i, 0)
      html.push(list.html)
      i = list.next
      continue
    }

    const paragraph: string[] = []
    while (i < lines.length && !isBlockStart(lines[i], lines[i + 1])) {
      paragraph.push(lines[i])
      i += 1
    }
    html.push(`<p>${renderInline(escapeHtml(paragraph.join(' ')))}</p>`)
  }

  return html.join('\n')
}
