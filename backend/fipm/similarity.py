"""spec 13-fip-dashboard.md §4: the exact similarity measure (§4.1), the
MinHash/LSH candidate-generation machinery (§4.2) and union-find clustering
(§4.4). **Pure**: no DB, no FastAPI import, no third-party dependency (D7) --
`hashlib.blake2b`, `random.Random` with a fixed seed, and plain Python
arithmetic only.

`score_pair` is the single most important function in this module: every
similarity score a user ever sees is its output, recomputed over stored
declarations. MinHash/LSH (`minhash`/`bands`) is used **only** to generate
candidates faster than an O(n^2) scan -- never to approximate a score
(§4.2's central invariant, asserted independently by AC-24)."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Protocol

NA = "NA"
PLANNED_STATUSES = frozenset({"planned", "planned-development", "planned-replacement"})


class CellLike(Protocol):
    question_id: str
    sub_principle: str | None
    not_applicable: bool


class DeclarationLike(Protocol):
    question_id: str
    fer_key: str
    status: str


# ---------------------------------------------------------------------------
# §4.2 -- the token set (MinHash input only, never the score)
# ---------------------------------------------------------------------------


def tokens(cells: list[CellLike], declarations: list[DeclarationLike]) -> set[str]:
    """`{question_id + "\\x1f" + fer_key}` over `current` declarations, plus
    `question_id + "\\x1fNA"` per not-applicable cell. Token-set Jaccard over
    this set is *not* the §4.1 measure (it's `weighting=question` with a
    different denominator) -- it exists only to feed `minhash`."""
    out: set[str] = set()
    for decl in declarations:
        if decl.status == "current":
            out.add(f"{decl.question_id}\x1f{decl.fer_key}")
    for cell in cells:
        if cell.not_applicable:
            out.add(f"{cell.question_id}\x1f{NA}")
    return out


# ---------------------------------------------------------------------------
# §4.1 -- the exact measure
# ---------------------------------------------------------------------------


def _question_sets(
    cells: list[CellLike], declarations: list[DeclarationLike], statuses: str
) -> dict[str, set[str]]:
    """`{question_id: S(q)}` for one FIP, restricted to the questions this
    FIP's own questionnaire carries a cell for (spec §4.1: "a question q
    present in both FIPs' questionnaires" -- the caller intersects the two
    FIPs' key sets). `S(q)` is the set of included declarations' `fer_key`s
    (`current`, or `current` + `planned*` when `statuses='currentPlanned'`)
    plus the `NA` sentinel when the cell is not-applicable (assumption A2)."""
    wanted = {"current"} | (PLANNED_STATUSES if statuses == "currentPlanned" else set())
    out: dict[str, set[str]] = {c.question_id: set() for c in cells}
    for cell in cells:
        if cell.not_applicable:
            out[cell.question_id].add(NA)
    for decl in declarations:
        if decl.status in wanted and decl.question_id in out:
            out[decl.question_id].add(decl.fer_key)
    return out


@dataclass(frozen=True)
class QuestionScore:
    question_id: str
    sub_principle: str | None
    jaccard: float | None
    included: bool


@dataclass(frozen=True)
class PairScore:
    """`overall` carries all three weightings at once (§4.1) -- they are
    cheap means over the same per-question Jaccards, so a caller reads
    `overall[weighting]` without a second pass. `shared_pairs` never
    contains the `NA` sentinel -- it names actual shared FER declarations,
    for `topShared` display."""

    overall: dict[str, float]
    per_question: list[QuestionScore]
    per_principle: dict[str, float]
    shared_keys: int
    shared_pairs: list[tuple[str, str]]


def score_pair(
    a_cells: list[CellLike],
    a_declarations: list[DeclarationLike],
    b_cells: list[CellLike],
    b_declarations: list[DeclarationLike],
    *,
    statuses: str = "current",
) -> PairScore:
    """spec §4.1, the exact measure. This is the function AC-24's
    independent brute-force reference is checked against for all three
    weightings -- it must never change without the spec changing."""
    a_sets = _question_sets(a_cells, a_declarations, statuses)
    b_sets = _question_sets(b_cells, b_declarations, statuses)
    sub_principle_by_q: dict[str, str | None] = {c.question_id: c.sub_principle for c in a_cells}
    for c in b_cells:
        sub_principle_by_q.setdefault(c.question_id, c.sub_principle)

    common_questions = sorted(set(a_sets) & set(b_sets))

    per_question: list[QuestionScore] = []
    shared_keys = 0
    shared_pairs: list[tuple[str, str]] = []
    by_principle: dict[str, list[float]] = {}

    for q in common_questions:
        sa, sb = a_sets[q], b_sets[q]
        sub_principle = sub_principle_by_q.get(q)
        if not sa and not sb:
            per_question.append(QuestionScore(q, sub_principle, None, False))
            continue
        inter = sa & sb
        union = sa | sb
        j = len(inter) / len(union) if union else 0.0
        per_question.append(QuestionScore(q, sub_principle, j, True))
        shared_keys += len(inter)
        for key in inter:
            if key != NA:
                shared_pairs.append((q, key))
        if sub_principle:
            by_principle.setdefault(sub_principle, []).append(j)

    per_principle = {p: sum(vs) / len(vs) for p, vs in by_principle.items()}

    included_js = [qs.jaccard for qs in per_question if qs.included]
    overall_question = sum(included_js) / len(included_js) if included_js else 0.0
    overall_principle = sum(per_principle.values()) / len(per_principle) if per_principle else 0.0

    by_letter: dict[str, list[float]] = {}
    for p, j in per_principle.items():
        by_letter.setdefault(p[0], []).append(j)
    letter_means = [sum(vs) / len(vs) for vs in by_letter.values()]
    overall_letter = sum(letter_means) / len(letter_means) if letter_means else 0.0

    return PairScore(
        overall={
            "principle": overall_principle,
            "question": overall_question,
            "letter": overall_letter,
        },
        per_question=per_question,
        per_principle=per_principle,
        shared_keys=shared_keys,
        shared_pairs=shared_pairs,
    )


# ---------------------------------------------------------------------------
# §4.2 -- MinHash signatures and LSH banding, pure Python (D7)
# ---------------------------------------------------------------------------

_MERSENNE_61 = (1 << 61) - 1
_MASK32 = 0xFFFFFFFF
_BAND_MASK62 = (1 << 62) - 1


def _hash_coefficients(k: int, seed: int) -> list[tuple[int, int]]:
    """`a_i`, `b_i` drawn once from `random.Random(seed)` and frozen --
    deterministic across processes and across calls (never re-randomised),
    which is what makes signatures comparable across a reprojection and a
    fresh process (AC-31)."""
    rng = random.Random(seed)
    return [(rng.randrange(1, _MERSENNE_61), rng.randrange(0, _MERSENNE_61)) for _ in range(k)]


def _base_hash(token: str) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big")


def minhash(token_set: set[str], *, k: int, seed: int) -> bytes:
    """spec §4.2: one 64-bit base hash per token, `k` permutations
    `h_i = ((a_i * h0 + b_i) % (2**61 - 1)) & 0xFFFFFFFF`. Returns `k`
    big-endian uint32s packed into `bytes` (512 bytes at k=128). An empty
    token set yields the all-`0xFFFFFFFF` sentinel signature -- deterministic,
    never a special case for a caller."""
    coefficients = _hash_coefficients(k, seed)
    if not token_set:
        mins = [_MASK32] * k
    else:
        base_hashes = [_base_hash(t) for t in token_set]
        mins = [
            min(((a * h0 + b) % _MERSENNE_61) & _MASK32 for h0 in base_hashes)
            for a, b in coefficients
        ]
    return b"".join(v.to_bytes(4, "big") for v in mins)


def bands(signature: bytes, *, n_bands: int, rows_per_band: int) -> list[int]:
    """spec §4.2: split the signature into `n_bands` consecutive groups of
    `rows_per_band` 4-byte minhashes; each band's hash is
    `blake2b(band_bytes, digest_size=8)` masked to 62 bits (positive,
    `BigInteger`-safe on both SQLite and Postgres, spec §1.9)."""
    band_size = rows_per_band * 4
    out: list[int] = []
    for i in range(n_bands):
        chunk = signature[i * band_size : (i + 1) * band_size]
        h = int.from_bytes(hashlib.blake2b(chunk, digest_size=8).digest(), "big")
        out.append(h & _BAND_MASK62)
    return out


# ---------------------------------------------------------------------------
# §4.4 -- union-find clustering, pure Python, O(E alpha(n))
# ---------------------------------------------------------------------------


class UnionFind:
    """D6: single-link connected components over a thresholded candidate
    graph -- not true hierarchical clustering, which needs the full
    distance matrix this spec exists to avoid."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = {}

    def add(self, x: str) -> None:
        self._parent.setdefault(x, x)
        self._rank.setdefault(x, 0)

    def find(self, x: str) -> str:
        self.add(x)
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, x: str, y: str) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1

    def components(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for x in list(self._parent):
            out.setdefault(self.find(x), []).append(x)
        return out


def cluster_edges(node_ids: list[str], edges: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Connected components of `node_ids` under `edges` -- the clustering
    step of spec §4.4, run over the LSH-candidate graph (or the exact
    all-pairs graph below `EXACT_PAIRS_MAX_FIPS`), never the complete graph.
    Returns `{representative_id: [member_ids]}`, one entry per component
    (including size-1 components for an unconnected node)."""
    uf = UnionFind()
    for n in node_ids:
        uf.add(n)
    for a, b in edges:
        uf.union(a, b)
    return uf.components()
