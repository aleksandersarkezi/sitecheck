// Motion for aleksandersarkezi.com.
//
// Archivo's width axis ("wdth", 62 to 125) does most of the work: both lines
// of the name are fitted to run exactly edge to edge of their column, and
// titles stretch open as they arrive. In the infrastructure section a light
// runs through each path, box by box.
//
// Everything here is decoration on top of a complete static page, so any
// failure just leaves that page as it is.

(function () {
  "use strict";

  var root = document.documentElement;

  function endBoot() {
    root.classList.remove("booting");
  }

  if (!root.classList.contains("js") || !window.gsap || !window.ScrollTrigger) {
    endBoot();
    return;
  }

  var gsap = window.gsap;
  var ScrollTrigger = window.ScrollTrigger;
  gsap.registerPlugin(ScrollTrigger);

  var finePointer = window.matchMedia("(pointer: fine)").matches;
  var MIN_W = 62;
  var MAX_W = 125;

  function wdth(el, w) {
    el.style.fontVariationSettings = '"wdth" ' + Math.min(MAX_W, Math.max(MIN_W, w)).toFixed(1);
  }

  // Wraps letters (or words) in spans and keeps the original text for screen
  // readers on the parent element.
  function split(el, mode) {
    var label = el.textContent.replace(/\s+/g, " ").trim();
    if (!el.hasAttribute("aria-label")) el.setAttribute("aria-label", label);
    var parts = [];
    var lines = el.querySelectorAll(".line");
    var targets = lines.length ? Array.prototype.slice.call(lines) : [el];

    targets.forEach(function (target) {
      var words = target.textContent.replace(/\s+/g, " ").trim().split(" ");
      target.textContent = "";
      words.forEach(function (word, i) {
        var w = document.createElement("span");
        w.setAttribute("aria-hidden", "true");
        w.style.display = "inline-block";
        w.style.whiteSpace = "nowrap";
        if (mode === "words") {
          w.className = "w";
          w.textContent = word;
          parts.push(w);
        } else {
          Array.from(word).forEach(function (char) {
            var c = document.createElement("span");
            c.className = "ch";
            c.textContent = char;
            w.appendChild(c);
            parts.push(c);
          });
        }
        target.appendChild(w);
        if (i < words.length - 1) target.appendChild(document.createTextNode(" "));
      });
    });
    return parts;
  }

  // ---- smooth scrolling and the top bar --------------------------------

  var lenis = null;
  if (window.Lenis) {
    lenis = new window.Lenis({ autoRaf: false, lerp: 0.09 });
    lenis.on("scroll", ScrollTrigger.update);
    gsap.ticker.add(function (time) {
      lenis.raf(time * 1000);
    });
    gsap.ticker.lagSmoothing(0);
  }

  var top = document.querySelector(".top");
  if (lenis && top) {
    lenis.on("scroll", function (l) {
      top.classList.toggle("away", l.scroll > 160 && l.direction > 0);
    });
  }

  document.addEventListener("click", function (e) {
    var a = e.target.closest('a[href^="#"]');
    if (!a || !lenis) return;
    var target = document.querySelector(a.getAttribute("href"));
    if (!target) return;
    e.preventDefault();
    lenis.scrollTo(target, { offset: 0, duration: 1.6 });
    target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
  });

  // ---- the name, fitted edge to edge -----------------------------------

  var name = document.querySelector(".name");
  var lines = Array.prototype.slice.call(name.querySelectorAll(".line"));
  split(name, "letters");
  var lineLetters = lines.map(function (line) {
    return Array.prototype.slice.call(line.querySelectorAll(".ch"));
  });
  var fitted = [100, 125];

  // Width of the text itself, not of the box it sits in.
  function lineWidth(line) {
    var range = document.createRange();
    range.selectNodeContents(line);
    return range.getBoundingClientRect().width;
  }

  // Binary search on the width axis until the line is exactly as wide as
  // the box it sits in.
  function fitLine(line, target) {
    var lo = MIN_W;
    var hi = MAX_W;
    for (var i = 0; i < 14; i++) {
      var mid = (lo + hi) / 2;
      wdth(line, mid);
      if (lineWidth(line) > target) hi = mid; else lo = mid;
    }
    wdth(line, lo);
    return lo;
  }

  function fitName() {
    var box = name.clientWidth;
    // The widest setting of the shorter line decides the size...
    name.style.fontSize = "100px";
    wdth(lines[1], MAX_W);
    var size = (100 * box) / lineWidth(lines[1]);
    // ...unless that would make the name taller than about 40% of the screen.
    size = Math.min(size, (window.innerHeight * 0.4) / (2 * 0.97));
    name.style.fontSize = size.toFixed(2) + "px";
    fitted = lines.map(function (line) {
      return fitLine(line, box);
    });
  }

  function fitFooter() {
    var el = document.querySelector(".foot-name");
    if (!el) return;
    var parent = el.parentElement;
    var cs = getComputedStyle(parent);
    var box = parent.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    el.style.fontSize = "100px";
    var w = lineWidth(el);
    el.style.fontSize = ((100 * box) / w).toFixed(2) + "px";
  }

  fitName();
  fitFooter();

  var resizeTimer;
  var lastWidth = window.innerWidth;
  window.addEventListener("resize", function () {
    // Phones fire resize when the address bar hides; only width matters here.
    if (window.innerWidth === lastWidth) return;
    lastWidth = window.innerWidth;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      fitName();
      fitFooter();
      ScrollTrigger.refresh();
    }, 150);
  });

  // The two lines drift apart as you scroll away from the top.
  gsap.to(lines[0], {
    xPercent: -8,
    ease: "none",
    scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true },
  });
  gsap.to(lines[1], {
    xPercent: 8,
    ease: "none",
    scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true },
  });

  gsap.to(".portrait img", {
    yPercent: 10,
    ease: "none",
    scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true },
  });

  if (finePointer) {
    var drift = lines.map(function (line) {
      return gsap.quickTo(line, "x", { duration: 1.2, ease: "power3.out" });
    });
    document.querySelector(".hero").addEventListener("pointermove", function (e) {
      var p = e.clientX / window.innerWidth - 0.5;
      drift[0](p * -24);
      drift[1](p * 24);
    });
  }

  function playIntro() {
    name.style.opacity = "1";
    var tl = gsap.timeline();
    lineLetters.forEach(function (letters, li) {
      var o = { w: MIN_W };
      gsap.set(letters, { yPercent: 105, opacity: 0 });
      letters.forEach(function (el) { wdth(el, MIN_W); });
      tl.to(letters, {
        yPercent: 0,
        opacity: 1,
        duration: 1,
        ease: "power4.out",
        stagger: 0.04,
      }, li * 0.15);
      tl.to(o, {
        w: fitted[li],
        duration: 1.4,
        ease: "expo.inOut",
        onUpdate: function () {
          letters.forEach(function (el) { wdth(el, o.w); });
        },
        // Hand the width back to the line, so a later re-fit applies.
        onComplete: function () {
          letters.forEach(function (el) { el.style.fontVariationSettings = ""; });
        },
      }, li * 0.15 + 0.2);
    });
    tl.fromTo(".portrait", { clipPath: "inset(100% 0% 0% 0%)" },
      { clipPath: "inset(0% 0% 0% 0%)", duration: 1.3, ease: "expo.inOut" }, 0);
    tl.fromTo(".portrait img", { scale: 1.35 }, { scale: 1, duration: 1.8, ease: "expo.out" }, 0.2);
    tl.from(".hero-place, .hero-role", { opacity: 0, y: 20, duration: 0.9, ease: "power3.out", stagger: 0.1 }, 0.7);
    tl.from(".top", { opacity: 0, duration: 0.6 }, 1);
  }

  // ---- boot screen -----------------------------------------------------

  function bootSequence(done) {
    var boot = document.querySelector(".boot");
    var log = boot.querySelector(".boot-log");
    var count = boot.querySelector(".boot-count");
    boot.style.animation = "none";

    var stamp = document.querySelector(".foot a[href*='/commit/']");
    var tag = stamp ? "sha-" + stamp.textContent.trim().slice(0, 7) : "latest";
    var steps = [
      "git push origin main",
      "ci: lint, tests, docker smoke test",
      "image: ghcr.io/aleksandersarkezi/sitecheck:" + tag,
      "deploy: health check passed",
      "caddy: serving aleksandersarkezi.com",
    ];
    var STEP = 0.26;
    var total = steps.length * STEP + 0.15;
    var tl;

    var finished = false;
    function finish() {
      if (finished) return;
      finished = true;
      if (tl) tl.kill();
      count.textContent = "100";
      gsap.timeline({
        onComplete: function () {
          endBoot();
          boot.removeAttribute("style");
        },
      })
        .to(".boot-inner", { opacity: 0, duration: 0.25 })
        .to(".boot-top", { yPercent: -100, duration: 0.9, ease: "expo.inOut" }, 0.1)
        .to(".boot-bottom", { yPercent: 100, duration: 0.9, ease: "expo.inOut" }, 0.1);
      gsap.delayedCall(0.45, done);
    }

    if (lenis) lenis.stop();
    var n = { v: 0 };
    tl = gsap.timeline({ onComplete: finish });
    tl.to(n, {
      v: 100,
      duration: total,
      ease: "power2.inOut",
      onUpdate: function () {
        count.textContent = String(Math.round(n.v)).padStart(3, "0");
      },
    }, 0);
    steps.forEach(function (text, i) {
      tl.call(function () {
        var li = document.createElement("li");
        li.textContent = text;
        log.appendChild(li);
      }, null, i * STEP);
    });

    boot.addEventListener("click", finish);
    window.addEventListener("keydown", finish, { once: true });
  }

  function start() {
    if (lenis) lenis.start();
    playIntro();
  }

  var fontsReady = document.fonts ? document.fonts.ready : Promise.resolve();
  fontsReady.then(function () {
    // Re-fit once Archivo is really there; the first fit may have measured a
    // fallback font.
    fitName();
    fitFooter();
    ScrollTrigger.refresh();
    if (root.classList.contains("booting")) bootSequence(start);
    else start();
  });

  // ---- statement: words light up as you read --------------------------

  document.querySelectorAll(".reveal-words").forEach(function (p) {
    var words = split(p, "words");
    gsap.fromTo(words, { opacity: 0.12 }, {
      opacity: 1,
      ease: "none",
      stagger: 0.1,
      scrollTrigger: { trigger: p, start: "top 80%", end: "bottom 45%", scrub: true },
    });
  });

  // ---- section titles open up as they arrive ---------------------------

  document.querySelectorAll(".big").forEach(function (h) {
    var letters = split(h, "letters");
    var tl = gsap.timeline({
      scrollTrigger: { trigger: h, start: "top 95%", end: "top 50%", scrub: 0.7 },
    });
    letters.forEach(function (el, i) {
      var o = { w: MIN_W };
      wdth(el, MIN_W);
      tl.to(o, {
        w: 100,
        duration: 1,
        ease: "power3.out",
        onUpdate: function () { wdth(el, o.w); },
      }, i * 0.05);
    });
    tl.from(letters, { yPercent: 60, opacity: 0, duration: 0.7, stagger: 0.05, ease: "power3.out" }, 0);
  });

  // ---- marquee: runs with the scroll ----------------------------------

  var track = document.querySelector(".marquee-track");
  if (track) {
    Array.from(track.children).forEach(function (child) {
      track.appendChild(child.cloneNode(true));
    });
    var loop = gsap.to(track, { xPercent: -50, duration: 36, ease: "none", repeat: -1 });
    var skew = gsap.quickTo(track, "skewX", { duration: 0.5, ease: "power3.out" });
    var settle;
    if (lenis) {
      lenis.on("scroll", function (l) {
        var dir = l.direction < 0 ? -1 : 1;
        var boost = 1 + Math.min(Math.abs(l.velocity) / 5, 7);
        gsap.to(loop, { timeScale: dir * boost, duration: 0.25, overwrite: true });
        gsap.to(loop, { timeScale: dir, duration: 1.4, delay: 0.25 });
        skew(Math.max(-10, Math.min(10, -l.velocity * 0.4)));
        clearTimeout(settle);
        settle = setTimeout(function () { skew(0); }, 120);
      });
    }
  }

  // ---- projects: each card sinks back as the next one lands -----------

  var mm = gsap.matchMedia();
  mm.add("(min-width: 52.01rem)", function () {
    var cards = gsap.utils.toArray(".card");
    // A card taller than the screen sticks higher up, so its bottom edge is
    // still reachable before the next card covers it.
    var setTops = function () {
      cards.forEach(function (card) {
        card.style.top = Math.min(72, window.innerHeight - card.offsetHeight - 16) + "px";
      });
    };
    setTops();
    ScrollTrigger.addEventListener("refreshInit", setTops);
    cards.forEach(function (card, i) {
      var next = cards[i + 1];
      if (!next) return;
      gsap.to(card, {
        scale: 0.9,
        opacity: 0.35,
        ease: "none",
        scrollTrigger: { trigger: next, start: "top bottom", end: "top 4.5rem", scrub: true },
      });
    });
    return function () {
      ScrollTrigger.removeEventListener("refreshInit", setTops);
      cards.forEach(function (card) { card.style.top = ""; });
    };
  });

  var shot = document.querySelector(".shot img");
  if (shot) {
    gsap.to(shot, {
      yPercent: -12,
      ease: "none",
      scrollTrigger: { trigger: ".shot", start: "top bottom", end: "bottom top", scrub: true },
    });
  }

  // ---- infrastructure: a light runs through each path -------------------

  var flows = document.querySelector(".flows");
  var packet = document.querySelector(".packet");
  if (flows && packet) {
    var boxes = gsap.utils.toArray(".flow li");
    gsap.from(boxes, {
      opacity: 0,
      y: 18,
      duration: 0.7,
      ease: "power3.out",
      stagger: 0.06,
      scrollTrigger: { trigger: flows, start: "top 80%", once: true },
    });

    // Each path, as lists of boxes: Ship, Serve, and Watch's two halves.
    var rows = gsap.utils.toArray(".flow").map(function (ol) {
      return Array.prototype.slice.call(ol.children);
    });
    var paths = [rows[0], rows[1], rows[2].slice(0, 2), rows[2].slice(2, 4)];

    var centre = function (el) {
      var f = flows.getBoundingClientRect();
      var r = el.getBoundingClientRect();
      return { x: r.left - f.left + r.width / 2, y: r.top - f.top + r.height / 2 };
    };

    var trace = null;
    var build = function () {
      if (trace) trace.kill();
      boxes.forEach(function (b) { b.classList.remove("lit"); });
      trace = gsap.timeline({ repeat: -1, repeatDelay: 0.8, paused: true });
      paths.forEach(function (path) {
        var first = centre(path[0]);
        trace.set(packet, { x: first.x, y: first.y });
        trace.to(packet, { opacity: 1, scale: 1, duration: 0.25, startAt: { scale: 0 } });
        trace.call(function () { path[0].classList.add("lit"); });
        path.slice(1).forEach(function (box) {
          var c = centre(box);
          trace.to(packet, { x: c.x, y: c.y, duration: 0.6, ease: "power2.inOut" }, "+=0.25");
          trace.call(function () { box.classList.add("lit"); });
        });
        trace.to(packet, { opacity: 0, scale: 0.4, duration: 0.3 }, "+=0.35");
      });
      trace.call(function () {
        boxes.forEach(function (b) { b.classList.remove("lit"); });
      }, null, "+=0.6");
    };
    build();
    ScrollTrigger.create({
      trigger: flows,
      start: "top 75%",
      end: "bottom top",
      onToggle: function (self) {
        if (self.isActive) trace.play(); else trace.pause();
      },
      onRefresh: function (self) {
        // Box positions change with the layout, so the path is measured again.
        build();
        if (self.isActive) trace.play();
      },
    });
  }

  // ---- footer: uncovered from under the page ---------------------------

  var footName = document.querySelector(".foot-name");
  if (footName) {
    var footLetters = split(footName, "letters");
    gsap.from(footLetters, {
      yPercent: 70,
      ease: "none",
      stagger: 0.04,
      scrollTrigger: { trigger: "main", start: "bottom bottom", end: "bottom 30%", scrub: true },
    });
  }

  var clock = document.querySelector(".clock");
  if (clock && window.Intl) {
    var fmt = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Ljubljana",
      hour: "2-digit",
      minute: "2-digit",
    });
    var tick = function () { clock.textContent = fmt.format(new Date()) + " local time"; };
    tick();
    setInterval(tick, 20000);
  }

  // ---- links that scramble when you point at them ----------------------

  var GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/<>_";
  document.querySelectorAll("[data-scramble]").forEach(function (a) {
    var text = a.textContent;
    var running = null;
    a.addEventListener("pointerenter", function () {
      if (running) return;
      var frame = 0;
      running = setInterval(function () {
        frame++;
        var out = "";
        for (var i = 0; i < text.length; i++) {
          out += i < frame / 2 || text[i] === " "
            ? text[i]
            : GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
        }
        a.textContent = out;
        if (frame / 2 >= text.length) {
          clearInterval(running);
          running = null;
          a.textContent = text;
        }
      }, 28);
    });
  });

  // ---- cursor ----------------------------------------------------------

  var cursor = document.querySelector(".cursor");
  var cursorLabel = document.querySelector(".cursor-label");
  if (finePointer && cursor) {
    var cx = gsap.quickTo(cursor, "x", { duration: 0.4, ease: "power3.out" });
    var cy = gsap.quickTo(cursor, "y", { duration: 0.4, ease: "power3.out" });
    window.addEventListener("pointermove", function (e) {
      cursor.classList.add("on");
      cx(e.clientX);
      cy(e.clientY);
    });
    document.addEventListener("pointerleave", function () {
      cursor.classList.remove("on");
    });
    document.addEventListener("pointerover", function (e) {
      var labelled = e.target.closest("[data-cursor]");
      cursor.classList.toggle("label", !!labelled);
      cursor.classList.toggle("big", !labelled && !!e.target.closest("a"));
      if (labelled) cursorLabel.textContent = labelled.getAttribute("data-cursor");
    });
  }

  // The email address leans toward the pointer a little.
  var mail = document.querySelector(".mail");
  if (finePointer && mail) {
    var mx = gsap.quickTo(mail, "x", { duration: 0.6, ease: "power3.out" });
    var my = gsap.quickTo(mail, "y", { duration: 0.6, ease: "power3.out" });
    mail.addEventListener("pointermove", function (e) {
      var r = mail.getBoundingClientRect();
      mx((e.clientX - (r.left + r.width / 2)) * 0.05);
      my((e.clientY - (r.top + r.height / 2)) * 0.25);
    });
    mail.addEventListener("pointerleave", function () {
      mx(0);
      my(0);
    });
  }
})();
