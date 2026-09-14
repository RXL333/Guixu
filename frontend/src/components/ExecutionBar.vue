<script setup lang="ts">
defineProps<{
  ready: number;
  pending: number;
  action: string;
  disabled?: boolean;
}>();
defineEmits<{ confirm: [] }>();
</script>
<template><footer class="action-bar"><span>可执行 {{ready}} 项 · 待确认 {{pending}} 项将原地保留</span><button class="primary-button" :disabled="disabled" @click="$emit('confirm')">{{action}}</button></footer></template>
