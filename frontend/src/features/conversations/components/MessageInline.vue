<script setup lang="ts">
import type { InlineNode } from '../markdown'

defineProps<{ nodes: InlineNode[] }>()
</script>

<!--
  Renders one level of inline nodes with plain bindings. There is deliberately no
  `v-html` anywhere: model output can never become markup, so a reply containing
  `<script>` or `<img onerror=...>` is shown as the literal text the model typed.
  Self-reference gives the recursion needed for emphasis nested in emphasis.
-->
<template>
  <template v-for="(node, index) in nodes" :key="index">
    <strong v-if="node.kind === 'strong'"><MessageInline :nodes="node.children" /></strong>
    <em v-else-if="node.kind === 'em'"><MessageInline :nodes="node.children" /></em>
    <code v-else-if="node.kind === 'code'" class="message-inline-code">{{ node.text }}</code>
    <a v-else-if="node.kind === 'link'" class="message-link" :href="node.href" target="_blank" rel="noopener noreferrer">{{ node.text }}</a>
    <template v-else>{{ node.text }}</template>
  </template>
</template>
