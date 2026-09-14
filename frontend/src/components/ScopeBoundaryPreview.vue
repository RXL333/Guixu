<script setup lang="ts">
defineProps<{ mode: string; root: string; protectedNames?: string[] }>();
</script>
<template><aside class="state-card"><h2>扫描边界</h2><code>{{root||'尚未授权'}}</code><p>{{mode==='preserve_top_level'?'直接子目录是受保护区域，文件不会跨区。':mode==='current_only'?'只读取根目录直接文件。':'后代文件属于同一整理区域。'}}</p><ul><li v-for="name in protectedNames||[]" :key="name">🔒 {{name}}</li></ul></aside></template>
