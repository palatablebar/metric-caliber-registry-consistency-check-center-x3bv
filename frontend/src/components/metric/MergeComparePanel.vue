<template>
  <div v-if="record" class="compare-panel">
    <div class="compare-grid">
      <div class="compare-col">
        <div class="eyebrow">before · 合并前</div>
        <ul class="clean-list mt-1">
          <li><span class="label">节点数</span> <b class="num">{{ beforeGraph.node_count }}</b></li>
          <li><span class="label">依赖边</span> <b class="num">{{ beforeGraph.edge_count }}</b></li>
          <li><span class="label">环 / 孤儿</span> <b class="num">{{ beforeGraph.cycle_count }} / {{ beforeGraph.orphan_count }}</b></li>
        </ul>
        <div class="label mt-2">图节点</div>
        <div class="key-cloud mt-1">
          <span v-for="key in beforeGraph.node_keys" :key="`b-${key}`" class="chip" :class="{ hot: key === sourceKey }">{{ key }}</span>
        </div>
        <div class="label mt-2">主指标看板</div>
        <div class="key-cloud mt-1">
          <span v-for="board in record.before?.primary_boards ?? []" :key="`bb-${board}`" class="chip">{{ board }}</span>
          <span v-if="!(record.before?.primary_boards ?? []).length" class="hint">无</span>
        </div>
      </div>

      <div class="compare-arrow" aria-hidden="true">→</div>

      <div class="compare-col">
        <div class="eyebrow">after · 合并后（旧编码已转为历史入口）</div>
        <ul class="clean-list mt-1">
          <li><span class="label">节点数</span> <b class="num">{{ afterGraph.node_count }}</b></li>
          <li><span class="label">依赖边</span> <b class="num">{{ afterGraph.edge_count }}</b></li>
          <li><span class="label">环 / 孤儿</span> <b class="num">{{ afterGraph.cycle_count }} / {{ afterGraph.orphan_count }}</b></li>
        </ul>
        <div class="label mt-2">图节点（不含旧编码）</div>
        <div class="key-cloud mt-1">
          <span v-for="key in afterGraph.node_keys" :key="`a-${key}`" class="chip" :class="{ hot: key === primaryKey }">{{ key }}</span>
        </div>
        <div class="label mt-2">主指标看板（去重并集）</div>
        <div class="key-cloud mt-1">
          <span v-for="board in record.after?.primary_boards ?? []" :key="`ab-${board}`" class="chip">{{ board }}</span>
          <span v-if="!(record.after?.primary_boards ?? []).length" class="hint">无</span>
        </div>
      </div>
    </div>

    <div v-if="record.migration" class="migration mt-2">
      <div class="label">本次迁移（每条关系只迁移一次）</div>
      <div class="row mt-1" style="gap: 14px; flex-wrap: wrap">
        <span class="chip"><b>边</b>{{ record.migration.edges_before }} → {{ record.migration.edges_after }}</span>
        <span class="chip"><b>迁移</b>{{ record.migration.edges_migrated.length }}</span>
        <span class="chip is-hot"><b>去重</b>{{ record.migration.duplicate_edges_dropped.length }}</span>
        <span class="chip"><b>看板并集</b>{{ record.migration.boards_merged.length }}</span>
      </div>
    </div>

    <details class="snapshot-raw mt-2">
      <summary class="hint">查看完整快照 JSON（目录与关系行，回滚即按此恢复）</summary>
      <pre class="dsl-code mt-1">{{ JSON.stringify(record.before_snapshot, null, 2) }}</pre>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MergeRecord } from '../../types/merge'

const props = defineProps<{ record: MergeRecord | null }>()

function emptyGraph() {
  return { node_count: 0, edge_count: 0, cycle_count: 0, orphan_count: 0, node_keys: [] as string[], edges: [], table_edges: [] }
}

const beforeGraph = computed(
  () => props.record?.before?.graph ?? props.record?.after_snapshot?.verification?.graph ?? emptyGraph(),
)
const afterGraph = computed(
  () => props.record?.after?.graph ?? props.record?.after_snapshot?.verification?.graph ?? emptyGraph(),
)
const primaryKey = computed(() => String((props.record?.primary_metric as Record<string, unknown>)?.metric_key ?? ''))
const sourceKey = computed(() => String((props.record?.source_metric as Record<string, unknown>)?.metric_key ?? ''))
</script>

<style scoped>
.compare-panel { border: 1px solid var(--rule); background: var(--paper-raised); padding: 14px 16px; }
.compare-grid { display: grid; grid-template-columns: minmax(0, 1fr) 40px minmax(0, 1fr); gap: 14px; align-items: start; }
.compare-col { min-width: 0; }
.compare-arrow { font-size: 22px; color: var(--vermilion-deep); text-align: center; padding-top: 24px; }
.clean-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.key-cloud { display: flex; flex-wrap: wrap; gap: 6px; }
.chip.hot { border-color: var(--vermilion); color: var(--vermilion-deep); background: var(--vermilion-wash); }
.migration { border-top: 1px dashed var(--rule); padding-top: 10px; }
.snapshot-raw summary { cursor: pointer; }
</style>
