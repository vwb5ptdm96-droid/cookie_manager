<template>
  <section class="placeholder">
    <div class="placeholder-card">
      <h2>当前 Phase 尚未落到这里</h2>
      <p>这页对应的业务模块还没进入实现窗口。先把左侧已经接通的页面跑起来，再继续往下推进。</p>
    </div>
  </section>
</template>

<style scoped>
.placeholder-card {
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface-subtle);
  padding: 28px;
  color: var(--color-text-secondary);
}

.placeholder-card h2 {
  margin: 0 0 10px;
  color: var(--color-text-primary);
  font-size: 18px;
}
</style>
