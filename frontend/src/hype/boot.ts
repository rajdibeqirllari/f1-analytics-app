// Read before the shared session provider fills in its defaults, so the weekend picker can tell
// a first visit (show the latest completed weekend) from a returning one (keep the remembered weekend).
let had=false;
try{had=!!new URLSearchParams(location.search).get('event')||!!JSON.parse(localStorage.getItem('rh-session-v1')||'{}').event}catch{}
export const arrivedWithWeekend=had;
