import { cleanup, fireEvent, render, waitFor } from '@testing-library/vue'
import { h } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

const model = {
  id: 'model-1', name: '本地测试连接', provider: 'qwen_local', runtime: 'openai_compatible',
  base_url: 'http://127.0.0.1:8000/v1', model_id: 'qwen-test', trust_scope: 'loopback',
  options: {}, enabled: true, revision: 3, has_secret: false, capabilities: {},
}

// The page links to the conversations route. Without a router installed, Vue logs a
// "Failed to resolve component: RouterLink" warning on every render, which buries real
// warnings in the test output; stub it so the suite stays quiet.
const renderOptions = { global: { stubs: { RouterLink: () => h('a') } } }

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
    const view = render(ModelsPage, renderOptions)
    await view.findByText('本地测试连接')

    await fireEvent.click(view.getByRole('button', { name: '删除连接' }))
    expect(view.getByText('既有任务的审计引用仍会保留。', { exact: false })).toBeTruthy()
    await fireEvent.click(view.getByRole('button', { name: '确认删除' }))

    await waitFor(() => expect(mocks.deleteModel).toHaveBeenCalledWith('model-1', 3))
    await waitFor(() => expect(view.queryByText('本地测试连接')).toBeNull())
  })

  it('shows verified text and vision states plus a concrete probe error', async () => {
    mocks.models.mockResolvedValueOnce([{
      ...model,
      capabilities: {
        text: { status: 'supported', message: 'ok', tested_at: '2026-09-19T00:00:00Z', verified: true },
        vision: { status: 'error', message: 'MODEL_REQUEST_REJECTED', tested_at: '2026-09-19T00:00:00Z',
          verified: false, probe_error: 'MODEL_REQUEST_REJECTED: invalid_request_error: unsupported image' },
      },
    }])
    const view = render(ModelsPage, renderOptions)
    await view.findByText('文本：', { exact: false })
    expect(view.getByText((_, element) => element?.tagName === 'P' && element.textContent === '文本：已验证')).toBeTruthy()
    expect(view.getByText((_, element) => element?.tagName === 'P' && element.textContent === '视觉：失败')).toBeTruthy()
    expect(view.getByText((_, element) => element?.tagName === 'P' && element.textContent === '视觉失败原因：MODEL_REQUEST_REJECTED: invalid_request_error: unsupported image')).toBeTruthy()
  })

  it('shows vision as verified after a successful persisted probe', async () => {
    mocks.models.mockResolvedValueOnce([{
      ...model,
      capabilities: {
        text: { status: 'supported', message: 'ok', tested_at: '2026-09-19T00:00:00Z', verified: true },
        vision: { status: 'supported', message: 'ok', tested_at: '2026-09-19T00:00:00Z', verified: true,
          vision: true, vision_verified: true, probe_status: 'success', probe_error: null },
      },
    }])
    const view = render(ModelsPage, renderOptions)
    expect(await view.findByText((_, element) => element?.tagName === 'P' && element.textContent === '视觉：已验证')).toBeTruthy()
    expect(view.queryByText('视觉失败原因：', { exact: false })).toBeNull()
  })
})
