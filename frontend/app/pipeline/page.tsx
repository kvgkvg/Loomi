"use client";

import React, { useEffect, useState } from 'react';

// Live pipeline visualization: history from GET /api/runs, live runs from
// the pipeline_stage SSE events emitted by the Git poller.
// Visual design ported from Claude Design "Loomi Pipeline.dc.html".

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001';

const STAGE_DEFS = [
  { key: 'adapter', name: 'Git Adapter', sub: 'capture_commit', icon: 'git' },
  { key: 'version', name: 'Version Asset', sub: 'process_raw_event', icon: 'version' },
  { key: 'llm', name: 'Rationale Extraction', sub: 'GLM-5.2 · Featherless', icon: 'llm' },
  { key: 'persist', name: 'Persist Rationale', sub: 'Postgres', icon: 'persist' },
  { key: 'embed', name: 'Embed + Upsert', sub: 'MiniLM-L6-v2 → Chroma', icon: 'embed' },
  { key: 'finalize', name: 'Finalize', sub: 'commit + mark processed', icon: 'final' },
] as const;

interface Stage {
  key: string;
  status: string; // pending | running | success | failed | skipped
  log: string[];
  result: Record<string, unknown>;
}

interface Run {
  run_id: string;
  sha: string;
  full_sha: string;
  message: string;
  author: string;
  files: string[];
  received_at: string | null;
  status: string; // running | success | failed
  stages: Stage[];
  selectedStage: number;
  liveStartedAt?: number;
}

function emptyStages(): Stage[] {
  return STAGE_DEFS.map((d) => ({ key: d.key, status: 'pending', log: [], result: {} }));
}

function defaultSelected(stages: Stage[]): number {
  const failed = stages.findIndex((s) => s.status === 'failed');
  if (failed !== -1) return failed;
  const running = stages.findIndex((s) => s.status === 'running');
  if (running !== -1) return running;
  if (stages.some((s) => s.key === 'finalize' && s.result?.review_status === 'pending')) {
    return STAGE_DEFS.findIndex((s) => s.key === 'llm');
  }
  return STAGE_DEFS.length - 1;
}

function timeAgoLabel(run: Run): string {
  let ts: number | null = null;
  if (run.liveStartedAt) ts = run.liveStartedAt;
  else if (run.received_at) ts = new Date(run.received_at.replace(' ', 'T')).getTime();
  if (!ts || Number.isNaN(ts)) return '';
  const m = Math.floor((Date.now() - ts) / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return m + 'm ago';
  const h = Math.floor(m / 60);
  if (h < 24) return h + 'h ago';
  return Math.floor(h / 24) + 'd ago';
}

function lineColor(text: string) {
  if (text.indexOf('⚠') === 0 || text.indexOf('Error') !== -1) return '#f85149';
  if (text.indexOf('✓') !== -1) return '#3fb950';
  if (text.indexOf('$') === 0 || text.indexOf('POST') === 0 || text.indexOf('INSERT') === 0 || text.indexOf('UPDATE') === 0 || text.indexOf('COMMIT') === 0) return '#79c0ff';
  return '#8b949e';
}

function runStatus(stages: Stage[]): string {
  if (stages.some((s) => s.status === 'failed')) return 'failed';
  if (stages[STAGE_DEFS.length - 1].status === 'success') return 'success';
  return 'running';
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
  const [runs, setRuns] = useState<Run[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);

  const loadRuns = () => fetch(`${API_BASE}/api/runs`)
    .then((res) => res.json())
    .then((data) => {
      const loaded: Run[] = (data.runs || []).map((r: Omit<Run, 'selectedStage'>) => ({
        ...r,
        selectedStage: defaultSelected(r.stages || emptyStages()),
        stages: r.stages || emptyStages(),
      }));
      setRuns((prev) => {
        const loadedIds = new Set(loaded.map((r) => r.run_id));
        return [...loaded, ...prev.filter((r) => !loadedIds.has(r.run_id))];
      });
      return loaded;
    });

  // Load run history; honor ?asset= / ?run= deep links from Narrative Canvas
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const wantAsset = params.get('asset');
    const wantRun = params.get('run');

    loadRuns()
      .then((loaded) => {
        if (!loaded?.length) return;
        if (wantRun) {
          const match = loaded.find((r) => r.run_id === wantRun || r.sha === wantRun || r.full_sha === wantRun);
          if (match) setActiveId(match.run_id);
          return;
        }
        if (wantAsset) {
          const match = loaded.find((r) =>
            r.stages.some((s) => s.result && String((s.result as { asset_id?: string }).asset_id || '') === wantAsset)
          );
          if (match) setActiveId(match.run_id);
        }
      })
      .catch((err) => {
        console.error('Failed to load runs:', err);
        setLoadError('Could not load run history from the API.');
      });
  }, []);

  // Live pipeline_stage events
  useEffect(() => {
    const eventSource = new EventSource(`${API_BASE}/api/events/stream`);
    eventSource.addEventListener('pipeline_stage', (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data);
        const { run, stage, status, log, result } = payload;
        const stageIdx = STAGE_DEFS.findIndex((d) => d.key === stage);
        if (stageIdx === -1) return;
        setRuns((prev) => {
          const idx = prev.findIndex((r) => r.run_id === run.run_id);
          let next: Run[];
          if (idx === -1) {
            const fresh: Run = {
              ...run,
              stages: emptyStages(),
              selectedStage: stageIdx,
              status: 'running',
              liveStartedAt: Date.now(),
            };
            next = [fresh, ...prev];
          } else {
            next = prev.slice();
            next[idx] = { ...next[idx], stages: next[idx].stages.slice() };
          }
          const target = next.find((r) => r.run_id === run.run_id)!;
          target.stages[stageIdx] = { key: stage, status, log: log || [], result: result || {} };
          target.selectedStage = stageIdx;
          target.status = runStatus(target.stages);
          return next;
        });
        setActiveId(run.run_id);
      } catch (err) {
        console.error('Bad pipeline_stage event:', err);
      }
    });
    eventSource.onerror = (err) => console.error('SSE stream error:', err);
    return () => eventSource.close();
  }, []);

  const active = runs.find((r) => r.run_id === activeId) || runs[0];
  const mono = "'IBM Plex Mono', var(--font-mono), monospace";
  const pendingReview = active?.stages.find((s) => s.key === 'finalize' && s.result?.review_status === 'pending');
  const pendingVersionId = typeof pendingReview?.result?.version_id === 'string' ? pendingReview.result.version_id : null;
  const linkedAssetId = (() => {
    if (!active) return null;
    for (const s of active.stages) {
      const id = s.result?.asset_id;
      if (typeof id === 'string' && id.length > 0) return id;
    }
    return null;
  })();

  async function approveRationale() {
    if (!pendingVersionId || reviewBusy) return;
    setReviewBusy(true);
    setReviewMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/rationale-review/version/${encodeURIComponent(String(pendingVersionId))}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewer: 'Pipeline UI' }),
      });
      if (!res.ok) throw new Error((await res.json()).error || 'Review failed');
      setReviewMessage('Approved. Finalize stage completed.');
      const loaded = await loadRuns();
      const refreshed = loaded.find((r) => r.run_id === active.run_id);
      if (refreshed) setActiveId(refreshed.run_id);
    } catch (err) {
      setReviewMessage(err instanceof Error ? err.message : 'Review failed');
    } finally {
      setReviewBusy(false);
    }
  }

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
        .lp-scroll::-webkit-scrollbar { width: 8px; height: 8px; }
        .lp-scroll::-webkit-scrollbar-thumb { background: #30363d; border-radius: 4px; }
        .lp-scroll::-webkit-scrollbar-track { background: transparent; }
      `}</style>

      {/* SIDEBAR */}
      <div style={{ width: 290, flex: 'none', borderRight: '1px solid #21262d', display: 'flex', flexDirection: 'column', background: '#0a0d12' }}>
        <div style={{ padding: '18px 18px 14px', borderBottom: '1px solid #21262d' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 600, color: '#e6edf3' }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 0a8 8 0 0 0-2.53 15.59c.4.07.55-.17.55-.38v-1.44c-2.23.48-2.7-1.08-2.7-1.08-.36-.93-.89-1.17-.89-1.17-.72-.5.06-.49.06-.49.8.06 1.22.82 1.22.82.71 1.22 1.87.87 2.32.66.07-.52.28-.87.51-1.07-1.78-.2-3.65-.89-3.65-3.96 0-.88.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.03 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.08-1.88 3.76-3.66 3.96.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 8 0Z" fill="#8b949e"/></svg>
            kvgkvg/test_loomi_repo
          </div>
          <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#3fb950' }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#3fb950', display: 'inline-block', animation: 'blinkDot 1.6s ease-in-out infinite' }} />
            Polling tracked repository
          </div>
        </div>
        <div style={{ padding: '14px 18px 8px', fontSize: 11, fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase', color: '#6e7681' }}>Runs</div>
        <div className="lp-scroll" style={{ flex: 1, overflowY: 'auto', padding: '0 10px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {runs.length === 0 && (
            <div style={{ padding: '20px 10px', fontSize: 12.5, color: '#6e7681', lineHeight: 1.5 }}>
              {loadError || 'No runs yet. Push a .md/.txt/.prompt/.json/.yaml file to the tracked repo.'}
            </div>
          )}
          {runs.map((c) => {
            const isActive = active && c.run_id === active.run_id;
            let statusLabel = 'Success', statusColor = '#3fb950';
            if (c.status === 'running') { statusLabel = 'Running'; statusColor = '#d29922'; }
            else if (c.status === 'failed') { statusLabel = 'Failed'; statusColor = '#f85149'; }
            return (
              <div key={c.run_id} className="lp-run" onClick={() => setActiveId(c.run_id)}
                style={{ padding: 10, borderRadius: 8, cursor: 'pointer', border: `1px solid ${isActive ? '#58a6ff' : '#21262d'}`, background: isActive ? '#161b22' : 'transparent' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ fontFamily: mono, fontSize: 12, color: '#58a6ff' }}>{c.sha}</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10.5, color: statusColor }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: statusColor, display: 'inline-block', animation: c.status === 'running' ? 'blinkDot 1s ease-in-out infinite' : undefined }} />
                    {statusLabel}
                  </span>
                </div>
                <div style={{ marginTop: 5, fontSize: 12.5, color: '#c9d1d9', lineHeight: 1.35, overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{c.message}</div>
                <div style={{ marginTop: 6, fontSize: 11, color: '#6e7681' }}>{c.author} · {timeAgoLabel(c)}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* MAIN */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>

        {/* top bar */}
        <div style={{ flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 28px', borderBottom: '1px solid #21262d', gap: 16 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: '#e6edf3' }}>Git Capture Pipeline</div>
            <div style={{ fontSize: 12, color: '#6e7681', marginTop: 2 }}>capture_commit → process_raw_event → extract_rationale → embed → finalize</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
            {linkedAssetId && (
              <a
                href={`/?asset=${encodeURIComponent(linkedAssetId)}`}
                style={{
                  fontSize: 12.5,
                  fontWeight: 600,
                  color: '#0d1117',
                  background: '#3fb950',
                  border: '1px solid #2ea043',
                  borderRadius: 9999,
                  padding: '7px 14px',
                  textDecoration: 'none',
                }}
                title="Open this asset on the Narrative Canvas"
              >
                Open in Canvas
              </a>
            )}
            <a
              href="/"
              style={{
                fontSize: 12.5,
                fontWeight: 500,
                color: '#c9d1d9',
                border: '1px solid #30363d',
                borderRadius: 9999,
                padding: '7px 14px',
                textDecoration: 'none',
              }}
            >
              Canvas
            </a>
          </div>
        </div>

        {!active ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6e7681', fontSize: 14, padding: 28, textAlign: 'center' }}>
            Waiting for pipeline runs… push a prompt/workflow file to the tracked repository and the poller will pick it up.
          </div>
        ) : (
          <>
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
                {(() => {
                  let label = 'Success', color = '#3fb950';
                  if (active.status === 'running') { label = 'Running'; color = '#d29922'; }
                  else if (active.status === 'failed') { label = 'Failed'; color = '#f85149'; }
                  return (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end', fontSize: 12.5, fontWeight: 600, color }}>
                      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color, display: 'inline-block', animation: active.status === 'running' ? 'blinkDot 1s ease-in-out infinite' : undefined }} />
                      {label}
                    </div>
                  );
                })()}
                <div style={{ marginTop: 4, fontSize: 11.5, color: '#6e7681' }}>{active.author} · {timeAgoLabel(active)}</div>
              </div>
            </div>

            {/* failure banner */}
            {active.status === 'failed' && (
              <div style={{ flex: 'none', margin: '14px 28px 0', padding: '11px 16px', borderRadius: 7, background: 'rgba(248,81,73,0.1)', border: '1px solid rgba(248,81,73,0.35)', fontSize: 12.5, color: '#ffa198' }}>
                Pipeline failed at <strong>{STAGE_DEFS[Math.max(active.stages.findIndex((s) => s.status === 'failed'), 0)].name}</strong> — raw event left unprocessed; it is retried on the next processing pass.
              </div>
            )}

            {/* pipeline nodes */}
            <div style={{ flex: 'none', padding: '26px 28px 8px', display: 'flex', alignItems: 'stretch', gap: 0 }}>
              {STAGE_DEFS.map((def, i) => {
                const stage = active.stages[i];
                const status = stage.status;
                let borderColor = '#21262d', bg = '#0d1117', iconBg = '#161b22', iconColor = '#6e7681', pulse = false;
                if (status === 'running') { borderColor = '#d29922'; bg = 'rgba(210,153,34,0.06)'; iconBg = 'rgba(210,153,34,0.15)'; iconColor = '#d29922'; pulse = true; }
                else if (status === 'success') { borderColor = '#2ea04355'; bg = 'rgba(63,185,80,0.04)'; iconBg = 'rgba(63,185,80,0.14)'; iconColor = '#3fb950'; }
                else if (status === 'failed') { borderColor = '#f85149'; bg = 'rgba(248,81,73,0.06)'; iconBg = 'rgba(248,81,73,0.15)'; iconColor = '#f85149'; }
                else if (status === 'skipped') { borderColor = '#21262d'; bg = '#0a0d12'; iconBg = '#161b22'; iconColor = '#484f58'; }

                const lastLine = stage.log.length ? stage.log[stage.log.length - 1] : null;
                let actionText = 'Waiting…', actionColor = '#484f58';
                if (status === 'skipped') { actionText = 'Skipped — pipeline rolled back'; actionColor = '#484f58'; }
                else if (lastLine) { actionText = lastLine; actionColor = status === 'failed' ? '#f85149' : '#8b949e'; }

                const connectorColor = (status === 'success') ? '#2ea04355' : (status === 'failed' || status === 'skipped') ? '#30363d' : '#21262d';

                return (
                  <div key={def.key} style={{ display: 'flex', alignItems: 'stretch', flex: 1, minWidth: 0 }}>
                    <div className="lp-stage" onClick={() => setRuns((prev) => prev.map((r) => r.run_id === active.run_id ? { ...r, selectedStage: i } : r))}
                      style={{ flex: 1, minWidth: 0, padding: 14, borderRadius: 10, border: `1.5px solid ${borderColor}`, background: bg, cursor: 'pointer', animation: pulse ? 'pulseRing 1.6s ease-out infinite' : undefined }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div style={{ width: 30, height: 30, borderRadius: 7, background: iconBg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <StageIcon icon={def.icon} color={iconColor} />
                        </div>
                        {status === 'running' && (
                          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ animation: 'spin 0.8s linear infinite' }}><path d="M8 1a7 7 0 1 1-7 7" stroke="#d29922" strokeWidth="1.8" strokeLinecap="round"/></svg>
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
            {(() => {
              const selIdx = active.selectedStage;
              const selDef = STAGE_DEFS[selIdx];
              const stage = active.stages[selIdx];
              let selStatusLabel = 'Pending', selStatusColor = '#6e7681';
              if (stage.status === 'running') { selStatusLabel = 'Running'; selStatusColor = '#d29922'; }
              else if (stage.status === 'success') { selStatusLabel = 'Success'; selStatusColor = '#3fb950'; }
              else if (stage.status === 'failed') { selStatusLabel = 'Failed'; selStatusColor = '#f85149'; }
              else if (stage.status === 'skipped') { selStatusLabel = 'Skipped'; selStatusColor = '#484f58'; }
              const hasResult = (stage.status === 'success' || stage.status === 'failed') && Object.keys(stage.result).length > 0;
              return (
                <div style={{ flex: 1, minHeight: 0, margin: '14px 28px 22px', border: '1px solid #21262d', borderRadius: 10, background: '#0a0d12', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                  <div style={{ flex: 'none', padding: '12px 18px', borderBottom: '1px solid #21262d', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ fontSize: 12.5, fontWeight: 600, color: '#e6edf3' }}>{selDef.name}</span>
                      <span style={{ fontSize: 11, color: '#6e7681', fontFamily: mono }}>{selDef.sub}</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      {selDef.key === 'llm' && pendingVersionId && (
                        <button
                          type="button"
                          onClick={approveRationale}
                          disabled={reviewBusy}
                          style={{ border: '1px solid #d29922', background: reviewBusy ? '#21262d' : 'rgba(210,153,34,0.12)', color: '#f0c36a', borderRadius: 6, padding: '5px 9px', fontSize: 11, fontWeight: 600, cursor: reviewBusy ? 'default' : 'pointer' }}
                        >
                          {reviewBusy ? 'Approving…' : 'Human review: approve'}
                        </button>
                      )}
                      <span style={{ fontSize: 11, fontWeight: 600, color: selStatusColor }}>{selStatusLabel}</span>
                    </div>
                  </div>
                  <div className="lp-scroll" style={{ flex: 1, overflowY: 'auto', padding: '14px 18px', fontFamily: mono, fontSize: 12.5, lineHeight: 1.85 }}>
                    {selDef.key === 'llm' && pendingVersionId && (
                      <div style={{ marginBottom: 12, padding: 10, border: '1px solid rgba(210,153,34,0.35)', borderRadius: 7, background: 'rgba(210,153,34,0.08)', color: '#f0c36a', fontFamily: "'IBM Plex Sans', system-ui, sans-serif", fontSize: 12.5, lineHeight: 1.45 }}>
                        Human review required before trusted rationale is finalized. Draft embedding is already precomputed for fast approval.
                      </div>
                    )}
                    {reviewMessage && <div style={{ marginBottom: 10, color: reviewMessage.indexOf('Approved') === 0 ? '#3fb950' : '#f85149' }}>› {reviewMessage}</div>}
                    {stage.log.map((t, i) => (
                      <div key={i} style={{ color: lineColor(t), whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>› {t}</div>
                    ))}
                    {stage.log.length === 0 && <div style={{ color: '#6e7681' }}>Waiting for stage to start…</div>}
                    {hasResult && (
                      <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px dashed #21262d' }}>
                        <div style={{ color: '#6e7681', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 6 }}>Result</div>
                        {Object.entries(stage.result).map(([k, v]) => (
                          <div key={k}><span style={{ color: '#79c0ff' }}>{k}</span><span style={{ color: '#6e7681' }}>: </span><span style={{ color: '#a5d6ff' }}>{String(v)}</span></div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}
          </>
        )}
      </div>
    </div>
  );
}
