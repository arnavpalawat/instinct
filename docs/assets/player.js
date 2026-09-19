/**
 * Instinct — Audio Player Enhancement
 * -------------------------------------
 * Speed control, smooth section scrolling, and playback position persistence.
 * This script supplements the inline JS in page.html and can be loaded
 * externally when pages are served from the docs/ directory.
 */
(function () {
  "use strict";

  var audio = document.getElementById("briefing-audio");
  if (!audio) return;

  var STORAGE_KEY = "instinct-audio-" + location.pathname;

  // ---- Restore saved playback position ----
  var savedTime = sessionStorage.getItem(STORAGE_KEY);
  if (savedTime) {
    audio.addEventListener("loadedmetadata", function restoreOnce() {
      audio.currentTime = parseFloat(savedTime) || 0;
      audio.removeEventListener("loadedmetadata", restoreOnce);
    });
  }

  // ---- Persist playback position ----
  audio.addEventListener("timeupdate", function () {
    sessionStorage.setItem(STORAGE_KEY, audio.currentTime.toFixed(2));
  });

  audio.addEventListener("ended", function () {
    sessionStorage.removeItem(STORAGE_KEY);
  });

  // ---- Speed control ----
  var speedBtns = document.querySelectorAll(".speed-btn");
  speedBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var rate = parseFloat(this.getAttribute("data-speed"));
      if (!isNaN(rate) && rate > 0) {
        audio.playbackRate = rate;
        speedBtns.forEach(function (b) { b.classList.remove("active"); });
        this.classList.add("active");
      }
    });
  });

  // ---- Smooth scroll for nav pills ----
  document.querySelectorAll(".nav-pill").forEach(function (pill) {
    pill.addEventListener("click", function (e) {
      var href = this.getAttribute("href");
      if (href && href.charAt(0) === "#") {
        e.preventDefault();
        var target = document.querySelector(href);
        if (target) {
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    });
  });
})();
