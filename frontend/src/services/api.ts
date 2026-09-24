export type ScanMode = 'current_only' | 'recursive' | 'preserve_top_level'

export interface TaskSettings {
  scan_mode: ScanMode
  operation_mode: 'preview_move' | 'direct_move' | 'copy' | 'report_only'
  organization_strategy: 'modality_first' | 'topic_first' | 'hybrid'
  classification_source: 'template' | 'fixed_categories' | 'auto_plan'
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

export interface CacheStatus {
  evidence_count: number
  valid_count: number
  invalid_count: number
  stale_count: number
  error_count: number
  estimated_bytes: number
  counters: Record<string, number>
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
  deleted_at?: string | null
  deletion_source?: string | null
  delete_reason?: string | null
  source_root?: string | null
  model_name?: string | null
  recent_operation?: string | null
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
  source_path: string
  name: string
  extension: string
  mime_type: string | null
  modality: string
  document_kind: string | null
  metadata: Record<string, unknown>
  content_summary: string
  evidence: EvidenceItem[]
  coverage: { mode: string; total_pages: number | null; sampled_pages: number[]; total_duration_sec: number | null; truncated: boolean }
  warnings: string[]
  capabilities_used: string[]
  parser_version: string
  parser_status: 'ready' | 'partial' | 'failed' | 'unsupported'
  parser_warnings: string[]
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
  source?: 'template' | 'fixed' | 'auto'
  nodes: Array<{ category_id: string; parent_id: string | null; name: string; selectable: boolean; definition?: Record<string, unknown>; is_fallback?: boolean }>
}

export interface CapabilityItem {
  status: 'unknown' | 'supported' | 'unsupported' | 'error'; message: string; tested_at: string | null
  verified?: boolean; last_probe_at?: string | null; probe_status?: 'not_run' | 'success' | 'failed'; probe_error?: string | null
  vision?: boolean; vision_verified?: boolean
}
export interface ModelProfile {
  id: string; name: string; provider: 'deepseek' | 'qwen_local'; runtime: string; base_url: string; model_id: string
  trust_scope: 'cloud' | 'loopback' | 'trusted_lan'; options: Record<string, unknown>; enabled: boolean; revision: number
  has_secret: boolean; capabilities: Record<string, CapabilityItem>
}
export interface PlannedOperation { operation_id: string; file_id: string; ordinal: number; action: string; source_path: string; target_path: string | null; reason: string | null }
export interface ExecutionPlan { plan_id: string; task_id: string; version: number; operation_mode: string; plan_hash: string; operations: PlannedOperation[]; status?: string; plan_basis_revision?: number; approved_task_revision?: number|null; approved?: boolean; results?: Array<{operation_id:string;file_id:string;state:string;error_code:string|null}> }
export interface TaskEvent { seq: number; event_type: string; payload: Record<string, unknown>; created_at: string }

export interface ConversationScope {
  id: string
  scope_kind: string
  source_root: string
  display_name: string
  authorization_ref?: string | null
  authorization_json?: Record<string, unknown>
  scope_hash?: string | null
  created_at: string
  revoked_at?: string | null
}

export interface Conversation {
  id: string
  title: string
  status: 'ACTIVE' | 'ARCHIVED' | 'DELETED' | 'ERROR'
  revision: number
  model_profile_id?: string | null
  metadata?: Record<string, unknown>
  created_at: string
  updated_at: string
  deleted_at?: string | null
  last_message_at?: string | null
  scopes?: ConversationScope[]
  context?: ConversationContext | null
  tasks?: Task[]
}

export type ConversationMessageRole = 'USER' | 'ASSISTANT' | 'SYSTEM_EVENT'
export type ConversationMessageType = 'TEXT' | 'STATUS' | 'PLAN_PROPOSAL' | 'EXECUTION_RESULT' | 'ERROR' | 'SYSTEM_EVENT'

export interface ConversationMessage {
  id: string
  conversation_id: string
  role: ConversationMessageRole
  content: string
  sequence_number: number
  message_type: ConversationMessageType
  status: 'ACTIVE' | 'REDACTED'
  referenced_plan_version_id?: string | null
  referenced_execution_round_id?: string | null
  referenced_file_ids?: string[]
  reference_source?: string | null
  file_references?: Array<{ file_id: string; reference_source: string; reference_role: string; path_snapshot?: string | null; current_known_path?: string | null; state: string; basename: string }>
  metadata?: Record<string, unknown>
  created_at: string
}

export interface ConversationContext {
  id: string
  conversation_id: string
  context_revision: number
  current_taxonomy_id?: string | null
  current_plan_version_id?: string | null
  current_execution_round_id?: string | null
  model_profile_id?: string | null
  max_directory_depth: number
  organization_intent?: Record<string, unknown>
  confirmed_requirements?: Array<Record<string, unknown>>
  privacy_scope?: Record<string, unknown>
  selection_state?: { file_ids?: string[]; source?: string; updated_at?: string } & Record<string, unknown>
  file_state_revision: number
  strategy_state?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ConversationPlanVersion {
  id: string
  conversation_id: string
  version_number: number
  parent_plan_version_id?: string | null
  baseline_execution_round_id?: string | null
  plan_kind?: 'FULL'|'DELTA'
  basis_context_revision: number
  basis_file_state_revision?: number
  source: string
  status: string
  taxonomy_id?: string | null
  taxonomy_snapshot?: Record<string, unknown>
  plan_id?: string | null
  plan_hash?: string | null
  summary: string
  change_summary?: Record<string, unknown>
  affected_file_count: number
  kept_file_count?: number
  conflict_count?: number
  created_by_message_id?: string | null
  restored_from_version_id?: string | null
  created_at: string
  approved_at?: string | null
  executed_at?: string | null
  superseded_at?: string | null
}

export type PlanFileChangeType = 'UNCHANGED' | 'ADDED' | 'REMOVED' | 'TARGET_CHANGED' | 'KEEP_CHANGED' | 'CONFLICT_CHANGED'
export interface ConversationPlanDiff {
  old_plan_version_id: string | null
  new_plan_version_id: string
  old_version_number?: number
  new_version_number?: number
  categories_added: Array<Record<string, unknown>>
  categories_removed: Array<Record<string, unknown>>
  category_changes: Array<Record<string, unknown>>
  file_changes: Array<{ file_id: string; change_type: PlanFileChangeType; old?: Record<string, unknown> | null; new?: Record<string, unknown> | null }>
  affected_file_ids: string[]
  summary_counts: Record<string, number>
}

export interface ConversationExecutionRound {
  id: string
  conversation_id: string
  round_number: number
  plan_version_id: string
  execution_plan_id: string
  undo_plan_id?: string | null
  status: string
  undo_status?: string | null
  started_at?: string | null
  completed_at?: string | null
  summary?: Record<string, unknown>
  affected_file_count: number
  round_kind?: 'FORWARD' | 'UNDO'
  target_execution_round_id?: string | null
  undo_state?: 'NOT_UNDONE' | 'PARTIALLY_UNDONE' | 'FULLY_UNDONE' | 'UNDO_BLOCKED' | 'NOT_REVERSIBLE'
  reversible_file_count?: number
  undone_file_count?: number
  created_at: string
}

export type UndoItemStatus = 'READY'|'COMPLETED'|'ALREADY_REVERSED'|'BLOCKED_MISSING'|'BLOCKED_MODIFIED'|'BLOCKED_EXTERNAL_MOVE'|'BLOCKED_TARGET_CONFLICT'|'BLOCKED_DEPENDENCY'|'BLOCKED_SCOPE'|'FAILED'
export interface ConversationUndoPlanItem {
  id: string
  file_id: string
  original_operation_id: string
  undo_operation_id?: string | null
  operation_kind: 'MOVE'|'COPY'
  ordinal: number
  current_source: string
  restore_target: string
  expected_fingerprint: string
  status: UndoItemStatus
  block_reason?: string | null
}
export interface ConversationUndoPlan {
  id: string
  conversation_id: string
  target_execution_round_id: string
  core_plan_id?: string | null
  status: 'WAITING_FOR_APPROVAL'|'APPROVED'|'EXECUTING'|'COMPLETED'|'PARTIALLY_COMPLETED'|'BLOCKED'|'STALE'|'CANCELLED'|'RECOVERY_REQUIRED'
  basis_file_state_revision: number
  plan_hash: string
  requested_file_ids: string[]
  summary: { target_round_number?: number; total?: number; ready?: number; blocked?: number; already_reversed?: number; partial?: boolean; dependency?: Record<string, unknown> }
  approval: Record<string, unknown>
  execution_round_id?: string | null
  items: ConversationUndoPlanItem[]
  created_at: string
}

export interface ConversationFile {
  id: string
  conversation_id: string
  file_id: string
  first_seen_path: string
  current_known_path: string
  first_seen_fingerprint?: string | null
  current_fingerprint?: string | null
  first_seen_size_bytes?: number | null
  current_size_bytes?: number | null
  first_seen_mtime_ns?: number | null
  current_mtime_ns?: number | null
  added_at: string
  removed_from_scope_at?: string | null
  last_verified_at?: string | null
  state: 'ACTIVE' | 'FILE_CHANGED' | 'MISSING' | 'REMOVED'
  core_current_path?: string
  core_size_bytes?: number | null
  core_mtime_ns?: number | null
  core_sha256?: string | null
  current_category_id?: string | null
}

export interface AffectedScope {
  scope_type: 'LOCAL'|'PARTIAL'|'GLOBAL'
  affected_category_ids: string[]
  candidate_file_ids: string[]
  target_category_id?: string | null
  requires_global_replan: boolean
  preserve_unaffected: boolean
  reason: string
}

export interface RefinementMetrics {
  total_scope_files: number
  affected_files: number
  evidence_reused: number
  evidence_refreshed: number
  invalid_evidence: number
  delta_plan_count: number
  ai_calls: number
}

export interface ConversationWorkspaceState {
  conversation_id: string
  conversation_status: string
  file_state_revision: number
  context_revision: number
  latest_execution_round_id?: string | null
  latest_executed_plan_version_id?: string | null
  current_plan_version_id?: string | null
  current_taxonomy: Record<string, unknown>
  current_requirements: Array<Record<string, unknown>>
  current_files: ConversationFile[]
  total_scope_files: number
}

export interface WorkspaceReconciliationSummary {
  conversation_id: string
  scope_status: 'AVAILABLE' | 'SCOPE_UNAVAILABLE' | 'SCOPE_RELINK_REQUIRED'
  file_state_revision: number
  context_revision?: number
  known_files: number
  unchanged: number
  moved: number
  renamed: number
  modified: number
  missing: number
  new_files: number
  conflicts: number
  requires_user_action: boolean
  workspace_changed: boolean
  changed_file_ids?: string[]
  new_file_items?: Array<{ path: string; name: string }>
  events?: Array<{ file_id?: string | null; state: string; current_path: string }>
}

export interface AgentTurn {
  id: string
  conversation_id: string
  turn_kind: 'ANALYSIS' | 'REPLANNING' | 'EXECUTION' | 'OTHER'
  status: 'QUEUED' | 'RUNNING' | 'WAITING_FOR_USER' | 'WAITING_FOR_APPROVAL' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'INTERRUPTED'
  interruption_code?: string | null
  retry_of_turn_id?: string | null
  created_at: string
  started_at?: string | null
  completed_at?: string | null
}

export interface ConversationRecoveryStatus {
  conversation_id: string
  conversation_status: string
  reconciliation: WorkspaceReconciliationSummary | null
  agent_turns: AgentTurn[]
  model_available: boolean
  requires_user_action: boolean
}

export interface RefinementResult {
  status: 'WAITING_FOR_APPROVAL'|'GLOBAL_REPLAN_CONFIRMATION_REQUIRED'
  intent: 'POST_EXECUTION_REFINEMENT'
  affected_scope: AffectedScope
  metrics: RefinementMetrics
  plan_version?: ConversationPlanVersion
  assistant_message?: ConversationMessage
}

export interface FirstAnalysisResult {
  status: 'COMPLETED'
  intent: 'ORGANIZE_REQUEST'
  task: Task
  files: ConversationFile[]
  plan_version: ConversationPlanVersion
  user_message: ConversationMessage
  assistant_message: ConversationMessage
  context: ConversationContext
  progress: Array<{ stage: string; label: string; status: string; details: Record<string, unknown> }>
  metrics: Record<string, number | string | null>
  disk_files_changed: false
}

type Envelope<T> = { data: T; meta: { request_id: string } }

export class ApiError extends Error {
  constructor(public code: string, message: string, public details: unknown, public status: number) { super(message) }
}

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
  if (!response.ok) throw new ApiError(body.error?.code ?? `HTTP_${response.status}`, body.error?.message ?? `HTTP ${response.status}`, body.error?.details, response.status)
  return (body as Envelope<T>).data
}

export const api = {
  settings: () => request<{ revision: number; values: TaskSettings }>('/api/v1/settings'),
  tasks: (view: 'active'|'deleted'|'all' = 'active') => request<{ items: Task[] }>(`/api/v1/tasks?view=${view}`),
  createTask: (payload: { name: string; source_grant: string; output_grant?: string | null; settings: TaskSettings; model_profile_id: string; user_instructions?: string }) =>
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
  reanalyze: (taskId: string, revision: number, fileId: string, forceRefresh = false) =>
    request<{ status: string }>(`/api/v1/tasks/${taskId}/reanalyze`, {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ expected_revision: revision, file_ids: [fileId], force_refresh: forceRefresh }),
    }),
  cacheStatus: () => request<CacheStatus>('/api/v1/cache/status'),
  clearCache: () => request<{ cleared: number }>('/api/v1/cache/clear', { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() } }),
  cleanupCache: (olderThanDays = 30) => request<{ cleared: number }>(`/api/v1/cache/cleanup?older_than_days=${olderThanDays}`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() } }),
  renameTask: (id: string, revision: number, name: string) => request<Task>(`/api/v1/tasks/${id}`, {
    method:'PATCH', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({expected_revision:revision,name}),
  }),
  deleteTask: (id: string, revision: number, deleteReason?: string) => request<Task>(`/api/v1/tasks/${id}`, {
    method:'DELETE', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({expected_revision:revision,delete_reason:deleteReason||null}),
  }),
  batchDeleteTasks: (taskIds: string[]) => request<{items:Task[];deleted:number}>('/api/v1/tasks/batch-delete', {
    method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({task_ids:taskIds}),
  }),
  restoreTask: (id: string, revision: number) => request<Task>(`/api/v1/tasks/${id}/restore`, {
    method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({expected_revision:revision}),
  }),
  batchRestoreTasks: (taskIds: string[]) => request<{items:Task[];restored:number}>('/api/v1/tasks/batch-restore', {
    method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({task_ids:taskIds}),
  }),
  permanentlyDeleteTask: (id: string, revision: number) => request<{permanently_deleted:boolean;disk_files_changed:false}>(`/api/v1/tasks/${id}/permanent`, {
    method:'DELETE', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({expected_revision:revision}),
  }),
  batchPermanentlyDeleteTasks: (taskIds: string[]) => request<{permanently_deleted:number;disk_files_changed:false}>('/api/v1/tasks/batch-permanent-delete', {
    method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({task_ids:taskIds}),
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
  updateTaxonomy: (taskId: string, taxonomy: Taxonomy, revision: number) => request<Taxonomy>(`/api/v1/tasks/${taskId}/taxonomies/${taxonomy.taxonomy_id}`, {
    method: 'PUT', headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify({ expected_revision: revision, tree_hash: taxonomy.tree_hash, nodes: taxonomy.nodes }),
  }),
  retryClassification: (taskId: string, taxonomyId: string) => request<{ status: string }>(`/api/v1/tasks/${taskId}/taxonomies/${taxonomyId}/classify`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: '{}',
  }),
  grantConsent: (taskId: string, payload: Record<string, unknown>) => request<Record<string, unknown>>(`/api/v1/tasks/${taskId}/consents`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(payload),
  }),
  review: (taskId: string, revision: number, item: Record<string, unknown>) => request<{ applied: number; new_revision: number }>(`/api/v1/tasks/${taskId}/reviews/bulk`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ expected_revision: revision, items: [item] }),
  }),
  compilePlan: (taskId: string) => request<ExecutionPlan>(`/api/v1/tasks/${taskId}/plan/compile`, { method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:'{}' }),
  plan: (taskId: string, planId?: string) => request<ExecutionPlan>(`/api/v1/tasks/${taskId}/plan${planId?`?plan_id=${encodeURIComponent(planId)}`:''}`),
  approvePlan: (taskId: string, revision: number, plan: ExecutionPlan) => request<{status:string;approved:boolean;plan_id:string;plan_hash:string;plan_basis_revision:number;approved_task_revision:number}>(`/api/v1/tasks/${taskId}/plan/approve`, { method:'POST', headers:{'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({expected_revision:revision,plan_id:plan.plan_id,plan_hash:plan.plan_hash}) }),
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
  conversations: (view: 'active'|'deleted'|'all' = 'active') => request<Conversation[]>(`/api/v1/conversations?view=${view}`),
  createConversation: (payload: { title?: string; model_profile_id?: string | null; scope_grant: string; metadata?: Record<string, unknown>; context?: Record<string, unknown> }) =>
    request<Conversation>('/api/v1/conversations', { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(payload) }),
  conversation: (id: string) => request<Conversation>(`/api/v1/conversations/${id}`),
  renameConversation: (id: string, title: string) => request<Conversation>(`/api/v1/conversations/${id}`, {
    method: 'PATCH', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ title }),
  }),
  updateConversationModel: (id: string, modelProfileId: string) => request<Conversation>(`/api/v1/conversations/${id}`, {
    method: 'PATCH', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ model_profile_id: modelProfileId }),
  }),
  archiveConversation: (id: string) => request<Conversation>(`/api/v1/conversations/${id}`, {
    method: 'PATCH', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ status: 'ARCHIVED' }),
  }),
  deleteConversation: (id: string) => request<{ conversation: Conversation; disk_files_changed: false; undo_started: false }>(`/api/v1/conversations/${id}`, {
    method: 'DELETE', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: '{}',
  }),
  restoreConversation: (id: string) => request<Conversation>(`/api/v1/conversations/${id}/restore`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: '{}',
  }),
  conversationMessages: (id: string) => request<ConversationMessage[]>(`/api/v1/conversations/${id}/messages`),
  appendConversationMessage: (id: string, payload: { role: ConversationMessageRole; content: string; message_type?: ConversationMessageType; metadata?: Record<string, unknown>; referenced_plan_version_id?: string | null; referenced_execution_round_id?: string | null; selected_file_ids?: string[]; focused_file_id?: string | null; active_category_id?: string | null; expected_context_revision?: number; reference_role?: 'SUBJECT'|'RESULT'|'CONTEXT' }) =>
    request<ConversationMessage>(`/api/v1/conversations/${id}/messages`, {
      method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(payload),
    }),
  firstConversationTurn: (id: string, payload: { content: string; selected_file_ids?: string[]; focused_file_id?: string | null; active_category_id?: string | null; acknowledge_privacy: boolean; reference_role?: 'SUBJECT'|'RESULT'|'CONTEXT' }) =>
    request<FirstAnalysisResult>(`/api/v1/conversations/${id}/turns`, {
      method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(payload),
    }),
  conversationContext: (id: string) => request<ConversationContext>(`/api/v1/conversations/${id}/context`),
  updateConversationContext: (id: string, expected_revision: number, changes: Record<string, unknown>) => request<ConversationContext>(`/api/v1/conversations/${id}/context`, {
    method: 'PATCH', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ expected_revision, changes }),
  }),
  conversationFiles: (id: string) => request<ConversationFile[]>(`/api/v1/conversations/${id}/files`),
  conversationPlans: (id: string) => request<ConversationPlanVersion[]>(`/api/v1/conversations/${id}/plans`),
  conversationPlanVersions: (id: string, limit = 20) => request<ConversationPlanVersion[]>(`/api/v1/conversations/${id}/plan-versions?limit=${limit}`),
  conversationPlanVersion: (id: string, versionId: string) => request<ConversationPlanVersion>(`/api/v1/conversations/${id}/plan-versions/${versionId}`),
  currentConversationPlanVersion: (id: string) => request<ConversationPlanVersion>(`/api/v1/conversations/${id}/plan-versions/current`),
  conversationPlanDiff: (id: string, versionId: string, fromVersionId?: string | null) => request<ConversationPlanDiff>(`/api/v1/conversations/${id}/plan-versions/${versionId}/diff${fromVersionId ? `?from_version_id=${encodeURIComponent(fromVersionId)}` : ''}`),
  approveConversationPlanVersion: (id: string, versionId: string, payload: { expected_context_revision?: number; plan_hash?: string; authorization?: Record<string, unknown> } = {}) => request<Record<string, unknown>>(`/api/v1/conversations/${id}/plan-versions/${versionId}/approve`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(payload),
  }),
  restoreConversationPlanVersion: (id: string, versionId: string, payload: { expected_context_revision?: number; expected_current_plan_version_id?: string } = {}) => request<ConversationPlanVersion>(`/api/v1/conversations/${id}/plan-versions/${versionId}/restore`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(payload),
  }),
  requestConversationPlanExecution: (id: string, versionId: string, payload: { expected_context_revision?: number; plan_hash?: string; status?: 'PENDING'|'RUNNING'; summary?: Record<string, unknown>; affected_file_count?: number } = {}) => request<ConversationExecutionRound>(`/api/v1/conversations/${id}/plan-versions/${versionId}/execution-rounds`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(payload),
  }),
  conversationExecutions: (id: string) => request<ConversationExecutionRound[]>(`/api/v1/conversations/${id}/executions`),
  conversationUndoPlans: (id: string) => request<ConversationUndoPlan[]>(`/api/v1/conversations/${id}/undo-plans`),
  requestConversationUndo: (id: string, payload: { user_message?: string; execution_round_id?: string; referenced_file_ids?: string[] }) => request<{ target: Record<string, unknown>; undo_plan: ConversationUndoPlan | null; query?: { reversible: boolean; message: string } }>(`/api/v1/conversations/${id}/undo-plans`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(payload),
  }),
  approveConversationUndo: (id: string, undoPlanId: string, planHash: string) => request<ConversationUndoPlan>(`/api/v1/conversations/${id}/undo-plans/${undoPlanId}/approve`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ plan_hash: planHash, authorization: { kind: 'interactive', surface: 'conversation_workspace' } }),
  }),
  executeConversationUndo: (id: string, undoPlanId: string, planHash: string) => request<ConversationUndoPlan>(`/api/v1/conversations/${id}/undo-plans/${undoPlanId}/execute`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ plan_hash: planHash }),
  }),
  cancelConversationUndo: (id: string, undoPlanId: string) => request<ConversationUndoPlan>(`/api/v1/conversations/${id}/undo-plans/${undoPlanId}/cancel`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: '{}',
  }),
  conversationWorkspaceState: (id: string) => request<ConversationWorkspaceState>(`/api/v1/conversations/${id}/workspace-state`),
  conversationRecoveryStatus: (id: string, reconcile = true) => request<ConversationRecoveryStatus>(`/api/v1/conversations/${id}/recovery-status?reconcile=${reconcile ? 'true' : 'false'}`),
  reconcileConversation: (id: string) => request<WorkspaceReconciliationSummary>(`/api/v1/conversations/${id}/reconcile`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ trigger: 'MANUAL' }),
  }),
  revalidateConversationPlan: (id: string, planVersionId: string) => request<Record<string, unknown>>(`/api/v1/conversations/${id}/revalidate-plan`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ plan_version_id: planVersionId }),
  }),
  resumeConversationAnalysis: (id: string) => request<AgentTurn>(`/api/v1/conversations/${id}/resume-analysis`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: '{}',
  }),
  conversationAgentTurns: (id: string) => request<AgentTurn[]>(`/api/v1/conversations/${id}/agent-turns`),
  retryConversationAgentTurn: (id: string, turnId: string) => request<AgentTurn>(`/api/v1/conversations/${id}/agent-turns/${turnId}/retry`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: '{}',
  }),
  prepareConversationRefinement: (id: string, payload: { user_message: string; confirmed_global?: boolean; referenced_file_ids?: string[]; trigger_message_id?: string }) => request<RefinementResult>(`/api/v1/conversations/${id}/refinements/prepare`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(payload),
  }),
  executeConversationRefinement: (id: string, versionId: string, payload: { expected_context_revision?: number; plan_hash?: string } = {}) => request<{ execution_round: ConversationExecutionRound; workspace: ConversationWorkspaceState }>(`/api/v1/conversations/${id}/plan-versions/${versionId}/execute`, {
    method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(payload),
  }),
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
