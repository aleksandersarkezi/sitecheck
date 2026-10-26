// Loaded in <head> before first paint, so the motion styles never flash in.
// The boot screen plays once per browser tab session and never with reduced motion.
(function () {
  var root = document.documentElement;
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  root.classList.add(reduced ? "js-static" : "js");
  if (reduced) return;

  var seen = false;
  try {
    seen = window.sessionStorage.getItem("booted") === "1";
    window.sessionStorage.setItem("booted", "1");
  } catch (e) {
    seen = false;
  }
  if (!seen) root.classList.add("booting");
})();
