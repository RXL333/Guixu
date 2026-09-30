/**
 * A deliberately tiny Markdown subset for model replies.
 *
 * Model output is untrusted text, so nothing here ever produces HTML. The parser
 * returns a structured tree that templates render with ordinary Vue bindings, which
 * makes injection structurally impossible rather than dependent on a sanitiser's
 * allow-list staying correct. Raw tags such as `<script>` therefore survive as the
 * literal characters the model typed.
 *
 * Supported: fenced code blocks, bullet and numbered lists, paragraphs, `**bold**`,
 * `*italic*`/`_italic_`, `` `code` `` and http(s) links. Anything else stays literal.
 */

export type InlineNode =
  | { kind: 'text'; text: string }
  | { kind: 'code'; text: string }
  | { kind: 'strong'; children: InlineNode[] }
  | { kind: 'em'; children: InlineNode[] }
  | { kind: 'link'; href: string; text: string }

export type BlockNode =
  | { kind: 'paragraph'; children: InlineNode[] }
  | { kind: 'list'; ordered: boolean; items: InlineNode[][] }
  | { kind: 'code'; language: string; text: string }

const SAFE_LINK = /^https?:\/\//i
const FENCE = /^\s*```/
const BULLET = /^\s*[-*+]\s+(.*)$/
// Two digits at most, so a line like "2024. 年度总结" stays part of its paragraph.
const ORDERED = /^\s*\d{1,2}[.)]\s+(.*)$/
const LINK = /^\[([^\]\n]*)\]\(([^)\s]+)\)/

function isWordCharacter(char: string | undefined): boolean {
  return char !== undefined && /[A-Za-z0-9_]/.test(char)
}

/** Emphasis must not split an identifier: `snake_case_name` has to stay literal. */
function hasBoundary(before: string | undefined, after: string | undefined): boolean {
  return !isWordCharacter(before) && !isWordCharacter(after)
}

function parseInline(source: string, depth = 0): InlineNode[] {
  const nodes: InlineNode[] = []
  let text = ''
  const flush = () => {
    if (text) {
      nodes.push({ kind: 'text', text })
      text = ''
    }
  }
  let index = 0
  while (index < source.length) {
    const char = source[index]

    if (char === '`') {
      const close = source.indexOf('`', index + 1)
      if (close !== -1) {
        flush()
        nodes.push({ kind: 'code', text: source.slice(index + 1, close) })
        index = close + 1
        continue
      }
    }

    if (source.startsWith('**', index)) {
      const close = source.indexOf('**', index + 2)
      if (close !== -1 && close > index + 2 && hasBoundary(source[index - 1], source[close + 2])) {
        const inner = source.slice(index + 2, close)
        flush()
        nodes.push({ kind: 'strong', children: depth < 2 ? parseInline(inner, depth + 1) : [{ kind: 'text', text: inner }] })
        index = close + 2
        continue
      }
    }

    if ((char === '*' || char === '_') && hasBoundary(source[index - 1], source[index + 1])) {
      const close = source.indexOf(char, index + 1)
      if (close > index + 1) {
        const inner = source.slice(index + 1, close)
        flush()
        nodes.push({ kind: 'em', children: depth < 2 ? parseInline(inner, depth + 1) : [{ kind: 'text', text: inner }] })
        index = close + 1
        continue
      }
    }

    if (char === '[') {
      const match = LINK.exec(source.slice(index))
      // Anything that is not http(s) — `javascript:`, `data:`, relative paths — is
      // dropped as a link and kept as the text the model actually typed.
      if (match && SAFE_LINK.test(match[2]!)) {
        flush()
        nodes.push({ kind: 'link', href: match[2]!, text: match[1] || match[2]! })
        index += match[0].length
        continue
      }
    }

    text += char
    index += 1
  }
  flush()
  return nodes
}

export function parseMarkdown(source: string): BlockNode[] {
  const lines = source.replace(/\r\n/g, '\n').split('\n')
  const blocks: BlockNode[] = []
  let index = 0
  while (index < lines.length) {
    const line = lines[index]!

    if (FENCE.test(line)) {
      const language = line.replace(/^\s*```/, '').trim()
      const body: string[] = []
      index += 1
      while (index < lines.length && !FENCE.test(lines[index]!)) {
        body.push(lines[index]!)
        index += 1
      }
      index += 1
      blocks.push({ kind: 'code', language, text: body.join('\n') })
      continue
    }

    const bullet = BULLET.exec(line)
    const ordered = ORDERED.exec(line)
    if (bullet || ordered) {
      const isOrdered = Boolean(ordered)
      const matcher = isOrdered ? ORDERED : BULLET
      const items: InlineNode[][] = []
      while (index < lines.length) {
        const item = matcher.exec(lines[index]!)
        if (!item) break
        items.push(parseInline(item[1]!))
        index += 1
      }
      blocks.push({ kind: 'list', ordered: isOrdered, items })
      continue
    }

    if (!line.trim()) {
      index += 1
      continue
    }

    const paragraph: string[] = []
    while (index < lines.length && lines[index]!.trim() && !FENCE.test(lines[index]!)) {
      const candidate = lines[index]!
      if (paragraph.length && (BULLET.test(candidate) || ORDERED.test(candidate))) break
      paragraph.push(candidate.trim())
      index += 1
    }
    blocks.push({ kind: 'paragraph', children: parseInline(paragraph.join('\n')) })
  }
  return blocks
}
