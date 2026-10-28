<script setup lang="ts">
import { computed, watch } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const router = useRouter()
const signedIn = computed(() => auth.isSignedIn)

watch(signedIn, (active) => {
  const route = router.currentRoute.value
  if (!active && route.meta.requiresAuth) {
    void router.replace({ path: '/login', query: { next: route.fullPath } })
  }
})

function signOut() {
  auth.signOut()
  router.push('/login')
}
</script>

<template>
  <div class="site-shell">
    <header class="site-header">
      <RouterLink class="brand" to="/surveys" aria-label="问序首页">
        <span class="brand-mark">问</span>
        <span>问序<span class="brand-dot">.</span></span>
      </RouterLink>
      <nav class="header-actions" aria-label="主导航">
        <template v-if="signedIn">
          <RouterLink to="/surveys">我的问卷</RouterLink>
          <RouterLink to="/library">个人题库</RouterLink>
          <span class="header-user">{{ auth.username }}</span>
          <button class="text-button" type="button" @click="signOut">退出</button>
        </template>
        <RouterLink v-else to="/login">登录</RouterLink>
      </nav>
    </header>
    <main class="main-area"><RouterView :key="$route.path" /></main>
    <footer class="site-footer">问序 · 用清晰的问题，得到可靠的答案</footer>
  </div>
</template>
