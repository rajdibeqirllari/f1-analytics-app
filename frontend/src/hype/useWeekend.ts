import {useMemo} from 'react';
import {useSession} from '../state';
import {toRound} from './weekend';

// The chosen weekend, shared by the picker and every tool page.
export function useWeekend(){
 const ctx=useSession();
 const rounds=useMemo(()=>ctx.calendar.map(r=>toRound(r)).sort((a,b)=>a.round-b.round),[ctx.calendar]);
 const pick=rounds.find(r=>r.key===ctx.selection.event);
 const session=pick?.sessions.find(x=>x.code===ctx.selection.session);
 const canLoad=!!pick&&!!session&&(session.done||!session.start);
 return {...ctx,rounds,pick,session,canLoad};
}
