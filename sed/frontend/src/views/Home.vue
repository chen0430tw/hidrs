<template>
  <div class="home">
    <Search />
    <Analysis />
  </div>
</template>

<script>
import Search from '@/components/Search.vue'
import Analysis from '@/components/Analysis.vue'

export default {
  name: 'Home',
  components: { Search, Analysis }
}
</script>

<style scoped>
.home {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 1rem;
}
</style>
