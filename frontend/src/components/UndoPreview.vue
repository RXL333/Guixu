<script setup lang="ts">
defineProps<{
  recoverable: number;
  modified: number;
  occupied: number;
  missing: number;
}>();
</script>
<template><section class="state-card"><h2>撤销预览</h2><dl><dt>可恢复</dt><dd>{{recoverable}}</dd><dt>目标已修改</dt><dd>{{modified}}</dd><dt>原位置占用</dt><dd>{{occupied}}</dd><dt>文件缺失</dt><dd>{{missing}}</dd></dl><p>冲突项不会被覆盖或猜测性处理。</p></section></template>
