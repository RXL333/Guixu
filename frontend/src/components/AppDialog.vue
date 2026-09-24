<script setup lang="ts">
import { nextTick, onUnmounted, ref, watch } from 'vue'
import { dialogState } from './dialogState'
const dialog = ref<HTMLDialogElement | null>(null)
const value = ref('')
let previousFocus: HTMLElement | null = null
watch(dialogState, async state => {
  if (!state) return
  previousFocus = document.activeElement as HTMLElement | null
  value.value = state.value ?? ''
  await nextTick()
  dialog.value?.showModal()
  dialog.value?.querySelector<HTMLInputElement>('input')?.select()
})
function finish(accepted: boolean) {
  const state = dialogState.value
  dialog.value?.close()
  dialogState.value = null
  state?.resolve(accepted ? (state.value === undefined ? true : value.value.trim()) : null)
  previousFocus?.focus()
}
onUnmounted(() => { dialogState.value?.resolve(null); dialogState.value = null })
</script>
<template>
  <dialog ref="dialog" class="app-dialog" aria-labelledby="app-dialog-title" aria-describedby="app-dialog-description" @cancel.prevent="finish(false)">
    <form v-if="dialogState" @submit.prevent="finish(true)">
      <h2 id="app-dialog-title">{{ dialogState.title }}</h2>
      <p id="app-dialog-description">{{ dialogState.message }}</p>
      <input v-if="dialogState.value !== undefined" v-model="value" autofocus :aria-label="dialogState.title" maxlength="200" />
      <footer><button class="secondary-button" type="button" @click="finish(false)">取消</button><button class="primary-button" type="submit" :disabled="dialogState.value !== undefined && !value.trim()">确认</button></footer>
    </form>
  </dialog>
</template>
