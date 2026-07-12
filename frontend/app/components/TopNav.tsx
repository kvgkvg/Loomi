"use client";

import React from 'react';
import { usePathname } from 'next/navigation';

// Shared 64px product nav for Canvas and Pipeline. The `children` slot holds
// page-specific controls (Canvas: role + health; Pipeline: polling status +
// open-in-canvas). aria-current marks the active tab from the current path.
export default function TopNav({ children }: { children?: React.ReactNode }) {
  const pathname = usePathname();
  const onPipeline = pathname?.startsWith('/pipeline');

  return (
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
      zIndex: 100,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontWeight: 600, fontSize: '18px', color: 'var(--text-primary)' }}>Loomi</span>
          <span style={{
            fontSize: '11px',
            fontFamily: 'var(--font-mono)',
            padding: '2px 6px',
            border: '1px solid var(--accent-color)',
            color: 'var(--accent-color)',
            borderRadius: '4px',
          }}>MEM-ORGANIZATION</span>
        </div>
        <nav className="view-switch" aria-label="Product views">
          <a href="/" aria-current={onPipeline ? undefined : 'page'}>Canvas</a>
          <a href="/pipeline" aria-current={onPipeline ? 'page' : undefined}>Pipeline</a>
        </nav>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {children}
      </div>
    </nav>
  );
}
