<script setup lang="ts">
defineProps<{ title?: string }>();
</script>
<template><div class="app-shell-component"><header v-if="title"><h1>{{title}}</h1></header><slot/></div></template>
