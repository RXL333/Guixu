<script setup lang="ts">
defineProps<{ modelValue: string; disabled?: boolean }>();
defineEmits<{
  'update:modelValue': [value: string];
  compile: [];
}>();
</script>
<template><label>自然语言整理偏好<textarea :value="modelValue" :disabled="disabled" maxlength="10000" @input="$emit('update:modelValue',($event.target as HTMLTextAreaElement).value)"/><button class="secondary-button" :disabled="disabled" @click="$emit('compile')">解释一次规则</button><small>不会在每次键入时调用收费模型。</small></label></template>
