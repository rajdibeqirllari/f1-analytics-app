export type Selection={year:number;event:string;session:string;driver:string;driver_b:string;lap:number|null;lap_b:number|null;qualifying_part:string};
export type Output={id:string;url:string;name:string;category:string;size:number;modified:number;label?:string};
export type Job={id:string;kind?:string;status:string;progress:number;message:string;error:string;result:any};
export type Driver={name:string;team:string;color:string;portrait:string;laps:number[];segments?:Record<string,number[]>;status?:string};
export type Catalog={drivers:Record<string,Driver>;source?:string;notice?:string;qualifying_segments?:boolean};
export async function request<T=any>(url:string,options?:RequestInit):Promise<T>{
 const response=await fetch(url,options);
 if(!response.ok){let detail;try{detail=(await response.json()).detail}catch{detail=response.statusText}
  throw new Error(typeof detail==='string'?detail:JSON.stringify(detail));}
 return response.json();
}
export function post<T=any>(url:string,body:unknown){return request<T>(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}
export function clock(value:number|null|undefined){if(value==null||!Number.isFinite(value))return '—';return `${Math.floor(value/60)}:${(value%60).toFixed(3).padStart(6,'0')}`;}
export function teamColor(value?:string){return /^[0-9a-f]{6}$/i.test((value||'').replace('#',''))?'#'+value!.replace('#',''):'#62d7da';}
export function portrait(url:string){return url?.replace('.transform/1col/','.transform/8col/')||'';}
export const sessions:Record<string,string>={R:'Race',Q:'Qualifying',S:'Sprint',SQ:'Sprint qualifying',FP1:'Practice 1',FP2:'Practice 2',FP3:'Practice 3'};
export const countryFlags:Record<string,string>={Australia:'au',China:'cn',Japan:'jp',Bahrain:'bh','Saudi Arabia':'sa',USA:'us','United States':'us',Canada:'ca',Monaco:'mc',Spain:'es',Austria:'at','Great Britain':'gb','United Kingdom':'gb',Belgium:'be',Hungary:'hu',Netherlands:'nl',Italy:'it',Azerbaijan:'az',Singapore:'sg',Mexico:'mx',Brazil:'br',Qatar:'qa','Abu Dhabi':'ae','United Arab Emirates':'ae',France:'fr',Germany:'de',Portugal:'pt',Turkey:'tr',Türkiye:'tr',Russia:'ru'};
