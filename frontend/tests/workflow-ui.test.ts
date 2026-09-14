import { cleanup, fireEvent, render } from '@testing-library/vue'
import { afterEach, describe, expect, it } from 'vitest'
import TaskStepper from '../src/components/TaskStepper.vue'
import EvidenceDrawer from '../src/components/EvidenceDrawer.vue'
import { router } from '../src/router'

afterEach(cleanup)

describe('phase 06 UI safety contract', () => {
  it('UI04 exposes named task phases to assistive technology', () => {
    const view = render(TaskStepper, { props: { current: 3 } })
    expect(view.getByRole('navigation', { name: '任务阶段' })).toBeTruthy()
    expect(view.getByText('审阅').getAttribute('aria-current')).toBe('step')
  })

  it('UI09 renders evidence as text rather than trusted HTML', () => {
    const detail = {
      file: { id:'f', scope_id:'s', basename:'<img src=x onerror=alert(1)>', relative_path:'x', extension:'.txt', modality:'text', size_bytes:1, scan_status:'eligible', exclusion_code:null, scope_name:'root', metadata:{type_evidence:'x'} },
      profile: { file_id:'f', modality:'text', document_kind:null, metadata:{}, content_summary:'', evidence:[{id:'e',kind:'extracted_text',text:'<script>window.pwned=true</script>',locator:{paragraph:1},quality:'high',origin:'test'}],coverage:{mode:'full',total_pages:null,sampled_pages:[],total_duration_sec:null,truncated:false},warnings:[],capabilities_used:[],parser_version:'test' },
      suggestion:null, latest_review:null,
    }
    const view = render(EvidenceDrawer, { props: { detail } })
    expect(view.container.querySelector('script')).toBeNull()
    expect(view.container.querySelector('img')).toBeNull()
    expect(view.getByText('<script>window.pwned=true</script>')).toBeTruthy()
  })

  it('UI07 closes the evidence drawer with Escape', async () => {
    const detail = {
      file: { id:'f', scope_id:'s', basename:'notes.txt', relative_path:'notes.txt', extension:'.txt', modality:'text', size_bytes:1, scan_status:'eligible', exclusion_code:null, scope_name:'root', metadata:{type_evidence:'extension'} },
      profile:null, suggestion:null, latest_review:null,
    }
    const view = render(EvidenceDrawer, { props: { detail } })
    await fireEvent.keyDown(window, { key: 'Escape' })
    expect(view.emitted().close).toHaveLength(1)
  })

  it('UI08 has real routes for every required task and navigation view', () => {
    const paths = new Set(router.getRoutes().map(route => route.path))
    for (const path of ['/','/tasks/new','/tasks/:id/analyze','/tasks/:id/taxonomy','/tasks/:id/review','/tasks/:id/run','/tasks/:id/report','/templates','/rules','/history','/models','/settings']) expect(paths.has(path)).toBe(true)
  })

  it('UI03 distinguishes current page from all filtered results', async () => {
    const source = await import('../src/pages/TaskReviewPage.vue?raw')
    expect(source.default).toContain('全选当前页')
    expect(source.default).toContain('全选筛选结果')
    expect(source.default).toContain('offset<total.value')
    expect(source.default).toContain('api.files(task.value.id,500,offset')
  })

  it('UI10 binds dangerous execution to acknowledgement and plan hash', async () => {
    const source = await import('../src/pages/TaskRunPage.vue?raw')
    expect(source.default).toContain('我已核对目标与计划 hash')
    expect(source.default).toContain(':disabled="!ack||busy"')
    expect(source.default).toContain('approvePlan')
  })

  it('UI05 names budget and connection degradation states', async () => {
    const [models, analysis] = await Promise.all([import('../src/pages/ModelsPage.vue?raw'), import('../src/pages/TaskScanPage.vue?raw')])
    expect(models.default).toContain('unavailable')
    expect(analysis.default).toContain('原文件未改变')
  })

  it('model connections expose a confirmed delete action', async () => {
    const [page, service] = await Promise.all([import('../src/pages/ModelsPage.vue?raw'), import('../src/services/api.ts?raw')])
    expect(page.default).toContain('删除连接')
    expect(page.default).toContain('确认删除')
    expect(page.default).toContain('既有任务的审计引用仍会保留')
    expect(service.default).toContain("method: 'DELETE'")
  })

  it('execution latches duplicate clicks and refreshes the task revision', async () => {
    const page = await import('../src/pages/TaskRunPage.vue?raw')
    expect(page.default).toContain('if(busy.value||')
    expect(page.default).toContain('const current=await api.task')
  })
})
