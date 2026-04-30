<template>
  <div class="app">
    <header :style="{ background: swatchColor }">
      <span class="hex" :style="{ color: fgColor }">{{ hexColor }}</span>
      <div class="header-right">
        <span class="status" :style="{ color: fgColor }">{{ connectedText }}</span>
        <div class="btn-row">
          <button class="off-btn" :style="{ color: fgColor, borderColor: fgColor }" @click="turnOn">Turn on</button>
          <button class="off-btn" :style="{ color: fgColor, borderColor: fgColor }" @click="turnOff">Turn off</button>
        </div>
      </div>
    </header>

    <!-- Tab navigation -->
    <div class="tabs">
      <button :class="['tab', { active: activeTab === 'color' }]" @click="activeTab = 'color'">Color</button>
      <button :class="['tab', { active: activeTab === 'scenes' }]" @click="activeTab = 'scenes'">Scenes</button>
    </div>

    <!-- ── Color tab ── -->
    <div v-show="activeTab === 'color'" class="tab-content">
      <div class="picker-wrap">
        <div ref="pickerEl" />
      </div>

      <div class="manual-entry">
        <form @submit.prevent="applyManual">
          <label class="entry-label">
            <span>#</span>
            <input
              v-model="hexInput"
              class="hex-input"
              maxlength="6"
              placeholder="rrggbb"
              spellcheck="false"
              @input="syncRgbFromHex"
            />
          </label>
          <label class="entry-label">R <input v-model.number="rInput" class="rgb-input" type="number" min="0" max="255" @change="syncHexFromRgb" /></label>
          <label class="entry-label">G <input v-model.number="gInput" class="rgb-input" type="number" min="0" max="255" @change="syncHexFromRgb" /></label>
          <label class="entry-label">B <input v-model.number="bInput" class="rgb-input" type="number" min="0" max="255" @change="syncHexFromRgb" /></label>
          <button type="submit" class="apply-btn">Apply</button>
        </form>
      </div>

      <div class="favorites-section">
        <div class="favorites-header">
          <span>Favorites</span>
          <button class="save-btn" @click="saveFavorite">+ Save current</button>
        </div>
        <div v-if="favorites.length === 0" class="no-favs">No favorites saved yet.</div>
        <div class="swatches">
          <div
            v-for="(fav, i) in favorites"
            :key="i"
            class="swatch"
            :style="{ background: `rgb(${fav.r},${fav.g},${fav.b})` }"
            :title="fav.name || `#${hex(fav)}`"
            @click="applyFavorite(fav)"
          >
            <span class="swatch-label">{{ fav.name || '#' + hex(fav) }}</span>
            <button class="swatch-del" @click.stop="deleteFavorite(i)">×</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Scenes tab ── -->
    <div v-show="activeTab === 'scenes'" class="tab-content scenes-section">
      <p class="scenes-intro">
        Science-based lighting sequences that mirror natural daylight and support your
        circadian rhythm — from alerting blues in the morning to sleep-safe reds at night.
      </p>

      <!-- 24/7 continuous bar -->
      <div class="continuous-bar" :class="{ active: isContinuous }">
        <div class="continuous-left">
          <span class="continuous-icon">🕐</span>
          <div>
            <div class="continuous-title">Run 24/7</div>
            <div class="continuous-sub">
              {{ isContinuous
                ? 'Playing · auto-advances with the time of day (New York)'
                : 'Loops morning → afternoon → evening → night, synced to NY time' }}
            </div>
          </div>
        </div>
        <button v-if="!isContinuous" class="play-btn" @click="startContinuous">▶ Start</button>
        <button v-else               class="stop-btn" @click="stopScene">■ Stop</button>
      </div>

      <div class="scene-cards">
        <div v-for="scene in scenes" :key="scene.key" class="scene-card">
          <!-- Proportional colour strip -->
          <div class="scene-strip">
            <div
              v-for="phase in scene.phases"
              :key="phase.label"
              class="scene-strip-seg"
              :style="{ background: `rgb(${phase.r},${phase.g},${phase.b})`, flex: phase.hold_minutes }"
              :title="phase.label + ' · ' + phase.hold_minutes + ' min'"
            />
          </div>

          <div class="scene-body">
            <div class="scene-title-row">
              <span class="scene-icon">{{ scene.icon }}</span>
              <h3 class="scene-name">{{ scene.name }}</h3>
            </div>
            <p class="scene-desc">{{ scene.description }}</p>

            <div class="scene-phases">
              <div
                v-for="(phase, pi) in scene.phases"
                :key="pi"
                class="scene-phase-row"
                :class="{ 'phase-active': playingScene === scene.key && playingPhase === pi }"
              >
                <span class="phase-dot" :style="{ background: `rgb(${phase.r},${phase.g},${phase.b})` }" />
                <span class="phase-name">{{ phase.label }}</span>
                <span class="phase-dur">{{ phase.hold_minutes }}m</span>
              </div>
            </div>

            <div v-if="playingScene === scene.key" class="playing-badge">
              <span v-if="isContinuous">🕐 24/7 —</span>
              <span v-else>▶</span>
              Playing — Phase {{ (playingPhase ?? 0) + 1 }}/{{ scene.phases.length }}
            </div>

            <div class="scene-btn-row">
              <button
                v-if="playingScene !== scene.key || isContinuous"
                :disabled="isContinuous"
                class="play-btn"
                @click="playScene(scene.key)"
              >▶ Play</button>
              <button
                v-if="playingScene === scene.key && !isContinuous"
                class="stop-btn"
                @click="stopScene"
              >■ Stop</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import iro from '@jaames/iro'

const rgb = ref({ r: 0, g: 0, b: 0 })
const connected = ref(0)
const pickerEl = ref(null)
const favorites = ref([])
const activeTab = ref('color')

// Scenes state
const scenes = ref([])
const playingScene = ref(null)
const playingPhase = ref(null)
const isContinuous = ref(false)

const hexInput = ref('000000')
const rInput = ref(0)
const gInput = ref(0)
const bInput = ref(0)

function syncInputsFromRgb(r, g, b) {
  hexInput.value = [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('')
  rInput.value = r
  gInput.value = g
  bInput.value = b
}

function syncRgbFromHex() {
  const v = hexInput.value.replace(/[^0-9a-fA-F]/g, '').slice(0, 6)
  hexInput.value = v
  if (v.length === 6) {
    rInput.value = parseInt(v.slice(0, 2), 16)
    gInput.value = parseInt(v.slice(2, 4), 16)
    bInput.value = parseInt(v.slice(4, 6), 16)
  }
}

function syncHexFromRgb() {
  hexInput.value = [rInput.value, gInput.value, bInput.value]
    .map(v => Math.max(0, Math.min(255, v || 0)).toString(16).padStart(2, '0'))
    .join('')
}

async function applyManual() {
  const r = rInput.value
  const g = gInput.value
  const b = bInput.value
  await sendColor(r, g, b)
  applyRemoteColor(r, g, b)
}

let picker = null
let ws = null
let fromRemote = false
let debounce = null
let statusPoll = null

const swatchColor = computed(() => `rgb(${rgb.value.r},${rgb.value.g},${rgb.value.b})`)
const hexColor = computed(() => {
  const { r, g, b } = rgb.value
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
})
const fgColor = computed(() => {
  const { r, g, b } = rgb.value
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 128 ? '#000' : '#fff'
})
const connectedText = computed(
  () => `${connected.value} device${connected.value !== 1 ? 's' : ''} connected`
)

async function fetchState() {
  const res = await fetch('/api/state')
  const data = await res.json()
  rgb.value = { r: data.r, g: data.g, b: data.b }
  connected.value = data.connected
}

async function fetchFavorites() {
  const res = await fetch('/api/favorites')
  favorites.value = await res.json()
}

async function fetchScenes() {
  const res = await fetch('/api/scenes')
  scenes.value = await res.json()
}

async function fetchSceneStatus() {
  const res = await fetch('/api/scenes/status')
  const data = await res.json()
  playingScene.value = data.playing
  playingPhase.value = data.phase
  isContinuous.value = data.continuous
}

async function playScene(key) {
  await fetch(`/api/scenes/${key}/play`, { method: 'POST' })
  playingScene.value = key
  playingPhase.value = 0
  isContinuous.value = false
}

async function startContinuous() {
  await fetch('/api/scenes/continuous', { method: 'POST' })
  isContinuous.value = true
}

async function stopScene() {
  await fetch('/api/scenes/stop', { method: 'POST' })
  playingScene.value = null
  playingPhase.value = null
  isContinuous.value = false
}

function hex(fav) {
  return [fav.r, fav.g, fav.b].map(v => v.toString(16).padStart(2, '0')).join('')
}

async function saveFavorite() {
  const { r, g, b } = rgb.value
  const name = prompt('Name this color (leave blank for hex):', '') ?? ''
  await fetch('/api/favorites', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ r, g, b, name }),
  })
  await fetchFavorites()
}

async function deleteFavorite(index) {
  await fetch(`/api/favorites/${index}`, { method: 'DELETE' })
  await fetchFavorites()
}

async function applyFavorite(fav) {
  await sendColor(fav.r, fav.g, fav.b)
  applyRemoteColor(fav.r, fav.g, fav.b)
}

async function sendColor(r, g, b) {
  await fetch('/api/color', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ r, g, b }),
  })
}

async function turnOn() {
  await fetch('/api/on', { method: 'POST' })
}

async function turnOff() {
  await fetch('/api/off', { method: 'POST' })
  applyRemoteColor(0, 0, 0)
}

function applyRemoteColor(r, g, b) {
  rgb.value = { r, g, b }
  syncInputsFromRgb(r, g, b)
  fromRemote = true
  picker?.color.set({ r, g, b })
  fromRemote = false
}

onMounted(async () => {
  await Promise.all([fetchState(), fetchFavorites(), fetchScenes()])
  await fetchSceneStatus()

  // Poll scene status every 3 seconds
  statusPoll = setInterval(fetchSceneStatus, 3000)

  picker = new iro.ColorPicker(pickerEl.value, {
    width: 280,
    color: rgb.value,
    layout: [
      { component: iro.ui.Wheel },
      { component: iro.ui.Slider, options: { sliderType: 'value' } },
    ],
  })

  picker.on('color:change', (color) => {
    if (fromRemote) return
    const { r, g, b } = color.rgb
    // ignore pure black — use the Turn Off button for that
    if (r === 0 && g === 0 && b === 0) return
    rgb.value = { r, g, b }
    clearTimeout(debounce)
    debounce = setTimeout(() => sendColor(r, g, b), 50)
  })

  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws`)
  ws.onmessage = (e) => {
    const { r, g, b } = JSON.parse(e.data)
    applyRemoteColor(r, g, b)
  }
})

onUnmounted(() => {
  clearTimeout(debounce)
  clearInterval(statusPoll)
  ws?.close()
})
</script>

<style>
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  background: #111;
  color: #eee;
  font-family: system-ui, sans-serif;
}

.app {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 100vh;
}

header {
  width: 100%;
  min-height: 110px;
  padding: 1.5rem 2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  transition: background 0.25s;
}

.hex {
  font-size: 2rem;
  font-weight: 700;
  font-family: monospace;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
  transition: color 0.25s;
}

.status {
  font-size: 0.9rem;
  opacity: 0.85;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
  transition: color 0.25s;
}

.picker-wrap {
  margin: 2.5rem 0 1rem;
  display: flex;
  justify-content: center;
}

.manual-entry {
  margin-bottom: 1.5rem;
}

.manual-entry form {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  justify-content: center;
}

.entry-label {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.85rem;
  color: #aaa;
}

.hex-input {
  background: #1e1e1e;
  border: 1px solid #444;
  color: #eee;
  border-radius: 6px;
  padding: 0.3rem 0.5rem;
  font-family: monospace;
  font-size: 0.9rem;
  width: 7ch;
  text-transform: lowercase;
}

.rgb-input {
  background: #1e1e1e;
  border: 1px solid #444;
  color: #eee;
  border-radius: 6px;
  padding: 0.3rem 0.4rem;
  font-size: 0.85rem;
  width: 4.5rem;
}

.hex-input:focus,
.rgb-input:focus {
  outline: none;
  border-color: #888;
}

.apply-btn {
  background: #2a2a2a;
  color: #eee;
  border: 1px solid #555;
  padding: 0.3rem 0.9rem;
  border-radius: 6px;
  font-size: 0.85rem;
  cursor: pointer;
}

.apply-btn:hover {
  background: #3a3a3a;
}

.header-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.5rem;
}

.off-btn {
  background: transparent;
  border: 1px solid currentColor;
  padding: 0.35rem 1rem;
  border-radius: 6px;
  font-size: 0.85rem;
  cursor: pointer;
  opacity: 0.8;
  transition: opacity 0.15s;
  white-space: nowrap;
}

.off-btn:hover {
  opacity: 1;
}

.btn-row {
  display: flex;
  gap: 0.5rem;
}

.favorites-section {
  width: 100%;
  max-width: 500px;
  padding: 0 1.5rem 2rem;
}

.favorites-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
  font-size: 0.9rem;
  color: #aaa;
}

.save-btn {
  background: #2a2a2a;
  color: #eee;
  border: 1px solid #444;
  padding: 0.3rem 0.9rem;
  border-radius: 6px;
  font-size: 0.8rem;
  cursor: pointer;
}

.save-btn:hover {
  background: #3a3a3a;
}

.no-favs {
  color: #555;
  font-size: 0.85rem;
  text-align: center;
  padding: 1rem 0;
}

.swatches {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.swatch {
  position: relative;
  width: 72px;
  height: 72px;
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  overflow: hidden;
  box-shadow: 0 2px 6px rgba(0,0,0,0.4);
  transition: transform 0.12s;
}

.swatch:hover {
  transform: scale(1.07);
}

.swatch-label {
  font-size: 0.6rem;
  background: rgba(0,0,0,0.45);
  color: #fff;
  width: 100%;
  text-align: center;
  padding: 2px 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.swatch-del {
  position: absolute;
  top: 3px;
  right: 3px;
  background: rgba(0,0,0,0.5);
  color: #fff;
  border: none;
  border-radius: 50%;
  width: 18px;
  height: 18px;
  font-size: 0.75rem;
  line-height: 1;
  cursor: pointer;
  display: none;
  align-items: center;
  justify-content: center;
  padding: 0;
}

.swatch:hover .swatch-del {
  display: flex;
}

/* ── Tabs ──────────────────────────────────────────────────────────────────── */

.tabs {
  display: flex;
  width: 100%;
  border-bottom: 1px solid #2a2a2a;
}

.tab {
  flex: 1;
  background: transparent;
  border: none;
  color: #888;
  font-size: 0.95rem;
  padding: 0.75rem 0;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: color 0.15s, border-color 0.15s;
}

.tab.active {
  color: #eee;
  border-bottom-color: #4a9eff;
}

.tab:hover:not(.active) {
  color: #ccc;
}

.tab-content {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* ── Scenes tab ────────────────────────────────────────────────────────────── */

.scenes-section {
  padding: 1.5rem 1rem 3rem;
  max-width: 560px;
}

.scenes-intro {
  font-size: 0.82rem;
  color: #777;
  text-align: center;
  margin-bottom: 1.5rem;
  line-height: 1.5;
}

.scene-cards {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  width: 100%;
}

/* ── Continuous bar ─────────────────────────────────────────────────────────── */

.continuous-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  width: 100%;
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 14px;
  padding: 1rem 1.25rem;
  margin-bottom: 1.25rem;
  transition: border-color 0.2s;
}

.continuous-bar.active {
  border-color: #2a5a8c;
  background: #111e2e;
}

.continuous-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.continuous-icon {
  font-size: 1.6rem;
  flex-shrink: 0;
}

.continuous-title {
  font-size: 1rem;
  font-weight: 600;
  color: #ddd;
  margin-bottom: 0.15rem;
}

.continuous-sub {
  font-size: 0.78rem;
  color: #666;
  line-height: 1.4;
}

.continuous-bar.active .continuous-sub {
  color: #4a9eff;
}

.play-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.scene-card {
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 14px;
  overflow: hidden;
}

/* Proportional colour strip across the top */
.scene-strip {
  display: flex;
  height: 12px;
  width: 100%;
}

.scene-strip-seg {
  transition: opacity 0.2s;
}

.scene-strip-seg:hover {
  opacity: 0.8;
}

.scene-body {
  padding: 1rem 1.25rem 1.25rem;
}

.scene-title-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.4rem;
}

.scene-icon {
  font-size: 1.3rem;
}

.scene-name {
  font-size: 1.05rem;
  font-weight: 600;
  color: #ddd;
}

.scene-desc {
  font-size: 0.8rem;
  color: #777;
  margin-bottom: 0.9rem;
  line-height: 1.45;
}

.scene-phases {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin-bottom: 0.9rem;
}

.scene-phase-row {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  font-size: 0.8rem;
  color: #888;
  border-radius: 6px;
  padding: 0.15rem 0.4rem;
  transition: background 0.15s;
}

.scene-phase-row.phase-active {
  background: #232323;
  color: #ddd;
}

.phase-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.phase-name {
  flex: 1;
}

.phase-dur {
  color: #555;
  font-size: 0.75rem;
}

.playing-badge {
  font-size: 0.78rem;
  color: #4a9eff;
  margin-bottom: 0.7rem;
  font-weight: 500;
}

.scene-btn-row {
  display: flex;
  justify-content: flex-end;
}

.play-btn {
  background: #1a3a5c;
  color: #7bbfff;
  border: 1px solid #2a5a8c;
  padding: 0.45rem 1.4rem;
  border-radius: 8px;
  font-size: 0.9rem;
  cursor: pointer;
  transition: background 0.15s;
}

.play-btn:hover {
  background: #1e4a78;
}

.stop-btn {
  background: #3a1a1a;
  color: #ff8888;
  border: 1px solid #6a2a2a;
  padding: 0.45rem 1.4rem;
  border-radius: 8px;
  font-size: 0.9rem;
  cursor: pointer;
  transition: background 0.15s;
}

.stop-btn:hover {
  background: #4a2020;
}
</style>
