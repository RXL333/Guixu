export type ScanMode = 'current_only' | 'recursive' | 'preserve_top_level'

export interface TaskSettings {
  scan_mode: ScanMode
  operation_mode: 'preview_move' | 'direct_move' | 'copy' | 'report_only'
  organization_strategy: 'modality_first' | 'topic_first' | 'hybrid'
  classification_source: 'template' | 'fixed_categories' | 'auto_plan'
  classification_mode: 'rules_first' | 'ai_first' | 'rules_only'
  max_depth: number
  max_siblings: number
  max_nodes_per_scope: number
  max_new_directories: number
  analysis_preset: 'fast' | 'standard' | 'deep'
  uncertain_action: 'keep_in_place' | 'quarantine_after_review'
  collision_policy: 'keep_both' | 'skip'
  include_hidden: boolean
  allow_file_rename: false
  skip_project_directories: true
  allowed_modalities: string[]
  extension_allowlist: string[]
  exclusions: string[]
  large_file_warning_bytes: number
  privacy: Record<string, boolean>
  task_budget: Record<string, number | string | null>
}

export interface Task {
  id: string
  name: string
  status: string
  phase: string
  revision: number
  settings: TaskSettings
  counters: Record<string, number>
  created_at: string
  updated_at: string
}

export interface FileItem {
  id: string
  task_id?: string
  scope_id: string
  basename: string
  relative_path: string
  extension: string
  modality: string
  size_bytes: number
  scan_status: string
  exclusion_code: string | null
  scope_name: string
  metadata: { type_evidence: string }
}

export interface EvidenceItem {
  id: string
  kind: string
  text: string
  locator: Record<string, unknown>
  quality: string
  origin: string
}

export interface FileProfile {
  file_id: string
  modality: string
  document_kind: string | null
  metadata: Record<string, unknown>
  content_summary: string
  evidence: EvidenceItem[]
  coverage: { mode: string; total_pages: number | null; sampled_pages: number[]; total_duration_sec: number | null; truncated: boolean }
  warnings: string[]
  capabilities_used: string[]
  parser_version: string
}

export interface FileDetail {
  file: FileItem
  profile: FileProfile | null
  suggestion: null | { taxonomy_id: string; category_id: string | null; abstain: boolean; reason: string; source: string; review_band: string; evidence_ids: string[]; warnings: string[] }
  latest_review: null | { taxonomy_id: string; category_id: string | null; decision: string; note: string; revision: number }
}

export interface Taxonomy {
  taxonomy_id: string
  scope_id: string
  version: number
  status: 'draft' | 'approved' | 'superseded'
  tree_hash: string
  policy: Record<string, unknown>
  nodes: Array<{ category_id: string; parent_id: string | null; name: string; selectable: boolean }>
}

export interface ClassificationTemplate {
  template_id: string
  version: number
  name: string
  description: string
  modalities: string[]
  compatible_strategies: string[]
  minimum_depth: number
  requires_ai: boolean
  nodes: Array<{ category_id: string; parent_id: string | null; name: string; selectable: boolean }>
}

export interface RuleItem {
  id: string
  name: string
  priority: number
  enabled: boolean
  scope: Record<string, unknown>
  condition: Record<string, unknown>
  action: Record<string, unknown>
  revision: number
}

export interface CapabilityItem { status: 'unknown' | 'supported' | 'unsupported' | 'error'; message: string; tested_at: string | null }
export interface ModelProfile {
  id: string; name: string; provider: 'deepseek' | 'qwen_local'; runtime: string; base_url: string; model_id: string
  trust_scope: 'cloud' | 'loopback' | 'trusted_lan'; options: Record<string, unknown>; enabled: boolean; revision: number
  has_secret: boolean; capabilities: Record<string, CapabilityItem>
}
export interface PlannedOperation { operation_id: string; file_id: string; ordinal: number; action: string; source_path: string; target_path: string | null; reason: string | null }
export interface ExecutionPlan { plan_id: string; task_id: string; version: number; operation_mode: string; plan_hash: string; operations: PlannedOperation[] }
export interface TaskEvent { seq: number; event_type: string; payload: Record<string, unknown>; created_at: string }

type Envelope<T> = { data: T; meta: { request_id: string } }

function token(): string {
  return window.__GUIXU_SESSION__ ?? import.meta.env.VITE_GUIXU_SESSION ?? ''
}

async function waitForSession(): Promise<string> {
  const current = token()
  if (current) return current
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error('桌面安全会话尚未就绪')), 5000)
    window.addEventListener('guixu-ready', () => {
      window.clearTimeout(timeout)
      resolve(token())
    }, { once: true })
  })
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const session = await waitForSession()
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', 'X-Guixu-Session': session, ...init.headers },
  })
  const body = await response.json()
  if (!response.ok) throw new Error(body.error?.message ?? `HTTP ${response.status}`)
  return (body as Envelope<T>).data
}

export const api = {
  settings: () => request<{ revision: number; values: TaskSettings }>('/api/v1/settings'),
  tasks: () => request<{ items: Task[] }>('/api/v1/tasks'),
  createTask: (payload: { name: string; source_grant: string; output_grant?: string | null; settings: TaskSettings; model_profile_id?: string | null; template_key?: string | null }) =>
    request<Task>('/api/v1/tasks', {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify(payload),
    }),
  startTask: (id: string, revision: number) =>
    request<Task>(`/api/v1/tasks/${id}/start`, {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ expected_revision: revision }),
    }),
  task: (id: string) => request<Task>(`/api/v1/tasks/${id}`),
  files: (id: string, limit=100, offset=0, query='', status='') => request<{ items: FileItem[]; total: number; next_cursor:number|null }>(`/api/v1/tasks/${id}/files?limit=${limit}&offset=${offset}&q=${encodeURIComponent(query)}${status?`&scan_status=${encodeURIComponent(status)}`:''}`),
  file: (taskId: string, fileId: string) => request<FileDetail>(`/api/v1/tasks/${taskId}/files/${fileId}`),
  reanalyze: (taskId: string, revision: number, fileId: string) =>
    request<{ status: string }>(`/api/v1/tasks/${taskId}/reanalyze`, {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ expected_revision: revision, file_ids: [fileId] }),
    }),
  templates: () => request<{ items: ClassificationTemplate[]; total: number }>('/api/v1/templates'),
  rules: () => request<{ items: RuleItem[]; total: number }>('/api/v1/rules'),
  createRule: (payload: Record<string, unknown>) => request<RuleItem>('/api/v1/rules', {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(payload),
  }),
  testRule: (taskId: string, fileIds: string[], draftRule: Record<string, unknown>) => request<{matched_file_ids:string[];conflicts:string[]}>('/api/v1/rules/test', {
    method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({task_id:taskId,file_ids:fileIds,draft_rule:draftRule}),
  }),
  models: () => request<ModelProfile[]>('/api/v1/models'),
  createModel: (payload: Record<string, unknown>) => request<ModelProfile>('/api/v1/models', {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(payload),
  }),
  deleteModel: (id: string, revision: number) => request<{ disabled: boolean }>(`/api/v1/models/${id}`, {
    method: 'DELETE', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ expected_revision: revision }),
  }),
  saveModelSecret: (id: string, revision: number, secret: string | null) => request<{ has_secret: boolean }>(`/api/v1/models/${id}/secret`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ expected_revision: revision, secret }),
  }),
  probeModel: (id: string) => request<Record<string, CapabilityItem>>(`/api/v1/models/${id}/probe`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: '{}',
  }),
  taxonomies: (taskId: string) => request<Taxonomy[]>(`/api/v1/tasks/${taskId}/taxonomies`),
  approveTaxonomy: (taskId: string, taxonomyId: string, revision: number, treeHash: string) => request<{ status: string }>(`/api/v1/tasks/${taskId}/taxonomies/${taxonomyId}/approve`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ expected_revision: revision, tree_hash: treeHash }),
  }),
  review: (taskId: string, revision: number, item: Record<string, unknown>) => request<{ applied: number; new_revision: number }>(`/api/v1/tasks/${taskId}/reviews/bulk`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ expected_revision: revision, items: [item] }),
  }),
  compilePlan: (taskId: string) => request<ExecutionPlan>(`/api/v1/tasks/${taskId}/plan/compile`, { method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:'{}' }),
  plan: (taskId: string, planId?: string) => request<ExecutionPlan>(`/api/v1/tasks/${taskId}/plan${planId?`?plan_id=${encodeURIComponent(planId)}`:''}`),
  approvePlan: (taskId: string, revision: number, plan: ExecutionPlan) => request<{status:string}>(`/api/v1/tasks/${taskId}/plan/approve`, { method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({expected_revision:revision,plan_id:plan.plan_id,plan_hash:plan.plan_hash}) }),
  executePlan: (taskId: string, revision: number, plan: ExecutionPlan) => request<ExecutionPlan>(`/api/v1/tasks/${taskId}/execute`, { method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({expected_revision:revision,plan_id:plan.plan_id,plan_hash:plan.plan_hash}) }),
  compileUndo: (taskId: string, revision: number, forwardPlanId: string, forwardPlanHash: string) => request<ExecutionPlan>(`/api/v1/tasks/${taskId}/undo/plan`, { method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({expected_revision:revision,plan_id:forwardPlanId,plan_hash:forwardPlanHash}) }),
  events: (taskId: string, afterSeq = 0) => request<{items:TaskEvent[]}>(`/api/v1/tasks/${taskId}/events?after_seq=${afterSeq}`),
  pauseTask: (taskId: string, revision: number) => request<Task>(`/api/v1/tasks/${taskId}/pause`, { method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({expected_revision:revision}) }),
  resumeTask: (taskId: string, revision: number) => request<Task>(`/api/v1/tasks/${taskId}/resume`, { method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({expected_revision:revision}) }),
  cancelTask: (taskId: string, revision: number) => request<Task>(`/api/v1/tasks/${taskId}/cancel`, { method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({expected_revision:revision}) }),
  recoverTask: (taskId: string, revision: number) => request<{task:Task;result:Record<string,number>}>(`/api/v1/tasks/${taskId}/recover`, { method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({expected_revision:revision}) }),
  report: (taskId: string) => request<Record<string, unknown>>(`/api/v1/tasks/${taskId}/report`),
  exportReport: (taskId: string, grant: string, format: 'json'|'csv', filename?: string) => request<Record<string, unknown>>(`/api/v1/tasks/${taskId}/report/export`, { method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({export_grant:grant,format,filename}) }),
  components: () => request<Array<Record<string, unknown>>>('/api/v1/components'),
  devGrant: (path: string, purpose = 'source') => request<DirectoryGrant>('/api/v1/dev/grants', { method: 'POST', body: JSON.stringify({ path, purpose }) }),
}

export async function chooseDirectory(purpose: 'source'|'output'|'export', typedPath?: string): Promise<DirectoryGrant> {
  if (window.pywebview?.api) {
    return typedPath
      ? window.pywebview.api.register_typed_directory(typedPath, purpose)
      : window.pywebview.api.select_directory(purpose)
  }
  if (!typedPath) return { cancelled: true }
  return api.devGrant(typedPath, purpose)
}
export const chooseSource = (typedPath?: string) => chooseDirectory('source', typedPath)
