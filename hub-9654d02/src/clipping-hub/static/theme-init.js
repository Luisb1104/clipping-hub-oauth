/* Runs before first paint: apply the remembered theme (localStorage), else the device setting. */
(function () {
  var t = null;
  try { t = localStorage.getItem("clippinghub.theme"); } catch (e) {}
  if (t !== "light" && t !== "dark") t = (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", t);
})();
