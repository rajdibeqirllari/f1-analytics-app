/** Circuits bundled with the site, shared by Live and Replay. Keyed by slug of the event name.
 * The slug matches services/live_timing.py track_outline: accents removed first ("São Paulo" → "sao-paulo"). */
export type Circuit={x:number[];y:number[];rotation:number;source:string;pit?:{entry:number;exit:number}};
const BUNDLED=import.meta.glob('./circuits/*.json',{eager:true,import:'default'}) as Record<string,Circuit>;
export const slug=(v:string)=>v.normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
export const bundledCircuit=(event:string):Circuit|null=>BUNDLED[`./circuits/${slug(event)}.json`]||null;
