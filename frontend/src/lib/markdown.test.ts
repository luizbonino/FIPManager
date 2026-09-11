import { describe, expect, it } from 'vitest'
import { renderMarkdown } from './markdown'

// Criterion 15 (docs/specs/05-v1-completion.md §8): headings, lists and
// links render, and an injected `<script>` tag is always escaped to text —
// never inserted as a raw tag, whatever markup surrounds it.
describe('renderMarkdown', () => {
  it('renders #/##/### as h1/h2/h3', () => {
    const html = renderMarkdown('# Title\n## Section\n### Sub')
    expect(html).toContain('<h1>Title</h1>')
    expect(html).toContain('<h2>Section</h2>')
    expect(html).toContain('<h3>Sub</h3>')
  })

  it('renders a paragraph', () => {
    const html = renderMarkdown('Just a sentence.')
    expect(html).toContain('<p>Just a sentence.</p>')
  })

  it('renders a - list as <ul><li>', () => {
    const html = renderMarkdown('- first\n- second')
    expect(html).toContain('<ul>')
    expect(html).toContain('<li>first</li>')
    expect(html).toContain('<li>second</li>')
    expect(html).toContain('</ul>')
  })

  it('renders a 1. list as <ol><li>', () => {
    const html = renderMarkdown('1. first\n2. second')
    expect(html).toContain('<ol>')
    expect(html).toContain('<li>first</li>')
    expect(html).toContain('<li>second</li>')
    expect(html).toContain('</ol>')
    expect(html).not.toContain('<ul>')
  })

  // The real shape of the guides' hand-written tables of contents: a
  // numbered top level, with `   - ` sub-steps nested two spaces in. This is
  // what collapsed into one run-on paragraph before nested-list support
  // (docs/participant-guide.md's own "Table of contents" section).
  it('renders a nested unordered list under an ordered item (the guides TOC shape)', () => {
    const source = [
      '1. [What you are describing (key concepts)](#1-what-you-are-describing-key-concepts)',
      '2. [Three ways to start](#2-three-ways-to-start)',
      '4. [Walkthrough: fill in your first FIP](#4-walkthrough-fill-in-your-first-fip)',
      '   - [Step 1 — Choose your area](#step-1--choose-your-area)',
      '   - [Step 2 — Name your community](#step-2--name-your-community)',
      '5. [The five kinds of answer](#5-the-five-kinds-of-answer)',
    ].join('\n')
    const html = renderMarkdown(source)
    expect(html).toContain('<ol>')
    expect(html).toContain(
      '<li><a href="#4-walkthrough-fill-in-your-first-fip">Walkthrough: fill in your first FIP</a>' +
        '<ul><li><a href="#step-1--choose-your-area">Step 1 — Choose your area</a></li>' +
        '<li><a href="#step-2--name-your-community">Step 2 — Name your community</a></li></ul></li>'
    )
    // The nested list closes back into the outer <ol> before the next top-level item.
    expect(html).toContain('</ul></li><li><a href="#5-the-five-kinds-of-answer">')
  })

  it('renders a nested ordered list under an unordered item', () => {
    const html = renderMarkdown('- outer\n  1. inner one\n  2. inner two\n- outer two')
    expect(html).toContain('<ul><li>outer<ol><li>inner one</li><li>inner two</li></ol></li><li>outer two</li></ul>')
  })

  it('renders a list immediately following a paragraph', () => {
    const html = renderMarkdown('Some intro text.\n- first\n- second')
    expect(html).toContain('<p>Some intro text.</p>')
    expect(html).toContain('<ul><li>first</li><li>second</li></ul>')
  })

  it('renders a list immediately followed by a heading', () => {
    const html = renderMarkdown('- first\n- second\n## Next section')
    expect(html).toContain('<ul><li>first</li><li>second</li></ul>')
    expect(html).toContain('<h2>Next section</h2>')
  })

  it('renders links and inline code inside ordered list items', () => {
    const html = renderMarkdown('1. See [the docs](https://example.org/docs) and run `npm test`')
    expect(html).toContain('<a href="https://example.org/docs" target="_blank" rel="noopener">the docs</a>')
    expect(html).toContain('<code>npm test</code>')
  })

  it('escapes adversarial content inside a nested list item without ever emitting a raw tag', () => {
    const html = renderMarkdown('1. outer\n   - <img src=x onerror=alert(1)>')
    expect(html).not.toContain('<img src=x')
    expect(html).toContain('&lt;img')
  })

  it('renders **bold** and *em*', () => {
    const html = renderMarkdown('**strong** and *emphasised*')
    expect(html).toContain('<strong>strong</strong>')
    expect(html).toContain('<em>emphasised</em>')
  })

  it('renders [text](url) as a safe, new-tab link', () => {
    const html = renderMarkdown('[Privacy notice](https://example.org/privacy)')
    expect(html).toContain('<a href="https://example.org/privacy" target="_blank" rel="noopener">Privacy notice</a>')
  })

  it('renders --- as <hr>', () => {
    const html = renderMarkdown('above\n\n---\n\nbelow')
    expect(html).toContain('<hr>')
  })

  it('never emits a javascript: link target', () => {
    const html = renderMarkdown('[click me](javascript:alert(1))')
    expect(html).not.toContain('href="javascript:')
    expect(html).toContain('href="#"')
  })

  it('never emits a protocol-relative link target', () => {
    const html = renderMarkdown('[click me](//evil.example/phish)')
    expect(html).not.toContain('href="//evil.example')
    expect(html).toContain('href="#"')
  })

  // Browsers normalise a leading `/\` to `//` for special schemes, so
  // `new URL('/\\evil.example/p', 'https://app.example')` resolves to
  // `https://evil.example/p` -- a bare `startsWith('//')` check misses
  // this second protocol-relative spelling entirely (review finding 1).
  it('never emits a backslash-protocol-relative link target', () => {
    const html = renderMarkdown('[click me](/\\evil.example/phish)')
    expect(html).not.toContain('href="/\\evil.example')
    expect(html).toContain('href="#"')
  })

  it('escapes an injected <script> tag as text, in a paragraph', () => {
    const html = renderMarkdown('<script>alert(1)</script>')
    expect(html).not.toContain('<script>')
    expect(html).toContain('&lt;script&gt;')
  })

  it('escapes an injected <script> tag inside a heading', () => {
    const html = renderMarkdown('# <script>alert(1)</script>')
    expect(html).not.toContain('<script>alert')
    expect(html).toContain('&lt;script&gt;')
  })

  it('escapes an injected <script> tag inside a list item', () => {
    const html = renderMarkdown('- <script>alert(1)</script>')
    expect(html).not.toContain('<script>alert')
    expect(html).toContain('&lt;script&gt;')
  })

  it('escapes a raw tag hidden inside a link label', () => {
    const html = renderMarkdown('[<img src=x onerror=alert(1)>](https://example.org)')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img')
  })

  // --- Tables -------------------------------------------------------

  describe('tables', () => {
    it('renders a header row and body rows as a table', () => {
      const html = renderMarkdown('| Name | Role |\n|---|---|\n| Alice | Admin |\n| Bob | Editor |')
      expect(html).toContain('<table>')
      expect(html).toContain('<thead><tr><th>Name</th><th>Role</th></tr></thead>')
      expect(html).toContain('<td>Alice</td>')
      expect(html).toContain('<td>Admin</td>')
      expect(html).toContain('<td>Bob</td>')
      expect(html).toContain('<td>Editor</td>')
      expect(html).toContain('</table>')
    })

    it('applies alignment from the separator row colons', () => {
      const html = renderMarkdown('| A | B | C |\n|:---|:---:|---:|\n| 1 | 2 | 3 |')
      expect(html).toContain('<th style="text-align:left">A</th>')
      expect(html).toContain('<th style="text-align:center">B</th>')
      expect(html).toContain('<th style="text-align:right">C</th>')
      expect(html).toContain('<td style="text-align:right">3</td>')
    })

    it('renders inline markup inside table cells', () => {
      const html = renderMarkdown('| Term | Meaning |\n|---|---|\n| **FIP** | a `profile` with a [link](https://example.org) |')
      expect(html).toContain('<td><strong>FIP</strong></td>')
      expect(html).toContain('<code>profile</code>')
      expect(html).toContain('<a href="https://example.org" target="_blank" rel="noopener">link</a>')
    })

    it('handles a ragged row with fewer cells than the header without crashing', () => {
      const html = renderMarkdown('| A | B | C |\n|---|---|---|\n| 1 |')
      expect(html).toContain('<table>')
      expect(html).toContain('<td>1</td>')
      expect(html).toContain('<td></td>')
    })

    it('escapes a <script> tag inside a table cell', () => {
      const html = renderMarkdown('| Name |\n|---|\n| <script>alert(1)</script> |')
      expect(html).not.toContain('<script>alert')
      expect(html).toContain('&lt;script&gt;')
    })

    // A bare `---` rule also matches the table-separator pattern (a valid
    // one-column separator), so a paragraph merely mentioning "|" followed
    // by a horizontal rule used to be misread as a table, silently
    // swallowing the <hr> (review finding 5).
    it('does not mistake a "|" mention followed by a rule for a table', () => {
      const html = renderMarkdown('Use the | character.\n---\nNext paragraph.')
      expect(html).not.toContain('<table>')
      expect(html).toContain('<hr>')
      expect(html).toContain('<p>Use the | character.</p>')
    })
  })

  // --- Blockquotes ----------------------------------------------------

  describe('blockquotes', () => {
    it('renders a single-line > block as a blockquote', () => {
      const html = renderMarkdown('> A callout.')
      expect(html).toContain('<blockquote><p>A callout.</p></blockquote>')
    })

    it('joins multi-line > continuation lines into one blockquote', () => {
      const html = renderMarkdown('> Line one\n> Line two')
      expect(html).toContain('<blockquote><p>Line one Line two</p></blockquote>')
    })

    it('renders a **bold** lead-in inside a blockquote', () => {
      const html = renderMarkdown('> **Note:** remember to save.')
      expect(html).toContain('<blockquote><p><strong>Note:</strong> remember to save.</p></blockquote>')
    })

    it('escapes a <script> tag inside a blockquote', () => {
      const html = renderMarkdown('> <script>alert(1)</script>')
      expect(html).not.toContain('<script>alert')
      expect(html).toContain('&lt;script&gt;')
    })

    it('renders a table immediately following a blockquote', () => {
      const html = renderMarkdown('> A note.\n| A | B |\n|---|---|\n| 1 | 2 |')
      expect(html).toContain('<blockquote><p>A note.</p></blockquote>')
      expect(html).toContain('<table>')
      expect(html).toContain('<td>1</td>')
    })
  })

  // --- Images -----------------------------------------------------------

  describe('images', () => {
    it('renders ![alt](src) as an <img> with the alt text', () => {
      const html = renderMarkdown('![Screenshot of the dashboard](/api/guides/images/foo.png)')
      expect(html).toContain('<img src="/api/guides/images/foo.png" alt="Screenshot of the dashboard">')
    })

    it('drops a javascript: image src', () => {
      const html = renderMarkdown('![alt](javascript:alert(1))')
      expect(html).not.toContain('javascript:')
      expect(html).toContain('<img src="" alt="alt">')
    })

    it('drops a data:text/html image src', () => {
      const html = renderMarkdown('![alt](data:text/html,<script>alert(1)</script>)')
      expect(html).not.toContain('data:text/html')
      expect(html).not.toContain('<script>alert')
    })

    // Same isSafeUrl allowlist as href; the backslash-protocol-relative
    // bypass in isSafeUrl affects safeImageSrc too (review finding 1).
    it('drops a backslash-protocol-relative image src', () => {
      const html = renderMarkdown('![alt](/\\evil.example/p.png)')
      expect(html).not.toContain('/\\evil.example')
      expect(html).toContain('<img src="" alt="alt">')
    })

    it('escapes a <script> tag hidden inside alt text', () => {
      const html = renderMarkdown('![<script>alert(1)</script>](/api/guides/images/foo.png)')
      expect(html).not.toContain('<script>alert')
      expect(html).toContain('&lt;script&gt;')
    })
  })

  // --- Inline code --------------------------------------------------------

  describe('inline code', () => {
    it('renders `code` spans as <code>', () => {
      const html = renderMarkdown('Set the `FIPM_SECRET` env var.')
      expect(html).toContain('Set the <code>FIPM_SECRET</code> env var.')
    })

    it('does not apply bold/em markup found inside a code span', () => {
      const html = renderMarkdown('Run `**not bold**` literally.')
      expect(html).toContain('<code>**not bold**</code>')
      expect(html).not.toContain('<strong>')
    })

    it('escapes a <script> tag inside an inline code span', () => {
      const html = renderMarkdown('`<script>alert(1)</script>`')
      expect(html).not.toContain('<script>alert')
      expect(html).toContain('&lt;script&gt;')
    })

    // A code span inside a link target or alt text used to be restored
    // *after* the href/alt attribute string was already built, splicing a
    // raw <code> tag into the attribute value (review finding 2).
    it('never restores a code span as a raw tag inside an href value', () => {
      const html = renderMarkdown('[x](/a`b`c)')
      expect(html).not.toContain('<code>')
      expect(html).toContain('href="/abc"')
    })

    it('never restores a code span as a raw tag inside an alt value', () => {
      const html = renderMarkdown('![x`y`z](/i.png)')
      expect(html).not.toContain('<code>')
      expect(html).toContain('alt="xyz"')
    })

    it('still renders a code span as <code> in ordinary link label text', () => {
      const html = renderMarkdown('[a `code` label](https://example.org)')
      expect(html).toContain('<code>code</code>')
    })
  })

  // --- Fenced code blocks ---------------------------------------------

  describe('fenced code blocks', () => {
    it('renders a fenced block verbatim as <pre><code>', () => {
      const html = renderMarkdown('```\ndocker compose up -d\n```')
      expect(html).toContain('<pre><code>docker compose up -d</code></pre>')
    })

    it('does not process inline markup inside a fenced block', () => {
      const html = renderMarkdown('```\n**not bold** and [not a link](https://example.org)\n```')
      expect(html).toContain('<pre><code>**not bold** and [not a link](https://example.org)</code></pre>')
      expect(html).not.toContain('<strong>')
      expect(html).not.toContain('<a href')
    })

    it('escapes a <script> tag inside a fenced code block', () => {
      const html = renderMarkdown('```\n<script>alert(1)</script>\n```')
      expect(html).not.toContain('<script>alert')
      expect(html).toContain('&lt;script&gt;')
    })

    it('handles an unclosed fence by consuming to the end of input', () => {
      const html = renderMarkdown('```\necho one\necho two')
      expect(html).toContain('<pre><code>echo one\necho two</code></pre>')
    })
  })

  // --- Realistic multi-feature excerpt ---------------------------------

  it('renders a realistic guide excerpt combining headings, a callout, a table, code and an image', () => {
    const source = [
      '## Installing the server',
      '',
      '> **Note:** back up your database before upgrading.',
      '',
      'Set the `FIPM_SECRET` environment variable, then run:',
      '',
      '```',
      'docker compose up -d',
      '```',
      '',
      '| Variable | Purpose |',
      '|---|---|',
      '| `FIPM_SECRET` | signs session cookies |',
      '| `FIPM_DB_URL` | database connection string |',
      '',
      '![Admin dashboard](/api/guides/images/dashboard.png)',
    ].join('\n')

    const html = renderMarkdown(source)
    expect(html).toContain('<h2>Installing the server</h2>')
    expect(html).toContain('<blockquote><p><strong>Note:</strong> back up your database before upgrading.</p></blockquote>')
    expect(html).toContain('<code>FIPM_SECRET</code> environment variable')
    expect(html).toContain('<pre><code>docker compose up -d</code></pre>')
    expect(html).toContain('<table>')
    expect(html).toContain('<td><code>FIPM_SECRET</code></td>')
    expect(html).toContain('<td>signs session cookies</td>')
    expect(html).toContain('<img src="/api/guides/images/dashboard.png" alt="Admin dashboard">')
    expect(html).not.toContain('<script')
  })

  it('never leaves an unescaped <script anywhere in adversarial input', () => {
    const source = [
      '| <script>alert(1)</script> |',
      '|---|',
      '| <script>alert(2)</script> |',
      '',
      '> <script>alert(3)</script>',
      '',
      '![<script>alert(4)</script>](javascript:alert(5))',
      '',
      '`<script>alert(6)</script>`',
      '',
      '```',
      '<script>alert(7)</script>',
      '```',
    ].join('\n')

    const html = renderMarkdown(source)
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('<script ')
    expect(html).not.toContain('javascript:')
    expect(html).toContain('&lt;script&gt;')
  })
})


describe('guide anchors and NUL handling', () => {
  it('keeps a same-page fragment link so the guides table of contents works', () => {
    const html = renderMarkdown('[The editor](#3-the-editor-at-a-glance)')
    expect(html).toContain('href="#3-the-editor-at-a-glance"')
  })

  it('keeps an accented fragment, as the pt-PT and es headings produce', () => {
    const html = renderMarkdown('[\u00c1rea](#passo-1--escolher-a-sua-\u00e1rea)')
    expect(html).toContain('href="#passo-1--escolher-a-sua-\u00e1rea"')
  })

  it('still refuses a javascript: href', () => {
    expect(renderMarkdown('[x](javascript:alert(1))')).toContain('href="#"')
  })

  it('does not treat a fragment as a safe image src', () => {
    expect(renderMarkdown('![a](#nope)')).toContain('src=""')
  })

  it('strips NUL so crafted input cannot forge the code-span placeholder', () => {
    const forged = 'a \u0000CODE0\u0000 b `real`'
    const html = renderMarkdown(forged)
    expect(html).not.toContain('\u0000')
    expect(html).toContain('<code>real</code>')
  })

  it('does not send a same-page fragment to a new tab (the guides TOC)', () => {
    const html = renderMarkdown('[Section](#3-the-editor-at-a-glance)')
    expect(html).toContain('href="#3-the-editor-at-a-glance"')
    expect(html).not.toContain('target="_blank"')
  })

  it('still opens an external link in a new tab, with noopener', () => {
    const html = renderMarkdown('[GO FAIR](https://www.gofair.foundation/)')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener"')
  })

  it('refuses a protocol-relative URL written with a backslash', () => {
    expect(renderMarkdown('[x](/\\evil.example/p)')).toContain('href="#"')
  })
})
