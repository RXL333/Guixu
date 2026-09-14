<script setup lang="ts">
import type { ExecutionPlan, FileItem } from '../services/api';

defineProps<{ files: FileItem[]; plan: ExecutionPlan | null }>();
defineEmits<{ inspect: [file: FileItem] }>();
</script>
<template><div class="mapping-pane"><button v-for="file in files" :key="file.id" class="mapping-row" @click="$emit('inspect',file)"><span>{{file.basename}}</span><span>→</span><span>{{plan?.operations.find(item=>item.file_id===file.id)?.target_path||'原地保留'}}</span><em>{{file.scan_status}}</em></button></div></template>
