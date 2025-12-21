<script setup lang="ts">

defineProps<{ msg: string }>()

</script>

<template>
  <h1 class="cls">{{ msg }}</h1>

</template>

<style scoped>
.cls {
  color: #888;
}
</style>
