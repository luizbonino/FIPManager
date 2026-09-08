import qrcode from 'qrcode-generator'

export interface QrSvgOptions {
  /** Rendered size in px (both width and height); default 256. */
  size?: number
  /** Quiet-zone width, in modules; default 2. */
  margin?: number
  /** Default 'M', matching `qrcode-generator`'s own default. */
  errorCorrectionLevel?: 'L' | 'M' | 'Q' | 'H'
  /** Module fill colour; default '#000'. */
  darkColor?: string
  /** Background colour; default '#fff'. */
  lightColor?: string
}

/**
 * Render `text` as a QR code and return it as an inline `<svg>` string of
 * `<rect>`s (spec 02 §2.4): scales crisply, prints, no canvas, no server
 * round trip. Wrapped by `components/QrCode.vue`.
 */
export function qrCodeSvg(text: string, options: QrSvgOptions = {}): string {
  const {
    size = 256,
    margin = 2,
    errorCorrectionLevel = 'M',
    darkColor = '#000',
    lightColor = '#fff',
  } = options

  // typeNumber 0 = auto-detect the smallest QR version that fits `text`.
  const qr = qrcode(0, errorCorrectionLevel)
  qr.addData(text)
  qr.make()

  const moduleCount = qr.getModuleCount()
  const totalModules = moduleCount + margin * 2
  const cell = size / totalModules

  let rects = ''
  for (let row = 0; row < moduleCount; row++) {
    for (let col = 0; col < moduleCount; col++) {
      if (qr.isDark(row, col)) {
        const x = (col + margin) * cell
        const y = (row + margin) * cell
        rects += `<rect x="${x}" y="${y}" width="${cell}" height="${cell}"/>`
      }
    }
  }

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" ` +
    `width="${size}" height="${size}" shape-rendering="crispEdges" role="img">` +
    `<rect width="${size}" height="${size}" fill="${lightColor}"/>` +
    `<g fill="${darkColor}">${rects}</g>` +
    `</svg>`
  )
}
