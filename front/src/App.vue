<script setup>
import TopBar from "./components/TopBar.vue";
import AiAssistantDrawer from "./components/AiAssistantDrawer.vue";
</script>

<template>
  <div class="app-shell">
    <div class="app-main">
      <TopBar />
      <RouterView />
      <AiAssistantDrawer />
    </div>
  </div>
</template>
