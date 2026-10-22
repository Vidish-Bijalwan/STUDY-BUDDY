/* kinetic.js — Study-Buddy V2 motion layer.
 * Progressive enhancement ONLY: content is fully visible without JS.
 * - .sb-mask / .sb-reveal gain .in via IntersectionObserver (once).
 * - Decorative outline words drift subtly on scroll (rAF-throttled).
 * - Everything is disabled under prefers-reduced-motion.
 * No layout, content, or form behaviour depends on this file.
 */
(function () {
  'use strict';
  var reduce = window.matchMedia
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false;
  if (reduce) {
    document.querySelectorAll('.sb-mask, .sb-reveal').forEach(function (el) {
      el.classList.add('in');
    });
    return;
  }
  var targets = document.querySelectorAll('.sb-mask, .sb-reveal');
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
      });
    }, { threshold: 0.15 });
    targets.forEach(function (el) { io.observe(el); });
  } else {
    targets.forEach(function (el) { el.classList.add('in'); });
  }

  /* Subtle scroll drift for decorative outline words only. */
  var driftEls = document.querySelectorAll('[data-sb-drift]');
  if (!driftEls.length || !('requestAnimationFrame' in window)) return;
  var ticking = false;
  function update() {
    ticking = false;
    var y = window.scrollY || 0;
    driftEls.forEach(function (el) {
      var speed = parseFloat(el.getAttribute('data-sb-drift')) || 0.03;
      el.style.transform = 'translateX(' + (y * speed).toFixed(1) + 'px)';
    });
  }
  window.addEventListener('scroll', function () {
    if (!ticking) { ticking = true; requestAnimationFrame(update); }
  }, { passive: true });
  update();
})();
