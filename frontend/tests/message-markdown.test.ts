import { cleanup, render } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ConversationMessage from '../src/features/conversations/components/ConversationMessage.vue'

afterEach(() => cleanup())

function reply(content: string) {
  return render(ConversationMessage, {
    props: {
      message: {
        id: 'm1', conversation_id: 'c1', role: 'ASSISTANT', message_type: 'TEXT',
        sequence_number: 1, status: 'ACTIVE',
        content, created_at: '2026-09-29T10:00:00Z', referenced_file_ids: [], metadata: {},
      },
    },
  })
}

describe('model replies render as structured content, never as markup', () => {
  it('formats a normal reply so the markers are no longer visible', () => {
    const view = reply('好的，按 **建筑** 分目录：\n\n- 建筑\n- 截图')
    const body = view.container.querySelector('.message-content')!
    expect(body.querySelector('strong')?.textContent).toBe('建筑')
    expect(body.querySelectorAll('ul li')).toHaveLength(2)
    expect(view.container.textContent).not.toContain('**')
  })

  it('keeps a hostile reply as text and creates no elements from it', () => {
    const view = reply('<script>window.pwned = true</script><img src=x onerror="window.pwned = true">')
    expect(view.container.querySelector('script')).toBeNull()
    expect(view.container.querySelector('img')).toBeNull()
    expect((window as unknown as { pwned?: boolean }).pwned).toBeUndefined()
    expect(view.container.textContent).toContain('<script>')
  })

  it('never emits a javascript: or data: hyperlink', () => {
    const view = reply('[点我](javascript:window.pwned=true) 和 [图](data:text/html,<script>1</script>)')
    expect(view.container.querySelector('a')).toBeNull()
    expect((window as unknown as { pwned?: boolean }).pwned).toBeUndefined()
  })

  it('links safe http targets with noopener', () => {
    const view = reply('见 [文档](https://example.com/a)')
    const anchor = view.container.querySelector('a')!
    expect(anchor.getAttribute('href')).toBe('https://example.com/a')
    expect(anchor.getAttribute('rel')).toBe('noopener noreferrer')
  })

  it('preserves the raw text for the copy button', async () => {
    const source = '**建筑** 与 <script>x</script>'
    const view = reply(source)
    const button = view.container.querySelector('.message-copy-button') as HTMLButtonElement
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    button.click()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(writeText).toHaveBeenCalledWith(source)
  })
})
