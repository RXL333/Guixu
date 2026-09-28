import { cleanup, fireEvent, render, waitFor } from '@testing-library/vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TaskStepper from '../src/components/TaskStepper.vue'
import EvidenceDrawer from '../src/components/EvidenceDrawer.vue'
import HistoryPage from '../src/pages/HistoryPage.vue'
import { api } from '../src/services/api'
import * as dialogs from '../src/components/dialogState'
import { router } from '../src/router'

afterEach(() => { cleanup(); vi.restoreAllMocks() })
beforeEach(() => { vi.spyOn(api, 'conversations').mockResolvedValue([]) })

describe('phase 06 UI safety contract', () => {
  it('UI04 exposes named task phases to assistive technology', () => {
    const view = render(TaskStepper, { props: { current: 3 } })
    expect(view.getByRole('navigation', { name: '任务阶段' })).toBeTruthy()
    expect(view.getByText('审阅').getAttribute('aria-current')).toBe('step')
  })

  it('UI09 renders evidence as text rather than trusted HTML', () => {
    const detail = {
      file: { id:'f', scope_id:'s', basename:'<img src=x onerror=alert(1)>', relative_path:'x', extension:'.txt', modality:'text', size_bytes:1, scan_status:'eligible', exclusion_code:null, scope_name:'root', metadata:{type_evidence:'x'} },
      profile: { file_id:'f', source_path:'C:/fixture/notes.txt', name:'notes.txt', extension:'.txt', mime_type:'text/plain', modality:'text', document_kind:null, metadata:{}, content_summary:'', evidence:[{id:'e',kind:'extracted_text',text:'<script>window.pwned=true</script>',locator:{paragraph:1},quality:'high',origin:'test'}],coverage:{mode:'full',total_pages:null,sampled_pages:[],total_duration_sec:null,truncated:false},warnings:[],capabilities_used:[],parser_version:'test',parser_status:'ready' as const,parser_warnings:[] },
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
    for (const path of ['/','/tasks/new','/tasks/:id/analyze','/tasks/:id/taxonomy','/tasks/:id/review','/tasks/:id/run','/tasks/:id/report','/templates','/history','/trash','/models','/settings']) expect(paths.has(path)).toBe(true)
    expect(paths.has('/rules')).toBe(false)
    expect(router.getRoutes().find(route=>route.path==='/templates')?.redirect).toBe('/')
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
    expect(models.default).toContain('添加模型连接后')
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
    expect(page.default).toContain('const verified=await api.plan')
    expect(page.default).toContain('verified.plan_hash!==original.hash')
    expect(page.default).toContain('PLAN_NOT_APPROVED')
    expect(page.default).toContain('PLAN_HASH_MISMATCH')
  })

  it('new organization is a single AI-only flow without legacy modes', async () => {
    const task = await import('../src/pages/NewTaskPage.vue?raw')
    expect(task.default).toContain('开始一次 AI 整理')
    expect(task.default).toContain('告诉 AI 你希望怎样整理这些文件')
    expect(task.default).toContain('需要选择 AI 模型')
    expect(task.default).toContain('最大目录深度')
    expect(task.default).toContain('分析强度')
    expect(task.default).toContain('预览确认后移动')
    expect(task.default).toContain('acknowledgeAI')
    for (const legacy of ['template_key','fixed_tree','fixed_categories','direct_move','分类模板']) expect(task.default).not.toContain(legacy)
  })

  it('taxonomy review supports edits before AI file classification', async () => {
    const page = await import('../src/pages/TaskTaxonomyPage.vue?raw')
    expect(page.default).toContain('编辑分类树')
    expect(page.default).toContain('新增类别')
    expect(page.default).toContain('updateTaxonomy')
    expect(page.default).toContain('批准分类树并开始 AI 分类')
  })

  it('deletes one task only after explicit disk-safe confirmation', async () => {
    const item = {id:'t1',name:'测试任务',status:'FAILED',phase:'REPORT',revision:1,settings:{},counters:{discovered:2},created_at:'now',updated_at:'now'} as any
    vi.spyOn(api,'tasks').mockResolvedValueOnce({items:[item]}).mockResolvedValueOnce({items:[]})
    const remove=vi.spyOn(api,'deleteTask').mockResolvedValue({...item,deleted_at:'now'})
    vi.spyOn(dialogs,'confirmAction').mockResolvedValue(true)
    await router.push('/history');await router.isReady()
    const view=render(HistoryPage,{global:{plugins:[router]}})
    await view.findByText('测试任务')
    await fireEvent.click(view.getByRole('button',{name:'测试任务 更多操作'}))
    await fireEvent.click(view.getByRole('button',{name:/删除任务/}))
    await waitFor(()=>expect(remove).toHaveBeenCalledWith('t1',1))
    expect(dialogs.confirmAction).toHaveBeenCalledWith(expect.stringContaining('不会删除或移动磁盘上的文件'))
  })

  it('supports filtered batch selection and batch delete', async () => {
    const items=['a','b'].map(id=>({id,name:`任务${id}`,status:'FAILED',phase:'REPORT',revision:1,settings:{},counters:{},created_at:'now',updated_at:'now'})) as any
    vi.spyOn(api,'tasks').mockResolvedValueOnce({items}).mockResolvedValueOnce({items:[]})
    const remove=vi.spyOn(api,'batchDeleteTasks').mockResolvedValue({items:[],deleted:2})
    vi.spyOn(dialogs,'confirmAction').mockResolvedValue(true)
    await router.push('/history');const view=render(HistoryPage,{global:{plugins:[router]}});await view.findByText('任务a')
    await fireEvent.click(view.getByRole('button',{name:'选择全部当前筛选结果'}))
    await fireEvent.click(view.getByRole('button',{name:'批量删除'}))
    await waitFor(()=>expect(remove).toHaveBeenCalledWith(['a','b']))
  })

  it('recently deleted tasks can be restored and running deletion is disabled', async () => {
    const deleted={id:'d',name:'已删除',status:'FAILED',phase:'REPORT',revision:2,settings:{},counters:{},created_at:'now',updated_at:'now',deleted_at:'now'} as any
    vi.spyOn(api,'tasks').mockResolvedValueOnce({items:[deleted]}).mockResolvedValueOnce({items:[]})
    const restore=vi.spyOn(api,'restoreTask').mockResolvedValue({...deleted,deleted_at:null})
    await router.push('/trash');const view=render(HistoryPage,{global:{plugins:[router]}});await view.findByText('已删除')
    await fireEvent.click(view.getByRole('button',{name:'已删除 更多操作'}));await fireEvent.click(view.getByRole('button',{name:'恢复'}))
    await waitFor(()=>expect(restore).toHaveBeenCalledWith('d',2))
    const source=await import('../src/pages/HistoryPage.vue?raw')
    expect(source.default).toContain("['RUNNING','PAUSE_REQUESTED','RECOVERY_REQUIRED']")
    expect(source.default).toContain(':disabled="!deletedView&&blocked(item)"')
  })

  it('recently deleted tasks support guarded batch permanent deletion', async () => {
    const items=['x','y'].map(id=>({id,name:`删除${id}`,status:'FAILED',phase:'REPORT',revision:2,settings:{},counters:{},created_at:'now',updated_at:'now',deleted_at:'now'})) as any
    vi.spyOn(api,'tasks').mockResolvedValueOnce({items}).mockResolvedValueOnce({items:[]})
    const purge=vi.spyOn(api,'batchPermanentlyDeleteTasks').mockResolvedValue({permanently_deleted:2,disk_files_changed:false})
    vi.spyOn(dialogs,'confirmAction').mockResolvedValue(true)
    await router.push('/trash');const view=render(HistoryPage,{global:{plugins:[router]}});await view.findByText('删除x')
    await fireEvent.click(view.getByRole('button',{name:'选择全部当前筛选结果'}))
    await fireEvent.click(view.getByRole('button',{name:'批量永久删除'}))
    await waitFor(()=>expect(purge).toHaveBeenCalledWith(['x','y']))
    expect(dialogs.confirmAction).toHaveBeenCalledWith(expect.stringContaining('不会删除磁盘上的文件'))
  })

  it('clears recent deletion while reporting retained safety records', async () => {
    const item={id:'old',name:'旧任务',status:'COMPLETED',phase:'REPORT',revision:2,settings:{},counters:{},created_at:'now',updated_at:'now',deleted_at:'now'} as any
    vi.spyOn(api,'tasks').mockResolvedValueOnce({items:[item]}).mockResolvedValueOnce({items:[]})
    const clear=vi.spyOn(api,'clearTrash').mockResolvedValue({permanently_deleted_tasks:0,retained_safety_records:1,permanently_deleted_conversations:0,disk_files_changed:false})
    vi.spyOn(dialogs,'confirmAction').mockResolvedValue(true)
    await router.push('/trash');const view=render(HistoryPage,{global:{plugins:[router]}});await view.findByText('旧任务')
    await fireEvent.click(view.getByRole('button',{name:'清空最近删除'}))
    await waitFor(()=>expect(clear).toHaveBeenCalledOnce())
    await view.findByText(/1 条安全记录已从列表移出并保留日志/)
    expect(dialogs.confirmAction).toHaveBeenCalledWith(expect.stringContaining('磁盘文件不会改变'))
  })

  it('shows deleted conversations and permanently removes only their records', async () => {
    const conversation = { id: 'c1', title: '照片对话', status: 'DELETED', revision: 2, created_at: 'now', updated_at: 'now', deleted_at: 'now' } as any
    vi.mocked(api.conversations).mockResolvedValueOnce([conversation]).mockResolvedValueOnce([])
    vi.spyOn(api, 'tasks').mockResolvedValue({ items: [] })
    const purge = vi.spyOn(api, 'permanentlyDeleteConversation').mockResolvedValue({ permanently_deleted: true, disk_files_changed: false })
    vi.spyOn(dialogs, 'confirmAction').mockResolvedValue(true)
    await router.push('/trash')
    const view = render(HistoryPage, { global: { plugins: [router] } })
    await view.findByText('照片对话')
    await fireEvent.click(view.getByRole('button', { name: '永久删除对话' }))
    await waitFor(() => expect(purge).toHaveBeenCalledWith('c1'))
    expect(dialogs.confirmAction).toHaveBeenCalledWith(expect.stringContaining('磁盘文件不会改变'))
  })

  it('navigation removes template and rule products and exposes recent deletion', async () => {
    const app=await import('../src/App.vue?raw')
    expect(app.default).toContain('整理记录')
    expect(app.default).toContain('最近删除')
    expect(app.default).not.toContain('分类模板')
    expect(app.default).not.toContain('自动规则')
  })
})
