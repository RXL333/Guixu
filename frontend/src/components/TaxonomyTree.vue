<script setup lang="ts">
import type { Taxonomy } from '../services/api'
defineProps<{ taxonomy: Taxonomy; selected?: string }>()
defineEmits<{ select: [string] }>()
</script>
<template><ul class="taxonomy-tree"><li v-for="node in taxonomy.nodes" :key="node.category_id" :style="{paddingLeft:node.parent_id?'24px':'0'}"><button :class="{selected:selected===node.category_id}" @click="$emit('select',node.category_id)"><span class="tree-index">{{ node.parent_id?'└':'□' }}</span>{{ node.name }}<small>{{ node.selectable?'可归档':'结构节点' }}</small></button></li></ul></template>
