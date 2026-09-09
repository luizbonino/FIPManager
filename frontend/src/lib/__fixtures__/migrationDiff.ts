/**
 * Shared fixture for `lib/migration.test.ts` (spec 07 §8 AC20) and
 * `FipMigrate.test.ts`: a small `gofair-fip-mini`-shaped pair mirroring
 * AC11's scenario (one `en` text edited, one question added, one deleted,
 * one hidden, one answered question split) — kept self-contained here
 * rather than fetched from the backend fixtures, since spec 07's backend
 * half is implemented separately; a real shared fixture can replace this
 * once both sides exist.
 */
import type { Answer, KnowledgeModelContent } from '@/types/api'

export const oldContent: KnowledgeModelContent = {
  id: 'gofair-fip-mini',
  version: '1.0.0',
  status: 'published',
  license: 'CC0-1.0',
  title: { en: 'GO FAIR FIP mini-questionnaire' },
  description: { en: 'Fixture model' },
  changelog: [],
  sections: [
    {
      id: 'F',
      title: { en: 'Findable' },
      questions: [
        {
          id: 'F1',
          principle: 'F1',
          scope: null,
          text: { en: 'Metadata is registered or indexed.' },
          help: null,
          ferType: 'identifier-service',
          required: true,
          allowMultiple: false,
        },
        {
          id: 'F2',
          principle: 'F2',
          scope: null,
          text: { en: 'Rich metadata is provided.' },
          help: null,
          ferType: 'metadata-repository',
          required: true,
          allowMultiple: false,
        },
        {
          id: 'F3',
          principle: 'F3',
          scope: null,
          text: { en: 'A globally unique identifier is included.' },
          help: null,
          ferType: null,
          required: false,
          allowMultiple: false,
        },
      ],
    },
    {
      id: 'A',
      title: { en: 'Accessible' },
      questions: [
        {
          id: 'A2',
          principle: 'A2',
          scope: null,
          text: { en: 'The access protocol is open, free and universally implementable.' },
          help: null,
          ferType: 'repository',
          required: false,
          allowMultiple: false,
        },
      ],
    },
  ],
}

export const newContent: KnowledgeModelContent = {
  id: 'gofair-fip-mini',
  version: '1.1.0',
  status: 'published',
  license: 'CC0-1.0',
  title: { en: 'GO FAIR FIP mini-questionnaire' },
  description: { en: 'Fixture model' },
  changelog: [{ version: '1.1.0', date: '2026-11-02', notes: 'Split F2, hide F3, drop A2, add R1.3-data.' }],
  sections: [
    {
      id: 'F',
      title: { en: 'Findable' },
      questions: [
        {
          id: 'F1',
          principle: 'F1',
          scope: null,
          // whitespace-only-normalised difference is not enough to flag; this is a real wording change.
          text: { en: 'Metadata is registered or indexed in a searchable resource.' },
          help: null,
          ferType: 'identifier-service',
          required: true,
          allowMultiple: false,
        },
        {
          id: 'F2-metadata',
          principle: 'F2',
          scope: 'metadata',
          text: { en: 'Rich metadata is provided (metadata).' },
          help: null,
          ferType: 'metadata-repository',
          required: true,
          allowMultiple: false,
        },
        {
          id: 'F2-data',
          principle: 'F2',
          scope: 'data',
          text: { en: 'Rich metadata is provided (data).' },
          help: null,
          ferType: 'metadata-repository',
          required: true,
          allowMultiple: false,
        },
        {
          id: 'F3',
          principle: 'F3',
          scope: null,
          text: { en: 'A globally unique identifier is included.' },
          help: null,
          ferType: null,
          required: false,
          allowMultiple: false,
          hidden: true,
        },
      ],
    },
    {
      id: 'R',
      title: { en: 'Reusable' },
      questions: [
        {
          id: 'R1.3-data',
          principle: 'R1.3',
          scope: 'data',
          text: { en: 'Detailed provenance is provided (data).' },
          help: null,
          ferType: null,
          required: false,
          allowMultiple: false,
        },
      ],
    },
  ],
}

/** F1, F2 and F3 answered; A2 answered (and removed in `newContent`); R1.3-data left unanswered. */
export const answers: Answer[] = [
  { questionId: 'F1', declarations: [{ status: 'current', ferFreeText: 'ORCID' }], comment: null },
  { questionId: 'F2', declarations: [{ status: 'current', ferFreeText: 'Zenodo' }], comment: null },
  { questionId: 'F3', declarations: [{ status: 'planned', ferFreeText: 'DataCite' }], comment: null },
  { questionId: 'A2', declarations: [{ status: 'current', ferFreeText: 'REST API' }], comment: null },
]
