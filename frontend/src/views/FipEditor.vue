<template>
  <section class="stub-view">
    <h1>{{ $t('editor.title') }}</h1>
    <p>FipEditor is not implemented yet.</p>
  </section>
</template>

<script lang="ts" setup>
// Placeholder (spec 02 §2.2): kept minimal so the router and build stay
// green while the full editor lands in a follow-up pass. It will drive
// stores/fipEditor.ts (load/setDeclaration/addDeclaration/removeDeclaration/
// flush) and register its own `onBeforeRouteLeave` if extra cleanup is
// needed beyond the global flush already wired in router/index.ts.
</script>
