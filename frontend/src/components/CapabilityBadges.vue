<script setup lang="ts">
import type { CapabilityItem } from '../services/api';

defineProps<{ capabilities: Record<string, CapabilityItem> }>();
</script>
<template><div class="capability-badges"><span v-for="(item,key) in capabilities" :key="key"><b>{{key}}</b> {{item.status}}<small>{{item.message}}</small></span></div></template>
