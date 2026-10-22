/* HYPOLAB Ideas: copy buttons everywhere; in the draft editor, live checks (debounced, no simulation).
   1.12.0: inside the Android app, window.HypolabAndroid adds Share and Paste buttons and does the copying. */
(function () {
  var A = window.HypolabAndroid || null;
  /* 1.13.0: on a small screen the bottom bar scrolls; keep the open page's tab in view */
  var on = document.querySelector(".rail a.on");
  if (on && window.matchMedia("(max-width: 760px)").matches && on.scrollIntoView) {
    try { on.scrollIntoView({ inline: "center", block: "nearest" }); } catch (e) {}
  }
  function flash(b, word) { var t = b.textContent; b.textContent = word; setTimeout(function () { b.textContent = t; }, 1400); }

  if (A) {
    document.querySelectorAll("button.copy").forEach(function (b) {
      var s = document.createElement("button");
      s.type = "button"; s.className = "btn small share"; s.textContent = "Share";
      s.setAttribute("data-copy", b.getAttribute("data-copy"));
      s.title = "Send this text to another app (for example the Claude app)";
      b.insertAdjacentElement("afterend", s);
    });
    document.querySelectorAll("textarea[data-paste]").forEach(function (ta) {
      var p = document.createElement("button");
      p.type = "button"; p.className = "btn small pastebtn"; p.textContent = "Paste from clipboard";
      p.addEventListener("click", function (e) {
        e.preventDefault();
        var t = A.paste() || "";
        if (!t) { flash(p, "Clipboard is empty"); return; }
        ta.value = t; ta.dispatchEvent(new Event("input", { bubbles: true })); ta.focus();
        flash(p, "Pasted");
      });
      ta.insertAdjacentElement("afterend", p);
    });
  }

  document.addEventListener("click", function (e) {
    var sh = e.target.closest("button.share");
    if (sh && A) {
      e.preventDefault();
      var node = document.querySelector(sh.getAttribute("data-copy"));
      if (node) A.share(node.textContent, document.title);
      return;
    }
    var b = e.target.closest("button.copy");
    if (!b) return;
    e.preventDefault();
    var src = document.querySelector(b.getAttribute("data-copy"));
    if (!src) return;
    var text = src.textContent;
    var done = function () { flash(b, "Copied"); };
    if (A) { A.copy(text); done(); return; }
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
