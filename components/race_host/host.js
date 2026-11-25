/* The host watches the timing feed and generates her own reactions. */
const hostService = 'http://127.0.0.1:8172';
async function startHost() {
  const status = document.querySelector('#status');
  const app = new PIXI.Application({view: document.querySelector('canvas'), resizeTo: window,
    backgroundAlpha: 0, antialias: true});
  const model = await PIXI.live2d.Live2DModel.from('./model/mao_pro.model3.json',
    {autoInteract: false});
  const width = model.width, height = model.height;
  model.anchor.set(0.5, 0);
  function resize() {
    model.scale.set(Math.min(innerWidth / width, innerHeight * 1.6 / height));
    model.position.set(innerWidth / 2, 0);
  }
  resize();
  addEventListener('resize', resize);
  app.stage.addChild(model);
  const ctx = new AudioContext();
  const audio = new Audio();
  audio.crossOrigin = 'anonymous';
  const analyser = ctx.createAnalyser();
  ctx.createMediaElementSource(audio).connect(analyser);
  analyser.connect(ctx.destination);
  analyser.fftSize = 512;
  const samples = new Uint8Array(analyser.fftSize);
  model.internalModel.on('beforeModelUpdate', () => {
    analyser.getByteTimeDomainData(samples);
    let power = 0;
    for (const sample of samples) power += ((sample - 128) / 128) ** 2;
    model.internalModel.coreModel.setParameterValueById('ParamA',
      Math.min(1, 6 * Math.sqrt(power / samples.length)));
  });
  addEventListener('click', () => ctx.resume());
  let run, seen = 0, pending;
  function clear() {
    pending = null;
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
  }
  async function tick() {
    try {
      const response = await fetch(hostService + '/state', {cache:'no-store', signal:AbortSignal.timeout(5500)});
      if (!response.ok) throw Error('Timing unavailable');
      const {feed, host:c} = await response.json();
      const lines = c?.lines || [];
      const latest = lines.reduce((max,l) => Math.max(max,l.id), 0);
      if (!feed || c.run !== run || feed.paused) {
        clear();
        run = c?.run;
        seen = latest;
      } else {
        const fresh = lines.filter(l => l.id > seen && l.audio);
        seen = Math.max(seen, latest);
        if (fresh.length) pending = fresh[0];
        const clock = feed.clock - (feed.mode === 'follow' ? 5 : 0);
        if (pending && pending.event_clock != null && clock - pending.event_clock > 20 * (feed.speed || 1)) pending = null;
        if (pending && (pending.event_clock == null || pending.event_clock <= clock)
            && (audio.paused || audio.ended || pending.prio >= 5) && ctx.state === 'running') {
          audio.src = hostService + pending.audio;
          pending = null;
          await audio.play();
        }
      }
      status.textContent = ctx.state !== 'running' ? 'Click to enable host audio' :
        c.error || '';
    } catch {
      clear();
      run = undefined;
      status.textContent = 'Reconnecting to race host…';
    } finally {
      setTimeout(tick, 750);
    }
  }
  tick();
}
startHost().catch(err => {
  document.querySelector('#status').textContent = 'Host could not load: ' + err.message;
});
