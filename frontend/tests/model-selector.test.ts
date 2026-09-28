import { cleanup, fireEvent, render, waitFor } from '@testing-library/vue'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ConversationHeader from '../src/features/conversations/components/ConversationHeader.vue'
import { useConversationStore } from '../src/features/conversations/store'
import { api } from '../src/services/api'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('conversation model selector', () => {
  it('refreshes a cached model list and lets a verified local model be selected', async () => {
    const pinia = createPinia()
    const store = useConversationStore(pinia)
    const conversation = { id: 'c1', title: '照片整理', status: 'ACTIVE', model_profile_id: 'deepseek' } as any
    store.currentConversation = conversation
    store.models = [{ id: 'deepseek', name: 'DeepSeek 云端', provider: 'deepseek', model_id: 'deepseek-flash' }] as any
    vi.spyOn(api, 'models').mockResolvedValue([
      ...store.models,
      { id: 'qwen', name: '本地千问', provider: 'qwen_local', model_id: 'qwen3-vl:4b-instruct' },
    ] as any)
    vi.spyOn(api, 'updateConversationModel').mockResolvedValue({
      ...conversation, model_profile_id: 'qwen', context: { model_profile_id: 'qwen' },
    } as any)
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/models', component: { template: '<div />' } }] })
    await router.push('/models')
    await router.isReady()
    const view = render(ConversationHeader, { props: { conversation }, global: { plugins: [pinia, router] } })

    await fireEvent.click(view.getByRole('button', { name: /DeepSeek 云端/ }))
    await waitFor(() => expect(view.getByRole('button', { name: /本地千问/ })).toBeTruthy())
    await fireEvent.click(view.getByRole('button', { name: /本地千问/ }))
    await waitFor(() => expect(api.updateConversationModel).toHaveBeenCalledWith('c1', 'qwen'))
    expect(store.currentConversation?.model_profile_id).toBe('qwen')
  })
})
