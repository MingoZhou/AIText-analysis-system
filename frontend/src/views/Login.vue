<template>
  <main class="auth-page">
    <!-- ============================ 左侧 3D 舞台 ============================ -->
    <section class="visual-stage">
      <!-- 赛博网格背景 -->
      <div class="cyber-grid"></div>
      <!-- Three.js WebGL 容器 -->
      <div ref="webglContainer" class="webgl-container"></div>

      <!-- 品牌头部 -->
      <header class="brand-header">
        <div class="brand-logo-wrapper">
          <div class="brand-icon-box">
            <el-icon :size="24"><DataAnalysis /></el-icon>
          </div>
          <span class="brand-title">策知</span>
        </div>
        <div class="brand-sub">行业资讯与政策智能分析平台</div>

        <div class="status-pill">
          <div class="pulse-dot"></div>
          <span>AI 策知系统：节点自动追踪中</span>
        </div>

        <ul class="feature-bullets">
          <li class="feature-item" v-for="(f, i) in features" :key="i" :style="{ animationDelay: `${0.3 + i * 0.1}s` }">
            <span class="feature-check"></span>
            {{ f }}
          </li>
        </ul>
      </header>

      <!-- HUD 悬浮科技卡片 -->
      <div class="hud-overlay">
        <div class="hud-card card-pos-1">
          <div class="hud-icon"><el-icon><DataLine /></el-icon></div>
          <div>
            <div class="hud-num">{{ animStats.articles }}+</div>
            <div class="hud-label">采集行业文章 / 日</div>
          </div>
        </div>
        <div class="hud-card card-pos-2">
          <div class="hud-icon"><el-icon><TrendCharts /></el-icon></div>
          <div>
            <div class="hud-num">{{ animStats.keywords }}+</div>
            <div class="hud-label">核心监控关键词</div>
          </div>
        </div>
        <div class="hud-card card-pos-3">
          <div class="hud-icon"><el-icon><MagicStick /></el-icon></div>
          <div>
            <div class="hud-num">AI Engine</div>
            <div class="hud-label">实时追寻与归因分析</div>
          </div>
        </div>
      </div>

      <!-- 底部追踪信息 -->
      <div class="tracker-info-box">
        <span class="tracker-label">TARGET LOCK:</span>
        <span class="tracker-target">{{ currentTarget }}</span>
        <span class="tracker-sep">|</span>
        <span class="tracker-status">STATUS: PARSING POLICY STREAM</span>
      </div>
    </section>

    <!-- ============================ 右侧登录/注册 ============================ -->
    <section class="login-stage">
      <div class="login-card">
        <!-- 移动端品牌 -->
        <div class="mobile-brand">
          <el-icon :size="24"><DataAnalysis /></el-icon>
          <span>策知</span>
        </div>

        <!-- Tab 切换 -->
        <div class="tab-group">
          <div class="tab-btn" :class="{ active: mode === 'login' }" @click="mode = 'login'">登录</div>
          <div class="tab-btn" :class="{ active: mode === 'register' }" @click="mode = 'register'">注册</div>
        </div>

        <transition name="fade-slide" mode="out-in">
          <!-- 登录 -->
          <div v-if="mode === 'login'" key="login" class="form-section">
            <h2 class="welcome-title">欢迎回来</h2>
            <p class="welcome-sub">登录以进入策知智能决策终端</p>
            <form @submit.prevent="submitLogin">
              <div class="input-box">
                <label class="input-label">账号 / 用户名</label>
                <el-input
                  v-model="loginForm.username"
                  size="large"
                  autocomplete="username"
                  :prefix-icon="User"
                  placeholder="请输入用户名"
                />
              </div>
              <div class="input-box">
                <label class="input-label">访问密码</label>
                <el-input
                  v-model="loginForm.password"
                  size="large"
                  type="password"
                  show-password
                  autocomplete="current-password"
                  :prefix-icon="Lock"
                  placeholder="请输入密码"
                />
              </div>
              <el-button class="submit-btn" size="large" native-type="submit" :loading="submitting">
                <span>进 入 系 统</span>
              </el-button>
              <div class="form-footer">
                <el-checkbox v-model="rememberDevice">记住此设备</el-checkbox>
                <span class="forgot-link">忘记密码？</span>
              </div>
            </form>
          </div>

          <!-- 注册 -->
          <div v-else key="register" class="form-section">
            <h2 class="welcome-title">创建账号</h2>
            <p class="welcome-sub">注册新账号开始使用策知平台</p>
            <form @submit.prevent="submitRegister">
              <div class="input-box">
                <label class="input-label">用户名</label>
                <el-input v-model="registerForm.username" size="large" autocomplete="username" :prefix-icon="User" placeholder="至少 3 个字符" />
              </div>
              <div class="input-box">
                <label class="input-label">显示名称</label>
                <el-input v-model="registerForm.display_name" size="large" :prefix-icon="Postcard" placeholder="可选" />
              </div>
              <div class="input-box">
                <label class="input-label">邮箱</label>
                <el-input v-model="registerForm.email" size="large" type="email" :prefix-icon="Message" placeholder="请输入邮箱" />
              </div>
              <div class="input-box">
                <label class="input-label">验证码</label>
                <el-input v-model="registerForm.verificationCode" class="verify-input" size="large" :prefix-icon="Key" placeholder="请输入验证码">
                  <template #append>
                    <el-button :disabled="countdown > 0" :loading="sendingCode" @click="sendVerificationCode">
                      {{ countdown > 0 ? `${countdown}s` : '发送验证码' }}
                    </el-button>
                  </template>
                </el-input>
              </div>
              <div class="input-box">
                <label class="input-label">密码</label>
                <el-input v-model="registerForm.password" size="large" type="password" show-password autocomplete="new-password" :prefix-icon="Lock" placeholder="至少 8 个字符" />
              </div>
              <div class="input-box">
                <label class="input-label">确认密码</label>
                <el-input v-model="registerForm.confirmPassword" size="large" type="password" show-password autocomplete="new-password" :prefix-icon="Lock" placeholder="再次输入密码" />
              </div>
              <el-button class="submit-btn" size="large" native-type="submit" :loading="submitting">
                <span>注 册 并 进 入</span>
              </el-button>
            </form>
          </div>
        </transition>
      </div>
    </section>
  </main>
</template>

<script setup>
import { reactive, ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import gsap from 'gsap'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, Postcard, User, Message, Key, DataAnalysis, DataLine, TrendCharts, MagicStick } from '@element-plus/icons-vue'
import { loginAccount, registerAccount } from '../auth'
import { profileApi } from '../api'

const route = useRoute()
const router = useRouter()
const mode = ref('login')
const submitting = ref(false)
const sendingCode = ref(false)
const countdown = ref(0)
let countdownTimer = null
const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', display_name: '', email: '', verificationCode: '', password: '', confirmPassword: '' })
const rememberDevice = ref(Boolean(localStorage.getItem('cezhi-remember-device')))

const features = ['关键词驱动全球实时采集', '多源异构数据融合与知识图谱', 'AI 大模型智能摘要与趋势推演', '三维数据流多维可视化面板']
const animStats = reactive({ articles: 0, keywords: 0 })
const currentTarget = ref('BEIJING [116.4E, 39.9N]')

/* ======================== Three.js 3D 地球 ======================== */
const webglContainer = ref(null)
let scene = null
let camera = null
let renderer = null
let controls = null
let globeGroup = null
let mainGlobe = null
let innerSphere = null
let atmosphere = null
let atmosphereGlow = null
let equatorRing = null
let nodesGroup = null
let arcsGroup = null
let waveGroup = null
let starsField = null
let targetRing = null
let flyingDots = []
let waveRings = []
let animationId = null
let targetSwitchTimer = null
let resizeHandlerRef = null
let clock = null

const cities = [
  { name: 'BEIJING [116.4E, 39.9N]', lat: 39.9, lon: 116.4 },
  { name: 'LONDON [0.1W, 51.5N]', lat: 51.5, lon: -0.1 },
  { name: 'NEW YORK [74.0W, 40.7N]', lat: 40.7, lon: -74.0 },
  { name: 'TOKYO [139.6E, 35.6N]', lat: 35.6, lon: 139.6 },
  { name: 'SINGAPORE [103.8E, 1.3N]', lat: 1.3, lon: 103.8 },
  { name: 'BRUSSELS [4.3E, 50.8N]', lat: 50.8, lon: 4.3 },
]

function latLonToVector3(lat, lon, r) {
  const phi = (90 - lat) * (Math.PI / 180)
  const theta = (lon + 180) * (Math.PI / 180)
  return new THREE.Vector3(
    -(r * Math.sin(phi) * Math.cos(theta)),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta)
  )
}

function initThreeJS() {
  const container = webglContainer.value
  if (!container) return
  const width = container.clientWidth
  const height = container.clientHeight

  // 场景与相机
  scene = new THREE.Scene()
  scene.fog = new THREE.Fog(0x030712, 200, 800)
  camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 2000)
  camera.position.set(20, 15, 230)

  renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
  renderer.setSize(width, height)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  container.appendChild(renderer.domElement)

  // ---- OrbitControls 拖拽交互 ----
  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.enableZoom = true
  controls.enablePan = false
  controls.autoRotate = true
  controls.autoRotateSpeed = 0.4
  controls.minDistance = 120
  controls.maxDistance = 400

  // ---- 星空背景 ----
  const starCount = 8000
  const starPositions = new Float32Array(starCount * 3)
  const starColors = new Float32Array(starCount * 3)
  for (let i = 0; i < starCount; i++) {
    starPositions[i * 3] = Math.random() * 2 - 1
    starPositions[i * 3 + 1] = Math.random() * 2 - 1
    starPositions[i * 3 + 2] = Math.random() * 2 - 1
    const c = new THREE.Color()
    c.setHSL(Math.random() * 0.2 + 0.5, 0.55, Math.random() * 0.25 + 0.55)
    starColors[i * 3] = c.r
    starColors[i * 3 + 1] = c.g
    starColors[i * 3 + 2] = c.b
  }
  const starGeo = new THREE.BufferGeometry()
  starGeo.setAttribute('position', new THREE.BufferAttribute(starPositions, 3))
  starGeo.setAttribute('color', new THREE.BufferAttribute(starColors, 3))
  const starMat = new THREE.PointsMaterial({
    size: 1.2, vertexColors: true, transparent: true, opacity: 0.8,
    blending: THREE.AdditiveBlending, sizeAttenuation: true,
  })
  starsField = new THREE.Points(starGeo, starMat)
  starsField.scale.set(500, 500, 500)
  scene.add(starsField)

  // ---- 地球组 ----
  globeGroup = new THREE.Group()
  globeGroup.position.set(35, 0, 0)
  scene.add(globeGroup)

  const radius = 70

  // 1) 高密度粒子球体
  const particleCount = 4500
  const positions = new Float32Array(particleCount * 3)
  const colors = new Float32Array(particleCount * 3)
  const color1 = new THREE.Color(0x00f5a0)
  const color2 = new THREE.Color(0x00d2ff)
  for (let i = 0; i < particleCount; i++) {
    const phi = Math.acos(-1 + (2 * i) / particleCount)
    const theta = Math.sqrt(particleCount * Math.PI) * phi
    const x = radius * Math.cos(theta) * Math.sin(phi)
    const y = radius * Math.sin(theta) * Math.sin(phi)
    const z = radius * Math.cos(phi)
    positions[i * 3] = x
    positions[i * 3 + 1] = y
    positions[i * 3 + 2] = z
    const mixedColor = color1.clone().lerp(color2, (y + radius) / (2 * radius))
    colors[i * 3] = mixedColor.r
    colors[i * 3 + 1] = mixedColor.g
    colors[i * 3 + 2] = mixedColor.b
  }
  const particleGeo = new THREE.BufferGeometry()
  particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  particleGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  const particleMat = new THREE.PointsMaterial({ size: 1.4, vertexColors: true, transparent: true, opacity: 0.85 })
  mainGlobe = new THREE.Points(particleGeo, particleMat)
  globeGroup.add(mainGlobe)

  // 2) 内核发光球
  const innerGeo = new THREE.SphereGeometry(radius * 0.98, 32, 32)
  const innerMat = new THREE.MeshBasicMaterial({ color: 0x051d2d, transparent: true, opacity: 0.6 })
  innerSphere = new THREE.Mesh(innerGeo, innerMat)
  globeGroup.add(innerSphere)

  // 3) 大气层线框
  const atmoGeo = new THREE.SphereGeometry(radius * 1.05, 24, 24)
  const atmoMat = new THREE.MeshBasicMaterial({ color: 0x00f5a0, wireframe: true, transparent: true, opacity: 0.08 })
  atmosphere = new THREE.Mesh(atmoGeo, atmoMat)
  globeGroup.add(atmosphere)

  // 3b) 大气光圈（用更大的半透明球壳模拟 Fresnel 辉光）
  const glowGeo = new THREE.SphereGeometry(radius * 1.15, 32, 32)
  const glowMat = new THREE.MeshBasicMaterial({
    color: 0x00f5a0, transparent: true, opacity: 0.06, side: THREE.BackSide,
  })
  atmosphereGlow = new THREE.Mesh(glowGeo, glowMat)
  globeGroup.add(atmosphereGlow)

  // 4) 赤道扫描环
  const ringGeo = new THREE.RingGeometry(radius * 1.25, radius * 1.27, 64)
  const ringMat = new THREE.MeshBasicMaterial({ color: 0x00d2ff, side: THREE.DoubleSide, transparent: true, opacity: 0.35 })
  equatorRing = new THREE.Mesh(ringGeo, ringMat)
  equatorRing.rotation.x = Math.PI / 2 + 0.3
  globeGroup.add(equatorRing)

  // 5) 城市节点 + 飞线弧
  nodesGroup = new THREE.Group()
  arcsGroup = new THREE.Group()
  waveGroup = new THREE.Group()
  globeGroup.add(nodesGroup)
  globeGroup.add(arcsGroup)
  globeGroup.add(waveGroup)

  const cityVectors = cities.map(c => {
    const vec = latLonToVector3(c.lat, c.lon, radius)
    // 城市发光点
    const dotGeo = new THREE.SphereGeometry(1.5, 8, 8)
    const dotMat = new THREE.MeshBasicMaterial({ color: 0x00f5a0 })
    const dot = new THREE.Mesh(dotGeo, dotMat)
    dot.position.copy(vec)
    nodesGroup.add(dot)

    // 城市标注光柱（小型竖线）
    const pillarGeo = new THREE.CylinderGeometry(0.3, 0.3, 8, 6)
    const pillarMat = new THREE.MeshBasicMaterial({ color: 0x00f5a0, transparent: true, opacity: 0.5 })
    const pillar = new THREE.Mesh(pillarGeo, pillarMat)
    pillar.position.copy(vec.clone().normalize().multiplyScalar(radius + 4))
    pillar.lookAt(0, 0, 0)
    pillar.rotateX(Math.PI / 2)
    nodesGroup.add(pillar)

    // 扩散波纹圈
    const waveGeo = new THREE.RingGeometry(2, 2.5, 32)
    const waveMat = new THREE.MeshBasicMaterial({
      color: 0x00f5a0, side: THREE.DoubleSide, transparent: true, opacity: 0.8,
    })
    const wave = new THREE.Mesh(waveGeo, waveMat)
    wave.position.copy(vec)
    wave.lookAt(0, 0, 0)
    wave.userData = { phase: Math.random() * 2, baseScale: 1, vec: vec.clone() }
    waveGroup.add(wave)
    waveRings.push(wave)

    return { ...c, vec }
  })

  // 飞线弧 + 移动粒子
  const arcCurves = []
  for (let i = 0; i < cityVectors.length; i++) {
    for (let j = i + 1; j < cityVectors.length; j++) {
      const v1 = cityVectors[i].vec
      const v2 = cityVectors[j].vec
      const mid = v1.clone().add(v2).multiplyScalar(0.5)
      const midLen = mid.length()
      mid.normalize().multiplyScalar(midLen * 1.4)
      const curve = new THREE.QuadraticBezierCurve3(v1, mid, v2)
      const points = curve.getPoints(50)
      const curveGeo = new THREE.BufferGeometry().setFromPoints(points)
      const curveMat = new THREE.LineBasicMaterial({ color: 0x00f5a0, transparent: true, opacity: 0.25 })
      arcsGroup.add(new THREE.Line(curveGeo, curveMat))
      arcCurves.push(curve)
    }
  }

  // 沿飞线移动的粒子
  const flyDotGeo = new THREE.SphereGeometry(0.8, 8, 8)
  const flyDotMat = new THREE.MeshBasicMaterial({ color: 0xF8D764, transparent: true, opacity: 0.9 })
  for (let i = 0; i < Math.min(arcCurves.length, 8); i++) {
    const dot = new THREE.Mesh(flyDotGeo, flyDotMat.clone())
    dot.userData = {
      curve: arcCurves[i % arcCurves.length],
      progress: Math.random(),
      speed: 0.002 + Math.random() * 0.003,
    }
    arcsGroup.add(dot)
    flyingDots.push(dot)
  }

  // 6) 目标锁定圈
  const targetRingGeo = new THREE.RingGeometry(3, 4, 16)
  const targetRingMat = new THREE.MeshBasicMaterial({ color: 0x00d2ff, side: THREE.DoubleSide, transparent: true, opacity: 0.9 })
  targetRing = new THREE.Mesh(targetRingGeo, targetRingMat)
  globeGroup.add(targetRing)

  // 7) 自动追踪切换
  let currentCityIndex = 0
  function switchTarget() {
    currentCityIndex = (currentCityIndex + 1) % cityVectors.length
    const target = cityVectors[currentCityIndex]
    currentTarget.value = target.name
    gsap.to(targetRing.position, {
      x: target.vec.x, y: target.vec.y, z: target.vec.z,
      duration: 1.5, ease: 'power2.inOut',
      onUpdate: () => {
        targetRing.lookAt(globeGroup.position.clone().add(targetRing.position).multiplyScalar(2))
      },
    })
    gsap.fromTo(targetRing.scale,
      { x: 0.5, y: 0.5, z: 0.5 },
      { x: 1.8, y: 1.8, z: 1.8, duration: 1.2, repeat: 1, yoyo: true }
    )
  }
  switchTarget()
  targetSwitchTimer = setInterval(switchTarget, 4000)

  clock = new THREE.Timer()

  // 8) 动画循环
  function animate() {
    animationId = requestAnimationFrame(animate)
    clock.update()
    const dt = clock.getDelta()
    const t = clock.getElapsed()

    // 地球自转
    mainGlobe.rotation.y += 0.002
    innerSphere.rotation.y += 0.002
    nodesGroup.rotation.y += 0.002
    arcsGroup.rotation.y += 0.002
    waveGroup.rotation.y += 0.002
    equatorRing.rotation.z -= 0.001

    // 星空缓慢旋转
    starsField.rotation.y += 0.00015

    // 扩散波纹动画
    for (const wave of waveRings) {
      wave.userData.phase += dt * 0.6
      if (wave.userData.phase > 2) wave.userData.phase = 0
      const s = 1 + wave.userData.phase * 3
      wave.scale.set(s, s, s)
      wave.material.opacity = Math.max(0, 0.8 - wave.userData.phase * 0.4)
    }

    // 飞线移动粒子
    for (const dot of flyingDots) {
      dot.userData.progress += dot.userData.speed
      if (dot.userData.progress > 1) dot.userData.progress = 0
      const pos = dot.userData.curve.getPoint(dot.userData.progress)
      dot.position.copy(pos)
      // 尾部透明度渐变
      const fade = Math.sin(dot.userData.progress * Math.PI)
      dot.material.opacity = 0.3 + fade * 0.7
    }

    controls.update()
    renderer.render(scene, camera)
  }
  animate()

  // 9) 窗口适配
  resizeHandlerRef = () => {
    if (!container || !camera || !renderer) return
    const w = container.clientWidth
    const h = container.clientHeight
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    renderer.setSize(w, h)
  }
  window.addEventListener('resize', resizeHandlerRef)
}

function cleanupThreeJS() {
  if (animationId) { cancelAnimationFrame(animationId); animationId = null }
  if (targetSwitchTimer) { clearInterval(targetSwitchTimer); targetSwitchTimer = null }
  if (resizeHandlerRef) { window.removeEventListener('resize', resizeHandlerRef); resizeHandlerRef = null }
  if (targetRing) { gsap.killTweensOf(targetRing.position); gsap.killTweensOf(targetRing.scale) }
  if (controls) { controls.dispose(); controls = null }
  if (renderer) {
    renderer.dispose()
    if (renderer.domElement && renderer.domElement.parentNode) {
      renderer.domElement.parentNode.removeChild(renderer.domElement)
    }
  }
  flyingDots = []
  waveRings = []
  if (scene) {
    scene.traverse(obj => {
      if (obj.geometry) obj.geometry.dispose()
      if (obj.material) {
        if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose())
        else obj.material.dispose()
      }
    })
  }
  scene = camera = renderer = globeGroup = null
}

onMounted(() => {
  // 数字递增动画
  const target1 = 1280, target2 = 36
  let c1 = 0, c2 = 0
  const interval = setInterval(() => {
    c1 += Math.ceil(target1 / 30)
    c2 += Math.ceil(target2 / 30)
    if (c1 >= target1) c1 = target1
    if (c2 >= target2) c2 = target2
    animStats.articles = c1
    animStats.keywords = c2
    if (c1 >= target1 && c2 >= target2) clearInterval(interval)
  }, 50)

  nextTick(() => initThreeJS())
})

onUnmounted(() => {
  if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
  cleanupThreeJS()
  if (rememberDevice.value) localStorage.setItem('cezhi-remember-device', '1')
  else localStorage.removeItem('cezhi-remember-device')
})

function errorMessage(error) {
  const detail = error.response?.data?.detail
  return typeof detail === 'string' ? detail : '操作失败，请稍后重试'
}

function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

function startCountdown() {
  countdown.value = 60
  countdownTimer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) { clearInterval(countdownTimer); countdownTimer = null }
  }, 1000)
}

async function sendVerificationCode() {
  const email = registerForm.email.trim()
  if (!email) { ElMessage.warning('请输入邮箱'); return }
  if (!isValidEmail(email)) { ElMessage.warning('邮箱格式不正确'); return }
  sendingCode.value = true
  try {
    await profileApi.sendCode({ email })
    ElMessage.success('验证码已发送，请查收邮箱')
    startCountdown()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    sendingCode.value = false
  }
}

async function enterSystem() {
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
  await router.replace(redirect)
}

async function submitLogin() {
  if (!loginForm.username.trim() || !loginForm.password) {
    ElMessage.warning('请输入用户名和密码'); return
  }
  submitting.value = true
  try {
    await loginAccount({ username: loginForm.username, password: loginForm.password })
    if (rememberDevice.value) localStorage.setItem('cezhi-remember-device', '1')
    else localStorage.removeItem('cezhi-remember-device')
    await enterSystem()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    submitting.value = false
  }
}

async function submitRegister() {
  if (registerForm.password.length < 8) { ElMessage.warning('密码至少需要 8 个字符'); return }
  if (registerForm.password !== registerForm.confirmPassword) { ElMessage.warning('两次输入的密码不一致'); return }
  if (!registerForm.email.trim()) { ElMessage.warning('请输入邮箱'); return }
  if (!isValidEmail(registerForm.email.trim())) { ElMessage.warning('邮箱格式不正确'); return }
  if (!registerForm.verificationCode.trim()) { ElMessage.warning('请输入验证码'); return }
  submitting.value = true
  try {
    await registerAccount({
      username: registerForm.username,
      password: registerForm.password,
      display_name: registerForm.display_name,
      email: registerForm.email.trim(),
      verification_code: registerForm.verificationCode.trim(),
    })
    await enterSystem()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
/* ====================== 全局布局 ====================== */
.auth-page {
  display: flex;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: #030712;
  color: #f3f4f6;
  font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', -apple-system, sans-serif;
}

/* ====================== 左侧 3D 舞台 ====================== */
.visual-stage {
  flex: 1.25;
  position: relative;
  background: radial-gradient(circle at 40% 50%, #061527 0%, #030712 100%);
  overflow: hidden;
}

.cyber-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(0, 245, 160, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 245, 160, 0.03) 1px, transparent 1px);
  background-size: 40px 40px;
  pointer-events: none;
  z-index: 2;
}

.webgl-container {
  position: absolute;
  inset: 0;
  z-index: 1;
}

.webgl-container :deep(canvas) {
  display: block;
  width: 100% !important;
  height: 100% !important;
}

/* ====================== 品牌头部 ====================== */
.brand-header {
  position: absolute;
  top: 40px;
  left: 50px;
  z-index: 10;
  pointer-events: none;
}

.brand-logo-wrapper {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}

.brand-icon-box {
  width: 44px;
  height: 44px;
  background: rgba(0, 245, 160, 0.08);
  border: 1px solid rgba(0, 245, 160, 0.4);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 20px rgba(0, 245, 160, 0.25), inset 0 0 10px rgba(0, 245, 160, 0.15);
  backdrop-filter: blur(8px);
  color: #00f5a0;
}

.brand-title {
  font-size: 32px;
  font-weight: 800;
  letter-spacing: 3px;
  background: linear-gradient(135deg, #ffffff 30%, #00f5a0 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.brand-sub {
  font-size: 13px;
  color: #94a3b8;
  letter-spacing: 2px;
  margin-bottom: 24px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand-sub::before {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  background: #00f5a0;
  border-radius: 50%;
  box-shadow: 0 0 8px #00f5a0;
}

/* 状态追踪 Badge */
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 6px 14px;
  background: rgba(3, 7, 18, 0.6);
  border: 1px solid rgba(0, 245, 160, 0.3);
  border-radius: 20px;
  font-size: 11px;
  color: #00f5a0;
  letter-spacing: 1px;
  backdrop-filter: blur(10px);
  margin-bottom: 24px;
}

.pulse-dot {
  width: 8px;
  height: 8px;
  background: #00f5a0;
  border-radius: 50%;
  position: relative;
  flex-shrink: 0;
}

.pulse-dot::after {
  content: '';
  position: absolute;
  top: -3px;
  left: -3px;
  width: 14px;
  height: 14px;
  border: 1px solid #00f5a0;
  border-radius: 50%;
  animation: pulseRing 1.8s infinite ease-out;
}

@keyframes pulseRing {
  0% { transform: scale(0.5); opacity: 1; }
  100% { transform: scale(2.2); opacity: 0; }
}

/* 特性列表 */
.feature-bullets {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
  pointer-events: auto;
  padding: 0;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: #cbd5e1;
  padding: 8px 14px;
  background: rgba(15, 23, 42, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-left: 3px solid #00f5a0;
  border-radius: 0 8px 8px 0;
  backdrop-filter: blur(8px);
  width: fit-content;
  transition: all 0.3s ease;
  opacity: 0;
  animation: fadeInLeft 0.6s ease-out forwards;
}

@keyframes fadeInLeft {
  from { opacity: 0; transform: translateX(-24px); }
  to { opacity: 1; transform: translateX(0); }
}

.feature-item:hover {
  background: rgba(0, 245, 160, 0.1);
  border-color: rgba(0, 245, 160, 0.4);
  transform: translateX(6px);
}

.feature-check {
  width: 6px;
  height: 6px;
  background: #00f5a0;
  border-radius: 50%;
  box-shadow: 0 0 6px #00f5a0;
  flex-shrink: 0;
}

/* ====================== HUD 悬浮卡片 ====================== */
.hud-overlay {
  position: absolute;
  inset: 0;
  z-index: 5;
  pointer-events: none;
}

.hud-card {
  position: absolute;
  pointer-events: auto;
  background: rgba(8, 15, 28, 0.65);
  border: 1px solid rgba(0, 245, 160, 0.25);
  border-radius: 12px;
  padding: 14px 20px;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), inset 0 0 15px rgba(0, 245, 160, 0.05);
  display: flex;
  align-items: center;
  gap: 16px;
  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
  opacity: 0;
  animation: hudFadeIn 0.8s ease-out forwards;
}

@keyframes hudFadeIn {
  from { opacity: 0; transform: translateY(20px) scale(0.95); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.hud-card::before {
  content: '';
  position: absolute;
  top: -1px;
  left: 20%;
  width: 30px;
  height: 2px;
  background: #00f5a0;
  box-shadow: 0 0 10px #00f5a0;
}

.hud-card:hover {
  transform: translateY(-6px) scale(1.03);
  border-color: rgba(0, 245, 160, 0.6);
  box-shadow: 0 15px 35px rgba(0, 245, 160, 0.2);
}

.card-pos-1 { top: 18%; right: 10%; animation-delay: 0.5s; }
.card-pos-2 { top: 48%; right: 6%; animation-delay: 0.7s; }
.card-pos-3 { bottom: 18%; right: 12%; animation-delay: 0.9s; }

.hud-icon {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(0, 245, 160, 0.2), rgba(0, 180, 216, 0.1));
  border: 1px solid rgba(0, 245, 160, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: #00f5a0;
  flex-shrink: 0;
}

.hud-num {
  font-family: 'Orbitron', 'Consolas', monospace;
  font-size: 20px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: 1px;
}

.hud-label {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 2px;
}

/* 追踪信息栏 */
.tracker-info-box {
  position: absolute;
  bottom: 40px;
  left: 50px;
  z-index: 10;
  background: rgba(3, 7, 18, 0.7);
  border: 1px solid rgba(0, 210, 255, 0.3);
  border-radius: 8px;
  padding: 10px 16px;
  backdrop-filter: blur(10px);
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 12px;
  color: #94a3b8;
  font-family: 'Orbitron', 'Consolas', monospace;
}

.tracker-target {
  color: #00d2ff;
  font-weight: 600;
  transition: color 0.3s;
}

.tracker-sep { opacity: 0.4; }

/* ====================== 右侧登录区 ====================== */
.login-stage {
  flex: 0.85;
  background: #080d1a;
  border-left: 1px solid rgba(0, 245, 160, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  z-index: 20;
  box-shadow: -20px 0 50px rgba(0, 0, 0, 0.8);
}

.login-stage::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 1px;
  height: 100%;
  background: linear-gradient(180deg, transparent, #00f5a0, #00d2ff, transparent);
  opacity: 0.6;
}

.login-card {
  width: 380px;
  max-width: 100%;
  padding: 40px;
  background: rgba(13, 22, 38, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
  position: relative;
  overflow: hidden;
  animation: cardFadeIn 0.7s ease-out 0.2s both;
}

@keyframes cardFadeIn {
  from { opacity: 0; transform: translateY(24px); }
  to { opacity: 1; transform: translateY(0); }
}

.login-card::after {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  width: 80px;
  height: 80px;
  background: radial-gradient(circle, rgba(0, 245, 160, 0.15) 0%, transparent 70%);
  pointer-events: none;
}

/* ---- Element Plus 深色主题变量覆盖（核心：修复输入框白色问题） ---- */
.login-card {
  --el-bg-color: transparent;
  --el-fill-color: rgba(5, 11, 20, 0.8);
  --el-fill-color-blank: rgba(5, 11, 20, 0.8);
  --el-fill-color-light: rgba(5, 11, 20, 0.6);
  --el-fill-color-lighter: rgba(5, 11, 20, 0.4);
  --el-fill-color-dark: rgba(5, 11, 20, 0.9);
  --el-text-color-primary: #ffffff;
  --el-text-color-regular: #cbd5e1;
  --el-text-color-placeholder: #475569;
  --el-border-color: rgba(255, 255, 255, 0.12);
  --el-border-color-hover: rgba(0, 245, 160, 0.5);
  --el-border-color-focus: #00f5a0;
  --el-color-primary: #00f5a0;
  --el-color-primary-light-3: rgba(0, 245, 160, 0.3);
  --el-color-primary-light-5: rgba(0, 245, 160, 0.2);
  --el-color-primary-light-7: rgba(0, 245, 160, 0.1);
  --el-color-primary-light-8: rgba(0, 245, 160, 0.08);
  --el-color-primary-light-9: rgba(0, 245, 160, 0.05);
}

/* 输入框深色背景 */
.login-card :deep(.el-input__wrapper) {
  background: rgba(5, 11, 20, 0.8) !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  box-shadow: none !important;
  border-radius: 10px;
  transition: all 0.3s ease;
}

.login-card :deep(.el-input__wrapper:hover) {
  border-color: rgba(0, 245, 160, 0.5) !important;
  background: rgba(5, 11, 20, 0.95) !important;
}

.login-card :deep(.el-input__wrapper.is-focus) {
  border-color: #00f5a0 !important;
  box-shadow: 0 0 15px rgba(0, 245, 160, 0.2) !important;
  background: rgba(5, 11, 20, 0.95) !important;
}

.login-card :deep(.el-input__inner) {
  color: #ffffff !important;
}

.login-card :deep(.el-input__inner::placeholder) {
  color: #475569 !important;
}

.login-card :deep(.el-input__prefix) {
  color: #00f5a0 !important;
}

.login-card :deep(.el-input__suffix) {
  color: #64748b !important;
}

/* 验证码 append 按钮 */
.verify-input :deep(.el-input-group__append) {
  padding: 0;
  background: rgba(0, 245, 160, 0.08);
  border: 1px solid rgba(0, 245, 160, 0.2);
  border-left: none;
  border-radius: 0 10px 10px 0;
}

.verify-input :deep(.el-input-group__append .el-button) {
  color: #00f5a0;
  font-weight: 600;
  border: none;
  background: transparent;
  white-space: nowrap;
  padding: 0 16px;
}

.verify-input :deep(.el-input-group__append .el-button:not(.is-disabled):hover) {
  color: #00ffcc;
  background: rgba(0, 245, 160, 0.12);
}

.verify-input :deep(.el-input-group__append .el-button.is-disabled) {
  color: #475569;
  cursor: not-allowed;
}

/* ---- Tab 切换 ---- */
.tab-group {
  display: flex;
  gap: 28px;
  margin-bottom: 32px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding-bottom: 12px;
}

.tab-btn {
  font-size: 16px;
  font-weight: 600;
  color: #64748b;
  cursor: pointer;
  position: relative;
  transition: color 0.3s;
  user-select: none;
}

.tab-btn:hover { color: #94a3b8; }

.tab-btn.active { color: #00f5a0; }

.tab-btn.active::after {
  content: '';
  position: absolute;
  bottom: -13px;
  left: 0;
  width: 100%;
  height: 2px;
  background: #00f5a0;
  box-shadow: 0 0 10px #00f5a0;
}

/* ---- 表单标题 ---- */
.welcome-title {
  font-size: 26px;
  font-weight: 700;
  color: #ffffff;
  margin-bottom: 8px;
  letter-spacing: 1px;
}

.welcome-sub {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 32px;
}

/* ---- 输入框容器 ---- */
.input-box { margin-bottom: 22px; }

.input-label {
  display: block;
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 8px;
  letter-spacing: 0.5px;
}

/* ---- 提交按钮 ---- */
.submit-btn {
  width: 100%;
  height: 46px;
  background: linear-gradient(135deg, #00f5a0 0%, #00b4d8 100%) !important;
  border: none !important;
  border-radius: 10px !important;
  color: #030712 !important;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 2px;
  transition: all 0.3s ease;
  box-shadow: 0 0 20px rgba(0, 245, 160, 0.3);
  margin-top: 10px;
  position: relative;
  overflow: hidden;
}

.submit-btn::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.35), transparent);
  transition: left 0.6s;
}

.submit-btn:hover::before { left: 100%; }

.submit-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 30px rgba(0, 245, 160, 0.5);
}

.submit-btn:active { transform: translateY(0); }

/* ---- 表单底部 ---- */
.form-footer {
  margin-top: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #64748b;
}

.form-footer :deep(.el-checkbox__label) {
  color: #64748b;
  font-size: 12px;
}

.form-footer :deep(.el-checkbox__inner) {
  background: rgba(5, 11, 20, 0.8);
  border-color: rgba(0, 245, 160, 0.3);
  border-radius: 4px;
}

.form-footer :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  background: #00f5a0;
  border-color: #00f5a0;
}

.form-footer :deep(.el-checkbox__input.is-checked + .el-checkbox__label) {
  color: #00f5a0;
}

.forgot-link {
  color: #00f5a0;
  cursor: pointer;
  transition: opacity 0.2s;
}

.forgot-link:hover { opacity: 0.8; }

/* ---- 表单切换动画 ---- */
.form-section { min-height: 280px; }

.fade-slide-enter-active { transition: all 0.3s ease; }
.fade-slide-leave-active { transition: all 0.2s ease; }
.fade-slide-enter-from { opacity: 0; transform: translateX(20px); }
.fade-slide-leave-to { opacity: 0; transform: translateX(-20px); }

/* ---- 移动端品牌 ---- */
.mobile-brand { display: none; }

/* ====================== 响应式 ====================== */
@media (max-width: 1100px) {
  .visual-stage { flex: 1.1; }
  .login-stage { flex: 0.9; }
  .brand-header { top: 30px; left: 30px; }
  .tracker-info-box { left: 30px; bottom: 30px; }
}

@media (max-width: 900px) {
  .visual-stage { flex: 1; }
  .login-stage { flex: 1; }
  .hud-card { padding: 10px 14px; }
  .hud-icon { width: 36px; height: 36px; font-size: 16px; }
  .hud-num { font-size: 16px; }
}

@media (max-width: 760px) {
  .auth-page { flex-direction: column; }
  .visual-stage { display: none; }
  .login-stage {
    flex: 1;
    padding: 24px 20px;
    border-left: none;
  }
  .login-card {
    width: 100%;
    padding: 32px 24px;
  }
  .mobile-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 24px;
    font-weight: 700;
    letter-spacing: 3px;
    margin-bottom: 24px;
    color: #ffffff;
  }
  .mobile-brand .el-icon { color: #00f5a0; }
}
</style>
