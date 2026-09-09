/**
 * A ~50-line, escape-first Markdown -> HTML renderer for the privacy
 * notice only (spec 05 §2): every character is HTML-escaped before any
 * markup is recognised, so no input — however crafted — can ever produce
 * a raw tag. Supports exactly the subset the notice uses: `#`-`###`
 * headings, paragraphs, `-` lists, `**bold**`, `*em*`, `[text](url)`
 * links and `---` rules. No new dependency.
 */

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** Only `http(s)://` and same-origin `/...` targets are ever linked. */
function safeHref(url: string): string {
  if (/^https?:\/\//i.test(url) || url.startsWith('/')) return url
  return '#'
}

/** Bold/italic/links, applied to already-escaped text — never raw input. */
function renderInline(escaped: string): string {
  let out = escaped
  out = out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_match, label: string, url: string) => {
    return `<a href="${safeHref(url)}" target="_blank" rel="noopener">${label}</a>`
  })
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  out = out.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  return out
}

const HEADING = /^(#{1,3})\s+(.*)$/
const LIST_ITEM = /^-\s+(.*)$/
const RULE = /^-{3,}\s*$/
const BLANK = /^\s*$/

export function renderMarkdown(source: string): string {
  const lines = source.replace(/\r\n/g, '\n').split('\n')
  const html: string[] = []
  let listOpen = false
  let i = 0

  function closeList() {
    if (listOpen) {
      html.push('</ul>')
      listOpen = false
    }
  }

  while (i < lines.length) {
    const line = lines[i]

    if (BLANK.test(line)) {
      closeList()
      i += 1
      continue
    }

    if (RULE.test(line)) {
      closeList()
      html.push('<hr>')
      i += 1
      continue
    }

    const heading = HEADING.exec(line)
    if (heading) {
      closeList()
      const level = heading[1].length
      html.push(`<h${level}>${renderInline(escapeHtml(heading[2]))}</h${level}>`)
      i += 1
      continue
    }

    const item = LIST_ITEM.exec(line)
    if (item) {
      if (!listOpen) {
        html.push('<ul>')
        listOpen = true
      }
      html.push(`<li>${renderInline(escapeHtml(item[1]))}</li>`)
      i += 1
      continue
    }

    closeList()
    const paragraph: string[] = []
    while (i < lines.length && !BLANK.test(lines[i]) && !HEADING.test(lines[i]) && !LIST_ITEM.test(lines[i]) && !RULE.test(lines[i])) {
      paragraph.push(lines[i])
      i += 1
    }
    html.push(`<p>${renderInline(escapeHtml(paragraph.join(' ')))}</p>`)
  }

  closeList()
  return html.join('\n')
}
