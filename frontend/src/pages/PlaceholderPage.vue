<script setup lang="ts">
defineProps<{
  title: string
  phase: string
}>()
</script>
<template><section class="page"><p class="eyebrow">CAPABILITY STATUS</p><h1>{{ title }}</h1><div class="state-card"><strong>尚未实现</strong><p>此能力按交付计划在{{ phase }}接入；当前不会显示模拟成功状态。</p></div></section></template>
