<script setup lang="ts">
defineProps<{
  events: Array<{ seq: number; event_type: string; created_at: string }>;
}>();
</script>
<template><ol class="task-timeline"><li v-for="event in events" :key="event.seq"><b>{{event.event_type}}</b><time>{{event.created_at}}</time></li></ol></template>
