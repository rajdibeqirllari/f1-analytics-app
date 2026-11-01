const {test} = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const timeline = require('../components/constructor_showcase/timeline.js');
const root = path.resolve(__dirname, '..');
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const config = JSON.parse(execFileSync(python, ['-c',
  'import json; from ui.constructor_config import CONSTRUCTOR_ASSETS, SHOWCASE_SETTINGS, DEBUG_CAR_ALIGNMENT; print(json.dumps(dict(assets=CONSTRUCTOR_ASSETS, settings=SHOWCASE_SETTINGS, debug=DEBUG_CAR_ALIGNMENT)))'], {cwd:root, encoding:'utf8'}));
const settings=config.settings, count=Object.keys(config.assets).length, viewport=856;
const step=timeline.segmentLength(settings,viewport);
const sample=(px,reduced=false,compact=false) => timeline.sample(px,count,settings,viewport,reduced,compact);
const near=(a,b,epsilon=1e-9) => assert.ok(Math.abs(a-b)<epsilon, `${a} != ${b}`);

test('11 calibrated assets, no fixed ranking; debug off', () => {
  assert.equal(count,11);
  assert.equal(config.debug,false);
  assert.equal(settings.autoAdvanceMs,3000);
  assert.equal(settings.autoTransitionMs,750);
  for(const asset of Object.values(config.assets)) {
    assert.ok(!('index' in asset));
    assert.ok(asset.scale>0 && Number.isFinite(asset.x) && Number.isFinite(asset.y));
  }
});
test('autoplay blends smoothly without a blank frame, including last to first', () => {
  for (let i=0;i<count;i++) {
    const from=sample(i*step).states;
    const to=sample(((i+1)%count)*step).states;
    for (const [t,expected] of [[0,from],[1,to]]) {
      timeline.blend(from,to,t).forEach((state,j) => {
        for (const key of Object.keys(state)) near(state[key],expected[j][key]);
      });
    }
    for (let t=0;t<=1;t+=0.01) {
      const states=timeline.blend(from,to,t);
      near(states.reduce((sum,state)=>sum+state.opacity,0),1);
      assert.ok(Math.max(...states.map(s=>s.opacity))>=0.5);
    }
  }
});
test('viewport-relative segment for every constructor, including the last', () => {
  near(step,188.32);
  near(timeline.duration(count,settings,viewport),11*step);
  near(timeline.segmentLength(settings,400),88);
});
test('initial leader fully visible, all cars reach calibrated rest', () => {
  for(let i=0;i<count;i++) {
    const frame=sample(i*step);
    assert.equal(frame.index,i);
    near(frame.states[i].opacity,1);
    near(frame.states[i].x,0);
    near(frame.states[i].y,0);
    near(frame.states[i].scale,1);
  }
});
test('continuous overlapping handovers, no blank panel anywhere', () => {
  for(let px=0;px<=count*step;px+=0.75) {
    const frame=sample(px), next=sample(px+0.001);
    const sum=frame.states.reduce((total,s)=>total+s.opacity,0);
    if(px<(count-1)*step) near(sum,1);
    assert.ok(Math.max(...frame.states.map(s=>s.opacity))>=0.5);
    assert.ok(frame.states.filter(s=>s.opacity>0).length<=2);
    for(let i=0;i<count;i++) {
      assert.ok(Math.abs(frame.states[i].opacity-next.states[i].opacity)<0.0001);
      assert.ok(Math.abs(frame.states[i].rotation)<=settings.rotationDegrees);
    }
  }
  const midpoint=(settings.transitionStart+settings.transitionEnd)/2;
  const frame=sample(step*midpoint);
  near(frame.states[0].opacity,0.5);
  near(frame.states[1].opacity,0.5);
});
test('last car has a complete rest/exit segment and remains visible at release', () => {
  const beginning=(count-1)*step;
  near(sample(beginning+step*0.6).states[count-1].opacity,1);
  const exit=sample(beginning+step*0.85).states[count-1].opacity;
  assert.ok(exit<1 && exit>settings.finalExitOpacity);
  near(sample(count*step).states[count-1].opacity,settings.finalExitOpacity);
  assert.deepEqual(sample(count*step+2000),sample(count*step));
  assert.deepEqual(sample(-2000),sample(0));
});
test('slow, fast, reverse and arbitrary scrollbar jumps are identical', () => {
  const samples=[0,91,1700.25,step*10.4,step*11,553,step*9.9,25];
  const expected=samples.map(px=>sample(px));
  samples.slice().reverse().forEach(px=>sample(px));
  samples.forEach((px,i)=>assert.deepEqual(sample(px),expected[i]));
});
test('reduced motion retains crossfades without translation/rotation/scale drift', () => {
  for(let px=0;px<count*step;px+=31) {
    const normal=sample(px), reduced=sample(px,true);
    for(let i=0;i<count;i++) {
      near(normal.states[i].opacity,reduced.states[i].opacity);
      near(reduced.states[i].x,0); near(reduced.states[i].y,0);
      near(reduced.states[i].rotation,0); near(reduced.states[i].scale,1);
    }
  }
});
test('hero wheel supports pixels, lines, pages, reverse and boundary handoff', () => {
  near(timeline.wheelStep(0,2000,120,0,856),120);
  near(timeline.wheelStep(0,2000,3,1,856),48);
  near(timeline.wheelStep(0,2000,1,2,856),856);
  near(timeline.wheelStep(600,2000,-120,0,856),480);
  near(timeline.wheelStep(0,2000,-120,0,856),0);
  near(timeline.wheelStep(2000,2000,120,0,856),2000);
  near(timeline.wheelStep(1900,2000,120,0,856),2000);
});
