import { cleanup, fireEvent, render, waitFor } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

const model = {
  id: 'model-1', name: '本地测试连接', provider: 'qwen_local', runtime: 'openai_compatible',
  base_url: 'http://127.0.0.1:8000/v1', model_id: 'qwen-test', trust_scope: 'loopback',
  options: {}, enabled: true, revision: 3, has_secret: false, capabilities: {},
}

const mocks = vi.hoisted(() => ({
  models: vi.fn(),
  deleteModel: vi.fn(),
  createModel: vi.fn(),
  saveModelSecret: vi.fn(),
  probeModel: vi.fn(),
}))

vi.mock('../src/services/api', () => ({ api: mocks }))

import ModelsPage from '../src/pages/ModelsPage.vue'

afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('model connection deletion', () => {
  it('requires confirmation, sends the current revision, then removes the card', async () => {
    mocks.models.mockResolvedValueOnce([model]).mockResolvedValueOnce([])
    mocks.deleteModel.mockResolvedValue({ disabled: true })
    const view = render(ModelsPage)
    await view.findByText('本地测试连接')

    await fireEvent.click(view.getByRole('button', { name: '删除连接' }))
    expect(view.getByText('既有任务的审计引用仍会保留。', { exact: false })).toBeTruthy()
    await fireEvent.click(view.getByRole('button', { name: '确认删除' }))

    await waitFor(() => expect(mocks.deleteModel).toHaveBeenCalledWith('model-1', 3))
    await waitFor(() => expect(view.queryByText('本地测试连接')).toBeNull())
  })
})
