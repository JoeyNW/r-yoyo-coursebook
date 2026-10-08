<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import TabBar from './components/TabBar.vue'
import { session } from './session'

const route = useRoute()
const showTabs = computed(() => Boolean(route.meta.tabs) && session.family)
</script>

<template>
  <div class="shell">
    <div class="page">
      <RouterView />
    </div>
    <TabBar v-if="showTabs" />
  </div>
</template>
