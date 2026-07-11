"use client";

import React, { useState, useEffect, useRef } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';

// Register GSAP plugins
if (typeof window !== 'undefined') {
  gsap.registerPlugin(useGSAP);
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001';

// Short human label for the tracked repo: "owner/repo" from the remote URL,
// else the repo folder name from its path.
function repoLabel(info: { repo_path?: string; remote_url?: string } | null): string {
  if (!info) return '';
  if (info.remote_url) {
    const m = info.remote_url.match(/[:/]([^/]+\/[^/]+?)(?:\.git)?$/);
    if (m) return m[1];
    return info.remote_url;
  }
  if (info.repo_path) {
    const parts = info.repo_path.replace(/\/+$/, '').split('/');
    return parts[parts.length - 1] || info.repo_path;
  }
  return '';
}

interface GitEvent {
  asset_id: string;
  title: string;
  owner: string;
  problem: string;
  timestamp?: string;
}

interface Suggestion {
  asset_id: string;
  title: string;
  problem: string;
  score: number;
  usage_count: number;
  owner_name: string;
  content?: string;
  role_reason?: string | null;
}

const ROLE_PRESETS = ['Developer', 'Intern', 'Tech Lead', 'Manager'];

interface IntentCheck {
  name: string;
  status: 'pass' | 'fail' | 'action_required' | 'error';
  detail: string;
  asset_id?: string;
}

interface IntentReview {
  id: string;
  prompt: string;
  source_env: string;
  user_name: string | null;
  intent: string | null;
  checks: IntentCheck[];
  status: 'passed' | 'pending' | 'approved' | 'rejected';
  reviewer?: string | null;
  created_at?: string | null;
}

const CHECK_ICON: Record<IntentCheck['status'], string> = {
  pass: '✓', fail: '✗', action_required: '●', error: '⚠'
};

interface Explanation {
  explanation: string;
  cited_versions: number[];
  cited_constraints: string[];
}

interface AssetVersion {
  version_number: number;
  created_at: string | null;
  diff_summary: string | null;
  problem: string | null;
  constraints: string[];
}

interface AssetDetail {
  asset_id: string;
  title: string;
  owner_name: string;
  usage_count: number;
  content: string;
  versions: AssetVersion[];
}

export default function Home() {
  // UI States
  const [health, setHealth] = useState<{ status: string; core_service?: any }>({ status: 'checking' });
  const [gitEvents, setGitEvents] = useState<GitEvent[]>([]);
  const [composerInput, setComposerInput] = useState('');
  const [ghostSuggestion, setGhostSuggestion] = useState<Suggestion | null>(null);
  const [isLoadingSuggestion, setIsLoadingSuggestion] = useState(false);
  const [activeAsset, setActiveAsset] = useState<any | null>(null);
  const [activeExplanation, setActiveExplanation] = useState<Explanation | null>(null);
  const [isLoadingExplanation, setIsLoadingExplanation] = useState(false);
  const [explanationQuestion, setExplanationQuestion] = useState('');
  const [isAskingQuestion, setIsAskingQuestion] = useState(false);
  const [adoptWarning, setAdoptWarning] = useState<string | null>(null);
  const [repoInfo, setRepoInfo] = useState<{ repo_path?: string; remote_url?: string; branch?: string; head_short?: string } | null>(null);
  const [role, setRole] = useState('Developer');
  const [intentReviews, setIntentReviews] = useState<IntentReview[]>([]);
  const [trackInput, setTrackInput] = useState('');
  const [isTracking, setIsTracking] = useState(false);
  const [trackError, setTrackError] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const rationaleTextRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Fetch health check on mount
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/health`);
        const data = await res.json();
        setHealth(data);
      } catch (err) {
        setHealth({ status: 'degraded' });
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  // Restore/persist the viewing role (personalization lens, not access control)
  useEffect(() => {
    const saved = window.localStorage.getItem('loomi-role');
    if (saved) setRole(saved);
  }, []);
  const handleRoleChange = (value: string) => {
    setRole(value);
    window.localStorage.setItem('loomi-role', value);
  };

  // Fetch which repository the poller is tracking
  useEffect(() => {
    fetch(`${API_BASE}/api/repo-info`)
      .then(res => res.json())
      .then(data => setRepoInfo(data))
      .catch(() => setRepoInfo(null));
  }, []);

  // Intent CI: initial list of prompt reviews
  useEffect(() => {
    fetch(`${API_BASE}/api/intent-reviews`)
      .then(res => res.json())
      .then(data => { if (Array.isArray(data)) setIntentReviews(data); })
      .catch(() => {});
  }, []);

  const handleResolveIntent = async (reviewId: string, action: 'approve' | 'reject') => {
    try {
      const res = await fetch(`${API_BASE}/api/intent-review/${reviewId}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, reviewer: role })
      });
      const data = await res.json();
      if (res.ok) {
        setIntentReviews(prev => prev.map(r => r.id === reviewId ? { ...r, status: data.status, reviewer: data.reviewer } : r));
      }
    } catch (err) {
      console.error("Error resolving intent review:", err);
    }
  };

  // Server-Sent Events (SSE) stream for Git commits
  useEffect(() => {
    console.log("Connecting to SSE stream...");
    const eventSource = new EventSource(`${API_BASE}/api/events/stream`);

    eventSource.addEventListener('intent_review', (event: MessageEvent) => {
      try {
        const review: IntentReview = JSON.parse(event.data);
        setIntentReviews(prev => [review, ...prev.filter(r => r.id !== review.id)].slice(0, 20));
      } catch (err) {
        console.error("Error parsing intent_review event:", err);
      }
    });

    eventSource.addEventListener('intent_review_resolved', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        setIntentReviews(prev => prev.map(r => r.id === data.id ? { ...r, status: data.status, reviewer: data.reviewer } : r));
      } catch (err) {
        console.error("Error parsing intent_review_resolved event:", err);
      }
    });

    eventSource.addEventListener('memory_ready', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        console.log("SSE Received memory_ready:", data);
        const newEvent: GitEvent = {
          asset_id: data.asset_id,
          title: data.title,
          owner: data.owner,
          problem: data.problem,
          timestamp: new Date().toLocaleTimeString()
        };
        setGitEvents(prev => [newEvent, ...prev]);

        // Muted notification sound/interaction effect
        gsap.fromTo(".notification-toast", 
          { y: -20, opacity: 0 },
          { y: 0, opacity: 1, duration: 0.4, ease: "power2.out" }
        );
      } catch (err) {
        console.error("Error parsing SSE event data:", err);
      }
    });

    eventSource.onerror = (err) => {
      console.error("SSE stream error:", err);
    };

    return () => {
      eventSource.close();
    };
  }, []);

  // Debounced Recommendation logic
  useEffect(() => {
    if (composerInput.trim().length < 24) {
      setGhostSuggestion(null);
      return;
    }

    setIsLoadingSuggestion(true);

    // Cancel stale recommendation requests
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const delayDebounceFn = setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/recommend`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_description: composerInput, top_k: 1, role }),
          signal: controller.signal
        });
        const results = await res.json();
        if (results && results.length > 0) {
          const best = results[0];
          // Threshhold gating: DESIGN.md specifies score 0.45 or above
          if (best.score >= 0.45) {
            setGhostSuggestion(best);
          } else {
            setGhostSuggestion(null);
          }
        } else {
          setGhostSuggestion(null);
        }
      } catch (err: any) {
        if (err.name !== 'AbortError') {
          console.error("Recommendation error:", err);
        }
      } finally {
        setIsLoadingSuggestion(false);
      }
    }, 650); // Debounce duration 650 ms

    return () => {
      clearTimeout(delayDebounceFn);
      if (controller) controller.abort();
    };
  }, [composerInput, role]);

  // GSAP Scrubbed Text Reveal Animation for Asset Rationale
  useGSAP(() => {
    if (activeExplanation && rationaleTextRef.current) {
      // Simple transform and opacity fade-in as per Design System rules
      gsap.fromTo(rationaleTextRef.current,
        { opacity: 0, y: 10 },
        { opacity: 1, y: 0, duration: 0.5, ease: "power2.out" }
      );
    }
  }, { dependencies: [activeExplanation], scope: containerRef });

  // Handle Review action
  const handleReview = async (assetId: string) => {
    setIsLoadingExplanation(true);
    setActiveExplanation(null);
    setExplanationQuestion('');
    setAdoptWarning(null);

    try {
      // Asset detail is fast (DB only) — show it immediately so the panel isn't
      // blank for the many seconds the LLM explanation takes.
      const assetRes = await fetch(`${API_BASE}/api/asset/${assetId}`);
      const assetData: AssetDetail | { error?: string } = await assetRes.json();

      if (assetRes.ok && 'asset_id' in assetData) {
        setActiveAsset({
          id: assetData.asset_id,
          title: assetData.title,
          owner: assetData.owner_name || foundGitOwner(assetId) || 'Unknown',
          content: assetData.content,
          versions: assetData.versions
        });
      } else {
        setActiveAsset({
          id: assetId,
          title: ghostSuggestion?.asset_id === assetId ? ghostSuggestion.title : 'Asset Review',
          owner: ghostSuggestion?.owner_name || foundGitOwner(assetId) || 'Unknown',
          content: '',
          versions: []
        });
      }

      const expRes = await fetch(`${API_BASE}/api/explain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ asset_id: assetId, role })
      });
      const explanationData = await expRes.json();
      setActiveExplanation(explanationData);
    } catch (err) {
      console.error("Error loading asset details:", err);
    } finally {
      setIsLoadingExplanation(false);
    }
  };

  // Switch the repository the poller tracks (git URL or a container-visible path)
  const handleTrack = async () => {
    const repo = trackInput.trim();
    if (!repo || isTracking) return;
    setIsTracking(true);
    setTrackError(null);
    try {
      const res = await fetch(`${API_BASE}/api/track`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to switch repository');
      setRepoInfo(data);
      setGitEvents([]); // new repo → fresh feed
      setTrackInput('');
    } catch (err: any) {
      setTrackError(err.message || 'Failed to switch repository');
    } finally {
      setIsTracking(false);
    }
  };

  const foundGitOwner = (assetId: string) => {
    const e = gitEvents.find(event => event.asset_id === assetId);
    return e ? e.owner : '';
  };

  // Handle Question submission to Onboarding Assistant
  const handleAskQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!explanationQuestion.trim() || !activeAsset) return;

    setIsAskingQuestion(true);
    try {
      const res = await fetch(`${API_BASE}/api/explain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          asset_id: activeAsset.id,
          question: explanationQuestion,
          role
        })
      });
      const data = await res.json();
      setActiveExplanation(data);
    } catch (err) {
      console.error("Error asking question:", err);
    } finally {
      setIsAskingQuestion(false);
    }
  };

  // Handle Explicit Prompt Adoption
  const handleAdopt = async () => {
    if (!activeAsset) return;

    // Insert the real stored asset content into the composer
    const promptContent = activeAsset.content || `[Prompt: ${activeAsset.title}] (content unavailable)`;
    setComposerInput(promptContent);

    // Record adoption in db/asset_usage
    try {
      const res = await fetch(`${API_BASE}/api/adopt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          asset_id: activeAsset.id,
          task_description: composerInput || "Adopting prompt from dashboard"
        })
      });
      const data = await res.json();
      if (data.status !== 'success') {
        throw new Error("Usage logging failed");
      }
      setAdoptWarning(null);
    } catch (err) {
      console.warn("Usage recording failed:", err);
      // Non-destructive warning
      setAdoptWarning("Prompt adopted locally, but usage persistence failed on the server.");
    }
  };

  return (
    <div ref={containerRef} style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      
      {/* 1. TOP NAVIGATION */}
      <nav style={{
        height: '64px',
        borderBottom: '1px solid var(--border-color)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 24px',
        backgroundColor: 'var(--panel-bg)',
        backdropFilter: 'blur(10px)',
        position: 'sticky',
        top: 0,
        zIndex: 100
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontWeight: 600, fontSize: '18px', color: 'var(--text-primary)' }}>Loomi</span>
          <span style={{
            fontSize: '11px',
            fontFamily: 'var(--font-mono)',
            padding: '2px 6px',
            border: '1px solid var(--accent-color)',
            color: 'var(--accent-color)',
            borderRadius: '4px'
          }}>MEM-ORGANIZATION</span>
        </div>
        
        {/* Aggregated Health Check */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {/* Role lens switcher — personalization, not access control */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span className="mono-text" style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Viewing as</span>
            <select
              value={role}
              onChange={(e) => handleRoleChange(e.target.value)}
              className="mono-text"
              style={{
                fontSize: '12px',
                padding: '4px 8px',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
                backgroundColor: 'var(--panel-bg)',
                color: 'var(--text-primary)',
                cursor: 'pointer'
              }}
            >
              {ROLE_PRESETS.map(r => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: health.status === 'ok' ? 'var(--accent-color)' : 'var(--alert-color)',
              display: 'inline-block'
            }} />
            <span className="mono-text" style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              System: {health.status === 'ok' ? 'HEALTHY' : 'DEGRADED'}
            </span>
          </div>
        </div>
      </nav>

      {/* 2. MAIN NARRATIVE CANVAS */}
      <main style={{
        flex: 1,
        display: 'grid',
        gridTemplateColumns: 'repeat(12, 1fr)',
        gap: '24px',
        padding: '24px',
      }}>
        
        {/* LEFT COLUMN: NARRATIVE EVENT FEED & COMPOSER (7 Columns) */}
        <section style={{
          gridColumn: 'span 7',
          display: 'flex',
          flexDirection: 'column',
          gap: '24px'
        }}>
          
          {/* Git Memory Notification Toast / Feed */}
          <div style={{
            padding: '20px',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--panel-radius)',
            backgroundColor: 'var(--panel-bg)'
          }}>
            <h3 style={{ fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)', marginBottom: '4px' }}>
              Captured Git Knowledge Feed
            </h3>
            <div className="mono-text" style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
              {repoInfo ? (
                <>
                  Tracking: <span style={{ color: 'var(--accent-color)', fontWeight: 600 }}>{repoLabel(repoInfo)}</span>
                  {repoInfo.branch ? <span> @ {repoInfo.branch}</span> : null}
                  {repoInfo.head_short ? <span style={{ color: 'var(--text-secondary)' }}> ({repoInfo.head_short})</span> : null}
                </>
              ) : (
                <span>Tracking: resolving repository…</span>
              )}
            </div>
            <div style={{ display: 'flex', gap: '8px', marginBottom: trackError ? '6px' : '12px' }}>
              <input
                className="mono-text"
                value={trackInput}
                onChange={(e) => setTrackInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleTrack(); }}
                placeholder="git URL or container path (e.g. https://github.com/owner/repo or /repo)"
                style={{ flex: 1, fontSize: '12px', padding: '8px 10px', borderRadius: 'var(--input-radius)', border: '1px solid var(--border-color)', backgroundColor: 'transparent', color: 'var(--text-primary)' }}
              />
              <button className="btn btn-secondary" onClick={handleTrack} disabled={isTracking}>
                {isTracking ? 'Switching…' : 'Track'}
              </button>
            </div>
            {trackError ? (
              <p style={{ fontSize: '12px', color: '#e5484d', marginBottom: '12px' }}>{trackError}</p>
            ) : null}

            {gitEvents.length === 0 ? (
              <div style={{ padding: '24px 0', textAlign: 'center', color: 'var(--text-secondary)' }}>
                <p style={{ fontSize: '14px' }}>No active Git events detected. Make a prompt commit to see Loomi capture it in real-time.</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {gitEvents.map((event, idx) => (
                  <div key={idx} className="notification-toast" style={{
                    padding: '16px',
                    borderRadius: 'var(--input-radius)',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'var(--accent-soft)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center'
                  }}>
                    <div>
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '4px' }}>
                        <span className="mono-text" style={{ fontSize: '11px', color: 'var(--accent-color)', fontWeight: 600 }}>GIT COMMIT</span>
                        <span className="mono-text" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{event.timestamp}</span>
                      </div>
                      <h4 style={{ fontSize: '16px', fontWeight: 500 }}>{event.title}</h4>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Author: {event.owner} • {event.problem}</p>
                    </div>
                    <button className="btn btn-secondary" onClick={() => handleReview(event.asset_id)}>
                      Review
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Assigned Task Composer Area */}
          <div style={{
            padding: '24px',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--panel-radius)',
            backgroundColor: 'var(--panel-bg)',
            position: 'relative'
          }}>
            <h2 style={{ fontSize: '20px', fontWeight: 500, marginBottom: '12px' }}>Composer</h2>
            <p style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
              Describe your current development assignment. Loomi will proactively suggest matching prompts from the database.
            </p>
            
            <textarea
              value={composerInput}
              onChange={(e) => setComposerInput(e.target.value)}
              placeholder="e.g. I need to write an agent that triages incoming customer support tickets..."
              style={{
                width: '100%',
                minHeight: '160px',
                padding: '16px',
                borderRadius: 'var(--input-radius)',
                border: '1px solid var(--border-color)',
                backgroundColor: 'transparent',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-sans)',
                fontSize: '16px',
                lineHeight: '1.5',
                resize: 'vertical',
                outline: 'none'
              }}
            />
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '12px' }}>
              <span className="mono-text" style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                {composerInput.length} characters (min 24 to match)
              </span>
              {isLoadingSuggestion && (
                <span className="mono-text" style={{ fontSize: '12px', color: 'var(--accent-color)' }}>
                  Searching memory...
                </span>
              )}
            </div>

            {/* Ghost Suggestion Panel overlay */}
            {ghostSuggestion && (
              <div style={{
                position: 'absolute',
                bottom: '80px',
                left: '24px',
                right: '24px',
                padding: '16px',
                borderRadius: 'var(--input-radius)',
                border: '1px solid var(--accent-color)',
                backgroundColor: 'rgba(201, 217, 204, 0.95)',
                color: '#1F2320',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                boxShadow: '0 4px 20px rgba(0,0,0,0.1)',
                backdropFilter: 'blur(5px)',
                zIndex: 10
              }}>
                <div style={{ flex: 1, paddingRight: '16px' }}>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '4px' }}>
                    <span className="mono-text" style={{ fontSize: '11px', color: 'var(--accent-color)', fontWeight: 600 }}>PROACTIVE RECOMMENDATION</span>
                    <span className="mono-text" style={{ fontSize: '11px', color: '#66706A' }}>Match: {(ghostSuggestion.score * 100).toFixed(0)}%</span>
                  </div>
                  <h4 style={{ fontSize: '16px', fontWeight: 600 }}>{ghostSuggestion.title}</h4>
                  <p style={{ fontSize: '13px', color: '#444' }}>Created by: {ghostSuggestion.owner_name} • {ghostSuggestion.problem}</p>
                  {ghostSuggestion.role_reason && (
                    <p className="mono-text" style={{ fontSize: '11px', color: '#66706A', marginTop: '4px' }}>
                      ◆ {role} lens: {ghostSuggestion.role_reason}
                    </p>
                  )}
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button className="btn btn-secondary" style={{ borderColor: 'var(--accent-color)', color: 'var(--accent-color)' }} onClick={() => handleReview(ghostSuggestion.asset_id)}>
                    Review
                  </button>
                  <button className="btn btn-primary" onClick={() => handleReview(ghostSuggestion.asset_id)}>
                    Adopt
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Intent CI: prompt reviews from chat environments */}
          <div style={{
            padding: '20px',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--panel-radius)',
            backgroundColor: 'var(--panel-bg)'
          }}>
            <h3 style={{ fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)', marginBottom: '4px' }}>
              Intent CI — Prompt Reviews
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
              Prompts captured from chat environments (Claude Code, Codex, …) run policy, reuse and clarity checks, then wait for your approve/reject.
            </p>
            {intentReviews.length === 0 ? (
              <p style={{ fontSize: '13px', color: 'var(--text-secondary)', textAlign: 'center', padding: '12px 0' }}>
                No prompt reviews yet. Hook a chat environment to POST /api/intent-review.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {intentReviews.map((review) => (
                  <div key={review.id} style={{
                    padding: '12px 14px',
                    borderRadius: 'var(--input-radius)',
                    border: '1px solid var(--border-color)'
                  }}>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '6px', flexWrap: 'wrap' }}>
                      <span className="mono-text" style={{
                        fontSize: '10px', fontWeight: 600, padding: '1px 6px', borderRadius: '4px',
                        border: '1px solid var(--border-color)', color: 'var(--text-secondary)'
                      }}>{review.source_env}</span>
                      <span className="mono-text" style={{
                        fontSize: '10px', fontWeight: 600, padding: '1px 6px', borderRadius: '4px',
                        color: review.status === 'passed' || review.status === 'approved' ? 'var(--accent-color)' : review.status === 'rejected' ? '#e5484d' : '#b98900',
                        border: `1px solid ${review.status === 'passed' || review.status === 'approved' ? 'var(--accent-color)' : review.status === 'rejected' ? '#e5484d' : '#b98900'}`
                      }}>{review.status.toUpperCase()}</span>
                      {review.user_name && (
                        <span className="mono-text" style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>{review.user_name}</span>
                      )}
                    </div>
                    <p style={{ fontSize: '13px', marginBottom: '4px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {review.prompt}
                    </p>
                    {review.intent && (
                      <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                        Intent: {review.intent}
                      </p>
                    )}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', marginBottom: review.status === 'pending' ? '8px' : 0 }}>
                      {review.checks.map((check) => (
                        <span key={check.name} className="mono-text" style={{
                          fontSize: '11px',
                          color: check.status === 'pass' ? 'var(--accent-color)' : check.status === 'fail' ? '#e5484d' : '#b98900'
                        }}>
                          {CHECK_ICON[check.status] || '·'} {check.name}: {check.detail}
                        </span>
                      ))}
                    </div>
                    {review.status === 'pending' && (
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button className="btn btn-primary" style={{ padding: '4px 12px', minHeight: 'auto', fontSize: '12px' }}
                          onClick={() => handleResolveIntent(review.id, 'approve')}>Approve</button>
                        <button className="btn btn-secondary" style={{ padding: '4px 12px', minHeight: 'auto', fontSize: '12px' }}
                          onClick={() => handleResolveIntent(review.id, 'reject')}>Reject</button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

        </section>

        {/* RIGHT COLUMN: REVIEW EVIDENCE STACK (5 Columns) */}
        <section style={{
          gridColumn: 'span 5',
          borderLeft: '1px solid var(--border-color)',
          paddingLeft: '24px',
          display: 'flex',
          flexDirection: 'column',
          gap: '24px'
        }}>
          
          <div style={{
            padding: '24px',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--panel-radius)',
            backgroundColor: 'var(--panel-bg)',
            flex: 1,
            display: 'flex',
            flexDirection: 'column'
          }}>
            
            {!activeAsset ? (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center', color: 'var(--text-secondary)' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 500, marginBottom: '8px' }}>Asset Onboarding Review</h3>
                <p style={{ fontSize: '14px', maxWidth: '300px' }}>Select an asset from recommendations or captured Git commits to review its rationale, version history, and constraints.</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
                
                {/* Evidence Heading */}
                <div style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: '16px', marginBottom: '16px' }}>
                  <span className="mono-text" style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Evidence Stack</span>
                  <h2 style={{ fontSize: '22px', fontWeight: 600, marginTop: '4px' }}>{activeAsset.title}</h2>
                  <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>Owner: {activeAsset.owner}</p>
                </div>

                {(
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', flex: 1 }}>

                    {/* Rationale loading hint (LLM synthesis takes a while) */}
                    {isLoadingExplanation && !activeExplanation && (
                      <div style={{
                        padding: '16px',
                        backgroundColor: 'var(--accent-soft)',
                        borderRadius: 'var(--input-radius)',
                        borderLeft: '4px solid var(--accent-color)'
                      }}>
                        <span className="mono-text" style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                          Synthesizing design rationale from version history…
                        </span>
                      </div>
                    )}

                    {/* Scrubbed Text Reveal Rationale */}
                    {activeExplanation && (
                      <div ref={rationaleTextRef} style={{
                        padding: '16px',
                        backgroundColor: 'var(--accent-soft)',
                        borderRadius: 'var(--input-radius)',
                        borderLeft: '4px solid var(--accent-color)'
                      }}>
                        <h4 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>Original Design Rationale</h4>
                        <p style={{ fontSize: '14px' }}>{activeExplanation.explanation}</p>
                      </div>
                    )}

                    {/* Constraints list */}
                    {activeExplanation && activeExplanation.cited_constraints.length > 0 && (
                      <div>
                        <h4 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>Identified Constraints</h4>
                        <ul style={{ paddingLeft: '20px', fontSize: '14px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          {activeExplanation.cited_constraints.map((c, i) => (
                            <li key={i}>{c}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Stored prompt content */}
                    {activeAsset.content && (
                      <div>
                        <h4 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>Stored Prompt Content</h4>
                        <pre className="mono-text" style={{
                          fontSize: '12px',
                          padding: '12px',
                          borderRadius: 'var(--input-radius)',
                          border: '1px solid var(--border-color)',
                          backgroundColor: 'transparent',
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                          maxHeight: '200px',
                          overflowY: 'auto',
                          margin: 0
                        }}>{activeAsset.content}</pre>
                      </div>
                    )}

                    {/* Version history */}
                    {activeAsset.versions && activeAsset.versions.length > 0 && (
                      <div>
                        <h4 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>Version History</h4>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                          {activeAsset.versions.map((v: AssetVersion) => {
                            const cited = activeExplanation?.cited_versions?.includes(v.version_number);
                            return (
                              <div key={v.version_number} style={{
                                padding: '10px 12px',
                                borderRadius: 'var(--input-radius)',
                                border: cited ? '1px solid var(--accent-color)' : '1px solid var(--border-color)',
                                backgroundColor: cited ? 'var(--accent-soft)' : 'transparent'
                              }}>
                                <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: v.problem ? '4px' : 0 }}>
                                  <span className="mono-text" style={{ fontSize: '11px', fontWeight: 600, color: 'var(--accent-color)' }}>v{v.version_number}</span>
                                  {v.created_at && (
                                    <span className="mono-text" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{v.created_at.slice(0, 19).replace('T', ' ')}</span>
                                  )}
                                  {cited && (
                                    <span className="mono-text" style={{ fontSize: '10px', color: 'var(--accent-color)', border: '1px solid var(--accent-color)', borderRadius: '4px', padding: '0 4px' }}>CITED</span>
                                  )}
                                </div>
                                {v.problem && (
                                  <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{v.problem}</p>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* Onboarding AI Assistant chat Q&A */}
                    <div style={{
                      marginTop: 'auto',
                      borderTop: '1px solid var(--border-color)',
                      paddingTop: '16px'
                    }}>
                      <h4 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '12px' }}>Ask Onboarding Assistant</h4>
                      
                      <form onSubmit={handleAskQuestion} style={{ display: 'flex', gap: '8px' }}>
                        <input
                          type="text"
                          value={explanationQuestion}
                          onChange={(e) => setExplanationQuestion(e.target.value)}
                          placeholder="Why was this designed this way?"
                          style={{
                            flex: 1,
                            padding: '10px 14px',
                            borderRadius: 'var(--input-radius)',
                            border: '1px solid var(--border-color)',
                            backgroundColor: 'transparent',
                            color: 'var(--text-primary)',
                            fontSize: '14px',
                            outline: 'none'
                          }}
                        />
                        <button type="submit" className="btn btn-primary" style={{ padding: '0 16px', minHeight: 'auto' }} disabled={isAskingQuestion}>
                          {isAskingQuestion ? '...' : 'Ask'}
                        </button>
                      </form>
                    </div>

                    {/* Adoption Actions */}
                    <div style={{ marginTop: '20px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      <button className="btn btn-primary" style={{ width: '100%' }} onClick={handleAdopt}>
                        Use Prompt Template
                      </button>
                      
                      {adoptWarning && (
                        <div style={{
                          padding: '10px 12px',
                          backgroundColor: 'var(--accent-soft)',
                          borderRadius: '8px',
                          border: '1px solid var(--accent-color)',
                          fontSize: '12px',
                          color: 'var(--accent-color)'
                        }}>
                          {adoptWarning}
                        </div>
                      )}
                    </div>

                  </div>
                )}

              </div>
            )}

          </div>

        </section>

      </main>
      
      {/* Muted Footer */}
      <footer style={{
        padding: '16px 24px',
        textAlign: 'center',
        borderTop: '1px solid var(--border-color)',
        fontSize: '12px',
        color: 'var(--text-secondary)',
        fontFamily: 'var(--font-mono)'
      }}>
        Loomi P5 Hackathon MVP • Built with Next.js, Express, FastAPI and Chroma
      </footer>

    </div>
  );
}
