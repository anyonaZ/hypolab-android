/* HYPOLAB Ideas: copy buttons everywhere; in the draft editor, live checks (debounced, no simulation). */
(function () {
  document.addEventListener("click", function (e) {
    var b = e.target.closest("button.copy");
    if (!b) return;
    e.preventDefault();
    var src = document.querySelector(b.getAttribute("data-copy"));
    if (!src) return;
    var text = src.textContent;
    var done = function () { var t = b.textContent; b.textContent = "Copied"; setTimeout(function () { b.textContent = t; }, 1400); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () { fallback(text); done(); });
    } else { fallback(text); done(); }
  });
  function fallback(text) {
    var ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (err) {}
    document.body.removeChild(ta);
  }

  var form = document.getElementById("card");
  if (!form) return;
  var timer = null, seq = 0;
  function check() {
    var mine = ++seq;
    fetch("/api/check", { method: "POST", body: new FormData(form) })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (mine !== seq) return;                 /* an older answer arriving late */
        document.getElementById("checks").innerHTML = d.html;
        var y = document.getElementById("yaml"); if (y) y.textContent = d.yaml;
        var c = document.getElementById("critic"); if (c) c.textContent = d.critic;
        var a = document.getElementById("approve"); if (a) a.disabled = !d.ok;
      })
      .catch(function () {});
  }
  function later() { clearTimeout(timer); timer = setTimeout(check, 450); }
  form.addEventListener("input", later);
  form.addEventListener("change", later);
  var region = document.querySelector("select[name=region][form=card]");
  if (region) region.addEventListener("change", check);

  document.querySelectorAll("button[data-action]").forEach(function (b) {
    b.addEventListener("click", function () {
      form.elements["action"].value = b.getAttribute("data-action");
      if (b.getAttribute("data-action") === "bin") {
        var r = document.getElementById("binreason");
        form.elements["reason"].value = r ? r.value : "";
      }
    });
  });
})();
