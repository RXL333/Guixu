/// <reference types="vite/client" />

interface Window {
  __GUIXU_SESSION__?: string
  pywebview?: {
    api: {
      select_directory(purpose: string): Promise<DirectoryGrant>
      register_typed_directory(path: string, purpose: string): Promise<DirectoryGrant>
      open_conversation_directory(conversationId: string): Promise<{ opened: boolean; path: string }>
    }
  }
}

interface DirectoryGrant {
  cancelled: boolean
  grant_id?: string
  display_path?: string
  exists?: boolean
  writable?: boolean
  warnings?: string[]
}
