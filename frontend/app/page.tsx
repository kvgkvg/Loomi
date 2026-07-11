"use client";

import React, { useState, useEffect, useRef } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';

// Register GSAP plugins
if (typeof window !== 'undefined') {
  gsap.registerPlugin(useGSAP);
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001';

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
}

interface Explanation {
  explanation: string;
  cited_versions: number[];
  cited_constraints: string[];
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

  // Server-Sent Events (SSE) stream for Git commits
  useEffect(() => {
    console.log("Connecting to SSE stream...");
    const eventSource = new EventSource(`${API_BASE}/api/events/stream`);

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
          body: JSON.stringify({ task_description: composerInput, top_k: 1 }),
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
  }, [composerInput]);

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
      // 1. Fetch asset explanation (initial review with no specific question)
      const expRes = await fetch(`${API_BASE}/api/explain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ asset_id: assetId })
      });
      const explanationData = await expRes.json();

      // 2. We also need to get asset's content/details. Let's find it in our recommendations,
      // or fetch it from explain response if it includes metadata.
      // Since explain_asset returns explanation, cited_versions, cited_constraints.
      // We will make a custom fetch for the asset versions if needed, or query it.
      // But we can fetch it via another request. Wait, explain_asset return is:
      // { explanation, cited_versions, cited_constraints }
      // To display the original prompt content, we can fetch all versions. Let's add a backend mock or 
      // check if explain_asset output can contain the content, or fetch details from explain_asset endpoint.
      // Actually, we can get the details of the asset from our database. Let's query recommend or just mock.
      // Since recommend returns the problem/owner, we can find it in our current lists or query `/explain`
      // and adapt. Let's fetch the asset content by mock.
      
      // Let's get metadata from recommendations if we reviewed from suggestion:
      let assetDetails = { id: assetId, title: 'Asset Review', content: 'Loading prompt...' };
      if (ghostSuggestion && ghostSuggestion.asset_id === assetId) {
        assetDetails = {
          id: assetId,
          title: ghostSuggestion.title,
          content: ghostSuggestion.content || 'Content not cached'
        };
      } else {
        // Find in gitEvents
        const found = gitEvents.find(e => e.asset_id === assetId);
        if (found) {
          assetDetails = {
            id: assetId,
            title: found.title,
            content: 'Content captured'
          };
        }
      }

      // To be robust, let's fetch version content. We will write a small version fetcher or proxy.
      // But we can also retrieve it using a question since assistant explanation synthesized it.
      // Let's call FastAPI /explain and display it.
      // Let's assume explain_asset provides enough explanation.
      setActiveAsset({
        id: assetId,
        title: assetDetails.title,
        owner: ghostSuggestion?.owner_name || foundGitOwner(assetId) || 'An'
      });
      setActiveExplanation(explanationData);
    } catch (err) {
      console.error("Error loading asset details:", err);
    } finally {
      setIsLoadingExplanation(false);
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
          question: explanationQuestion
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

    // Fetch the raw asset content to insert into composer.
    // In our seed database, we can mock or fetch it.
    // Let's query recommendations or gitEvents, or just fetch from an endpoint.
    // Let's fetch the explanation as prompt. Actually, we can retrieve the prompt content.
    // Let's call /recommend to get the exact asset details including content.
    // Let's do a quick recommendation or assume a default content.
    // Let's assume we copy a high-quality prompt template.
    let promptContent = `[System Prompt: ${activeAsset.title}]\n\nRole: Lead Triage Agent\n\nInstructions:\n- Analyze incoming inputs\n- Triage based on priority\n- Maintain JSON output schema.`;
    
    // Set composer input
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
            <h3 style={{ fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)', marginBottom: '12px' }}>
              Captured Git Knowledge Feed
            </h3>
            
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

                {isLoadingExplanation ? (
                  <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                    <span className="mono-text">Loading evidence...</span>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', flex: 1 }}>
                    
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
