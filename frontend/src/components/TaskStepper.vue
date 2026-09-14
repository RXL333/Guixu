<script setup lang="ts">
defineProps<{ current: number }>()
const labels = ['设置', '分析', '分类树', '审阅', '执行', '结果']
</script>
<template><nav class="task-stepper" aria-label="任务阶段"><span v-for="(label,index) in labels" :key="label" :class="{done:index<=current}" :aria-current="index===current?'step':undefined">{{ label }}</span></nav></template>
