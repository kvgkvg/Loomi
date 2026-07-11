"use client";

import React, { useEffect, useRef, useState } from 'react';

// Ported from Claude Design "Loomi Pipeline.dc.html" — simulated pipeline
// visualization: runs sidebar, six stage nodes, per-stage log + result panel.

const STAGE_DEFS = [
  { key: 'adapter', name: 'Git Adapter', sub: 'capture_commit', icon: 'git' },
  { key: 'version', name: 'Version Asset', sub: 'process_raw_event', icon: 'version' },
  { key: 'llm', name: 'Rationale Extraction', sub: 'GLM-5.2 · Featherless', icon: 'llm' },
  { key: 'persist', name: 'Persist Rationale', sub: 'SQLite', icon: 'persist' },
  { key: 'embed', name: 'Embed + Upsert', sub: 'MiniLM-L6-v2 → Chroma', icon: 'embed' },
  { key: 'finalize', name: 'Finalize', sub: 'commit + mark processed', icon: 'final' },
] as const;

const DURATIONS = [1100, 900, 2200, 700, 1300, 800];
const LINE_DELAY = 380;

const MESSAGE_POOL = [
  { message: 'Update onboarding assistant prompt flow', files: ['memory/onboarding-assistant.md'], problem: 'Onboarding assistant missed edge case for new hires without prior repo access', author: 'An Nguyen' },
  { message: 'Refine recommend engine scoring constraints', files: ['memory/recommend-hong.md', 'task.md'], problem: 'Recommend engine over-weighted recency versus semantic relevance', author: 'Hong Pham' },
  { message: 'Document git capture pipeline extension points', files: ['docs/components/git-capture-pipeline.md'], problem: 'Extension points for swapping SQLite to Postgres were undocumented', author: 'Khang Vo' },
  { message: 'Tune Featherless rationale prompt for shorter output', files: ['memory/khang.md'], problem: 'Rationale responses exceeded expected token budget for constraints field', author: 'Khang Vo' },
  { message: 'Add retry notes for capture pipeline failures', files: ['memory/an.md', 'README.md'], problem: 'Raw events left unprocessed on Chroma failure had no documented retry path', author: 'An Nguyen' },
];

interface RunCommit {
  id: string;
  sha: string;
  fullSha: string;
  message: string;
  author: string;
  files: string[];
  problem: string;
  createdAt: number;
  isNewAsset: boolean;
  versionNumber: number;
  assetType: string;
  assetId: string;
  versionId: string;
  willFailAt: number | null;
  stageStatuses: string[];
  stageLogsRevealed: number[];
  stageDurations: (number | null)[];
  selectedStage: number;
}

function shortSha() {
  let s = '';
  const chars = '0123456789abcdef';
  for (let i = 0; i < 7; i++) s += chars[Math.floor(Math.random() * 16)];
  return s;
}
function fullSha(short: string) {
  let s = short;
  const chars = '0123456789abcdef';
  while (s.length < 40) s += chars[Math.floor(Math.random() * 16)];
  return s;
}
function uid(prefix: string) {
  let s = prefix + '-';
  const chars = '0123456789abcdef';
  for (let i = 0; i < 8; i++) s += chars[Math.floor(Math.random() * 16)];
  return s;
}
function timeAgoLabel(msAgo: number) {
  const m = Math.floor(msAgo / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return m + 'm ago';
  const h = Math.floor(m / 60);
  if (h < 24) return h + 'h ago';
  return Math.floor(h / 24) + 'd ago';
}

function buildStageLog(c: RunCommit, idx: number): { lines: string[]; fail?: boolean; result: Record<string, unknown> | null } {
  if (idx === 0) {
    return {
      lines: [
        '$ git rev-parse --verify ' + c.sha + '^{commit}',
        'Resolved commit ' + c.fullSha.slice(0, 12) + '…',
        'Scanning diff-tree for changed paths',
        'Filtered ' + c.files.length + ' supported file' + (c.files.length > 1 ? 's' : '') + ': ' + c.files.join(', '),
        'Captured author ' + c.author + ' + diff',
        'Persisted raw_events row (processed=0)',
      ],
      result: { source_tool: 'git', title: c.message, paths: c.files.join(', ') },
    };
  }
  if (idx === 1) {
    return {
      lines: [
        'Computing asset_key = sha256(repo_root + sorted(paths))',
        c.isNewAsset ? 'No matching asset_key — creating new asset' : 'Matched existing asset — appending version ' + c.versionNumber,
        'Inferred type: ' + c.assetType,
        'Inserted asset_versions row v' + c.versionNumber,
      ],
      result: { asset_id: c.assetId, version: c.versionNumber },
    };
  }
  if (idx === 2) {
    const fail = c.willFailAt === 2;
    return {
      lines: fail ? [
        'POST https://api.featherless.ai/v1/chat/completions',
        'model=zai-org/GLM-5.2 temperature=0.1',
        '⚠ response was not valid JSON',
        'RationaleError: malformed JSON response',
      ] : [
        'POST https://api.featherless.ai/v1/chat/completions',
        'model=zai-org/GLM-5.2 temperature=0.1',
        'Parsing rationale JSON…',
        'problem: "' + c.problem + '"',
      ],
      fail,
      result: fail ? null : { problem: c.problem, confidence: 'auto' },
    };
  }
  if (idx === 3) {
    return {
      lines: [
        'INSERT INTO rationale (problem, failed_attempts, constraints, confidence)',
        'confidence: auto',
      ],
      result: { table: 'rationale', confidence: 'auto' },
    };
  }
  if (idx === 4) {
    return {
      lines: [
        'Encoding content with sentence-transformers/all-MiniLM-L6-v2',
        'Upserting vector id=' + c.assetId + ' into Chroma',
      ],
      result: { vector_id: c.assetId, collection: 'loomi_assets' },
    };
  }
  return {
    lines: [
      'UPDATE assets SET current_version_id = v' + c.versionNumber,
      'UPDATE raw_events SET processed = 1',
      'COMMIT transaction',
      'Pipeline complete ✓',
    ],
    result: { asset_id: c.assetId, version_id: c.versionId, embedded: true },
  };
}

function lineColor(text: string) {
  if (text.indexOf('⚠') === 0 || text.indexOf('Error') !== -1) return '#f85149';
  if (text.indexOf('✓') !== -1) return '#3fb950';
  if (text.indexOf('$') === 0 || text.indexOf('POST') === 0 || text.indexOf('INSERT') === 0 || text.indexOf('UPDATE') === 0 || text.indexOf('COMMIT') === 0) return '#79c0ff';
  return '#8b949e';
}

function makeCommit(seedOffsetMs: number, willFailAt?: number | null): RunCommit {
  const pick = MESSAGE_POOL[Math.floor(Math.random() * MESSAGE_POOL.length)];
  const sha = shortSha();
  return {
    id: uid('run'),
    sha,
    fullSha: fullSha(sha),
    message: pick.message,
    author: pick.author + ' <' + pick.author.toLowerCase().replace(' ', '.') + '@loomi.dev>',
    files: pick.files,
    problem: pick.problem,
    createdAt: Date.now() - seedOffsetMs,
    isNewAsset: Math.random() > 0.5,
    versionNumber: Math.floor(Math.random() * 4) + 1,
    assetType: pick.files.join(' ').toLowerCase().indexOf('recommend') !== -1 ? 'workflow' : 'prompt',
    assetId: uid('asset'),
    versionId: uid('ver'),
    willFailAt: willFailAt === undefined || willFailAt === null ? null : willFailAt,
    stageStatuses: STAGE_DEFS.map(() => 'pending'),
    stageLogsRevealed: STAGE_DEFS.map(() => 0),
    stageDurations: STAGE_DEFS.map(() => null),
    selectedStage: 0,
  };
}

function finalizeAllStages(commit: RunCommit): RunCommit {
  for (let i = 0; i < STAGE_DEFS.length; i++) {
    if (commit.willFailAt !== null && i > commit.willFailAt) {
      commit.stageStatuses[i] = 'skipped';
    } else if (commit.willFailAt !== null && i === commit.willFailAt) {
      commit.stageStatuses[i] = 'failed';
      commit.stageLogsRevealed[i] = buildStageLog(commit, i).lines.length;
      commit.stageDurations[i] = DURATIONS[i];
    } else {
      commit.stageStatuses[i] = 'success';
      commit.stageLogsRevealed[i] = buildStageLog(commit, i).lines.length;
      commit.stageDurations[i] = DURATIONS[i];
    }
  }
  commit.selectedStage = commit.willFailAt !== null ? commit.willFailAt : STAGE_DEFS.length - 1;
  return commit;
}

function StageIcon({ icon, color }: { icon: string; color: string }) {
  switch (icon) {
    case 'git':
      return <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M8 1v3M8 12v3M4 8a4 4 0 0 0 4 4M4 8a4 4 0 0 1 4-4M4 8H1M15 8h-3" stroke={color} strokeWidth="1.4" strokeLinecap="round"/><circle cx="8" cy="8" r="1.6" fill={color}/></svg>;
    case 'version':
      return <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M1 5l7-3 7 3-7 3-7-3Z" stroke={color} strokeWidth="1.3" strokeLinejoin="round"/><path d="M1 8l7 3 7-3M1 11l7 3 7-3" stroke={color} strokeWidth="1.3" strokeLinejoin="round"/></svg>;
    case 'llm':
      return <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><rect x="4" y="4" width="8" height="8" rx="1.4" stroke={color} strokeWidth="1.3"/><path d="M8 1v3M8 12v3M1 8h3M12 8h3M2.5 2.5l2 2M13.5 2.5l-2 2M2.5 13.5l2-2M13.5 13.5l-2-2" stroke={color} strokeWidth="1.2" strokeLinecap="round"/></svg>;
    case 'persist':
      return <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><ellipse cx="8" cy="3.2" rx="6" ry="2.2" stroke={color} strokeWidth="1.3"/><path d="M2 3.2v9.6c0 1.2 2.7 2.2 6 2.2s6-1 6-2.2V3.2M2 8c0 1.2 2.7 2.2 6 2.2s6-1 6-2.2" stroke={color} strokeWidth="1.3"/></svg>;
    case 'embed':
      return <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><circle cx="3" cy="3" r="1.8" stroke={color} strokeWidth="1.3"/><circle cx="13" cy="3" r="1.8" stroke={color} strokeWidth="1.3"/><circle cx="8" cy="13" r="1.8" stroke={color} strokeWidth="1.3"/><path d="M4.5 4.2L6.8 11M11.5 4.2L9.2 11M4.8 3h6.4" stroke={color} strokeWidth="1.1"/></svg>;
    default:
      return <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke={color} strokeWidth="1.3"/><path d="M5.2 8.2l1.9 1.9 3.7-4" stroke={color} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>;
  }
}

export default function PipelinePage() {
  const [commits, setCommits] = useState<RunCommit[]>(() => [
    finalizeAllStages(makeCommit(2 * 3600000)),
    finalizeAllStages(makeCommit(20 * 3600000, 2)),
    finalizeAllStages(makeCommit(3 * 86400000)),
  ]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    return () => { timersRef.current.forEach(clearTimeout); };
  }, []);
  const later = (fn: () => void, ms: number) => { timersRef.current.push(setTimeout(fn, ms)); };

  const effectiveActiveId = activeId ?? commits[0]?.id;

  const patchCommit = (id: string, mutator: (c: RunCommit) => void) => {
    setCommits((prev) => prev.map((c) => {
      if (c.id !== id) return c;
      const copy: RunCommit = {
        ...c,
        stageStatuses: c.stageStatuses.slice(),
        stageLogsRevealed: c.stageLogsRevealed.slice(),
        stageDurations: c.stageDurations.slice(),
      };
      mutator(copy);
      return copy;
    }));
  };

  const runStage = (commit: RunCommit, idx: number) => {
    if (idx >= STAGE_DEFS.length) { setRunningId(null); return; }
    const def = buildStageLog(commit, idx);
    patchCommit(commit.id, (c) => {
      c.stageStatuses[idx] = 'running';
      c.stageLogsRevealed[idx] = 0;
      c.selectedStage = idx;
    });
    let li = 0;
    const revealNext = () => {
      patchCommit(commit.id, (c) => { c.stageLogsRevealed[idx] = li + 1; });
      li++;
      if (li < def.lines.length) {
        later(revealNext, LINE_DELAY);
      } else {
        later(() => {
          if (def.fail) {
            patchCommit(commit.id, (c) => {
              c.stageStatuses[idx] = 'failed';
              c.stageDurations[idx] = DURATIONS[idx];
              for (let j = idx + 1; j < STAGE_DEFS.length; j++) c.stageStatuses[j] = 'skipped';
            });
            setRunningId(null);
          } else {
            patchCommit(commit.id, (c) => {
              c.stageStatuses[idx] = 'success';
              c.stageDurations[idx] = DURATIONS[idx];
            });
            runStage(commit, idx + 1);
          }
        }, 380);
      }
    };
    revealNext();
  };

  const simulateCommit = () => {
    if (runningId) return;
    const commit = makeCommit(0, null);
    setCommits((prev) => [commit, ...prev]);
    setActiveId(commit.id);
    setRunningId(commit.id);
    later(() => runStage(commit, 0), 250);
  };

  const retryRun = (commit: RunCommit) => {
    if (runningId) return;
    const reset: RunCommit = {
      ...commit,
      willFailAt: null,
      stageStatuses: STAGE_DEFS.map(() => 'pending'),
      stageLogsRevealed: STAGE_DEFS.map(() => 0),
      stageDurations: STAGE_DEFS.map(() => null),
    };
    patchCommit(commit.id, (c) => Object.assign(c, reset));
    setRunningId(commit.id);
    setActiveId(commit.id);
    later(() => runStage(reset, 0), 250);
  };

  const now = Date.now();
  const active = commits.find((c) => c.id === effectiveActiveId) || commits[0];
  const isRunning = !!runningId;
  const activeIsRunning = runningId === active.id;

  let activeStatusLabel = 'Success', activeStatusColor = '#3fb950';
  if (activeIsRunning) { activeStatusLabel = 'Running'; activeStatusColor = '#d29922'; }
  else if (active.willFailAt !== null) { activeStatusLabel = 'Failed'; activeStatusColor = '#f85149'; }

  const selIdx = active.selectedStage;
  const selDef = STAGE_DEFS[selIdx];
  const selLogDef = buildStageLog(active, selIdx);
  const selStatus = active.stageStatuses[selIdx];
  const selLines = selLogDef.lines.slice(0, active.stageLogsRevealed[selIdx]);
  let selStatusLabel = 'Pending', selStatusColor = '#6e7681';
  if (selStatus === 'running') { selStatusLabel = 'Running'; selStatusColor = '#d29922'; }
  else if (selStatus === 'success') { selStatusLabel = 'Success'; selStatusColor = '#3fb950'; }
  else if (selStatus === 'failed') { selStatusLabel = 'Failed'; selStatusColor = '#f85149'; }
  else if (selStatus === 'skipped') { selStatusLabel = 'Skipped'; selStatusColor = '#484f58'; }
  const hasResult = (selStatus === 'success' || selStatus === 'failed') && !!selLogDef.result;

  const mono = "'IBM Plex Mono', var(--font-mono), monospace";

  return (
    <div style={{ height: '100vh', width: '100%', display: 'flex', background: '#0d1117', color: '#e6edf3', fontFamily: "'IBM Plex Sans', system-ui, sans-serif", overflow: 'hidden' }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
        @keyframes pulseRing {
          0% { box-shadow: 0 0 0 0 rgba(210,153,34,0.45); }
          70% { box-shadow: 0 0 0 8px rgba(210,153,34,0); }
          100% { box-shadow: 0 0 0 0 rgba(210,153,34,0); }
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes blinkDot { 0%,100% { opacity: 1; } 50% { opacity: 0.25; } }
        .lp-run:hover { background: #161b22 !important; }
        .lp-stage:hover { border-color: #58a6ff !important; }
        .lp-sim:hover:not(:disabled) { background: #2ea043 !important; }
        .lp-retry:hover { background: rgba(248,81,73,0.12) !important; }
        .lp-scroll::-webkit-scrollbar { width: 8px; height: 8px; }
        .lp-scroll::-webkit-scrollbar-thumb { background: #30363d; border-radius: 4px; }
        .lp-scroll::-webkit-scrollbar-track { background: transparent; }
      `}</style>

      {/* SIDEBAR */}
      <div style={{ width: 290, flex: 'none', borderRight: '1px solid #21262d', display: 'flex', flexDirection: 'column', background: '#0a0d12' }}>
        <div style={{ padding: '18px 18px 14px', borderBottom: '1px solid #21262d' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 600, color: '#e6edf3' }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 0a8 8 0 0 0-2.53 15.59c.4.07.55-.17.55-.38v-1.44c-2.23.48-2.7-1.08-2.7-1.08-.36-.93-.89-1.17-.89-1.17-.72-.5.06-.49.06-.49.8.06 1.22.82 1.22.82.71 1.22 1.87.87 2.32.66.07-.52.28-.87.51-1.07-1.78-.2-3.65-.89-3.65-3.96 0-.88.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.03 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.08-1.88 3.76-3.66 3.96.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 8 0Z" fill="#8b949e"/></svg>
            kvgkvg/Loomi
          </div>
          <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#3fb950' }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#3fb950', display: 'inline-block', animation: 'blinkDot 1.6s ease-in-out infinite' }} />
            Watching main for commits
          </div>
        </div>
        <div style={{ padding: '14px 18px 8px', fontSize: 11, fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase', color: '#6e7681' }}>Runs</div>
        <div className="lp-scroll" style={{ flex: 1, overflowY: 'auto', padding: '0 10px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {commits.map((c) => {
            const isActive = c.id === effectiveActiveId;
            const isRunningThis = runningId === c.id;
            let statusLabel = 'Success', statusColor = '#3fb950';
            if (isRunningThis) { statusLabel = 'Running'; statusColor = '#d29922'; }
            else if (c.willFailAt !== null) { statusLabel = 'Failed'; statusColor = '#f85149'; }
            return (
              <div key={c.id} className="lp-run" onClick={() => { if (runningId !== c.id) setActiveId(c.id); }}
                style={{ padding: 10, borderRadius: 8, cursor: 'pointer', border: `1px solid ${isActive ? '#58a6ff' : '#21262d'}`, background: isActive ? '#161b22' : 'transparent' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ fontFamily: mono, fontSize: 12, color: '#58a6ff' }}>{c.sha}</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10.5, color: statusColor }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: statusColor, display: 'inline-block', animation: isRunningThis ? 'blinkDot 1s ease-in-out infinite' : undefined }} />
                    {statusLabel}
                  </span>
                </div>
                <div style={{ marginTop: 5, fontSize: 12.5, color: '#c9d1d9', lineHeight: 1.35, overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{c.message}</div>
                <div style={{ marginTop: 6, fontSize: 11, color: '#6e7681' }}>{c.author.split(' <')[0]} · {timeAgoLabel(now - c.createdAt)}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* MAIN */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>

        {/* top bar */}
        <div style={{ flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 28px', borderBottom: '1px solid #21262d' }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600, color: '#e6edf3' }}>Git Capture Pipeline</div>
            <div style={{ fontSize: 12, color: '#6e7681', marginTop: 2 }}>capture_commit → process_raw_event → extract_rationale → embed → finalize</div>
          </div>
          <button className="lp-sim" onClick={simulateCommit} disabled={isRunning}
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 16px', borderRadius: 7, border: '1px solid #30363d', background: isRunning ? '#21262d' : '#238636', color: '#fff', fontSize: 13, fontWeight: 600, cursor: isRunning ? 'default' : 'pointer', fontFamily: 'inherit' }}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 1v14M1 8h14" stroke="#fff" strokeWidth="1.6" strokeLinecap="round"/></svg>
            {isRunning ? 'Running…' : 'Simulate incoming commit'}
          </button>
        </div>

        {/* run summary */}
        <div style={{ flex: 'none', padding: '16px 28px', borderBottom: '1px solid #21262d', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, background: '#0a0d12' }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontFamily: mono, fontSize: 13, color: '#58a6ff' }}>{active.sha}</span>
              <span style={{ fontSize: 13.5, color: '#e6edf3', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{active.message}</span>
            </div>
            <div style={{ marginTop: 7, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {active.files.map((f) => (
                <span key={f} style={{ fontFamily: mono, fontSize: 10.5, color: '#8b949e', background: '#161b22', border: '1px solid #21262d', borderRadius: 5, padding: '2px 7px' }}>{f}</span>
              ))}
            </div>
          </div>
          <div style={{ flex: 'none', textAlign: 'right' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end', fontSize: 12.5, fontWeight: 600, color: activeStatusColor }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: activeStatusColor, display: 'inline-block', animation: activeIsRunning ? 'blinkDot 1s ease-in-out infinite' : undefined }} />
              {activeStatusLabel}
            </div>
            <div style={{ marginTop: 4, fontSize: 11.5, color: '#6e7681' }}>{active.author.split(' <')[0]} · {timeAgoLabel(now - active.createdAt)}</div>
          </div>
        </div>

        {/* failure banner */}
        {active.willFailAt !== null && !activeIsRunning && (
          <div style={{ flex: 'none', margin: '14px 28px 0', padding: '11px 16px', borderRadius: 7, background: 'rgba(248,81,73,0.1)', border: '1px solid rgba(248,81,73,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
            <div style={{ fontSize: 12.5, color: '#ffa198' }}>
              Pipeline failed at <strong>{STAGE_DEFS[active.willFailAt].name}</strong> — raw event left unprocessed for retry.
            </div>
            <button className="lp-retry" onClick={() => retryRun(active)} disabled={isRunning}
              style={{ flex: 'none', padding: '6px 13px', borderRadius: 6, border: '1px solid #f85149', background: 'transparent', color: '#f85149', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
              Retry
            </button>
          </div>
        )}

        {/* pipeline nodes */}
        <div style={{ flex: 'none', padding: '26px 28px 8px', display: 'flex', alignItems: 'stretch', gap: 0 }}>
          {STAGE_DEFS.map((def, i) => {
            const status = active.stageStatuses[i];
            const logDef = buildStageLog(active, i);
            const lines = logDef.lines.slice(0, active.stageLogsRevealed[i]);
            let borderColor = '#21262d', bg = '#0d1117', iconBg = '#161b22', iconColor = '#6e7681', pulse = false;
            if (status === 'running') { borderColor = '#d29922'; bg = 'rgba(210,153,34,0.06)'; iconBg = 'rgba(210,153,34,0.15)'; iconColor = '#d29922'; pulse = true; }
            else if (status === 'success') { borderColor = '#2ea04355'; bg = 'rgba(63,185,80,0.04)'; iconBg = 'rgba(63,185,80,0.14)'; iconColor = '#3fb950'; }
            else if (status === 'failed') { borderColor = '#f85149'; bg = 'rgba(248,81,73,0.06)'; iconBg = 'rgba(248,81,73,0.15)'; iconColor = '#f85149'; }
            else if (status === 'skipped') { borderColor = '#21262d'; bg = '#0a0d12'; iconBg = '#161b22'; iconColor = '#484f58'; }

            const lastLine = lines.length ? lines[lines.length - 1] : null;
            let actionText = 'Waiting…', actionColor = '#484f58';
            if (status === 'skipped') { actionText = 'Skipped — pipeline rolled back'; actionColor = '#484f58'; }
            else if (lastLine) { actionText = lastLine; actionColor = status === 'failed' ? '#f85149' : '#8b949e'; }

            const connectorColor = (status === 'success' || status === 'failed' || status === 'skipped')
              ? (status === 'failed' || status === 'skipped' ? '#30363d' : '#2ea04355') : '#21262d';

            return (
              <div key={def.key} style={{ display: 'flex', alignItems: 'stretch', flex: 1, minWidth: 0 }}>
                <div className="lp-stage" onClick={() => patchCommit(active.id, (c) => { c.selectedStage = i; })}
                  style={{ flex: 1, minWidth: 0, padding: 14, borderRadius: 10, border: `1.5px solid ${borderColor}`, background: bg, cursor: 'pointer', animation: pulse ? 'pulseRing 1.6s ease-out infinite' : undefined }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ width: 30, height: 30, borderRadius: 7, background: iconBg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <StageIcon icon={def.icon} color={iconColor} />
                    </div>
                    {status === 'running' && (
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ animation: 'spin 0.8s linear infinite' }}><path d="M8 1a7 7 0 1 1-7 7" stroke="#d29922" strokeWidth="1.8" strokeLinecap="round"/></svg>
                    )}
                    {(status === 'success' || status === 'failed') && (
                      <span style={{ fontFamily: mono, fontSize: 10.5, color: '#6e7681' }}>{active.stageDurations[i] ? (active.stageDurations[i]! / 1000).toFixed(1) + 's' : ''}</span>
                    )}
                  </div>
                  <div style={{ marginTop: 10, fontSize: 12.5, fontWeight: 600, color: '#e6edf3' }}>{def.name}</div>
                  <div style={{ fontSize: 10.5, color: '#6e7681', marginTop: 1 }}>{def.sub}</div>
                  <div style={{ marginTop: 8, fontFamily: mono, fontSize: 10.5, color: actionColor, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{actionText}</div>
                </div>
                {i < STAGE_DEFS.length - 1 && (
                  <div style={{ flex: 'none', width: 22, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div style={{ width: '100%', height: 2, background: connectorColor, borderRadius: 2 }} />
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* detail panel */}
        <div style={{ flex: 1, minHeight: 0, margin: '14px 28px 22px', border: '1px solid #21262d', borderRadius: 10, background: '#0a0d12', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ flex: 'none', padding: '12px 18px', borderBottom: '1px solid #21262d', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 12.5, fontWeight: 600, color: '#e6edf3' }}>{selDef.name}</span>
              <span style={{ fontSize: 11, color: '#6e7681', fontFamily: mono }}>{selDef.sub}</span>
            </div>
            <span style={{ fontSize: 11, fontWeight: 600, color: selStatusColor }}>{selStatusLabel}</span>
          </div>
          <div className="lp-scroll" style={{ flex: 1, overflowY: 'auto', padding: '14px 18px', fontFamily: mono, fontSize: 12.5, lineHeight: 1.85 }}>
            {selLines.map((t, i) => (
              <div key={i} style={{ color: lineColor(t), whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>› {t}</div>
            ))}
            {selLines.length === 0 && <div style={{ color: '#6e7681' }}>Waiting for stage to start…</div>}
            {hasResult && (
              <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px dashed #21262d' }}>
                <div style={{ color: '#6e7681', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 6 }}>Result</div>
                {Object.entries(selLogDef.result!).map(([k, v]) => (
                  <div key={k}><span style={{ color: '#79c0ff' }}>{k}</span><span style={{ color: '#6e7681' }}>: </span><span style={{ color: '#a5d6ff' }}>{String(v)}</span></div>
                ))}
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
