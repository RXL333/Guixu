<script setup lang="ts">
import type { ClassificationTemplate } from '../services/api';

defineProps<{ items: ClassificationTemplate[]; modelValue: string }>();
defineEmits<{ 'update:modelValue': [value: string] }>();
</script>
<template><label>分类模板<select :value="modelValue" @change="$emit('update:modelValue',($event.target as HTMLSelectElement).value)"><option v-for="item in items" :key="item.template_id" :value="item.template_id">{{item.name}} · {{item.nodes.length}} 类</option></select></label></template>
