import { cleanup, fireEvent, render, waitFor } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import FileWorkspace from '../src/features/conversations/components/FileWorkspace.vue'
import ChatComposer from '../src/features/conversations/components/ChatComposer.vue'
import { useConversationStore } from '../src/features/conversations/store'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('Phase M workspace interactions', () => {
  it('windows 5000 files and keeps the last file searchable and selectable', async () => {
    const pinia = createPinia()
    const store = useConversationStore(pinia)
    store.files = Array.from({ length: 5000 }, (_, index) => ({ id: `cf${index}`, conversation_id: 'c', file_id: `f${index}`, first_seen_path: `D:/测试/照片-${index}.jpg`, current_known_path: `D:/测试/照片-${index}.jpg`, added_at: '2026-09-22', state: 'ACTIVE' })) as any
    const view = render(FileWorkspace, { props: { plans: [], executions: [] }, global: { plugins: [pinia] } })
    expect(view.container.querySelectorAll('.file-item').length).toBeLessThanOrEqual(48)
    await fireEvent.update(view.getByRole('searchbox', { name: '搜索文件' }), '照片-4999')
    await fireEvent.click(view.getByRole('button', { name: /照片-4999/ }))
    expect(store.selectedFileIds).toEqual(['f4999'])
    expect(view.getByRole('button', { name: /照片-4999/ }).getAttribute('aria-pressed')).toBe('true')
    await fireEvent.click(view.getByRole('button', { name: '网格视图' }))
    expect(view.container.querySelectorAll('.file-item').length).toBe(1)
  })

  it('does not send while Chinese input is composing or when Shift+Enter is pressed', async () => {
    const pinia = createPinia()
    const store = useConversationStore(pinia)
    const send = vi.spyOn(store, 'appendMessage').mockResolvedValue(true)
    const view = render(ChatComposer, { global: { plugins: [pinia] } })
    const input = view.getByRole('textbox', { name: '整理要求' })
    await fireEvent.update(input, '整理照片')
    await fireEvent.keyDown(input, { key: 'Enter', isComposing: true })
    await fireEvent.keyDown(input, { key: 'Enter', shiftKey: true })
    expect(send).not.toHaveBeenCalled()
    await fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(send).toHaveBeenCalledWith('整理照片'))
  })

  it('opens file references from the composer without writing a message', async () => {
    const view = render(ChatComposer, { global: { plugins: [createPinia()] } })
    await fireEvent.click(view.getByRole('button', { name: '添加文件引用' }))
    expect(view.emitted('references')).toHaveLength(1)
  })
})
