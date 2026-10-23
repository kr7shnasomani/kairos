// Applies the saved theme, contrast and devtools state before first paint, so the page never
// flashes the wrong palette. Loaded as a blocking <script src> from the root layout: a file rather
// than inline HTML, so no dangerouslySetInnerHTML is needed.
(function () {
  try {
    var root = document.documentElement;
    var t = localStorage.getItem("kairos-theme");
    if (t === "dark" || t === "light") root.setAttribute("data-theme", t);
    if (localStorage.getItem("kairos-contrast") === "high") root.setAttribute("data-contrast", "high");
    if (localStorage.getItem("kairos-devtools") === "show") root.setAttribute("data-devtools", "show");
  } catch (e) {
    // Storage disabled: keep the server-rendered light theme.
  }
})();
