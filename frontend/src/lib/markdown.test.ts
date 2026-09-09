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
})
