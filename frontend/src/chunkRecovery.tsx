/** Recovery from code-split chunks that fail to load.
 *
 * The usual cause is a tab opened on an older build after a new one was published: the old entry asks for chunk
 * names the server no longer has. `recoverableLazy` replaces React.lazy: on a chunk failure it fetches the current
 * index.html (uncached) and compares its entry script with the one this tab runs.
 *  - New build available: save the route state (`registerResume` providers), reload once, restore after the reload.
 *    A sessionStorage flag per entry name means a given build can trigger at most one automatic reload.
 *  - Same build, or the server cannot be reached: no reload. The nearest <ChunkBoundary> shows "Try again", which
 *    re-imports the chunk without reloading the page (offline / engine-down cases recover when it is back). */
import React from 'react';

const FLAG = 'rhx-chunk-reload';
const RESUME = 'rhx-resume';

export class ChunkLoadError extends Error {
  kind: 'offline' | 'missing';
  constructor(kind: 'offline' | 'missing') {
    super(kind === 'offline' ? 'This page could not be loaded: the Race Hype engine did not answer.' : 'Part of this page could not be loaded from the engine.');
    this.kind = kind; this.name = 'ChunkLoadError';
  }
}

export function isChunkError(e: unknown) {
  const m = String((e as Error)?.message ?? e);
  return /dynamically imported module|Importing a module script failed|error loading dynamically imported|Failed to load module script|Unable to preload CSS/i.test(m);
}

function entryOf(html: string) { return (html.match(/\/assets\/index-[\w-]+\.js/) || [''])[0]; }
function currentEntry() {
  for (const s of Array.from(document.querySelectorAll('script[type="module"][src]'))) {
    const src = new URL((s as HTMLScriptElement).src, location.href).pathname;
    if (/\/assets\/index-/.test(src)) return src;
  }
  return '';
}

const providers = new Set<() => Record<string, unknown>>();
/** Pages register what they need back after a version reload (e.g. replay time and focused driver). */
export function registerResume(fn: () => Record<string, unknown>) { providers.add(fn); return () => { providers.delete(fn); }; }
/** The saved state for this route after a version reload (once; null otherwise). */
export function takeResume(key: string): any {
  try {
    const raw = sessionStorage.getItem(RESUME); if (!raw) return null;
    const r = JSON.parse(raw);
    if (r.path !== location.pathname || Date.now() - r.at > 10 * 60e3 || !(key in r.state)) return null;
    const v = r.state[key]; delete r.state[key]; sessionStorage.setItem(RESUME, JSON.stringify(r)); return v;
  } catch { return null; }
}

let pending: Promise<'reloading' | 'offline' | 'same-version'> | null = null;
export function recover() {
  if (!pending) pending = (async () => {
    let latest = '';
    try {
      const r = await fetch('/?rhx-version=' + Date.now(), { cache: 'no-store', headers: { Accept: 'text/html' } });
      if (!r.ok) return 'offline' as const;
      latest = entryOf(await r.text());
    } catch { return 'offline' as const; }
    const mine = currentEntry();
    if (!latest || latest === mine) return 'same-version' as const;
    if (sessionStorage.getItem(FLAG) === latest) return 'same-version' as const;   // already reloaded for this build
    sessionStorage.setItem(FLAG, latest);
    const state: Record<string, unknown> = {};
    providers.forEach(f => { try { Object.assign(state, f()); } catch { /* a page's state is optional */ } });
    sessionStorage.setItem(RESUME, JSON.stringify({ path: location.pathname, search: location.search, at: Date.now(), from: mine, to: latest, state }));
    location.reload();
    return 'reloading' as const;
  })().finally(() => { setTimeout(() => { pending = null; }, 0); });
  return pending;
}

const resets = new Set<() => void>();
/** React.lazy with version recovery; `resetLazy()` lets a boundary retry without a page reload. */
export function recoverableLazy<T extends React.ComponentType<any>>(factory: () => Promise<{ default: T }>): T {
  const make = () => React.lazy(async () => {
    try { return await factory(); }
    catch (e) {
      if (!isChunkError(e)) throw e;
      const r = await recover();
      if (r === 'reloading') return new Promise<never>(() => {});
      throw new ChunkLoadError(r === 'offline' ? 'offline' : 'missing');
    }
  });
  let L = make();
  resets.add(() => { L = make(); });
  const C = (props: any) => React.createElement(L, props);
  return C as unknown as T;
}
export function resetLazy() { resets.forEach(f => f()); }

/** Catches chunk-load failures locally (the rest of the app keeps working) and offers a retry. */
export class ChunkBoundary extends React.Component<{ children: React.ReactNode; className?: string }, { error: ChunkLoadError | null }> {
  state = { error: null as ChunkLoadError | null };
  static getDerivedStateFromError(error: Error) { if (error instanceof ChunkLoadError) return { error }; throw error; }
  retry = () => { resetLazy(); this.setState({ error: null }); };
  render() {
    const e = this.state.error;
    if (!e) return this.props.children;
    return <div className={this.props.className || 'rhx-chunk-error'} role="alert">
      <p><b>{e.message}</b> {e.kind === 'offline' ? 'Check that the engine is running (and the network), then try again.' : 'Try again; if it keeps failing, reload the page.'}</p>
      <button type="button" onClick={this.retry}>Try again</button>
    </div>;
  }
}
