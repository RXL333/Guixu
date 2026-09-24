import { shallowRef } from 'vue'

export const dialogState = shallowRef<null | { title: string; message: string; value?: string; resolve: (value: string | boolean | null) => void }>(null)
export function confirmAction(message: string, title = '请确认') {
  return new Promise<boolean>(resolve => {
    dialogState.value?.resolve(false)
    dialogState.value = { title, message, resolve: value => resolve(value === true) }
  })
}
export function promptAction(title: string, value = '') {
  return new Promise<string | null>(resolve => {
    dialogState.value?.resolve(null)
    dialogState.value = { title, message: '', value, resolve: result => resolve(typeof result === 'string' ? result : null) }
  })
}
