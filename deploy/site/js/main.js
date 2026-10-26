// Motion for aleksandersarkezi.com.
//
// The idea: Archivo's width axis ("wdth", 62 to 125) is the animation. The name
// boots up from squeezed to normal, widens around the pointer, and gets packed
// shut as you scroll away. Section titles open up the same way as they arrive.
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

  function clamp(v, lo, hi) {
    return Math.min(hi, Math.max(lo, v));
  }

  function setWidth(el, w) {
    el.style.fontVariationSettings = '"wdth" ' + clamp(w, MIN_W, MAX_W).toFixed(1);
  }

  // Wraps every letter in a span (words stay unbreakable) and keeps the
  // original text readable for screen readers.
  function splitLetters(el) {
    var text = el.textContent.replace(/\s+/g, " ").trim();
    el.setAttribute("aria-label", text);
    var letters = [];
    var lines = el.querySelectorAll(".line");
    var targets = lines.length ? Array.prototype.slice.call(lines) : [el];

    targets.forEach(function (target) {
      var words = target.textContent.replace(/\s+/g, " ").trim().split(" ");
      target.textContent = "";
      words.forEach(function (word, i) {
        var w = document.createElement("span");
        w.className = "word";
        w.setAttribute("aria-hidden", "true");
        w.style.display = "inline-block";
        w.style.whiteSpace = "nowrap";
        Array.from(word).forEach(function (char) {
          var c = document.createElement("span");
          c.className = "ch";
          c.textContent = char;
          w.appendChild(c);
          letters.push(c);
        });
        target.appendChild(w);
        if (i < words.length - 1) target.appendChild(document.createTextNode(" "));
      });
    });
    return letters;
  }

  // ---- smooth scrolling ------------------------------------------------

  var lenis = null;
  if (window.Lenis) {
    lenis = new window.Lenis({ autoRaf: false, lerp: 0.1 });
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
    lenis.scrollTo(target, { offset: -40 });
    target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
  });

  // ---- hero name -------------------------------------------------------

  var name = document.querySelector(".name");
  var heroLetters = splitLetters(name);
  // Each letter has its own width "w" (intro and pointer) and the whole name
  // shares a squeeze factor "k" (scroll). The rendered width is w * k.
  var state = heroLetters.map(function () {
    return { w: MIN_W, target: 100, intro: 0 };
  });
  var squeeze = { k: 1 };
  var pointer = { x: -9999, y: -9999, active: false };

  function renderHero() {
    var rects = pointer.active
      ? heroLetters.map(function (el) { return el.getBoundingClientRect(); })
      : null;

    heroLetters.forEach(function (el, i) {
      var s = state[i];
      var goal = 100;
      if (rects) {
        var r = rects[i];
        var dx = pointer.x - (r.left + r.width / 2);
        var dy = pointer.y - (r.top + r.height / 2);
        var dist = Math.sqrt(dx * dx + dy * dy);
        var reach = Math.max(window.innerWidth * 0.16, 140);
        goal = 100 + 25 * Math.max(0, 1 - dist / reach);
      }
      // During the intro the width is driven by the timeline, not the pointer.
      if (s.intro < 1) {
        s.w = MIN_W + (100 - MIN_W) * s.intro;
      } else {
        s.w += (goal - s.w) * 0.14;
      }
      setWidth(el, s.w * squeeze.k);
    });
  }

  var heroVisible = true;
  ScrollTrigger.create({
    trigger: ".hero",
    start: "top bottom",
    end: "bottom top",
    onToggle: function (self) {
      heroVisible = self.isActive;
    },
  });
  gsap.ticker.add(function () {
    if (heroVisible) renderHero();
  });

  if (finePointer) {
    document.querySelector(".hero").addEventListener("pointermove", function (e) {
      pointer.x = e.clientX;
      pointer.y = e.clientY;
      pointer.active = true;
    });
    document.querySelector(".hero").addEventListener("pointerleave", function () {
      pointer.active = false;
    });
  }

  // Scrolling away packs the name shut and lifts it slightly.
  gsap.to(squeeze, {
    k: MIN_W / 100,
    ease: "none",
    scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true },
  });
  gsap.to(name, {
    yPercent: -18,
    ease: "none",
    scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true },
  });

  function playIntro() {
    name.style.opacity = "1";
    gsap.set(heroLetters, { opacity: 0, y: "0.25em" });
    var tl = gsap.timeline();
    tl.to(heroLetters, {
      opacity: 1,
      y: 0,
      duration: 0.9,
      ease: "power4.out",
      stagger: 0.035,
    });
    state.forEach(function (s, i) {
      tl.to(s, { intro: 1, duration: 1.1, ease: "power3.inOut" }, i * 0.035);
    });
    tl.from(".hero-foot > *", { opacity: 0, y: 16, duration: 0.8, ease: "power3.out", stagger: 0.1 }, 0.5);
    tl.from(".top", { opacity: 0, duration: 0.6 }, 0.7);
  }

  // ---- boot screen -----------------------------------------------------

  function bootSequence(done) {
    var boot = document.querySelector(".boot");
    var log = boot.querySelector(".boot-log");
    var bar = boot.querySelector(".boot-bar span");
    boot.style.animation = "none";

    var stamp = document.querySelector(".foot a[href*='/commit/']");
    var tag = stamp ? "sha-" + stamp.textContent.trim().slice(0, 7) : "latest";
    var lines = [
      "git push origin main",
      "ci: lint, tests, docker smoke test",
      "image: ghcr.io/aleksandersarkezi/sitecheck:" + tag,
      "deploy: health check passed",
      "caddy: serving aleksandersarkezi.com over https",
    ];

    var finished = false;
    function finish() {
      if (finished) return;
      finished = true;
      tl.kill();
      gsap.to(boot, {
        yPercent: -100,
        duration: 0.8,
        ease: "power4.inOut",
        onComplete: function () {
          endBoot();
          boot.removeAttribute("style");
        },
      });
      done();
    }

    if (lenis) lenis.stop();
    var tl = gsap.timeline({ onComplete: finish });
    lines.forEach(function (text, i) {
      tl.call(function () {
        var li = document.createElement("li");
        li.textContent = text;
        log.appendChild(li);
      }, null, i * 0.24);
    });
    tl.to(bar, { width: "100%", duration: lines.length * 0.24 + 0.2, ease: "power1.inOut" }, 0);

    boot.addEventListener("click", finish);
    window.addEventListener("keydown", finish, { once: true });
  }

  function start() {
    if (lenis) lenis.start();
    playIntro();
  }

  if (root.classList.contains("booting")) {
    // Wait for the fonts so the name doesn't jump when Archivo arrives.
    (document.fonts ? document.fonts.ready : Promise.resolve()).then(function () {
      bootSequence(function () {
        gsap.delayedCall(0.35, start);
      });
    });
  } else {
    start();
  }

  // ---- section titles open up as they arrive ---------------------------

  document.querySelectorAll(".big").forEach(function (h) {
    var letters = splitLetters(h);
    var widths = letters.map(function () { return { w: MIN_W }; });
    var tl = gsap.timeline({
      scrollTrigger: { trigger: h, start: "top 92%", end: "top 45%", scrub: 0.6 },
    });
    widths.forEach(function (o, i) {
      tl.to(o, {
        w: 100,
        ease: "power2.out",
        duration: 1,
        onUpdate: function () { setWidth(letters[i], o.w); },
      }, i * 0.06);
    });
    tl.from(letters, { opacity: 0.15, duration: 0.6, stagger: 0.06 }, 0);
    letters.forEach(function (el) { setWidth(el, MIN_W); });
  });

  // ---- marquee ---------------------------------------------------------

  var track = document.querySelector(".marquee-track");
  if (track) {
    Array.from(track.children).forEach(function (child) {
      track.appendChild(child.cloneNode(true));
    });
    var loop = gsap.to(track, { xPercent: -50, duration: 40, ease: "none", repeat: -1 });
    // Scrolling speeds it up and scrolling back up runs it the other way.
    var speed = { v: 1 };
    if (lenis) {
      lenis.on("scroll", function (l) {
        var dir = l.direction < 0 ? -1 : 1;
        gsap.to(speed, {
          v: dir * (1 + Math.min(Math.abs(l.velocity) / 6, 6)),
          duration: 0.3,
          overwrite: true,
          onUpdate: function () { loop.timeScale(speed.v); },
        });
        gsap.to(speed, { v: dir, duration: 1.2, delay: 0.3 });
      });
    }
  }

  // ---- projects --------------------------------------------------------

  var frame = document.querySelector(".shot-frame");
  if (frame) {
    gsap.fromTo(frame,
      { clipPath: "inset(100% 0% 0% 0%)" },
      {
        clipPath: "inset(0% 0% 0% 0%)",
        ease: "none",
        scrollTrigger: { trigger: frame, start: "top 90%", end: "top 35%", scrub: 0.6 },
      });
    gsap.fromTo(frame.querySelector("img"),
      { yPercent: 0 },
      {
        yPercent: -10,
        ease: "none",
        scrollTrigger: { trigger: frame, start: "top bottom", end: "bottom top", scrub: true },
      });
  }

  // ---- infrastructure: the page goes dark, then the paths light up -----

  ScrollTrigger.create({
    trigger: "#infra",
    start: "top 55%",
    end: "bottom 45%",
    toggleClass: { targets: root, className: "is-dark" },
  });

  document.querySelectorAll(".flow").forEach(function (flow) {
    gsap.from(flow.children, {
      opacity: 0.1,
      x: -14,
      ease: "power2.out",
      stagger: 0.25,
      scrollTrigger: { trigger: flow, start: "top 88%", end: "top 55%", scrub: 0.6 },
    });
  });

  // ---- cursor ----------------------------------------------------------

  var cursor = document.querySelector(".cursor");
  if (finePointer && cursor) {
    var cx = gsap.quickTo(cursor, "x", { duration: 0.35, ease: "power3.out" });
    var cy = gsap.quickTo(cursor, "y", { duration: 0.35, ease: "power3.out" });
    window.addEventListener("pointermove", function (e) {
      cursor.classList.add("on");
      cx(e.clientX);
      cy(e.clientY);
    });
    document.addEventListener("pointerleave", function () {
      cursor.classList.remove("on");
    });
    document.addEventListener("pointerover", function (e) {
      cursor.classList.toggle("big", !!e.target.closest("a, .project-name"));
    });
  }

  // The contact address leans toward the pointer a little.
  var mail = document.querySelector(".mail");
  if (finePointer && mail) {
    var mx = gsap.quickTo(mail, "x", { duration: 0.6, ease: "power3.out" });
    var my = gsap.quickTo(mail, "y", { duration: 0.6, ease: "power3.out" });
    mail.addEventListener("pointermove", function (e) {
      var r = mail.getBoundingClientRect();
      mx((e.clientX - (r.left + r.width / 2)) * 0.06);
      my((e.clientY - (r.top + r.height / 2)) * 0.2);
    });
    mail.addEventListener("pointerleave", function () {
      mx(0);
      my(0);
    });
  }

  // Fonts can change line heights after load; re-measure the triggers.
  if (document.fonts) document.fonts.ready.then(function () { ScrollTrigger.refresh(); });
})();
