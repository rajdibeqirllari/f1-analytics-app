/* Hero-local wheel input. Page scrolling never advances the cars. */
(() => {
  let host, doc;
  try { host = window.parent; doc = host.document; } catch (_) { return; }
  const bridge = window.frameElement;
  if (bridge) bridge.setAttribute("data-rh-scanner-bridge", "");
  let retryObserver;
  function mount() {
    const story = doc.getElementById("rh-constructor-story");
    if (!story) return false;
    retryObserver?.disconnect();
    host.__rhConstructorCleanup?.();
    const {constructors, settings, debug} = scannerConfig;
    if (!scannerConfig.enabled) return true;
    const hero = story.querySelector(".rh-hero");
    const panel = story.querySelector(".rh-scanner");
    const cars = [...story.querySelectorAll(".rh-scanner-car")];
    const images = cars.map(car => car.querySelector("img"));
    const labels = [...story.querySelectorAll(".rh-constructor-label")];
    const grid = story.querySelector(".rh-scanner-grid");
    const progress = story.querySelector(".rh-scanner-progress i");
    const hint = story.querySelector(".rh-scroll-hint");
    const debugPanel = story.querySelector(".rh-alignment-debug");
    const debugOutput = debugPanel.querySelector("output");
    const reduced = host.matchMedia("(prefers-reduced-motion: reduce)");
    const compact = host.matchMedia("(max-width: 640px)");
    // Streamlit scrolls stMain, not window. Discover the real ancestor instead
    // of relying on a particular version's generated CSS class names.
    let scroller = story.parentElement;
    while (scroller && !/auto|scroll/.test(host.getComputedStyle(scroller).overflowY)) scroller = scroller.parentElement;
    scroller ||= doc.scrollingElement;
    const rootScroll = scroller === doc.scrollingElement;
    let distance = 0, total = 0, viewportHeight = 0;
    let frame = 0, ready = false, disposed = false, activeIndex = -1;
    let inView = true, smallPanel = false;
    let autoTimer = 0, animation = null, lastSample = null, paused = false;
    const autoButton = doc.createElement("button");
    autoButton.className = "rh-auto-toggle";
    autoButton.type = "button";
    autoButton.textContent = "Ⅱ";
    autoButton.setAttribute("aria-label", "Pause automatic car rotation");
    autoButton.title = "Pause automatic car rotation";
    hero.querySelector(".rh-scanner-caption").append(autoButton);
    function armAuto() {
      host.clearTimeout(autoTimer);
      if (!ready || disposed || paused || !inView || doc.hidden) return;
      autoTimer = host.setTimeout(advanceAuto, settings.autoAdvanceMs);
    }
    function advanceAuto() {
      if (disposed || paused || !inView || doc.hidden) return;
      const next = (Math.max(0, activeIndex) + 1) % constructors.length;
      const targetDistance = next * ConstructorTimeline.segmentLength(settings, viewportHeight);
      const target = ConstructorTimeline.sample(targetDistance, constructors.length, settings, viewportHeight, reduced.matches, compact.matches || smallPanel);
      const from = lastSample.states.map(state => ({...state}));
      const to = target.states.map(state => ({...state}));
      const motion = reduced.matches ? 0 : compact.matches || smallPanel ? 0.45 : 1;
      // A restrained overlapping glide, including the last-to-first handover.
      from[next].x = settings.transitionDistance * motion;
      from[next].scale = 1 + settings.scaleDrift * motion;
      from.forEach((state, i) => {
        if (i !== next && state.opacity > 0) {
          to[i].x = -settings.transitionDistance * motion;
          to[i].scale = 1 - settings.scaleDrift * motion;
        }
      });
      animation = {from, to, target, fromIndex:activeIndex, started:host.performance.now()};
      distance = targetDistance;
      schedule();
      armAuto();
    }
    function toggleAuto() {
      paused = !paused;
      autoButton.textContent = paused ? "▶" : "Ⅱ";
      const label = paused ? "Resume automatic car rotation" : "Pause automatic car rotation";
      autoButton.setAttribute("aria-label", label);
      autoButton.title = label;
      armAuto();
    }
    autoButton.addEventListener("click", toggleAuto);
    function visibilityChanged() { armAuto(); }
    doc.addEventListener("visibilitychange", visibilityChanged);
    function measure() {
      if (disposed) return;
      smallPanel = panel.clientWidth < 480;
      const fraction = total ? distance / total : 0;
      viewportHeight = rootScroll ? host.innerHeight : scroller.clientHeight;
      total = ConstructorTimeline.duration(constructors.length, settings, viewportHeight);
      distance = fraction * total;
      story.setAttribute("data-segment-px", String(ConstructorTimeline.segmentLength(settings, viewportHeight)));
      schedule();
    }
    function render() {
      frame = 0;
      if (!ready || disposed) return;
      story.setAttribute("data-car-distance", String(distance));
      let sample = ConstructorTimeline.sample(distance, constructors.length, settings, viewportHeight, reduced.matches, compact.matches || smallPanel);
      if (animation) {
        const t = Math.min(1, (host.performance.now() - animation.started) / settings.autoTransitionMs);
        sample = {...animation.target, states:ConstructorTimeline.blend(animation.from, animation.to, t),
          index:t < 0.5 ? animation.fromIndex : animation.target.index};
        if (t >= 1) animation = null;
        else schedule();
      }
      lastSample = sample;
      for (let i = 0; i < cars.length; i++) {
        const state = sample.states[i];
        cars[i].style.opacity = state.opacity.toFixed(5);
        cars[i].style.transform = `translate3d(${state.x}px,${state.y}px,0) scale(${state.scale}) rotate(${state.rotation}deg)`;
        // Fade names through a quiet midpoint rather than superimposing text.
        labels[i].style.opacity = Math.max(0, (state.opacity - 0.5) * 2).toFixed(5);
        labels[i].style.transform = `translateY(${reduced.matches ? 0 : (1 - state.opacity) * 3}px)`;
      }
      progress.style.transform = `scaleX(${sample.progress})`;
      grid.style.transform = reduced.matches ? "none" : `translate3d(${-sample.progress * 6}px,${sample.progress * 4}px,0)`;
      if (activeIndex !== sample.index) {
        activeIndex = sample.index;
        panel.setAttribute("aria-label", `2026 constructor showcase: ${constructors[activeIndex].name}, P${constructors[activeIndex].index} of ${constructors[activeIndex].field_size}`);
        story.dataset.constructor = constructors[activeIndex].id;
      }
      hint.textContent = distance >= total ? "CONTINUE TO SEASON ↓" : "SCROLL HERE TO EXPLORE ↓";
      if (debug) {
        const car = constructors[activeIndex];
        debugOutput.textContent = `${car.name} / P${car.index}\nscale ${car.scale.toFixed(3)} / x ${car.x} / y ${car.y}\nscroll ${Math.max(0, distance).toFixed(1)} px / local ${sample.local.toFixed(3)} / total ${sample.progress.toFixed(3)}`;
      }
    }
    function schedule() { if (!disposed && !frame) frame = host.requestAnimationFrame(render); }
    function onWheel(event) {
      if (!ready || disposed || event.ctrlKey || !event.cancelable) return;
      if (event.target.closest('button, a, input, select, textarea')) return;
      // Manual browsing takes priority; restart the three-second idle timer.
      armAuto();
      if (animation) {
        distance = Math.max(0, activeIndex) * ConstructorTimeline.segmentLength(settings, viewportHeight);
        animation = null;
      }
      const next = ConstructorTimeline.wheelStep(distance, total, event.deltaY, event.deltaMode, viewportHeight);
      // At either end, allow the next outward scroll to move the page.
      if (next === distance) return;
      event.preventDefault();
      distance = next;
      schedule();
    }
    const intersection = new host.IntersectionObserver(entries => {
      inView = entries[0].isIntersecting;
      story.classList.toggle("is-in-view", inView);
      armAuto();
      schedule();
    }, {root: rootScroll ? null : scroller, rootMargin: "100px"});
    intersection.observe(story);
    const resize = new host.ResizeObserver(measure);
    resize.observe(hero);
    resize.observe(scroller);
    hero.addEventListener("wheel", onWheel, {passive: false});
    host.addEventListener("resize", measure, {passive: true});
    reduced.addEventListener("change", schedule);
    compact.addEventListener("change", measure);
    story.classList.toggle("is-debug", debug);
    debugPanel.hidden = !debug;
    const debugClick = event => {
      const button = event.target.closest("[data-debug-step]");
      if (!button || !debug) return;
      const next = Math.max(0, Math.min(constructors.length - 1, activeIndex + Number(button.dataset.debugStep)));
      distance = next * ConstructorTimeline.segmentLength(settings, viewportHeight);
      animation = null;
      armAuto();
      schedule();
    };
    debugPanel.addEventListener("click", debugClick);
    const removal = new host.MutationObserver(() => {
      if (!story.isConnected || (bridge && !bridge.isConnected)) cleanup();
    });
    removal.observe(doc.body, {childList: true, subtree: true});
    function cleanup() {
      if (disposed) return;
      disposed = true;
      host.cancelAnimationFrame(frame);
      host.clearTimeout(autoTimer);
      doc.removeEventListener("visibilitychange", visibilityChanged);
      autoButton.removeEventListener("click", toggleAuto);
      autoButton.remove();
      hero.removeEventListener("wheel", onWheel);
      host.removeEventListener("resize", measure);
      reduced.removeEventListener("change", schedule);
      compact.removeEventListener("change", measure);
      debugPanel.removeEventListener("click", debugClick);
      intersection.disconnect(); resize.disconnect(); removal.disconnect();
      window.removeEventListener("pagehide", cleanup);
      if (host.__rhConstructorCleanup === cleanup) delete host.__rhConstructorCleanup;
    }
    host.__rhConstructorCleanup = cleanup;
    window.addEventListener("pagehide", cleanup, {once: true});
    // Eager loading + decode all 11 before advancing: no loading gaps even
    // when a user scrolls fast. The standings leader is visible immediately.
    const decode = image => image.decode ? image.decode() : new Promise((resolve, reject) => {
      if (image.complete) return image.naturalWidth ? resolve() : reject(new Error("Invalid PNG"));
      image.addEventListener("load", resolve, {once:true});
      image.addEventListener("error", reject, {once:true});
    });
    measure();
    Promise.all(images.map(decode)).then(() => {
      if (disposed) return;
      ready = true;
      story.classList.add("is-ready");
      story.dataset.ready = "true";
      measure();
      armAuto();
    }).catch(() => {
      if (disposed) return;
      hint.textContent = "SHOWCASE UNAVAILABLE";
      story.dataset.ready = "error";
      cleanup();
    });
    return true;
  }
  if (!mount()) {
    retryObserver = new host.MutationObserver(mount);
    retryObserver.observe(doc.body, {childList:true, subtree:true});
    window.addEventListener("pagehide", () => retryObserver.disconnect(), {once:true});
  }
})();
