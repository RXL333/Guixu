<script setup lang="ts">
defineProps<{
  destination: string;
  dataTypes: string[];
  characters: number;
  images: number;
  approved: boolean;
}>();
</script>
<template><section class="state-card"><h2>出站预览</h2><p>目的服务：{{destination||'未选择'}}</p><p>文字 {{characters}} 字符 · 派生图片/帧 {{images}} 张</p><p>类型：{{dataTypes.join('、')||'无'}}</p><strong>{{approved?'已按当前 scope hash 授权':'尚未授权，不会出站'}}</strong></section></template>
