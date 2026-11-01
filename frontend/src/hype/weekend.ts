import {sessions} from '../api';
import {VENUES} from './mapdata';

export type WeekendSession={code:string;name:string;start:Date|null;done:boolean};
export type Round={key:string;round:number;name:string;short:string;country:string;location:string;date:Date|null;done:boolean;
 sessions:WeekendSession[];point:[number,number]|null;sprint:boolean;raw:any};

const CODES:Record<string,string>={'practice 1':'FP1','practice 2':'FP2','practice 3':'FP3',qualifying:'Q',sprint:'S',
 'sprint qualifying':'SQ','sprint shootout':'SQ',race:'R'};

// FastF1 ships two timestamps per session: SessionNDate carries the venue offset,
// SessionNDateUtc is naive UTC. Prefer the one that pins an absolute instant.
function when(row:any,n:number):Date|null{
 const local=row[`Session${n}Date`],utc=row[`Session${n}DateUtc`];
 const parse=(v:string)=>{const d=new Date(v.replace(' ','T'));return Number.isNaN(+d)?null:d};
 if(typeof local==='string'&&/[+-]\d\d:?\d\d$|Z$/.test(local))return parse(local);
 if(typeof utc==='string')return parse(/Z$|[+-]\d\d:?\d\d$/.test(utc)?utc:utc+'Z');
 return null;
}
function eventDate(row:any){const v=row.EventDate;if(!v)return null;const d=new Date(String(v).replace(' ','T'));return Number.isNaN(+d)?null:d}
const norm=(v:any)=>String(v||'').trim().toLowerCase();

export function venuePoint(row:any):[number,number]|null{
 return VENUES[norm(row.Location)]||VENUES[norm(row.Location).replace(/\s+island$/,'')]||VENUES[norm(row.Country)]||null;
}

export function toRound(row:any,now=Date.now()):Round{
 const list:WeekendSession[]=[];
 for(let n=1;n<=5;n++){
  const code=CODES[norm(row[`Session${n}`])];if(!code||list.some(s=>s.code===code))continue;
  const start=when(row,n);
  // A session counts as run once it has started plus a short buffer for data to land.
  list.push({code,name:sessions[code]||row[`Session${n}`],start,done:start?+start+90*60e3<now:false});
 }
 const date=eventDate(row);
 const fallback=!list.length;
 if(fallback){const finished=date?+date+86400e3<now:false;
  for(const code of ['FP1','FP2','FP3','SQ','S','Q','R'])list.push({code,name:sessions[code],start:null,done:finished});}
 const name=String(row.EventName||'');
 return {key:name,round:Number(row.RoundNumber)||0,name,short:name.replace(/\s*Grand Prix$/i,'')||name,country:row.Country||'',location:row.Location||'',
  date,done:list.some(s=>s.code==='R'&&s.done)||(fallback&&!!date&&+date+86400e3<now),sessions:list,point:venuePoint(row),
  sprint:list.some(s=>s.code==='S'),raw:row};
}

export function preferredSession(round:Round,current:string){
 const here=round.sessions.find(s=>s.code===current);
 if(here&&(here.done||!here.start))return current;
 const run=round.sessions.filter(s=>s.done);
 return (run.find(s=>s.code==='Q')||run[run.length-1]||round.sessions[0])?.code||current;
}

const dayFmt=new Intl.DateTimeFormat(undefined,{weekday:'short'});
const timeFmt=new Intl.DateTimeFormat(undefined,{hour:'2-digit',minute:'2-digit'});
const dateFmt=new Intl.DateTimeFormat(undefined,{day:'numeric',month:'short'});
export const fmt={day:(d:Date|null)=>d?dayFmt.format(d):'',time:(d:Date|null)=>d?timeFmt.format(d):'',date:(d:Date|null)=>d?dateFmt.format(d):''};

export function relative(d:Date|null,now=Date.now()){
 if(!d)return '';const days=Math.round((+d-now)/86400e3);
 if(days===0)return 'today';if(days===1)return 'tomorrow';if(days===-1)return 'yesterday';
 return days>0?`in ${days} days`:`${-days} days ago`;
}
