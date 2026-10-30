<template>
  <div class="profile-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2 class="page-title">个人信息</h2>
      <p class="page-desc">管理你的账户资料、头像与安全设置</p>
    </div>

    <!-- 头像 + 资料表单 并排 -->
    <el-card shadow="hover" class="profile-card">
      <el-row :gutter="24">
        <!-- 头像上传区域 -->
        <el-col :xs="24" :sm="24" :md="8" class="avatar-col">
          <div class="avatar-panel">
            <div
              class="avatar-wrapper"
              role="button"
              tabindex="0"
              :aria-label="avatarUploading ? '头像上传中' : '点击更换头像'"
              @click="triggerAvatarUpload"
              @keydown.enter.prevent="triggerAvatarUpload"
            >
              <img v-if="avatarUrl" :src="avatarUrl" class="avatar-img" alt="头像" />
              <span v-else class="avatar-placeholder">{{ userInitial }}</span>
              <div class="avatar-mask">
                <el-icon size="22"><Camera /></el-icon>
                <span>{{ avatarUploading ? '上传中...' : '更换头像' }}</span>
              </div>
              <div v-if="avatarUploading" class="avatar-loading">
                <el-icon class="is-loading" size="28"><Loading /></el-icon>
              </div>
            </div>
            <div class="avatar-meta">
              <div class="avatar-name">{{ form.display_name || form.username || '用户' }}</div>
              <div class="avatar-sub">@{{ form.username }}</div>
            </div>
            <div class="avatar-tips">
              <el-icon><InfoFilled /></el-icon>
              <span>支持 JPG / PNG / WebP / GIF，最大 5MB</span>
            </div>
            <input
              ref="fileInputRef"
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              class="hidden-input"
              @change="handleAvatarChange"
            />
          </div>
        </el-col>

        <!-- 资料表单区域 -->
        <el-col :xs="24" :sm="24" :md="16" class="form-col">
          <div class="form-header">
            <span class="form-title">基本资料</span>
            <el-button type="primary" :icon="Check" :loading="saving" @click="handleSave">
              保存修改
            </el-button>
          </div>

          <el-form
            ref="profileFormRef"
            :model="form"
            label-position="top"
            class="profile-form"
          >
            <el-form-item label="显示名称" prop="display_name">
              <el-input
                v-model="form.display_name"
                placeholder="请输入显示名称"
                maxlength="100"
                clearable
              />
            </el-form-item>

            <el-form-item label="用户名">
              <el-input :model-value="form.username" readonly>
                <template #prefix>
                  <el-icon><User /></el-icon>
                </template>
              </el-input>
            </el-form-item>

            <el-form-item label="邮箱">
              <div class="email-field">
                <el-input v-model="form.email" placeholder="请输入邮箱" clearable>
                  <template #prefix>
                    <el-icon><Message /></el-icon>
                  </template>
                </el-input>
                <el-tag
                  v-if="form.email && !emailChanged"
                  :type="form.email_verified ? 'success' : 'warning'"
                  size="small"
                  effect="light"
                  class="email-tag"
                >
                  {{ form.email_verified ? '已验证' : '未验证' }}
                </el-tag>
                <el-button
                  v-if="form.email && !form.email_verified && !emailChanged && !verifyingCurrentEmail"
                  type="warning"
                  size="small"
                  plain
                  @click="startVerifyCurrentEmail"
                >
                  立即验证
                </el-button>
              </div>
              <div v-if="emailChanged || verifyingCurrentEmail" class="email-verify-row">
                <el-alert v-if="emailChanged" type="warning" :closable="false" show-icon class="verify-alert">
                  邮箱已修改，请发送验证码至新邮箱完成验证
                </el-alert>
                <el-alert v-else type="info" :closable="false" show-icon class="verify-alert">
                  正在验证当前邮箱，请发送验证码完成验证
                </el-alert>
                <div class="verify-input-row">
                  <el-input
                    v-model="emailCode"
                    placeholder="请输入验证码"
                    maxlength="10"
                    class="code-input"
                    @keyup.enter="handleSave"
                  >
                    <template #prefix>
                      <el-icon><Key /></el-icon>
                    </template>
                  </el-input>
                  <el-button
                    :disabled="emailCountdown > 0 || sendingEmailCode"
                    :loading="sendingEmailCode"
                    @click="sendEmailCode"
                    class="send-code-btn"
                  >
                    {{ emailCountdown > 0 ? `${emailCountdown}s` : '发送验证码' }}
                  </el-button>
                  <el-button
                    type="success"
                    :loading="saving"
                    :disabled="!emailCode.trim()"
                    @click="handleSave"
                    class="confirm-code-btn"
                  >
                    确认验证
                  </el-button>
                  <el-button v-if="verifyingCurrentEmail" @click="cancelVerifyCurrentEmail">
                    取消
                  </el-button>
                </div>
              </div>
            </el-form-item>

            <el-form-item label="手机号">
              <el-input v-model="form.phone" placeholder="请输入手机号" maxlength="20" clearable>
                <template #prefix>
                  <el-icon><Iphone /></el-icon>
                </template>
              </el-input>
            </el-form-item>

            <el-form-item class="switch-item">
              <div class="switch-row">
                <div class="switch-info">
                  <span class="switch-label">采集通知</span>
                  <span class="switch-desc">新文章采集完成后接收通知提醒</span>
                </div>
                <el-switch v-model="form.notify_on_crawl" />
              </div>
            </el-form-item>
          </el-form>
        </el-col>
      </el-row>
    </el-card>

    <!-- 修改密码 -->
    <el-card shadow="hover" class="password-card">
      <template #header>
        <div class="card-header">
          <el-icon><Lock /></el-icon>
          <span>修改密码</span>
        </div>
      </template>

      <el-form
        ref="passwordFormRef"
        :model="passwordForm"
        :rules="passwordRules"
        label-position="top"
        class="password-form"
      >
        <el-row :gutter="20">
          <el-col :xs="24" :sm="8">
            <el-form-item label="原密码" prop="old_password">
              <el-input
                v-model="passwordForm.old_password"
                type="password"
                show-password
                placeholder="请输入原密码"
                autocomplete="current-password"
              />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="新密码" prop="new_password">
              <el-input
                v-model="passwordForm.new_password"
                type="password"
                show-password
                placeholder="至少 8 位字符"
                autocomplete="new-password"
              />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="确认新密码" prop="confirm_password">
              <el-input
                v-model="passwordForm.confirm_password"
                type="password"
                show-password
                placeholder="请再次输入新密码"
                autocomplete="new-password"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <div class="password-actions">
          <el-button type="primary" :loading="changingPassword" @click="handleChangePassword">
            确认修改密码
          </el-button>
          <el-button @click="resetPasswordForm">重置</el-button>
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Check, Camera, Loading, InfoFilled,
  User, Message, Iphone, Lock, Key,
} from '@element-plus/icons-vue'
import { profileApi } from '../api'
import { authState } from '../auth'

// ===== 资料表单 =====
const form = reactive({
  display_name: '',
  username: '',
  email: '',
  phone: '',
  avatar: '',
  email_verified: false,
  notify_on_crawl: true,
})

const saving = ref(false)
const loading = ref(false)

// 邮箱修改验证码
const originalEmail = ref('')
const emailCode = ref('')
const emailCountdown = ref(0)
const sendingEmailCode = ref(false)
const verifyingCurrentEmail = ref(false)
let emailCountdownTimer = null

const emailChanged = computed(() => {
  return form.email.trim() !== '' && form.email.trim() !== originalEmail.value.trim()
})

function startVerifyCurrentEmail() {
  verifyingCurrentEmail.value = true
  emailCode.value = ''
}

function cancelVerifyCurrentEmail() {
  verifyingCurrentEmail.value = false
  emailCode.value = ''
}

// 用户名首字母（无头像时占位）
const userInitial = computed(() => {
  const value = form.display_name || form.username || '用'
  return value.slice(0, 1).toUpperCase()
})

// 头像地址：本地预览优先，否则使用服务端地址
const avatarPreview = ref('')
const avatarUrl = computed(() => avatarPreview.value || form.avatar || '')

// ===== 头像上传 =====
const fileInputRef = ref(null)
const avatarUploading = ref(false)
const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
const MAX_AVATAR_SIZE = 5 * 1024 * 1024

function triggerAvatarUpload() {
  if (avatarUploading.value) return
  fileInputRef.value?.click()
}

async function handleAvatarChange(e) {
  const file = e.target.files?.[0]
  // 重置 input，保证重复选择同一文件可触发 change
  e.target.value = ''
  if (!file) return

  if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
    ElMessage.error('仅支持 JPG / PNG / WebP / GIF 格式')
    return
  }
  if (file.size > MAX_AVATAR_SIZE) {
    ElMessage.error('头像文件不能超过 5MB')
    return
  }

  // 生成本地预览
  avatarPreview.value = URL.createObjectURL(file)
  avatarUploading.value = true
  try {
    const { data } = await profileApi.uploadAvatar(file)
    applyProfile(data)
    ElMessage.success('头像更新成功')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '头像上传失败')
  } finally {
    avatarUploading.value = false
    // 清理本地预览，统一使用服务端地址，避免内存泄漏
    if (avatarPreview.value) {
      URL.revokeObjectURL(avatarPreview.value)
      avatarPreview.value = ''
    }
  }
}

// ===== 同步 authState，使顶部头像/昵称保持一致 =====
function applyProfile(data) {
  form.display_name = data.display_name || ''
  form.username = data.username || ''
  form.email = data.email || ''
  originalEmail.value = data.email || ''
  emailCode.value = ''
  verifyingCurrentEmail.value = false
  form.phone = data.phone || ''
  form.avatar = data.avatar || ''
  form.email_verified = !!data.email_verified
  form.notify_on_crawl = data.notify_on_crawl !== false
  if (authState.user) {
    authState.user.display_name = form.display_name
    authState.user.username = form.username
    authState.user.email = form.email
    authState.user.phone = form.phone
    authState.user.avatar = form.avatar
    authState.user.email_verified = form.email_verified
    authState.user.notify_on_crawl = form.notify_on_crawl
  }
}

// ===== 加载资料 =====
async function loadProfile() {
  loading.value = true
  try {
    const { data } = await profileApi.get()
    applyProfile(data)
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '加载个人信息失败')
  } finally {
    loading.value = false
  }
}

// ===== 保存资料 =====
async function handleSave() {
  if (saving.value) return
  // 邮箱变更时必须有验证码
  if (emailChanged.value && !emailCode.value.trim()) {
    ElMessage.warning('邮箱已修改，请先发送验证码并输入')
    return
  }
  // 验证当前邮箱时必须有验证码
  if (verifyingCurrentEmail.value && !emailCode.value.trim()) {
    ElMessage.warning('请先发送验证码并输入')
    return
  }
  saving.value = true
  try {
    const payload = {
      display_name: form.display_name,
      email: form.email,
      phone: form.phone,
      notify_on_crawl: form.notify_on_crawl,
    }
    if (emailChanged.value || verifyingCurrentEmail.value) {
      payload.email_verification_code = emailCode.value.trim()
    }
    const { data } = await profileApi.update(payload)
    applyProfile(data)
    verifyingCurrentEmail.value = false
    ElMessage.success('个人信息已保存')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '保存失败，请重试')
  } finally {
    saving.value = false
  }
}

// ===== 发送邮箱修改验证码 =====
function startEmailCountdown() {
  emailCountdown.value = 60
  emailCountdownTimer = setInterval(() => {
    emailCountdown.value -= 1
    if (emailCountdown.value <= 0) {
      clearInterval(emailCountdownTimer)
      emailCountdownTimer = null
    }
  }, 1000)
}

async function sendEmailCode() {
  const email = form.email.trim()
  if (!email) {
    ElMessage.warning('请输入邮箱')
    return
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    ElMessage.warning('邮箱格式不正确')
    return
  }
  sendingEmailCode.value = true
  try {
    await profileApi.sendChangeEmailCode({ email })
    ElMessage.success(verifyingCurrentEmail.value ? '验证码已发送至当前邮箱' : '验证码已发送至新邮箱')
    startEmailCountdown()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '验证码发送失败')
  } finally {
    sendingEmailCode.value = false
  }
}

// ===== 修改密码 =====
const passwordFormRef = ref(null)
const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})
const changingPassword = ref(false)

const validateConfirm = (rule, value, callback) => {
  if (!value) {
    callback(new Error('请再次输入新密码'))
  } else if (value !== passwordForm.new_password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const passwordRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, max: 128, message: '密码长度为 8-128 位', trigger: 'blur' },
  ],
  confirm_password: [{ required: true, validator: validateConfirm, trigger: 'blur' }],
}

async function handleChangePassword() {
  if (changingPassword.value) return
  try {
    await passwordFormRef.value.validate()
  } catch {
    return
  }
  changingPassword.value = true
  try {
    await profileApi.changePassword({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password,
    })
    ElMessage.success('密码修改成功')
    resetPasswordForm()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '密码修改失败')
  } finally {
    changingPassword.value = false
  }
}

function resetPasswordForm() {
  passwordForm.old_password = ''
  passwordForm.new_password = ''
  passwordForm.confirm_password = ''
  passwordFormRef.value?.clearValidate()
}

onMounted(() => {
  loadProfile()
})

onUnmounted(() => {
  if (emailCountdownTimer) {
    clearInterval(emailCountdownTimer)
    emailCountdownTimer = null
  }
})
</script>

<style scoped>
.profile-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 页面标题 */
.page-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: #1d1e1f;
}
.page-desc {
  font-size: 13px;
  color: #999;
}

/* 卡片通用 */
.profile-card,
.password-card {
  border-radius: 8px;
}
:deep(.el-card__header) {
  padding: 14px 20px;
  border-bottom: 1px solid #f0f0f0;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #1d1e1f;
  font-size: 15px;
}

/* 头像区域 */
.avatar-col {
  border-right: 1px solid #f0f0f0;
}
.avatar-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 16px 16px;
  gap: 16px;
}
.avatar-wrapper {
  position: relative;
  width: 128px;
  height: 128px;
  border-radius: 50%;
  cursor: pointer;
  overflow: hidden;
  background: linear-gradient(135deg, #409eff, #79bbff);
  box-shadow: 0 6px 18px rgba(64, 158, 255, 0.25);
  flex-shrink: 0;
}
.avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.avatar-placeholder {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 52px;
  font-weight: 700;
  user-select: none;
}
.avatar-mask {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  color: #fff;
  font-size: 13px;
  background: rgba(0, 0, 0, 0.45);
  opacity: 0;
  transition: opacity 0.25s ease;
}
.avatar-wrapper:hover .avatar-mask,
.avatar-wrapper:focus-visible .avatar-mask {
  opacity: 1;
}
.avatar-loading {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.6);
  color: #409eff;
}
.avatar-meta {
  text-align: center;
}
.avatar-name {
  font-size: 17px;
  font-weight: 600;
  color: #1d1e1f;
}
.avatar-sub {
  font-size: 13px;
  color: #999;
  margin-top: 2px;
}
.avatar-tips {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: #c0c4cc;
}
.hidden-input {
  display: none;
}

/* 表单区域 */
.form-col {
  padding: 8px 8px 8px 24px;
}
.form-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.form-title {
  font-size: 16px;
  font-weight: 600;
  color: #1d1e1f;
}
.profile-form :deep(.el-form-item) {
  margin-bottom: 18px;
}
.email-tag {
  margin: 0;
  flex-shrink: 0;
}

.email-field {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.email-field .el-input {
  flex: 1;
}

.email-verify-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
  width: 100%;
}

.verify-alert {
  margin: 0;
}

.verify-input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.verify-input-row .code-input {
  flex: 1;
}

.send-code-btn {
  flex-shrink: 0;
  white-space: nowrap;
}

.confirm-code-btn {
  flex-shrink: 0;
  white-space: nowrap;
}

.switch-item :deep(.el-form-item__content) {
  justify-content: flex-start;
}
.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 12px 16px;
  background: #f7f9fc;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
}
.switch-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.switch-label {
  font-size: 14px;
  font-weight: 600;
  color: #1d1e1f;
}
.switch-desc {
  font-size: 12px;
  color: #999;
}

/* 修改密码 */
.password-form :deep(.el-form-item) {
  margin-bottom: 18px;
}
.password-actions {
  display: flex;
  gap: 12px;
  margin-top: 4px;
}

/* 响应式：小屏下头像与表单纵向排列 */
@media (max-width: 991px) {
  .avatar-col {
    border-right: none;
    border-bottom: 1px solid #f0f0f0;
    padding-bottom: 8px;
  }
  .form-col {
    padding: 20px 8px 8px;
  }
  .avatar-panel {
    flex-direction: row;
    flex-wrap: wrap;
    justify-content: center;
    text-align: center;
  }
  .avatar-wrapper {
    width: 96px;
    height: 96px;
  }
  .avatar-placeholder {
    font-size: 40px;
  }
}
</style>
