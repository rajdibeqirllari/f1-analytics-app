# RACE HYPE — Raporti i plotë i dorëzimit për Claude

Përditësuar: 30 tetor 2026. Projekti lokal: `C:\f1hud_app`.

Ky raport mbledh kërkesat e përdoruesit, punën e dokumentuar dhe gjendjen e kodit të inspektuar. Është dorëzim i projektit ekzistues, jo kërkesë për ta rindërtuar nga zero. Historia e chat-it nuk zëvendëson kodin dhe provat: ku një ide nuk është realizuar ose një rezultat është vetëm test lokal, kjo thuhet shprehimisht.

Përmbledhje e verifikuar gjatë këtij dorëzimi: **186 teste Python kaluan në 20.812s; 9 teste Node kaluan; build TypeScript/Vite kaloi.** Nuk u gjenerua MP4 e re dhe nuk u ndryshua logjika e aplikacionit. U rindërtuan vetëm build artifacts të frontend-it gjatë kontrollit. Backend localhost8000 nuk ishte i arritshëm në momentin e health check; raporti nuk pretendon se site është aktualisht ndezur.

## 1. Qëllimi dhe preferencat e përdoruesit

RACE HYPE është platformë personale motorsporti për analizë reale F1 dhe krijim përmbajtjeje për TikTok, Instagram Reels dhe YouTube Shorts. Përdoruesi ka deklaruar se përmbajtja është e pamonetizuar. Kjo nuk duhet interpretuar si heqje automatike e detyrimeve të licencimit.

Kërkesat e përsëritura:

- Platformë funksionale, jo faqe statike me të dhëna demonstrimi.
- Të ruhen llogaritjet FastF1 dhe burimet reale; pamja të jetë immersive, premium, racing/broadcast.
- Identiteti: **RACE HYPE**, **RH**, `@theracehype`, slogani **CHASE THE DETAIL.**
- Logoja personale në vend të tre vijave të kuqe; logo dhe “FOLLOW US ON” në video.
- Video ghost-lap tërheqëse, me kamerë dinamike por të qetë, HUD të lexueshëm në telefon dhe rezultat të saktë.
- Rreth 30–40 sekonda për një xhiro të plotë në format social; jo domosdoshmërisht xhiro 90-sekondëshe në kohë reale.
- Shpejtësi 1×, 2×, **3×**, 5×, 8×, 10×, 20× dhe pacing dinamik.
- Më pak flicker, animacion realisht smooth, linjë e lidhur me asfaltin dhe renderim sa më i shpejtë pa ulur fshehurazi cilësinë.
- Audio brenda të gjitha videove të reja, preview dhe download, jo vetëm një shembulli.
- Gjendja e fundit për muzikën: **instrumentale, pa zë/narracion/vokale**. Prototipet synth dhe motori i kampionuar nuk i pëlqyen.
- Përdoruesi preferon implementim e prova reale mbi përgjigje me sugjerime të përgjithshme.

“Viral / që askush të mos bëjë swipe” është objektiv krijues, jo rezultat i garantueshëm. Mos ndrysho të dhënat për të prodhuar dramë artificiale.

## 2. Nga çfarë nisëm dhe çfarë ndryshoi

Pika e nisjes ishte aplikacioni Python/Streamlit me analiza FastF1, eksport telemetrie, HUD, replay dhe radio. Përdoruesi solli ZIP-in `RaceHype-Immersive-Website.zip` dhe pamje referencë.

ZIP-i ishte prototip vizual HTML/CSS/JS me artwork Ferrari. Kurba demo, timing demo, lëvizje demo dhe speech synthesis nuk u trajtuan si të dhëna reale dhe nuk u përdorën si motor funksional i platformës.

Migrimi krijoi React/TypeScript mbi shërbimet Python ekzistuese, me FastAPI si urë. Streamlit u ruajt, jo u fshi. U nxorën mekanikisht 43 funksione ndihmëse/analize nga `app.py` në `services/analysis_service.py`, duke ruajtur matematikën ekzistuese. API nuk importon UI-në e Streamlit si motor ekzekutimi.

Vendndodhje të rëndësishme:

| Pjesa | Vendndodhja |
| --- | --- |
| UI aktual React | `frontend/src/` |
| API | `api/main.py`, `api/engines.py`, `api/jobs.py`, `api/files.py` |
| Llogaritje dhe renderim | `services/` |
| Aplikacioni i vjetër | `app.py`, `ui/`, `overlay_app.py` |
| Prototipi vizual i ruajtur | `frontend/public/design/` |
| Dokumentacion | `docs/` |
| Teste | `tests/` |
| Diagnostikë/render proofs | `scripts/`, `tmp/` |

## 3. Platforma aktuale: nëntë workspace funksionale

### 3.1 Race Center — `/`

Rezultate të publikuara, renditje pilotësh/konstruktorësh dhe informacion fundjave nga shërbimi overview/Jolpica, të ndara nga disponueshmëria e telemetrisë FastF1. Historiku nuk etiketohet si live feed.

Hero vizual me makina konstruktorësh, madhësi më të kontrolluar dhe carousel:

- React: swipe/tërheqje me pointer, shigjeta, pagination, tastierë dhe autoplay.
- Autoplay React ndalet gjatë hover/focus/drag dhe respekton reduced motion.
- Renditja e artwork lidhet me renditjen e konstruktorëve kur burimi është i disponueshëm; nuk shpiket P1 kur mungojnë standings.
- Komponenti i vjetër Streamlit ka mekanizëm tjetër scroll/wheel; mos i ngatërro dy implementimet.

Skedarë: `frontend/src/ConstructorShowcase.tsx`, `frontend/src/showcase.css`, `ui/constructor_config.py`, `components/constructor_showcase/`.

### 3.2 Timing & Positions — `/timing`

Klasifikim historik, xhiro, sektorë, weather dhe race-control messages nga FastF1. Nuk është implementuar simulator live timing. Një sesion që ngarkohet për video përmes OpenF1 nuk bëhet automatikisht sesion i plotë FastF1 për këtë faqe.

### 3.3 Lap & Strategy Analysis — `/analysis`

Grafiqe dhe krahasime me llogaritjet ekzistuese. Katalogu aktual ka 17 lloje:

1. Fastest lap map.
2. Telemetry Comparison.
3. Car Pace Delta Map.
4. Sector Performance Heatmap.
5. Selected driver race pace.
6. Driver lap comparison.
7. Lap consistency.
8. Lap-by-lap pace delta.
9. Lap-by-lap delta + stints.
10. Stint strategy.
11. Tyre Degradation Analysis.
12. Hard stint average pace.
13. Medium stint average pace.
14. Position Tracker.
15. Gap to Leader.
16. Team race pace delta.
17. Speed Trap Analysis.

Matplotlib përdoret nën lock, sepse konfigurimi i tij është global. Këto analiza inxhinierike mbeten kryesisht FastF1-only, jo zëvendësim i Session API nga OpenF1.

### 3.4 Create Comparison Videos — `/videos`

Pjesa më e zhvilluar gjatë punës së fundit. Shih seksionet 5–11 për hollësi.

### 3.5 Download Telemetry — `/telemetry`

Burime: Auto, FastF1, OpenF1, Upload CSV. Katër paketa: selected-lap CSV, full-source CSV, After Effects TSV dhe RaceRender CSV. Upload CSV kufizohet në 10 MB në UI/API.

Schema kanonike përfshin kohën, datën/session time, speed, RPM, gear, throttle, brake, DRS raw/active, distance, relative distance, XYZ, source dhe fushat e ardhshme të energjisë/aero. Fushat e ardhshme mbeten nullable kur burimi nuk i jep.

Full-session FastF1 car data dhe lap telemetry nuk kanë domosdoshmërisht të njëjtat kolona; mos i shpall gabim vetëm sepse ndryshojnë.

### 3.6 Create Video Overlays — `/overlays`

HUD nga telemetria, preview transparent, madhësi/pozicion i kontrollueshëm dhe eksport:

- WebM VP9 Alpha.
- MOV ProRes 4444.
- PNG Sequence.

Alpha u verifikua në prova të mëparshme: WebM alpha_mode=1 me alpha 0–255; ProRes me pixel format `yuva444p12le`. Jo çdo browser luan MOV; skedari mbetet për editor.

### 3.7 Watch Race Replays — `/replay`

Payload real replay, seeking, playback speed, driver focus, labels dhe DRS controls për burimet e mbështetura. Përdor FastF1 dhe cache replay; OpenF1 fallback i videove nuk zëvendëson këtë rrjedhë.

### 3.8 Listen to Team Radio — `/radio`

Kërkim, playback dhe download regjistrimesh reale të arkivit përmes `f1radio`. Jo radio e shpikur ose zë artificial që pretendohet si pilot real. Disponueshmëria mbetet e varur nga arkivi.

### 3.9 My Downloads — `/downloads`

Bibliotekë rezultatesh me kërkim, filtrim, preview dhe download. Skedarët shërbehen me ID opake, jo me endpoint që pranon çfarëdo path-i. Rrënjët e lejuara janë `outputs/`, `output/`, `charts/`; raw 3D assets nuk duhen ekspozuar.

### Sjellje e përbashkët

Vit/event/session/driver/lap kalojnë mes faqeve përmes URL query dhe state/local storage. UI responsive ka menu mobile dhe sidebar. Në checkpoint e migrimit u kontrollua edhe gjerësi 390px pa overflow horizontal.

## 4. Problemet FastF1/OpenF1 dhe çfarë u rregullua

### Simptomat e përdoruesit

- `None of ['Date'] are in the columns`.
- Vetëm disa pista/sesione ngarkoheshin; ato me cache shpesh punonin.
- `Timing data could not be downloaded ... timing archive is unavailable`.
- Ndryshimi nga lidhja e zakonshme te Bluetooth hotspot/5G nuk garantoi sukses.
- Në eksport: `cannot convert float NaN to bool`.

### Çfarë dimë dhe çfarë nuk duhet pretenduar

Mungesa e Wi-Fi nuk është diagnozë e mjaftueshme. Mund të dështojë rruga drejt provider-it, të mungojnë stream-et, të mos ketë përfunduar sesioni ose FastF1 të kthehet pa lap data. Nuk u provua një shkak universal për çdo sesion që përdoruesi pa të dështonte.

U shtua mbrojtje që `load_video_session` të mos ruajë në memory cache një objekt sesioni bosh/pangarkuar. Dështimi del si gabim i qartë dhe mund të riprovohet. Cache ekzistuese FastF1 nuk fshihet si “zgjidhje”.

### Fallback i implementuar

FastF1 është burimi i parë. Kur katalogu ose telemetria e krahasimit nuk mund të përdoret, provohet OpenF1 për sesione historike të përfunduara nga 2023 e tutje. Auto telemetry export përdor të njëjtën rrjedhë fallback.

- Përputhje unike venue/session; jo ndërrim i heshtur me event tjetër të të njëjtit shtet.
- Kërkohen timed laps, car channels dhe pozicione jo-degjenerative të sinkronizuara në kohë.
- Gaps mbi dy sekonda dhe input i pamjaftueshëm refuzohen.
- Requests serializohen dhe ndahen me të paktën 2.1 sekonda në proces për rate limiting.
- Përgjigjet historike të suksesshme e jo-bosh persistohen në `outputs/openf1_cache/`.
- FastF1 përdor `fastf1_cache/`; dy cache-t nuk zëvendësojnë njëra-tjetrën.
- UI raporton source dhe fallback reason.

Kufizime OpenF1:

- Q1/Q2/Q3 filtering çaktivizohet kur nuk mund të provohet.
- “Fastest” nuk certifikon automatikisht deleted-lap validity.
- DRS i munguar mbetet i panjohur në eksport/display; mos e paraqit default të brendshëm si sinjal të matur.
- Nuk fabrikohen active-aero, boost/overtake/recharge modes.
- Replay i plotë, timing tables dhe grafiqet ekzistuese nuk marrin fallback të plotë OpenF1.

Gabimi NaN/boolean u trajtua te eksportet nullable dhe u shtuan teste për DRS/brake realë e të munguar, sidomos After Effects. Nuk duhet bërë konvertim i verbër i `pd.NA`/NaN në bool ose 0 që pretendon matje reale. Normalizimi FastF1/CSV ka edhe politika default për disa fusha; duhen lexuar sipas burimit, jo shpallur të gjitha missing values identike.

Referenca: `docs/openf1-fallback.md`, `services/openf1_service.py`, `services/openf1_comparison.py`, `services/video_comparison.py`, `services/export_service.py`, `tests/test_openf1_fallback.py`, `tests/test_video_session_loading.py`.

## 5. Video Studio: gjendja e saktë aktuale

### Mode të dukshme në React

| Emri në UI | Implementimi/përdorimi |
| --- | --- |
| Race Hype Cut | 3D director/story presets |
| The Breakdown | Krahasim 2D |
| Trackside | 3D cinematic, follow/full circuit |
| On Their Tail | 3D chase, fokus A ose B |
| In the Cockpit | Onboard ghost, kamera e fokusit A/B; landscape rekomandohet |

Brenda Race Hype Cut: **The Limit**, **Cinematic Ghost Chase**, **Classic Broadcast / Overhead**, **Legacy Race Hype Cut** (`Social director`).

Default aktual React:

- Race Hype Cut → The Limit.
- Vertical 9:16.
- Balanced.
- Preview 540p, final selector 1080p.
- **60 fps native**.
- Full lap.
- Cinematic Dynamic Pacing, target 35s.
- Soundtrack Industrial Cut (`The Duel` në API), volume 80%.

API që nuk merr FPS explicit ka ende default 24 preview / 30 final; mos ngatërro default React me default të çdo klienti API.

Preview: 540p/720p/1080p. Final: 720p/1080p. Cadence: 24/30/60 fps. Portrait 9:16 dhe landscape 16:9. Xhiro më e shpejtë ose numër xhiroje për secilin pilot; Q filtering vetëm kur burimi e mbështet.

Kamera ka kontrolle smoothness, lookahead, camera distance, dynamic zoom, movement intensity dhe framing size. Plot-lap dhe short-clip kanë interval source-time, jo prerje arbitrare të kohës së pilotëve.

### Pipeline i vërtetë

`FastF1/OpenF1 → Comparison → timeline e përbashkët → rrugë/pozicione/kamerë → Blender EEVEE → PNG frames → Pillow HUD/branding → RGB pipe → FFmpeg H.264 → audio AAC mux → MP4 final`.

React nis dhe ndjek job-in. Nuk filmohet canvas/browser me screen recording. Nuk përdoret API gjenerative video për garën.

Një worker video (`ThreadPoolExecutor(max_workers=1)`) zotëron render queue. Një Uvicorn process duhet të zotërojë gjendjen; multi-worker deployment nuk është konfigurim i mbështetur për metadata in-memory.

## 6. Integriteti i kohës dhe rezultatit

Përdoruesi vuri re që video dukej sikur Verstappen fitonte kur të dhënat/referenca tregonin tjetër gjë. Ky është invariant kritik:

- Secili pilot ruan kohën dhe xhiron e vet burimore.
- Të dy fillojnë nga elapsed lap time zero dhe përdorin të njëjtin source clock.
- Fituesi/gap final dalin nga lap durations, jo nga shpejtësia e fundit apo ngjyra e makinës.
- Delta në mes të xhiros përdor kohë në distancë të përputhur; nuk është thjesht diferencë mes dy timestamp-eve aktuale.
- Pozicionimi përdor integrim të vazhdueshëm të speed dhe progress anchors. Nuk shtohet “boost” për ta bërë fituesin më dramatik.

Ka dy shembuj që nuk duhen bashkuar:

1. Austin 2026 FP1, prova LEC/VER me lap-12 times **96.052 / 96.136** në dokumentacionin e Social Director. Mos përdor një xhiro tjetër të VER dhe mos e quaj domosdoshmërisht krahasim me referencën qualifying.
2. Mostra kryesore e rebuild-it është **COTA 2026 Qualifying**, e zgjedhur shprehimisht nga përdoruesi pasi brief-i fillimisht thoshte FP1: **ANT lap 14 = 1:34.035; VER lap 8 = 1:34.214; ANT fiton 0.179s**.

Mos ndrysho klasifikim sipas një screenshot-i Google pa kontrolluar session/lap/source. Këto vlera janë metadata e provave lokale; ky raport nuk bën verifikim të ri online të rezultateve sportive.

## 7. Pista, makina, trajektorja dhe elevation

### Çfarë u përmirësua

- Nga asfalt që dukej “në ajër” mbi një ambient jeshil bosh: terrain i lidhur, kerbs, runoff/scenery ilustruese, barriera, gardhe, tribuna/ndërtesa, ndriçim ditë/natë sipas rrjedhës.
- Modeli aktiv: **Qvist_designs F1 2026 concept**, i përgatitur për Blender, team-inspired body paint sipas ekipit të pilotit në sesionin e zgjedhur, jo ekipit të tij të sotëm.
- Materiale paint/clear-coat/carbon/tyres/rims, rrota të animuara, steering ilustrues nga curvature.
- Ghost transparent për rivalin dhe kamera chase/onboard me fokus A/B.
- Rrugë e përbashkët e lëmuar, e kufizuar në asfalt; cornering line me minimum-curvature dhe lateral offsets të kontrolluar, jo thjesht makinë që ngelet në vijën e mesit në çdo kthesë.
- Minimap ndjek të njëjtat pozicione/rrugë të përdorura nga renderuesi.
- Test footprint të plotë: nëntë pika për makinë për frame ndaj trekëndëshave realë të asfaltit të renderuar.

### Politikë AKTUALE e burimit të pistës

**Vetëm Telemetry-built** është aktiv në rrjedhën aktuale të prodhimit. `services/circuits_3d.py` kthen vetëm atë opsion; API e kalon explicit. Imported GLB/circuit models refuzohen.

Historikisht u eksploruan Paul Ricard dhe dy versione Singapore GLB, u bënë indexing/alignment/provenance audits dhe mbetën asset-et/scripts. Kjo nuk do të thotë se sot janë enabled. Dokumentet e vjetra që ofrojnë “Original GLB” janë historike. Mos i riaktivizo pa kërkesë dhe kontroll të veçantë.

Katalogu ka 37 event keys/presets, jo 37 pista unike të matura. Përfshin evente aktuale dhe historike: Melbourne, Shanghai, Suzuka, Bahrain, Jeddah, Miami, Montreal, Monaco, Barcelona/Spain, Austria/Styrian, Silverstone/70th Anniversary, Spa, Hungaroring, Zandvoort, Monza, Baku, Singapore, Austin, Mexico/Mexican, Interlagos/Brazil, Vegas, Lusail, Yas Marina, Imola, Paul Ricard, Hockenheim, Sochi, Istanbul, Portimão, Mugello, Nürburgring dhe Sakhir Outer.

Mbulimi në katalog nuk garanton të dhëna për çdo vit ose sesion. Një track i ri kërkon reference lap të plotë, layout të arsyeshëm dhe validim gjeometrik.

### Kufizime që duhen thënë qartë

- Nuk kemi surveyed/scanned geometry, gjerësi reale në çdo segment, apex-e të matura ose banking të provuar.
- Të dy ghost-et përdorin një shared illustrative route. Nuk kemi rindërtuar trajektoren e saktë të secilit pilot dhe as “mesataren reale të gjithë makinave” me të dhëna të mjaftueshme.
- Makina është një concept generic, jo Ferrari/Mercedes/Red Bull real i vitit përkatës me livery autentike.
- Z nga telemetria përdoret si **relative estimated elevation**, i filtruar dhe validuar. Profile drifting/spiky/të pambështetshme kthehen flat explicit. Nuk duhet reklamuar si elevation real i certifikuar.
- Në provën Austin u pranua range afërsisht 30.10m. Kjo nuk provon topografinë e vërtetë. Disa layout-e, p.sh. prova Monaco, kërkuan flat fallback.

Skedarë kyç: `services/procedural_circuit.py`, `driving_path.py`, `cornering.py`, `trajectory_spline.py`, `circuit_scenery.py`, `circuit_lighting.py`, `night_chase.py`, `scripts/day_environment.py`, `scripts/night_environment.py`, `scripts/car_finish.py`.

## 8. Smoothness, flicker dhe performanca: diagnozat reale

### 8.1 Ghost/cockpit flicker

Në klipin 540p Fast të përdoruesit u inspektuan frames rreth brightness jumps. U gjetën mbivendosje të sipërfaqeve ghost dhe prerje pranë kamerës. U përdor frontmost-shell transparency dhe fade gradual i fragmenteve ghost pranë kamerës (0.30–2.5m), jo zhdukje e makinës opaque.

Provë e kontrolluar 12-frame rreth Austin FP1: maksimumi i ndryshimit mesatar të brightness në ROI cockpit ra **23.024 → 7.113**. Kjo është metrikë lokale, jo “69% më pak flicker në çdo video”. Aliasing i hollë apo artifacts të tjerë mund të mbeten.

### 8.2 Shadow atlas overflow

Full lap 1080p Balanced mbushte atlas EEVEE 512MB. U vendos pool 1024MB për RTX3060 12GB, pa ulur samples/resolution/shadow quality. Repeated overflow ndal renderin në vend që të publikojë frames me shadows që mungojnë.

### 8.3 Shpejtim pa ulje të fshehtë cilësie

- Blender prodhon frame-in tjetër ndërsa Pillow/FFmpeg konsumon të përfunduarin.
- PNG me compression low-effort lossless 10; frame-i i konsumuar hiqet nga tmp.
- Vectorization e locator trails dhe ripërdorim i gradients statikë.
- Cache e completed render me key që përfshin telemetrinë, laps, kamerën, timeline, madhësinë, FPS, cilësinë, branding dhe revision e gjeometrisë.
- ETA pas frame-ve fillestare, cancellation dhe partial-output handling.

Benchmark i locator-only: **0.890s → 0.229s (~3.9×)** për 240 frames identike byte-for-byte. **Jo 3.9× whole-video speedup.** Pipeline sequential/streaming u krahasua edhe me MP4 hashes identike në teste.

### 8.4 “broken PNG file”

Ishte race mes producer dhe consumer: shfaqja e filename nuk provon që PNG është mbyllur. U shtua `.ready` marker dhe full image decode para përdorimit; consumer pret për producer-in. Një sequence e paplotë nuk publikohet si video e suksesshme.

### 8.5 “Render not found” pas restart

Job metadata është në memory. Restart humb job-id/progress aktiv, por jo MP4-të e përfunduara dhe disk cache. UI jep shpjegim; My Downloads mbetet rruga për skedarët e ruajtur. **Persistent/resumable jobs nuk janë implementuar.**

### 8.6 Stutter: 24 unique fps brenda 30 fps

U audituan source-i i vjetër dhe MP4 i postuar. Afërsisht çdo frame i pestë në 30fps ishte near-duplicate; mapping `floor(export_index * 24/30)` u konfirmua në 300 frames. Prova tregoi konvertim të mëvonshëm 24→30, jo bllokim të browser-it. Nuk u identifikua editor-i i jashtëm që e kishte bërë.

U shtua **native 60fps** në të gjithë pipeline-in. Çdo frame aktiv merr timestamp unik të simulimit; në constant 3×/60fps hapi është 0.05 source seconds. Nuk përdoret frame duplication/artificial interpolation si zgjidhje kryesore.

Rebuild-i përfshiu C1 Hermite constrained route spline (devijim i kufizuar 0.12m), angular unwrap, kamerë predictive me damping, local safe framing dhe zoom të lëmuar. Dynamic pacing ka clock monotone të përbashkët dhe i jep më shumë output-time frenimit/timing swings, pa ndryshuar lap durations.

Prova e plotë 1080×1920/60fps/35s/2100frames: **0 near-duplicate transitions në 1978 krahasime aktive**, PTS afërsisht 16.667ms, 37,800 footprint checks pass. Në të njëjtat poses/timestamps camera translational jerk p95 ra rreth 89.42%; jo çdo metrikë zoom u përmirësua.

Render/encode i asaj prove zgjati afërsisht **29m19s**. Native60fps kushton realisht më shumë frames se 24fps. Nuk kemi arritur renderim full-lap 1080p në pak sekonda. Accelerated playback dhe cache kursejnë frame count/rerender; nuk heqin startup cost.

Settings të tanishme EEVEE: **Fast8 / Balanced24 / High64 samples**. Shënimet e vjetra 2/8/32 janë të tejkaluara. H.264 CRF18, yuv420p, FFmpeg libx264 me fast preset në rrjedhën 3D.

Referenca: `docs/render-performance.md`, `docs/ghost-flicker-audit.md`, `docs/cinematic-ghost-rebuild.md`.

## 9. Rregullimi i linjës/trajectory ribbon

Përdoruesi kërkoi diagnozë matematikore, jo korrigjim kozmetik. Gjetja ishte:

- Track/cars/ribbon ishin tashmë në të njëjtin world space dhe të njëjtën Blender camera.
- Ribbon ishte ngritur **85mm** mbi asfalt, duke krijuar separation/parallax.
- Car përdorte RouteSpline; ribbon lidhte knots me chords të drejta.
- Shader cutting/time inversion i vjetër nuk vendoste vertex explicit në current car pose.
- Ghost ribbons ndanin layer kur mbivendoseshin.

Implementimi i ri `services/surface_trail.py`:

- Përdor të njëjtin `pose_at_progress` si makina.
- Sampling rreth 20cm + knots + adaptive refinement; curve/chord error ≤0.5mm.
- Head/tail explicit në source timestamp-in e çdo frame-i.
- Inverse analitik i të njëjtit integrated-speed clock.
- BVH projekton vetëm Z mbi asfalt; XY nuk snap-ohet në një rrugë tjetër.
- Nominal 2mm lift, 1mm shtesë për ghost-in tjetër kundër z-fighting.
- Width 24cm në Cinematic, fading/colors sipas semantikës ekzistuese.
- Kontroll i edges dhe triangle centroids, identity transform, pa screen-space corrections.
- Failure ndal publikimin; cache revision v30.

Provë COTA e plotë: 33,252 trajectory points, max spacing0.200098m, off-asphalt vertices0; source times/car/camera/zoom arrays identike para/pas. Head/car XY numerikisht afër epsilon-it CPU; jo pretendim për matje fizike nën-milimetrike të pistës reale.

Debug opsional tregon raw knots, spline, asphalt boundaries dhe car root markers. Nuk është ideal racing line i matur; është **trajectory-history trail i rrugës së renderuar**.

Referenca: `docs/surface-locked-trail.md`, `scripts/trail_alignment_debug.py`, `tests/test_surface_trail.py`.

## 10. Ideja signature: THE LIMIT

U kërkua ide e veçantë, jashtë videos standarde ghost-lap. U implementua **The Limit**, jo thjesht u propozua:

- Hyrje analitike 3.2s: circuit-shaped “time canyon” në studio të errët.
- Lartësia e ridge përfaqëson signed matched-distance time advantage; **nuk është elevation i pistës**.
- Hook me gap real, travelling spark, perspective push-in dhe dissolve drejt replay-it 3D.
- Deri në tre timing swings më të forta, jo-overlapping, mbi windows 6% lap distance.
- Callout p.sh. “ANT FINDS 0.169s HERE”, me të dhëna; nuk shpiket shkak fizik ose emër corner kur nuk ka provë.
- Callouts zgjasin 1.65 output seconds pavarësisht shpejtësisë, përveç ndërprerjes nga finish real.
- Rezultat i saktë dhe sculpture payoff me logo/handle/follow labels.
- Intro është shared-clock hold i shtuar: nuk humbet aksionin fillestar të xhiros.

Target35s përfshin action/result2s, por jo intro shtesë: The Limit bëhet **38.2s**. Target40s bëhet43.2s. Intro nuk është një morph i pandërprerë fizik në Blender; është kompozim/editorial transition.

Nuk janë implementuar physical speed-gate geometry, debris/time particles ose continuous3D morph. Këto mbeten ide.

Skedarë: `services/limit_story.py`, `services/limit_overlay.py`, `scripts/preview_the_limit.py`, `docs/the-limit.md`, `tests/test_limit_story.py`.

## 11. Audio: gjithë historia dhe gjendja e fundit

### 11.1 Paketa F1 2026 / motori sipas pilotit

Përdoruesi vendosi sound pack në `C:\f1hud_app\assets\sounds\F1 2026 Sound Pack` dhe kërkoi motor sipas ekipit, RPM, gear, throttle/brake.

U hetua FMOD1.08.12 dhe SDK lokal. Event metadata kishte rpm/throttle, gear state dhe wind speed. Integrimi i plotë Studio u bllokua nga **missing mixer/master bank / Bus not found** me GUID specifike. Një master bank rastësor nuk e zgjidh përputhjen.

U provua alternativa me decoding të subsounds të lejuara nga bank-at lokale dhe custom mixer approximate. Prova për Ferrari/RedBull, pitch RPM, throttle blend dhe shifts prodhuan WAV. Përdoruesi i refuzoi si të dobëta; vetëm fundi i VER i dukej disi i pranueshëm. Version2 mbeti prototip/listening review, jo feature aktive në eksport.

**Mos aktivizo engine audio si të përfunduar.** SDK/banks janë private dhe nuk duhen redistribuuar. Zgjidhje e ardhshme kërkon stems/loops të lejuara ose matching standalone master bank nga autori, plus validim tingulli dhe lejesh.

Skedarë historikë: `services/fmod_audio.py`, `engine_audio.py`, `engine_samples.py`, `scripts/test_engine_render.py`, `scripts/test_sampled_engine.py`, `docs/engine-audio-status.md`.

### 11.2 Audio kreative/synth dhe vokalet

U provua procedural “The Duel / Hear the Gap”, me ritëm/akcent sipas timing battle. U integrua audio default në të gjitha mode-t. Përdoruesi nuk e pëlqeu backing synth.

U kërkua vocal song; gjenerimi në ChatCut u bllokua me **INSUFFICIENT_CREDITS**. Nuk u krijua këngë vokale. Përdoruesi zgjodhi të mbajë instrumental për momentin dhe më pas kërkoi pa zë. Mos pretendo se ekziston soundtrack vocal i prodhuar.

Procedural synthesis ekziston ende për diagnostikë/histori, por nuk është backing default i prodhimit.

### 11.3 Soundtracks aktuale në site

1. **Industrial Cut · percussion / tension**, ID API **`The Duel`** për kompatibilitet: *Industrial Cinematic* — Kevin MacLeod.
2. **Grit & Drums · guitar / bass**: *Gearhead* — Kevin MacLeod.
3. **Silent**, opt-out explicit.

Janë recordings të publikuara, shkarkuar nga burimi zyrtar i autorit, me provenance/license record lokal CC BY4.0. Janë full mixes, jo stems të ndara. Nuk janë Justice/HansZimmer, narracion ose audio reale motori.

- Default80%, të gjitha mode-t 2D/3D/preview/final dhe klienti legacy.
- Hyrje nga onset më energjik, forward playback natyral, crossfade250ms për loop gjatë.
- Pitch/tempo muzikës nuk shpejtohet 3×/20× bashkë me simulimin.
- 48kHz stereo PCM, loudness normalization, AAC192k në MP4.
- Audio mux me `-c:v copy`; nuk ri-renderon Blender vetëm për mux kur video e saktë është në cache.
- Credit i dukshëm në çdo frame + metadata MP4/job + tekst për caption social.
- Ndërrimi track mund të kërkojë video me credit të ri; vetëm ndryshimi volume mund të ripërdorë të njëjtën video të kredituar.
- MP4 ekzistuese nuk përditësohen vetë.

### 11.4 Bug-u “muzika ndalet te callout dhe rezultati”

Shkaku ishte duck rreth88% te cues dhe envelope që hiqte backing pas finish. U hoq duck/gate. Tani muzika vazhdon në gain callouts, result card dhe finale; vetëm fundi real ka fade180ms. Mund të ketë level ride të butë, jo pauzë të komanduar nga grafika.

Revision audio **`continuous-music-2`**. Në proof-in e korrigjuar të gjithë2292video packets dhe PTS mbetën identikë me videon e kredituar para tij. Test me constant recording izolon mixer-induced dips nga pauzat natyrale të vetë këngës.

Skedarë aktualë: `services/recorded_music.py`, `services/duel_audio.py`, `assets/music/industrial-cinematic.mp3`, `assets/music/gearhead.mp3`, `assets/music/ATTRIBUTION.md`, `docs/recorded-soundtracks.md`.

Ruaj attribution edhe në social description. Mos premto mungesë absolute të ContentID/automated claims. Për monetizim/sponsorship të ardhshëm duhen rishikuar kushtet e burimeve; ky raport nuk është vlerësim ligjor i ri.

## 12. Bug-u më i fundit: Mexico 2025 Q / The Limit / Cinematic Dynamic

Raportimi: drivable coverage1.0,5220route knots,46656asphalt footprint checks ALL_PASS, por Blender ndalte renderin sepse car safe-frame ishte minY **0.379186**, ndërsa guard kërkonte **0.38**.

Shkaku real:

- Planner përdorte horizontal generic proxy për makinën.
- Guard final Blender përdorte actual metadata bounds dhe root rotation me road pitch.
- Planner dhe validator kontrollonin gjeometri jo identike. Nuk ishte dështim asfalt/line.

Fix:

- `scripts/cinematic_math.py:project_cars` pranon actual local corners dhe road-pitch transform të njëjtë si car root.
- `services/cinematic_camera.py:cinematic_ghost_rig` merr të njëjtat corners.
- `scripts/render_3d_test.py` i nxjerr nga model metadata dhe ia kalon rig-ut.
- Fitting target pak më brenda për float32 clearance; **guard origjinal final nuk u hoq dhe nuk u relaksua**.
- `services/video_3d.py` shton camera-cache revision **`pitched-actual-mesh-bounds-v2`** vetëm për kamerat e prekura.
- Nuk u ndryshuan lap times, car poses, track, trail ose audio.

Validim: NumPy projection kundër `world_to_camera_view` real Blender, portrait/landscape540/1080 dhe chase/overhead. Offline Mexico cached pairings **LEC/VER, NOR/VER, NOR/LEC** kaluan çdo frame të timeline2592frames; min portraitY≥0.39563. Përdoruesi nuk kishte identifikuar çiftin e vet. ANT nuk ishte në cache-n lokale Mexico të kësaj prove.

**Nuk u renderua full MP4 e re Mexico si pjesë e këtij fix-i.** Ishte full-timeline mathematical/Blender projection validation, jo film i parë nga fillimi në fund.

Scripts: `scripts/prepare_mexico_camera_validation.py`, `scripts/validate_cinematic_projection.py`. Reports: `tmp/mexico-camera/*.validation.json`. Dokument: `docs/cinematic-framing-fix.md`. Teste: `tests/test_cinematic_bounds.py`.

## 13. Prova dhe output-et që duhen ruajtur

Të gjitha këto rrugë janë relative ndaj `C:\f1hud_app`; ekzistenca e MP4-ve kryesore u kontrollua gjatë dorëzimit.

| Skedari | Çfarë provon / kufizimi |
| --- | --- |
| `output/video_studio/2026-ANT-VER-COTA-Qualifying-Cinematic-60fps-20261026.mp4` | Full1080×1920/native60fps/35s; cinematic rebuild; para fix-eve të mëvonshme trail/audio |
| `output/video_studio/2026-ANT-VER-COTA-Surface-Locked-Trail-540p-60fps.mp4` | Trail i korrigjuar,35s,540p/Fast; jo benchmark cilësie identik me1080pBalanced |
| `output/video_studio/2026-ANT-VER-COTA-Trail-Alignment-DEBUG.mp4` | Overlay diagnostike alignment |
| `output/video_studio/2026-ANT-VER-COTA-THE-LIMIT-60fps.mp4` | TheLimit38.2s,540p,2292frames; mostër pa soundtrack të mëvonshëm |
| `output/video_studio/2026-ANT-VER-INDUSTRIAL-CONTINUOUS-60fps.mp4` | Mostra audio më e re e korrigjuar: continuous music;38.2s/native60fps/540p |
| `output/video_studio/2026-ANT-VER-GRIT-AND-DRUMS-60fps.mp4` | Provë e track-ut alternativ, por mix-i i ruajtur paraprin continuous-music fix; gjenero të re për sjelljen e fundit |

Mostrat me emra `THE-DUEL`/`CINEMATIC-PULSE` të vjetra mund të përmbajnë synth të refuzuar. Mos i jep si default-in aktual. Asnjë file historik nuk “merr” automatikisht një fix që është bërë më pas në kod.

Artifact directories me vlerë:

- `tmp/smoothness-audit/`: cadence, motion, re-encode origin, frame sheets.
- `tmp/trail-alignment/`: before/after config, debug geometry, comparison.
- `tmp/the-limit/`: intro, callout, proof.
- `tmp/recorded-music/`: credit/layout/audio UI proof.
- `tmp/mexico-camera/`: full-timeline projection validation.
- `tmp/shadow-budget/`, `tmp/flicker-audit/`: prova të problemeve të hershme.

## 14. Setup, nisja dhe përdorimi

Mjedisi i përdorur: Windows/PowerShell, Python3.10 në `.venv`, RTX3060 12GB, Blender4.5.9 LTS portativ, FFmpeg/ffprobe në PATH. React19/TypeScript/Vite7; FastAPI/Uvicorn. Versionet Python janë pinned në `requirements.txt`; frontend ka lockfile.

```powershell
cd C:\f1hud_app
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
.\scripts\start-platform.ps1 -SkipBuild
```

Hap `http://localhost:8000`. Pa `-SkipBuild`, script bën build para nisjes. Alternativë backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Development frontend: `npm run dev` brenda `frontend`; Vite5173 proxy te API8000. Streamlit i vjetër: `.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501`.

Blender autodetect te `tools/blender/blender-*/blender.exe` ose environment variable `RACE_HYPE_BLENDER`. Mos supozo `.venv`/absolute paths të këtij PC funksionojnë pas kopjimit në PC tjetër.

Endpoints të dobishme: `/api/health`, `/api/docs`, `/api/openapi.json`. Frontend dist shërbehet nga backend. Local workstation: bind loopback127.0.0.1, jo publikim interneti pa audit të veçantë.

Rrjedha e përdorimit: season → event → session → Load session → dy driver/lap → mode/camera → pacing/FPS/detail/audio → short preview → full preview/final → download. Player tregon renderin e fundit të përfunduar, jo ndryshimet e reja derisa të shtypet render përsëri.

**Kontrolli i sotëm i health:** lidhja te127.0.0.1:8000 u refuzua; backend nuk ishte i arritshëm në atë moment. Nuk u rinis, sepse kërkesa ishte raport/dorëzim. Kjo nuk provon regresion kodi; është gjendje runtime për t’u kontrolluar nga Claude.

## 15. Testimi dhe verifikimi

Komandat bazë:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
node --test tests/constructor_timeline.test.js
cd frontend
npm run build
```

Proof commands më të rëndësishme:

```powershell
# Proof i shkurtër i production path; jo full1080p render
.\.venv\Scripts\python.exe -m scripts.preview_cinematic_ghost --the-limit --end 12 --quality Fast --output tmp/the-limit/proof

# Alignment debug
.\.venv\Scripts\python.exe -m scripts.preview_cinematic_ghost --alignment-debug --end 12 --quality Fast --output tmp/trail-alignment/debug-check

# Përgatitje Mexico cases nga cache lokale
.\.venv\Scripts\python.exe -m scripts.prepare_mexico_camera_validation

# Projection math kundër Blender
& .\tools\blender\blender-4.5.9-windows-x64\blender.exe --background --disable-autoexec --python-exit-code 1 --python scripts/validate_cinematic_projection.py
& .\tools\blender\blender-4.5.9-windows-x64\blender.exe --background --disable-autoexec --python-exit-code 1 --python scripts/validate_cinematic_projection.py -- --case tmp/mexico-camera/LEC-VER.json
```

Verifikim i ri më 30 tetor 2026, gjatë përgatitjes së këtij raporti: **186 teste Python passed në20.812s, 9 teste Node passed dhe build TypeScript/Vite passed**. Kontrolli i parë i suite brenda sandbox u ndal pasi ngeci në kufizimet e socket-it lokal; ekzekutimi i dytë me aksesin përkatës përfundoi normalisht. Kjo nuk u raportua si regresion i aplikacionit. Ka warnings Streamlit për bare runtime dhe deprecation të Starlette/httpx, por suite përfundoi OK.

Checkpoint i mëparshëm pas fix-it Mexico kishte gjithashtu186teste. Numrat95/147/156/169/179/184 në docs janë checkpoints historike, jo gjendje paralele. Nuk u bë render i ri i plotë ose UI visual inspection gjatë këtij raporti.

Testimi mbulon clock, lap result, fallback, missing channels, no-partial-publication, cancellation, media mux, credits, car/asphalt coverage, camera bounds, exact trail alignment, API routing dhe defaults. Test i kaluar nuk zëvendëson perceptual review të çdo pistë/video.

Për çdo ndryshim të renderer-it: rendero clip të shkurtër, kontrollo frames radhazi në turn-in/apex/exit, verifiko source clock dhe rezultat, ffprobe/FFmpeg decode, kontrollo shadow overflow/footprints/safe frame, pastaj full video nëse duhet. Mos e quaj sukses të plotë vetëm nga screenshot statik ose ndryshim i një label-i FPS.

## 16. Transferimi te Claude: mos humb punën

**Gjendja Git është dirty dhe shumë pjesë kryesore janë untracked.** Inspektimi tregoi `?? api/`, `?? frontend/`, `?? docs/`, `?? scripts/`, shumë `services/*.py`, `tests/`, assets dhe output. Vetëm `git clone` i remote nuk garanton transferimin e kësaj pune. Nuk u krye commit/push gjatë raportit.

Në të njëjtin PC: Claude Code duhet të hapë direkt `C:\f1hud_app` dhe të lexojë këtë raport përpara editimit. Për PC tjetër: nevojitet kopje e kontrolluar e kodit aktual dhe private assets të kërkuara; mund të rindërtohen dependencies.

Çfarë duhet ruajtur/kopjuar qëllimisht:

- Source: `api/`, `frontend/src/`, frontend config/lockfile/public assets, `services/`, `ui/`, `components/`, `scripts/`, `tests/`, `docs/`, entrypoints, requirements.
- Logo: `frontend/src/assets/rh-logo.png`, `assets/logo/RH Racing Social Media Overlay.png`, artwork/flags që përdor UI.
- Modeli aktiv dhe metadata: `assets/3d/cars/qvist/`; ruaj original dhe credits, jo vetëm `.blend` të përgatitur.
- Muzika dhe `assets/music/ATTRIBUTION.md`.
- `fastf1_cache/`, `outputs/openf1_cache/`, `replay_cache/` nëse duhet punë offline; këto janë shumë të vlefshme dhe jo të gjitha gjenden në Git.
- `output/`, `outputs/`, `charts/` nëse duhen rezultatet historike. Kujdes: `output` dhe `outputs` janë dy dosje të ndryshme.
- Proof reports/configs në `tmp/` sipas nevojës, në veçanti camera/trail/cadence validation.

Çfarë nuk duhet publikuar si source publik:

- `.streamlit/secrets.toml`, `.env`, credentials, profile personale pa kontroll.
- Raw licensed 3D models dhe bank/SDK nga `assets/sounds/` pa të drejta redistribuimi.
- `.venv`, `frontend/node_modules`, Blender tools bundle nuk janë zëvendësim i instalimit në një mjedis tjetër.

`.gitignore` aktual nuk duhet trajtuar si audit licence apo backup plan: disa private/gjeneruara mund të jenë untracked por jo ignored. Mos bëj `git add .`/push verbërisht. Mos fshi cache për të “pastruar” transferimin pa miratimin e përdoruesit.

## 17. Mospërputhje në dokumente: çfarë ka përparësi

Dokumentet u shkruan gjatë fazave të ndryshme. README dhe disa faqe të vjetra thonë ende silent24fps, tetë pista, flat elevation ose OriginalGLB enabled. Këto nuk janë përshkrimi aktual i plotë.

Për gjendjen e fundit kontrollo në këtë rend:

1. Kodin runtime/UI dhe testet aktuale.
2. `docs/cinematic-framing-fix.md` për bounds e kamerës.
3. `docs/recorded-soundtracks.md` për audio continuous/all modes.
4. `docs/surface-locked-trail.md` për ribbon.
5. `docs/the-limit.md` për story; pohimi i vjetër “no soundtrack” atje është tejkaluar.
6. `docs/cinematic-ghost-rebuild.md` për native60fps; pohimi pa audio është historik.
7. `docs/MIGRATION.md` për strukturën; checkpoint95tests është historik.

`docs/engine-audio-status.md` është prototip i papërfunduar, jo përshkrim i muzikës së sotme. `docs/the-duel-audio.md` është histori synth v1/v2, jo backing aktual.

Edhe teksti i attribution metadata në `recorded_music.music_info` përmban ende fjalën historike “ducking”; rruga reale e mix-it dhe `MIX_VERSION=continuous-music-2` nuk bëjnë cue duck/pause. Ky është cleanup i vogël dokumentues i mbetur, jo arsye për të rikthyer ducking ose për të ngatërruar tekstin me sjelljen audio.

Brief-i origjinal i gjatë i përdoruesit për rebuild ruhet lokalisht te `C:\Users\user\.codex\attachments\422393f8-a6f9-4a1b-9d14-2b88405f94ab\Pasted text.txt`. Në transferim në PC tjetër, bashkëngjite veçmas nëse nevojitet: nuk është pjesë e dosjes së projektit. E njëjta vlen për referencat video te Downloads dhe screenshots te Temp; ato nuk duhen supozuar të disponueshme në Claude vetëm nga emri në këtë raport.

## 18. Çfarë mbetet për t’u bërë — plan i propozuar, jo punë e kryer

### P0 — Dorëzim i sigurt dhe baseline

1. Hap projektin ekzistues, inspekto Git pa reset/clean, ruaj të gjitha ndryshimet e përdoruesit.
2. Kontrollo dependencies/assets/cache dhe nise vetëm kur s’ka render aktiv. Një server/worker.
3. Rerun tests/build; mos kthe GLB, synth ose24fps si default për të “rregulluar” regresione.
4. Merr driver pair/laps e sakta Mexico të përdoruesit dhe bëj clip real pastaj full-timeline/video sipas nevojës; fix-i aktual ka full projection validation por jo MP4 të re Mexico.
5. Bashko dokumentet e vjetra me gjendjen aktuale që të mos krijojnë udhëzime kontradiktore.

### P1 — Besueshmëri e jobs dhe performance engineering

1. Persistent jobs/status manifest (p.sh.SQLite) dhe rikuperim pas restart. Aktualisht jo resumable.
2. Structured timing log për provider load, geometry prep, Blender startup, per-frame, HUD, encode dhe audio; ETA me phase separation.
3. Cache-layer ndarë scene/HUD/audio për të shmangur Blender rerender nga ndryshime editoriale kur është teknikisht e sigurt. Sot credit change mund të ndikojë render cache; mos premto cache reuse universal.
4. Benchmark i kontrolluar i hardware encoding/alternative frame transport/scene caching. Prano vetëm nëse cilësia/cadence/credits mbeten të provuara; jo ndërrim i verbër NVENC ose ulje samples.
5. Regression matrix për shumë pista, portrait/landscape, close/wide, separated/overlap ghosts dhe të gjitha camera styles.

### P1 — Cilësi pamjeje dhe të dhënash

1. Vazhdo frame-by-frame flicker tests: distinguish aliasing, transparency, shadows, z-fighting dhe compression. Nuk ka certifikim zero-flicker universal.
2. Përmirëso scenery/kerb/runoff circuit-specific me assets/data të licencuara.
3. Për elevation real duhen burime terrain/DEM/survey të përshtatshme dhe validim scale/coordinate/bridge overlaps. Z telemetry vetëm nuk mjafton.
4. Driver-specific line vetëm kur pozicionet janë mjaft të sakta dhe të sinkronizuara; ndryshe etiketo route illustrative. Mos shpik apex-e nga marketingu.
5. Car replicas/liveries vetëm pas sigurimit të të drejtave/metadata; concept ekzistues mbetet baseline.

### P2 — Audio dhe editorial

1. Përdoruesi nuk ka miratuar që soundtrack-et aktuale janë zgjedhja përfundimtare artistike. Mund të nevojiten alternativa më të mira me prova dëgjimi A/B të shkurtra para gjithë pipeline-it.
2. Music import/personal licensed library dhe edit pa Blender rerender mund të jenë shtesa me vlerë; **jo feature e implementuar sot**.
3. Nëse kërkohet motori: standalone licensed loops/stems ose matching master bank nga krijuesi; jo patch/bypass i dependencies pronësore.
4. Voice/vocal vetëm me kërkesë të re. Gjendja e sotme është no voice.
5. TheLimit hooks/callout A/B, first-second visual clarity, payoff dhe branding-safe margins. Mat retention në platforma; mos pretendoni “no one swipes”.
6. Continuous3D time-canyon morph/speed gates mbeten ide opsionale, jo prioritet ndaj besueshmërisë.

### P2 — Produkti dhe publikimi

1. Auto-SEO/caption/hashtag templates me metadata reale mund të shtohen; deri tani kërkesat SEO trajtoheshin në bisedë, jo si gjenerator i verifikuar në aplikacion.
2. Posting automatik në TikTok/Instagram/YouTube, llogari publike/multi-user/cloud render nuk janë dorëzuar.
3. Deployment publik kërkon auth, isolation, queue/storage limits, secrets dhe licence review; aplikacioni aktual është workstation lokal.

## 19. Rregulla që Claude duhet të ruajë

- Mos fillo nga zero dhe mos ndrysho framework pa arsye e miratim.
- Mos fshi cache/output/assets dhe mos përdor `git reset --hard`, checkout shkatërrues ose clean mbi këtë worktree.
- Mos restart server kur Blender/FFmpeg ka render aktiv; restart heq metadata in-memory.
- Mos ngarko source3D/soundbanks/secrets në Git publik.
- Mos e zëvendëso një missing channel me fakt të shpikur.
- Mos përziej FP1 dhe qualifying, xhiro të ndryshme ose rezultate historike me live.
- Mos ndrysho lap times/progress që fituesi të duket më bindës.
- Cars/track/trail duhet të ndajnë world-space dhe camera pipeline; endpoint trail duhet të vijë nga pose clock i makinës.
- Ruaj ready markers, atomic output, cancellation dhe footprint/safe-frame guards.
- Testet/proofs duhet të dallojnë “math check”, “short clip”, “full render” dhe “visual approval”.
- Mos premto më shumë shpejtësi, realizëm, licenca ose virality sesa është provuar.

## 20. Prompt i gatshëm për Claude

Kopjo këtë bashkë me raportin, ose jepi Claude Code path-in e këtij dokumenti:

> Continue my existing RACE HYPE project at C:\f1hud_app. Read docs/CLAUDE_HANDOVER_SQ.md, the current runtime code, relevant tests and latest focused docs before editing. This is an existing working React/TypeScript + FastAPI/Python + Blender/FFmpeg platform, not a greenfield website. Preserve the dirty/untracked worktree, private assets, caches, source telemetry, exact lap times and outputs. Current production uses telemetry-built tracks only, generic Qvist concept cars, illustrative shared cornering routes, native selected FPS (React defaults to60), a shared source clock, surface-locked exact trajectory trails, The Limit/Cinematic Ghost Chase story presets, and licensed recorded instrumental music across all new preview/final videos. Do not re-enable imported circuit models, rejected synthetic backing or experimental engine audio without my approval. Latest camera fix aligns the planner with actual pitched mesh bounds and keeps the original Blender guard; Mexico2025Q full-timeline projection cases passed, but my exact driver pairing still needs a rendered reproduction if relevant. First report what you have verified, what is only historical documentation and the highest-priority remaining issues. Do not rebuild everything or launch expensive full renders without a reason. My priorities are correct data, stable cinematic motion, faster quality-preserving exports, convincing track/car presentation, good continuous audio, my RH branding/@theracehype, and engaging social videos without fake racing outcomes or guaranteed-virality claims.

