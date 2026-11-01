import {RadioTower,Clapperboard,Layers,ChartNoAxesCombined,Timer,Download,RotateCcw,Radio,FolderOpen,MapPinned} from 'lucide-react';

// Tool pages, in the order they appear on the weekend picker ("Take it into").
export const TOOLS=[
 ['/videos',Clapperboard,'Comparison video','Two laps, one clip for Reels, TikTok and Shorts'],
 ['/overlays',Layers,'Video overlay','A transparent HUD to drop over your footage'],
 ['/analysis',ChartNoAxesCombined,'Lap & strategy','Telemetry traces, stints and pace deltas'],
 ['/timing',Timer,'Timing','Classification, sectors and race control'],
 ['/telemetry',Download,'Telemetry export','CSV for After Effects and RaceRender'],
 ['/replay',RotateCcw,'Race replay','Every car on the circuit'],
 ['/radio',Radio,'Team radio','Search the archive'],
] as const;

// Top navigation: [path under /hype, label, icon, matching classic route]
export const NAV=[
 ['',"Weekend",MapPinned,'/'],
 ['/live','Live',RadioTower,'/'],
 ['/replay','Replay',RotateCcw,'/replay'],
 ['/videos','Video',Clapperboard,'/videos'],
 ['/overlays','Overlay',Layers,'/overlays'],
 ['/analysis','Analysis',ChartNoAxesCombined,'/analysis'],
 ['/timing','Timing',Timer,'/timing'],
 ['/telemetry','Telemetry',Download,'/telemetry'],
 ['/radio','Radio',Radio,'/radio'],
 ['/library','Library',FolderOpen,'/downloads'],
] as const;
