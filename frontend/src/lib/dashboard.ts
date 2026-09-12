/**
 * Pure, unit-tested dashboard helpers (spec 13 §6.3): population spec <->
 * query string (including the three shorthands), client-side rollup
 * between coverage's four grouping levels, share formatting and
 * `cell_state` ordering. No network call lives here.
 *
 * The frontend always fetches coverage/gaps at the finest server grain
 * (`groupBy=question`, spec 13 §3.1's "rolling 126 rows up to
 * principles/groups happens in Python after the aggregate" — the same
 * response already carries every level's key) and rolls the response up
 * client-side, so a grouping change is never a refetch, exactly like
 * `SessionMatrix.vue`'s language switch (spec 13 §6.2 / builder brief C
 * read-first list: `matrix.ts`'s toggles-as-pure-view-state discipline).
 */
import { normaliseFreeText as matrixNormaliseFreeText } from './matrix'
import type { CoverageData, CoverageRow, GroupingLevel } from '@/types/dashboard'

/** Re-exported so callers only need to import from `lib/dashboard`. */
export const normaliseFreeText = matrixNormaliseFreeText

// ---------------------------------------------------------------------------
// Population spec <-> query string (spec 13 §2.1, §6.1)
// ---------------------------------------------------------------------------

export type PopulationTermKind = 'session' | 'public' | 'network' | 'questionnaire' | 'area' | 'mine'

export interface PopulationTerm {
  kind: PopulationTermKind
  id?: string
  version?: string
  sessionId?: string
}

export interface PopulationSpec {
  version: 1
  include: PopulationTerm[]
  exclude: PopulationTerm[]
  updatedAfter: string | null
  updatedBefore: string | null
}

export function emptyPopulationSpec(): PopulationSpec {
  return { version: 1, include: [], exclude: [], updatedAfter: null, updatedBefore: null }
}

function termSortKey(t: PopulationTerm): string {
  return [t.kind, t.id ?? '', t.version ?? '', t.sessionId ?? ''].join('\u0000')
}

/** Sort, drop duplicates, drop null/undefined fields — mirrors spec 13 §2.1's canonicalisation. */
function canonicaliseTerms(terms: PopulationTerm[]): PopulationTerm[] {
  const cleaned = terms.map((t) => {
    const out: PopulationTerm = { kind: t.kind }
    if (t.id != null) out.id = t.id
    if (t.version != null) out.version = t.version
    if (t.sessionId != null) out.sessionId = t.sessionId
    return out
  })
  cleaned.sort((a, b) => termSortKey(a).localeCompare(termSortKey(b)))
  const seen = new Set<string>()
  const out: PopulationTerm[] = []
  for (const t of cleaned) {
    const key = termSortKey(t)
    if (seen.has(key)) continue
    seen.add(key)
    out.push(t)
  }
  return out
}

export function canonicalisePopulationSpec(spec: PopulationSpec): PopulationSpec {
  return {
    version: 1,
    include: canonicaliseTerms(spec.include),
    exclude: canonicaliseTerms(spec.exclude),
    updatedAfter: spec.updatedAfter ?? null,
    updatedBefore: spec.updatedBefore ?? null,
  }
}

function base64UrlEncode(input: string): string {
  const bytes = new TextEncoder().encode(input)
  let binary = ''
  bytes.forEach((b) => {
    binary += String.fromCharCode(b)
  })
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function base64UrlDecode(input: string): string {
  const padded = input.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(input.length / 4) * 4, '=')
  const binary = atob(padded)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return new TextDecoder().decode(bytes)
}

const INLINE_POP_MAX_BYTES = 2048

/**
 * Encode a spec as a `pop` query value: the three human shorthands when the
 * spec matches one exactly (no exclude, no date range, one include term),
 * else urlsafe-base64 JSON capped at 2 KB (spec 13 §2.1).
 */
export function encodePopulationParam(spec: PopulationSpec): string {
  const canon = canonicalisePopulationSpec(spec)
  if (canon.exclude.length === 0 && !canon.updatedAfter && !canon.updatedBefore && canon.include.length === 1) {
    const term = canon.include[0]
    if (term.kind === 'public') return 'public'
    if (term.kind === 'network') return 'network'
    if (term.kind === 'session' && term.id) return `session:${term.id}`
  }
  const json = JSON.stringify(canon)
  const encoded = base64UrlEncode(json)
  if (new TextEncoder().encode(encoded).length > INLINE_POP_MAX_BYTES) {
    // Over the cap: caller must save the population server-side first
    // (`POST /api/dashboard/populations`) and use the returned hash instead.
    throw new Error('population_too_large_for_inline_url')
  }
  return encoded
}

/**
 * Decode a `pop` query value produced by `encodePopulationParam` (the three
 * shorthands, or inline base64 JSON). Returns `null` for an opaque saved
 * hash — the caller has nothing to reconstruct locally; the server's
 * response `population` field carries the label/fipCount/computedAt to
 * display instead.
 */
export function decodePopulationParam(pop: string): PopulationSpec | null {
  if (!pop) return null
  if (pop === 'public') return { version: 1, include: [{ kind: 'public' }], exclude: [], updatedAfter: null, updatedBefore: null }
  if (pop === 'network') return { version: 1, include: [{ kind: 'network' }], exclude: [], updatedAfter: null, updatedBefore: null }
  if (pop.startsWith('session:')) {
    return {
      version: 1,
      include: [{ kind: 'session', id: pop.slice('session:'.length) }],
      exclude: [],
      updatedAfter: null,
      updatedBefore: null,
    }
  }
  try {
    const parsed = JSON.parse(base64UrlDecode(pop))
    if (parsed && parsed.version === 1 && Array.isArray(parsed.include) && Array.isArray(parsed.exclude)) {
      return parsed as PopulationSpec
    }
  } catch {
    // Not inline JSON — an opaque saved-population hash.
  }
  return null
}

/** `true` when `pop` is a saved-population hash rather than a shorthand or inline spec. */
export function isSavedPopulationHash(pop: string): boolean {
  return !!pop && decodePopulationParam(pop) === null
}

// ---------------------------------------------------------------------------
// cell_state ordering (spec 13 §1.3) — the six states, precedence order
// ---------------------------------------------------------------------------

export const CELL_STATE_ORDER = ['current', 'planned', 'none', 'notApplicable', 'unanswered', 'absent'] as const
export type CellStateKey = (typeof CELL_STATE_ORDER)[number]

export function orderCellStates<T extends string>(keys: T[]): T[] {
  return [...keys].sort((a, b) => {
    const ai = CELL_STATE_ORDER.indexOf(a as unknown as CellStateKey)
    const bi = CELL_STATE_ORDER.indexOf(b as unknown as CellStateKey)
    return (ai === -1 ? CELL_STATE_ORDER.length : ai) - (bi === -1 ? CELL_STATE_ORDER.length : bi)
  })
}

// ---------------------------------------------------------------------------
// Share formatting
// ---------------------------------------------------------------------------

/** `0.7545` -> `"75.5%"`. Never renders a server-flagged approximate number as exact (spec 13 AC-6) — callers append their own `~`/tilde marker when `truncated`/`degraded` applies. */
export function formatShare(value: number, digits = 1): string {
  if (!Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat(undefined, { useGrouping: true }).format(value)
}

// ---------------------------------------------------------------------------
// Convergence key formatting (spec 13 §11.3 amendment)
// ---------------------------------------------------------------------------

/** Last `/`- or `#`-separated segment of an IRI, trailing separators ignored — same idiom as `NetworkFipDetail.vue`'s `iriTail`. */
export function iriTail(iri: string): string {
  const trimmed = iri.replace(/[/#]+$/, '')
  const idx = Math.max(trimmed.lastIndexOf('#'), trimmed.lastIndexOf('/'))
  return idx >= 0 ? trimmed.slice(idx + 1) : trimmed
}

export interface FormattedConvergenceKey {
  text: string
  isFreeText: boolean
}

const FREE_TEXT_PREFIX = 'text:'

/**
 * `NeighbourRow.topShared[].label` and `ConvergenceRow.topLabel`/`topKey`
 * carry the raw convergence key itself (spec 13 §11.3 amendment), never a
 * resolved display name: either a resource IRI, or `'text:' +
 * normaliseFreeText(text)` (`matrix.ts` line 189). Never present the raw
 * key to a user — an IRI shows its tail, a `text:` key is unprefixed and
 * flagged as free text so it is never mistaken for a catalogued label.
 */
export function formatConvergenceKey(raw: string): FormattedConvergenceKey {
  if (raw.startsWith(FREE_TEXT_PREFIX)) {
    return { text: raw.slice(FREE_TEXT_PREFIX.length), isFreeText: true }
  }
  return { text: iriTail(raw), isFreeText: false }
}

// ---------------------------------------------------------------------------
// Coverage rollup (spec 13 §3.1 / §6.2 / §6.3)
// ---------------------------------------------------------------------------

const COUNT_KEYS = ['current', 'planned', 'none', 'notApplicable', 'unanswered', 'absent'] as const

function rollupKeyFor(row: CoverageRow, level: GroupingLevel): { key: string; subPrinciple: string; principle: string; principleGroup: string } {
  if (level === 'question') {
    return { key: row.questions[0] ?? row.key, subPrinciple: row.subPrinciple, principle: row.principle, principleGroup: row.principleGroup }
  }
  if (level === 'subPrinciple') {
    return { key: row.subPrinciple, subPrinciple: row.subPrinciple, principle: row.principle, principleGroup: row.principleGroup }
  }
  if (level === 'principle') {
    // fip_cells.principle is already `subPrinciple` up to the first '.'
    // (spec 13 §1.3) — no string surgery needed here.
    return { key: row.principle, subPrinciple: row.principle, principle: row.principle, principleGroup: row.principleGroup }
  }
  return { key: row.principleGroup, subPrinciple: row.principleGroup, principle: row.principleGroup, principleGroup: row.principleGroup }
}

/**
 * Roll finest-grain (`groupBy=question`) coverage rows up to `level`,
 * purely client-side — no refetch on a grouping change (spec 13 AC-3).
 */
export function rollupCoverage(data: CoverageData, level: GroupingLevel): CoverageRow[] {
  if (level === 'question') return data.rows

  // Preserve `order` sequence when possible, else fall back to key order.
  // `data.order` holds keys at the level the SERVER grouped by (finest
  // grain, e.g. question ids) — a rolled-up bucket's own key (e.g. a
  // sub-principle) generally will not appear in it. So track, per bucket,
  // the minimum order-index among the SOURCE rows that fed into it (mirrors
  // the backend's `order_hint` in dashboard/views.py).
  const orderIndex = new Map(data.order.map((k, i) => [k, i]))
  const merged = new Map<string, CoverageRow>()
  const minOrderIndex = new Map<string, number>()
  for (const row of data.rows) {
    const { key, subPrinciple, principle, principleGroup } = rollupKeyFor(row, level)
    let target = merged.get(key)
    if (!target) {
      target = {
        key,
        level,
        subPrinciple,
        principle,
        principleGroup,
        questions: [],
        ferTypes: [],
        counts: { current: 0, planned: 0, none: 0, notApplicable: 0, unanswered: 0, absent: 0 },
        shares: { current: 0, planned: 0, none: 0, notApplicable: 0, unanswered: 0, absent: 0 },
        assurance: row.assurance ? {} : undefined,
      }
      merged.set(key, target)
    }
    for (const q of row.questions) if (!target.questions.includes(q)) target.questions.push(q)
    for (const ft of row.ferTypes) if (!target.ferTypes.includes(ft)) target.ferTypes.push(ft)
    for (const k of COUNT_KEYS) target.counts[k] += row.counts[k] ?? 0
    if (row.assurance && target.assurance) {
      for (const [k, v] of Object.entries(row.assurance)) target.assurance[k] = (target.assurance[k] ?? 0) + v
    }
    const rowIndex = orderIndex.get(row.key) ?? Number.MAX_SAFE_INTEGER
    const prevIndex = minOrderIndex.get(key) ?? Number.MAX_SAFE_INTEGER
    if (rowIndex < prevIndex) minOrderIndex.set(key, rowIndex)
  }

  const rows = [...merged.values()]
  for (const row of rows) {
    const total = COUNT_KEYS.reduce((sum, k) => sum + row.counts[k], 0)
    for (const k of COUNT_KEYS) row.shares[k] = total > 0 ? row.counts[k] / total : 0
  }
  rows.sort((a, b) => {
    const ai = minOrderIndex.get(a.key) ?? Number.MAX_SAFE_INTEGER
    const bi = minOrderIndex.get(b.key) ?? Number.MAX_SAFE_INTEGER
    if (ai !== bi) return ai - bi
    return a.key.localeCompare(b.key)
  })
  return rows
}
