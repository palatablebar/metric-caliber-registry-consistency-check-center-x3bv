<template>
  <div class="rise">
    <PageHeader
      eyebrow="metric merge · 重复编码治理"
      title="指标合并工作台"
      lede="把两个重复登记的指标编码并成一个主指标：旧编码保留历史查询并指向主指标，依赖与看板关系只迁移一次；同一组合重复提交幂等，失败自动回滚，合并前后目录、详情与依赖图可核对。"
    >
      <template #actions>
        <router-link class="btn btn-sm" to="/catalog">返回目录 →</router-link>
      </template>
    </PageHeader>

    <ErrorNotice :error="error" class="mt-2" />

    <div v-if="!auth.isAdmin" class="empty-state mt-3">
      <div class="glyph">⊘</div>
      <div class="section-title mt-2">仅治理管理员可执行合并</div>
      <p class="hint mt-1">分析员与指标负责人可在下方只读查看合并台账；发起或回滚合并请使用 admin 账号。</p>
    </div>

    <template v-else>
      <section class="index-card is-flat mt-3">
        <SectionHeading eyebrow="new merge" title="发起一次合并" />
        <div class="merge-form mt-2">
          <label class="field">
            <span class="label">主指标（保留的编码，依赖与看板迁移到这里）</span>
            <select v-model.number="primaryId" class="select" @change="resetPreview">
              <option :value="0" disabled>选择主指标…</option>
              <option v-for="metric in selectableMetrics" :key="`p-${metric.id}`" :value="metric.id">
                {{ metric.key }} · {{ metric.name }}（{{ metric.domain }}）
              </option>
            </select>
          </label>
          <label class="field">
            <span class="label">旧编码（重复登记，合并后转为只读历史入口）</span>
            <select v-model.number="sourceId" class="select" @change="resetPreview">
              <option :value="0" disabled>选择旧编码…</option>
              <option
                v-for="metric in selectableMetrics.filter((item) => item.id !== primaryId)"
                :key="`s-${metric.id}`"
                :value="metric.id"
              >
                {{ metric.key }} · {{ metric.name }}（{{ metric.domain }}）
              </option>
            </select>
          </label>
          <label class="field" style="min-width: 240px">
            <span class="label">合并原因（可选）</span>
            <input v-model="reason" class="input" maxlength="255" placeholder="如：治理委员会 2026Q4 重复编码归并" />
          </label>
          <div class="field action-cell">
            <button class="btn" :disabled="!pairValid || previewLoading" @click="runPreview">
              {{ previewLoading ? '预演中…' : '预演影响' }}
            </button>
            <button class="btn btn-solid" :disabled="!pairValid || submitting" @click="runMerge">
              {{ submitting ? '合并中…' : '执行合并' }}
            </button>
          </div>
        </div>

        <div v-if="preview" class="preview mt-3">
          <div class="row-between">
            <div>
              <div class="eyebrow">dry run · 不落库</div>
              <h3 class="card-title mt-1">合并预演：{{ preview.source_metric.key }} → {{ preview.primary_metric.key }}</h3>
            </div>
            <span v-if="preview.already_merged" class="badge merged">该组合已合并，重复提交将直接返回原记录（幂等）</span>
          </div>
          <div class="preview-grid mt-2">
            <div class="preview-cell">
              <div class="label">依赖边</div>
              <div class="num preview-number">{{ preview.edges_before }} → {{ preview.edges_after }}</div>
              <div class="hint">迁移 {{ preview.edges_migrated_count }} 条 · 去重 {{ preview.duplicate_edges_dropped_count }} 条</div>
            </div>
            <div class="preview-cell">
              <div class="label">旧编码历史版本</div>
              <div class="num preview-number">{{ preview.source_versions_kept }}</div>
              <div class="hint">版本与 DSL 全部保留，入口转只读</div>
            </div>
            <div class="preview-cell">
              <div class="label">并入主指标的看板</div>
              <div class="row mt-1" style="flex-wrap: wrap; gap: 6px">
                <span v-for="board in preview.boards_to_merge" :key="board" class="chip">{{ board }}</span>
                <span v-if="!preview.boards_to_merge.length" class="hint">无新增看板（已全部存在）</span>
              </div>
            </div>
          </div>
        </div>
      </section>
    </template>

    <section class="mt-4">
      <SectionHeading eyebrow="merge ledger" title="合并台账（含合并前后快照与回滚）">
        <template #actions>
          <select v-model="statusFilter" class="select select-sm" @change="loadMerges">
            <option value="">全部状态</option>
            <option value="active">已合并</option>
            <option value="rolled_back">已回滚</option>
          </select>
          <button class="btn btn-sm" @click="loadMerges">刷新</button>
        </template>
      </SectionHeading>

      <LoadingHint v-if="ledgerLoading" />
      <div v-if="merges.length" class="table-wrap mt-2">
        <table class="data">
          <thead>
            <tr>
              <th>#</th><th>旧编码 → 主指标</th><th>状态</th><th>次数</th><th>原因</th><th>合并人/时间</th><th>回滚人/时间</th><th>核对</th><th v-if="auth.isAdmin">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in merges" :key="row.id">
              <td class="mono">{{ row.id }}</td>
              <td>
                <router-link class="dep-link mono" :to="`/metrics/${(row.source_metric as Record<string, unknown>)?.id}`">
                  {{ (row.source_metric as Record<string, unknown>)?.metric_key }}
                </router-link>
                <span class="faint"> → </span>
                <router-link class="dep-link mono" :to="`/metrics/${(row.primary_metric as Record<string, unknown>)?.id}`">
                  {{ (row.primary_metric as Record<string, unknown>)?.metric_key }}
                </router-link>
              </td>
              <td><span class="badge" :class="row.status">{{ row.status_label }}</span></td>
              <td class="num">{{ row.merge_count }}</td>
              <td>{{ row.reason ?? '—' }}</td>
              <td class="small">{{ row.merged_by ?? '—' }}<br /><span class="mono faint">{{ row.merged_at ?? '—' }}</span></td>
              <td class="small">{{ row.rolled_back_by ?? '—' }}<br /><span class="mono faint">{{ row.rolled_back_at ?? '—' }}</span></td>
              <td>
                <button class="btn btn-sm" @click="toggleDetail(row.id)">
                  {{ expandedId === row.id ? '收起核对' : '合并前后' }}
                </button>
              </td>
              <td v-if="auth.isAdmin">
                <button
                  v-if="row.status === 'active'"
                  class="btn btn-sm btn-accent"
                  :disabled="rollingBackId === row.id"
                  @click="runRollback(row.id)"
                >
                  {{ rollingBackId === row.id ? '回滚中…' : '回滚' }}
                </button>
                <span v-else class="hint">已回滚</span>
              </td>
            </tr>
            <tr v-if="expandedId" :key="`detail-${expandedId}`">
              <td :colspan="auth.isAdmin ? 9 : 8">
                <MergeComparePanel :record="expandedRecord" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <EmptyState
        v-else
        class="mt-2"
        title="还没有合并记录"
        hint="选择主指标与旧编码并执行合并后，这里会保留每次合并的前后目录与依赖图快照。"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '../components/common/PageHeader.vue'
import SectionHeading from '../components/common/SectionHeading.vue'
import ErrorNotice from '../components/common/ErrorNotice.vue'
import LoadingHint from '../components/common/LoadingHint.vue'
import EmptyState from '../components/common/EmptyState.vue'
import MergeComparePanel from '../components/metric/MergeComparePanel.vue'
import { useAuthStore } from '../stores/authStore'
import { fetchMetrics } from '../api/metric'
import { createMerge, fetchMerges, previewMerge, rollbackMerge } from '../api/merge'
import type { Metric } from '../types/metric'
import type { MergePreview, MergeRecord } from '../types/merge'
import type { ApiError } from '../types/api'

const auth = useAuthStore()
const route = useRoute()

const metrics = ref<Metric[]>([])
const primaryId = ref(Number(route.query.primary) || 0)
const sourceId = ref(0)
const reason = ref('')
const preview = ref<MergePreview | null>(null)
const previewLoading = ref(false)
const submitting = ref(false)

const merges = ref<MergeRecord[]>([])
const ledgerLoading = ref(false)
const statusFilter = ref('')
const expandedId = ref<number | null>(null)
const rollingBackId = ref<number | null>(null)
const error = ref<ApiError | null>(null)

const pairValid = computed(() => primaryId.value > 0 && sourceId.value > 0 && primaryId.value !== sourceId.value)
const selectableMetrics = computed(() => metrics.value.filter((metric) => !metric.is_merged))
const expandedRecord = computed(() => merges.value.find((row) => row.id === expandedId.value) ?? null)

function resetPreview() {
  preview.value = null
}

async function loadMetrics() {
  const result = await fetchMetrics({ include_merged: true, page_size: 200 })
  metrics.value = result.items
}

async function runPreview() {
  if (!pairValid.value) return
  error.value = null
  previewLoading.value = true
  try {
    preview.value = await previewMerge({
      primary_metric_id: primaryId.value,
      source_metric_id: sourceId.value,
      reason: reason.value || null,
    })
  } catch (err) {
    error.value = err as ApiError
  } finally {
    previewLoading.value = false
  }
}

async function runMerge() {
  if (!pairValid.value) return
  error.value = null
  submitting.value = true
  try {
    const result = await createMerge({
      primary_metric_id: primaryId.value,
      source_metric_id: sourceId.value,
      reason: reason.value || null,
    })
    if (result.idempotent_reused) {
      error.value = null
    }
    primaryId.value = 0
    sourceId.value = 0
    reason.value = ''
    preview.value = null
    await Promise.all([loadMetrics(), loadMerges()])
    expandedId.value = result.id
  } catch (err) {
    error.value = err as ApiError
  } finally {
    submitting.value = false
  }
}

async function loadMerges() {
  ledgerLoading.value = true
  error.value = null
  try {
    const result = await fetchMerges(statusFilter.value || undefined)
    merges.value = result.items
    if (expandedId.value && !result.items.some((row) => row.id === expandedId.value)) {
      expandedId.value = null
    }
  } catch (err) {
    error.value = err as ApiError
  } finally {
    ledgerLoading.value = false
  }
}

function toggleDetail(id: number) {
  expandedId.value = expandedId.value === id ? null : id
}

async function runRollback(id: number) {
  error.value = null
  rollingBackId.value = id
  try {
    await rollbackMerge(id)
    await Promise.all([loadMetrics(), loadMerges()])
  } catch (err) {
    error.value = err as ApiError
  } finally {
    rollingBackId.value = null
  }
}

onMounted(async () => {
  await Promise.all([loadMetrics(), loadMerges()])
})
</script>

<style scoped>
.merge-form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)) auto; gap: 14px; align-items: end; }
.action-cell { flex-direction: row; gap: 8px; }
.select-sm { width: auto; padding: 5px 9px; font-size: 11.5px; }
.preview { border: 1px solid var(--rule); background: var(--paper-deep); padding: 14px 16px; }
.preview-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
.preview-cell { border-left: 2px solid var(--sage); padding-left: 12px; }
.preview-number { font-family: var(--font-display); font-size: 22px; color: var(--ink-strong); }
@media (max-width: 1080px) {
  .merge-form { grid-template-columns: 1fr 1fr; }
  .preview-grid { grid-template-columns: 1fr; }
}
</style>
