<script setup lang="ts">
defineProps<{ modelValue: string; disabled?: boolean }>();
defineEmits<{
  'update:modelValue': [value: string];
  choose: [];
}>();
</script>
<template><label>目录<div class="path-picker"><input :value="modelValue" :disabled="disabled" @input="$emit('update:modelValue',($event.target as HTMLInputElement).value)"/><button class="secondary-button" :disabled="disabled" @click="$emit('choose')">选择目录</button></div></label></template>
