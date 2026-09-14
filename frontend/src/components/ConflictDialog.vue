<script setup lang="ts">
defineProps<{ open: boolean; title: string; details: string[] }>();
defineEmits<{ close: [] }>();
</script>
<template><div v-if="open" role="dialog" aria-modal="true" :aria-label="title" class="conflict-dialog"><h2>{{title}}</h2><ul><li v-for="item in details" :key="item">{{item}}</li></ul><button class="secondary-button" @click="$emit('close')">关闭并保留文件</button></div></template>
