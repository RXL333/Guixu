import { describe, expect, it } from 'vitest'
import { parseMarkdown, type InlineNode } from './markdown'

/** Concatenate only the literal text of a node list, ignoring nested emphasis. */
function plain(nodes: InlineNode[]): string {
  return nodes.map(node => ('text' in node ? node.text : '')).join('')
}

describe('parseMarkdown', () => {
  it('renders headings-free replies as paragraphs, lists and code', () => {
    const blocks = parseMarkdown('可以这样分类：\n\n- 建筑\n- 截图\n\n1. 先建目录\n2. 再移动')
    expect(blocks.map(block => block.kind)).toEqual(['paragraph', 'list', 'list'])
    const [list, ordered] = blocks.slice(1)
    expect(list.kind === 'list' && list.ordered).toBe(false)
    expect(ordered.kind === 'list' && ordered.ordered).toBe(true)
    expect(ordered.kind === 'list' && ordered.items).toHaveLength(2)
  })

  it('keeps fenced code verbatim', () => {
    const blocks = parseMarkdown('示例：\n```python\nprint("**不是加粗**")\n```')
    expect(blocks).toHaveLength(2)
    const code = blocks[1]!
    expect(code.kind).toBe('code')
    expect(code.kind === 'code' && code.text).toBe('print("**不是加粗**")')
    expect(code.kind === 'code' && code.language).toBe('python')
  })

  it('parses emphasis and inline code around CJK text', () => {
    const blocks = parseMarkdown('这是**重点**，用 `report_only` 模式。')
    expect(blocks).toHaveLength(1)
    const children = blocks[0]!.kind === 'paragraph' ? blocks[0]!.children : []
    const strong = children.find(node => node.kind === 'strong')
    expect(strong && strong.kind === 'strong' ? plain(strong.children) : '').toBe('重点')
    expect(children.some(node => node.kind === 'code' && node.text === 'report_only')).toBe(true)
  })

  it('never turns an underscore inside a filename into emphasis', () => {
    const blocks = parseMarkdown('请移动 my_photo_final.jpg 和 snake_case_name 到照片目录')
    const children = blocks[0]!.kind === 'paragraph' ? blocks[0]!.children : []
    expect(children.some(node => node.kind === 'em')).toBe(false)
    expect(plain(children)).toContain('my_photo_final.jpg')
  })

  it('leaves unterminated markers as literal text', () => {
    const blocks = parseMarkdown('未闭合的 **加粗')
    const children = blocks[0]!.kind === 'paragraph' ? blocks[0]!.children : []
    expect(children.some(node => node.kind === 'strong')).toBe(false)
    expect(plain(children)).toContain('**加粗')
  })

  it('only links http and https targets', () => {
    const safe = parseMarkdown('见 [文档](https://example.com/a)')
    const link = safe[0]!.kind === 'paragraph' ? safe[0]!.children.find(node => node.kind === 'link') : undefined
    expect(link).toMatchObject({ kind: 'link', href: 'https://example.com/a', text: '文档' })

    for (const hostile of ['[点我](javascript:alert(1))', '[点我](data:text/html;base64,PHN2Zz4=)', '[点我](/local/path)']) {
      const blocks = parseMarkdown(hostile)
      const children = blocks[0]!.kind === 'paragraph' ? blocks[0]!.children : []
      expect(children.some(node => node.kind === 'link')).toBe(false)
      expect(plain(children)).toBe(hostile)
    }
  })

  it('keeps raw HTML as the literal characters the model typed', () => {
    const hostile = '<script>alert(1)</script> 和 <img src=x onerror="alert(2)">'
    const blocks = parseMarkdown(hostile)
    const children = blocks[0]!.kind === 'paragraph' ? blocks[0]!.children : []
    expect(children.every(node => node.kind === 'text')).toBe(true)
    expect(plain(children)).toBe(hostile)
  })

  it('does not mistake a year for an ordered list marker', () => {
    const blocks = parseMarkdown('2024. 年度总结')
    expect(blocks).toHaveLength(1)
    expect(blocks[0]!.kind).toBe('paragraph')
  })

  it('returns no blocks for empty content', () => {
    expect(parseMarkdown('')).toEqual([])
  })
})
