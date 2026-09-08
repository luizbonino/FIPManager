import { get } from './client'
import type { FerType, ListOut } from '@/types/api'

/** `GET /api/fer-types` (spec 02 §5.2) — the FER-type chip label source. */
export function getFerTypes() {
  return get<ListOut<FerType>>('/fer-types')
}
