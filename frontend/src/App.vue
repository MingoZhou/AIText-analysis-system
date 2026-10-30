<template>
  <router-view v-if="route.meta.public" />
  <el-container v-else class="app-container">
    <!-- 侧边栏 -->
    <el-aside :width="sidebarCollapsed ? '64px' : '220px'" class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="logo">
        <el-icon size="24"><DataAnalysis /></el-icon>
        <span v-show="!sidebarCollapsed">策知</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        class="sidebar-menu"
        :collapse="sidebarCollapsed"
        background-color="#1d1e1f"
        text-color="#bfcbd9"
        active-text-color="#409eff"
      >
        <el-menu-item index="/" aria-label="首页" title="首页">
          <el-icon><HomeFilled /></el-icon>
          <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/collection" aria-label="数据采集" title="数据采集">
          <el-icon><Download /></el-icon>
          <span>数据采集</span>
        </el-menu-item>
        <el-menu-item index="/articles" aria-label="采集信息" title="采集信息">
          <el-icon><Document /></el-icon>
          <span>采集信息</span>
        </el-menu-item>
        <el-menu-item index="/data-analysis" aria-label="数据分析" title="数据分析">
          <el-icon><PieChart /></el-icon>
          <span>数据分析</span>
        </el-menu-item>
        <el-menu-item index="/analysis" aria-label="AI 分析" title="AI 分析">
          <el-icon><MagicStick /></el-icon>
          <span>AI 分析</span>
        </el-menu-item>
        <el-menu-item index="/profile" aria-label="个人信息" title="个人信息">
          <el-icon><User /></el-icon>
          <span>个人信息</span>
        </el-menu-item>
      </el-menu>
      <div class="sidebar-footer">
        <a
          href="https://github.com/Zhou-1204?tab=repositories"
          target="_blank"
          rel="noopener noreferrer"
          class="github-link"
          title="GitHub"
        >
          <svg class="github-icon" viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
          </svg>
        </a>
        <span v-show="!sidebarCollapsed" class="version-text">v1.0.0</span>
      </div>
    </el-aside>

    <!-- 主内容区 -->
    <el-container>
      <el-header class="header">
        <div class="header-left">
          <button class="sidebar-toggle" type="button" @click="sidebarCollapsed = !sidebarCollapsed" :aria-label="sidebarCollapsed ? '展开菜单' : '收起菜单'">
            <el-icon size="20"><Fold v-if="!sidebarCollapsed" /><Expand v-else /></el-icon>
          </button>
          <div class="header-title">{{ currentTitle }}</div>
        </div>
        <el-dropdown trigger="click" @command="handleUserCommand">
          <button class="user-trigger" type="button" aria-label="用户菜单">
            <span class="user-avatar">{{ userInitial }}</span>
            <span class="user-name">{{ authState.user?.display_name || authState.user?.username }}</span>
            <el-icon><ArrowDown /></el-icon>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item disabled>{{ authState.user?.username }}</el-dropdown-item>
              <el-dropdown-item divided command="profile">
                <el-icon><User /></el-icon>个人信息
              </el-dropdown-item>
              <el-dropdown-item divided command="logout">
                <el-icon><SwitchButton /></el-icon>退出登录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main class="main">
        <router-view />
        <div class="app-footer">Copyright @ 2026-2028 by ZMH</div>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { authState, logoutAccount } from './auth'

const route = useRoute()
const router = useRouter()
const activeMenu = computed(() => route.path)
const currentTitle = computed(() => route.meta.title || '首页')
const sidebarCollapsed = ref(false)
const userInitial = computed(() => {
  const value = authState.user?.display_name || authState.user?.username || '用'
  return value.slice(0, 1).toUpperCase()
})

async function handleUserCommand(command) {
  if (command === 'profile') {
    await router.push('/profile')
    return
  }
  if (command === 'logout') {
    await logoutAccount()
    await router.replace('/login')
  }
}
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body, #app { height: 100%; }
body { font-family: -apple-system, 'Segoe UI', 'Microsoft YaHei', sans-serif; }

.app-container { height: 100vh; }

.sidebar {
  background: #1d1e1f;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width 0.28s ease;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 20px;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  border-bottom: 1px solid #333;
  white-space: nowrap;
  overflow: hidden;
}

.sidebar.collapsed .logo {
  justify-content: center;
  padding: 0;
}

.sidebar-menu {
  flex: 1;
  border-right: none !important;
}

.sidebar-menu:not(.el-menu--collapse) {
  width: 100%;
}

.sidebar-menu .el-menu-item {
  height: 50px;
  line-height: 50px;
}

.sidebar-menu .el-menu-item.is-active {
  background: #409eff22 !important;
  border-left: 3px solid #409eff;
}

.sidebar-footer {
  padding: 10px 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-top: 1px solid #333;
}

.sidebar.collapsed .sidebar-footer {
  flex-direction: column;
  gap: 6px;
}

.github-link {
  display: flex;
  align-items: center;
  color: #555;
  transition: color 0.2s;
  text-decoration: none;
}

.github-link:hover {
  color: #409eff;
}

.github-icon {
  flex-shrink: 0;
}

.version-text {
  color: #555;
  font-size: 12px;
}

.header {
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px !important;
  padding: 0 24px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sidebar-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  background: #fff;
  color: #555;
  cursor: pointer;
  transition: all 0.2s;
}

.sidebar-toggle:hover {
  background: #f0f7ff;
  border-color: #409eff;
  color: #409eff;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
  color: #1d1e1f;
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 4px 7px;
  border: 0;
  background: transparent;
  color: #414541;
  cursor: pointer;
}
.user-trigger:hover { background: #f1f4f1; }
.user-avatar {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  background: #357c4b;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
}
.user-name { max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.main {
  background: #f0f2f5;
  padding: 20px;
  overflow-y: auto;
}

.app-footer {
  text-align: center;
  font-size: 12px;
  color: #999;
  padding: 16px 0;
  margin-top: 12px;
}

@media (max-width: 760px) {
  .sidebar {
    width: 64px !important;
  }

  .logo {
    justify-content: center;
    padding: 0;
  }

  .logo span,
  .sidebar-menu .el-menu-item span,
  .sidebar-footer {
    display: none;
  }

  .sidebar-menu .el-menu-item {
    justify-content: center;
    padding: 0 !important;
  }

  .sidebar-menu .el-menu-item .el-icon {
    margin-right: 0;
  }

  .header {
    height: 50px !important;
    padding: 0 14px;
  }

  .main {
    padding: 12px;
  }

  .user-name { display: none; }

  .el-dialog {
    width: calc(100% - 24px) !important;
    margin-top: 5vh !important;
  }

  .el-drawer {
    width: 100% !important;
  }
}
</style>
