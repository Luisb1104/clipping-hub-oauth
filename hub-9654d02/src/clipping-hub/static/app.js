/* Clipping Hub shell. Same-origin /api/* (localhost or Tailscale :8445→8505). Approve/reject persist server-side with X-Hub-Token. Never posts to platforms. */
(function () {
  "use strict";
  var PANES = ["home", "queue", "approvals", "channels", "revenue", "trends"];
  var PATHS = { "/": "home", "/home": "home", "/queue": "queue", "/approvals": "approvals", "/channels": "channels", "/revenue": "revenue", "/trends": "trends" };
  var state = { theme: null, clips: [], checklist: [] };
  var approvals = { items: [], pending: 0 };
  var shorts = { items: [], empty: true, reason: "" };
  var revenue = { empty: true, connected: false, total_usd: 0 };
  var credits = { empty: true };
  var campaigns = { empty: true, campaigns: [] };
  var channels = { empty: true, channels: [] }, scriptQueue = { empty: true, items: [] };
  var events = { events: [] };
  var sheetOpen = false, notice = "", wide = window.matchMedia("(min-width:900px)");
  var filter = "pending", idx = 0;
  var changeFor = null;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  function paintTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    $$("[data-theme-set]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-theme-set") === t ? "true" : "false"); });
  }
  function currentTheme() { return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light"; }
  function setTheme(t) {
    paintTheme(t);
    try { localStorage.setItem("clippinghub.theme", t); } catch (e) {}
    post({ op: "theme", value: t });
  }

  function show(name, push) {
    if (PANES.indexOf(name) < 0) name = "home";
    $$(".pane").forEach(function (p) {
      var on = p.getAttribute("data-pane") === name;
      p.hidden = !on;
      p.classList.remove("m-tab");
      if (on) { void p.offsetWidth; p.classList.add("m-tab"); }
    });
    $$(".nav a").forEach(function (a) {
      if (a.getAttribute("data-go") === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    var path = name === "home" ? "/" : "/" + name;
    if (push && location.pathname !== path) history.pushState({ p: name }, "", path);
    document.title = (name === "home" ? "" : label(name) + " · ") + "Clipping Hub";
    if (name === "home") { renderCredits(); renderScriptQueue(); renderCampaigns(); }
    if (name === "queue") { renderQueue(); renderBatch(); }
    if (name === "approvals") renderApprovals();
    if (name === "channels") renderChannelsPane();
  }
  function label(n) {
    return { home: "Home", queue: "Clips", approvals: "Approvals", channels: "Channels", revenue: "Revenue", trends: "Trend Watcher" }[n];
  }

  function hubToken() { var m = document.querySelector('meta[name="hub-token"]'); return m ? m.getAttribute("content") || "" : ""; }
  function paintYtGrantChip(grants) {
    var el = document.getElementById("yt-grant-chip");
    if (!el) {
      var host = document.getElementById("appr-count");
      if (host && host.parentNode) {
        el = document.createElement("span");
        el.id = "yt-grant-chip";
        el.className = "chip dash";
        el.hidden = true;
        host.parentNode.insertBefore(el, host.nextSibling);
      }
    }
    // Production (testing_mode false): hide countdown chip entirely.
    if (!el || !grants || grants.testing_mode === false) { if (el) el.hidden = true; return; }
    var best = null;
    ["MAIN", "PAID", "GAMING"].forEach(function (ch) {
      var g = grants[ch];
      if (!g || !g.present || g.show_countdown === false) return;
      if (!best || (g.expires_in_s != null && (best.expires_in_s == null || g.expires_in_s < best.expires_in_s))) best = g;
    });
    if (!best) { el.hidden = true; return; }
    el.hidden = false;
    if (best.expired || best.needs_regrant) {
      el.className = "chip warn";
      el.textContent = "YouTube grant expired — re-grant";
    } else {
      el.className = "chip dash";
      el.textContent = "YouTube grant expires in " + (best.expires_in_days != null ? best.expires_in_days : "?") + "d";
    }
  }
  function startYtRegrant(channel) {
    var ch = String(channel || "").toUpperCase();
    if (ch !== "MAIN" && ch !== "PAID" && ch !== "GAMING") return Promise.resolve(false);   // unknown ?yt_regrant: never start a grant
    return fetch("/api/youtube-oauth/start", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Hub-Token": hubToken() },
      body: JSON.stringify({ channel: ch, approval_id: "regrant" }),
    }).then(function (r) { return r.json(); }).then(function (body) {
      if (body && body.ok && (body.oauth_url || body.auth_url)) {
        try {
          var u = new URL(body.oauth_url || body.auth_url, window.location.href);
          if (u.protocol === "https:" && u.hostname === "accounts.google.com") {
            window.location.href = u.href;
            return true;
          }
        } catch (e) {}
      }
      return false;
    }).catch(function () { return false; });
  }

  function get() {
    return Promise.all([
      fetch("/api/state", { cache: "no-store" }).then(function (r) { return r.json(); }).then(adopt).catch(function () {}),
      fetch("/api/approvals", { cache: "no-store" }).then(function (r) { return r.json(); }).then(adoptApprovals).catch(function () {}),
      fetch("/api/shorts", { cache: "no-store" }).then(function (r) { return r.json(); }).then(adoptShorts).catch(function () {}),
      fetch("/api/credits", { cache: "no-store" }).then(function (r) { return r.json(); }).then(adoptCredits).catch(function () {}),
      fetch("/api/script-queue", { cache: "no-store" }).then(function (r) { return r.json(); }).then(adoptScriptQueue).catch(function () {}),
      fetch("/api/campaigns", { cache: "no-store" }).then(function (r) { return r.json(); }).then(adoptCampaigns).catch(function () {}),
      fetch("/api/channels", { cache: "no-store" }).then(function (r) { return r.json(); }).then(adoptChannels).catch(function () {}),
      fetch("/api/revenue", { cache: "no-store" }).then(function (r) { return r.json(); }).then(adoptRevenue).catch(function () {}),
      fetch("/api/events", { cache: "no-store" }).then(function (r) { return r.json(); }).then(adoptEvents).catch(function () {})
    ]).then(function () { renderAll(); });
  }
  function post(body) {
    return fetch("/api/state", { method: "POST", headers: { "Content-Type": "application/json", "X-Hub-Token": hubToken() }, body: JSON.stringify(body) })
      .then(function (r) { if (!r.ok) throw new Error("bad"); return r.json(); })
      .then(function (s) { adopt(s); renderAll(); return true; })
      .catch(function () { var c = $("#q-count"); if (c) { c.textContent = "Not saved"; c.className = "chip bad"; } return false; });
  }
  function postApproval(body) {
    return fetch("/api/approvals", { method: "POST", headers: { "Content-Type": "application/json", "X-Hub-Token": hubToken() }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; }); });
  }
  function adopt(s) {
    state = { theme: s.theme || null, clips: s.clips || [], checklist: s.checklist || [], autopost_enabled: !!s.autopost_enabled, youtube_grants: s.youtube_grants || null, label_step_enabled: s.label_step_enabled === true, public_publish_enabled: s.public_publish_enabled === true };
    var stored = null; try { stored = localStorage.getItem("clippinghub.theme"); } catch (e) {}
    if (!stored && state.theme) paintTheme(state.theme);
    paintYtGrantChip(state.youtube_grants);
  }
  function adoptApprovals(s) {
    approvals = { items: (s && s.items) || [], pending: (s && s.pending) || 0 };
  }
  function adoptEvents(s) {
    events = { events: (s && s.events) || [] };
    maybeNotifyNew();
  }

  var STATUS_TXT = { pending: "Waiting", approved: "Approved here only", edit: "Marked for edit", skipped: "Skipped" };
  var EMPTY_TXT = {
    pending: ["All caught up", "Nothing is waiting for your OK."],
    approved: ["Nothing approved yet", "Approved clips show up here. Nothing has been posted."],
    edit: ["Nothing marked for edit", "Clips you want changed show up here."],
    skipped: ["Nothing skipped", "Clips you skip show up here."]
  };
  function counts() {
    var n = { pending: 0, approved: 0, edit: 0, skipped: 0 };
    state.clips.forEach(function (c) { n[c.status]++; });
    return n;
  }
  function renderAll() {
    updateShellTruth(); renderHome(); renderQueue(); renderApprovals(); renderBadge(); }
  function renderHome() {
    var n = counts();
    $("#sum-pending").textContent = String(n.pending);
    var sa = $("#sum-approvals"); if (sa) sa.textContent = String(approvals.pending || 0);
  }
  function renderBadge() {
    var b = $("#nav-appr-badge"), n = approvals.pending || 0;
    if (!b) return;
    b.hidden = n < 1;
    b.textContent = n > 99 ? "99+" : String(n);
  }

  function renderQueue() {
    var n = counts(), total = state.clips.length;
    ["pending", "approved", "edit", "skipped"].forEach(function (k) { $("#n-" + k).textContent = String(n[k]); });
    var qc = $("#q-count"); if (!qc) return;
    qc.className = "chip dash"; qc.textContent = total + (total === 1 ? " clip" : " clips");
    $$("[data-qf]").forEach(function (b) { var on = b.getAttribute("data-qf") === filter; b.classList.toggle("on", on); b.setAttribute("aria-selected", on ? "true" : "false"); });
    var list = state.clips.filter(function (c) { return c.status === filter; });
    if (idx >= list.length) idx = Math.max(0, list.length - 1);
    var card = $("#q-card"), empty = $("#q-empty");
    card.hidden = !list.length; empty.hidden = !!list.length;
    if (!list.length) sheetOpen = false;
    buildChecklist();
    if (!list.length) {
      $("#q-empty-h").textContent = total ? EMPTY_TXT[filter][0] : "No clips yet";
      $("#q-empty-p").textContent = total ? EMPTY_TXT[filter][1] : "When clips are ready, they wait here for your OK.";
    } else {
      var c = list[idx];
      card.setAttribute("data-id", c.id);
      $("#q-title").textContent = c.title;
      $("#q-label").textContent = c.sample ? "Sample clip" : "Clip";
      $("#q-plat").textContent = (c.platform || "Channel") + " · planned";
      $("#q-sample").hidden = !c.sample;
      $("#q-status").textContent = STATUS_TXT[c.status];
      var done = c.checks.length, total_items = state.checklist.length, ok = total_items > 0 && done === total_items;
      $("#q-actions").hidden = c.status !== "pending";
      $("#q-approve").disabled = !ok;
      var hint = $("#q-hint"); hint.hidden = ok || c.status !== "pending";
      $("#q-hint-t").textContent = (notice ? notice + " " : "") + "Finish the checklist first";
      $("#q-undo").hidden = c.status === "pending";
      $("#q-checkprog").textContent = "Checklist · " + done + " of " + total_items;
      $("#q-check-count").textContent = done + " of " + total_items; $("#q-check-count").className = "chip " + (ok ? "ok" : "dash");
      $$("[data-item]").forEach(function (i) { i.checked = c.checks.indexOf(i.getAttribute("data-item")) >= 0; });
      $("#q-pos").textContent = (idx + 1) + " of " + list.length;
      $("#q-prev").disabled = idx === 0; $("#q-next").disabled = idx >= list.length - 1;
      $("#q-pager").classList.toggle("one", list.length < 2);
    }
    $("#q-add").hidden = total >= 5;
    $("#q-clear").hidden = !state.clips.some(function (c) { return c.sample; });
    placeCheck();
  }

  function buildChecklist() {
    var ul = $("#q-checklist"), want = state.checklist.map(function (x) { return x.id; }).join("|");
    if (ul.getAttribute("data-built") === want) return;
    ul.setAttribute("data-built", want); ul.textContent = "";
    state.checklist.forEach(function (x) {
      var li = document.createElement("li"), lab = document.createElement("label"), inp = document.createElement("input"), box = document.createElement("span"), txt = document.createElement("span");
      lab.className = "chk m-press"; inp.type = "checkbox"; inp.setAttribute("data-item", x.id);
      box.className = "box"; box.setAttribute("aria-hidden", "true"); box.innerHTML = '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
      txt.className = "txt"; txt.textContent = x.text;
      lab.appendChild(inp); lab.appendChild(box); lab.appendChild(txt); li.appendChild(lab); ul.appendChild(li);
    });
  }
  function placeCheck() {
    var box = $("#q-check"), want = wide.matches ? $("#q-check-slot") : $('[data-pane="queue"]');
    if (!box || !want) return;
    if (box.parentNode !== want) want.appendChild(box);
    var open = sheetOpen && !wide.matches && !$("#q-card").hidden;
    box.classList.toggle("open", open); $("#q-scrim").hidden = !open;
    $('[data-pane="queue"]').classList.toggle("sheet-open", open); $(".foot-actions").inert = open;
    $("#q-checkopen").setAttribute("aria-expanded", open ? "true" : "false");
    if (open) { box.classList.remove("m-tab"); void box.offsetWidth; box.classList.add("m-tab"); }
  }
  function curClip() { var id = $("#q-card").getAttribute("data-id"); return state.clips.filter(function (c) { return c.id === id; })[0]; }
  function tick(item, value) {
    var c = curClip(); if (!c) return;
    var was = c.status;
    post({ op: "check", id: c.id, item: item, value: value }).then(function (ok) {
      if (!ok) return renderQueue();
      var now = state.clips.filter(function (x) { return x.id === c.id; })[0];
      if (now && was === "approved" && now.status === "pending") {
        filter = "pending"; idx = state.clips.filter(function (x) { return x.status === "pending"; }).map(function (x) { return x.id; }).indexOf(c.id);
        notice = "Moved back to Waiting."; renderQueue();
      }
    });
  }
  function act(action) {
    var cur = curClip(); notice = "";
    if (action === "approve" && !(cur && state.checklist.length && cur.checks.length === state.checklist.length)) return renderQueue();
    var id = $("#q-card").getAttribute("data-id");
    post({ op: "clip", id: id, action: action }).then(function (ok) {
      if (ok && action === "approve") glow($("#q-card"));
    });
  }
  function glow(el) {
    el.classList.remove("m-glow"); void el.offsetWidth; el.classList.add("m-glow");
    setTimeout(function () { el.classList.remove("m-glow"); }, 500);
  }





  function adoptCampaigns(s) { campaigns = s || { empty: true, campaigns: [] }; renderCampaigns(); setSyncedLine("camp-synced", campaigns); }
  
  function lastSyncedLabel(obj) {
    var s = (obj && (obj.last_synced || obj.as_of)) || "";
    if (!s) return "";
    // "Last synced 11-06 11:57 ET"
    var slice = String(s).slice(5, 16).replace("T", " ");
    return "Last synced " + slice + " ET";
  }
  function setSyncedLine(elId, obj) {
    var el = document.getElementById(elId);
    if (!el) return;
    var line = lastSyncedLabel(obj);
    el.textContent = line;
    el.hidden = !line;
  }

  function updateShellTruth() {
    var revOn = !!(revenue && revenue.connected);
    var autoOn = !!(state && state.autopost_enabled);
    var stamp = document.getElementById("shell-stamp") || document.querySelector(".stamp");
    var lede = document.getElementById("home-lede");
    var ribbon = document.getElementById("rev-ribbon");
    var parts = ["LOCAL SHELL", "APPROVE ACTIONS SHOWN PER CLIP"];
    parts.push(autoOn ? "AUTOPOST ON" : "AUTOPOST OFF");
    parts.push(revOn ? "REVENUE CONNECTED" : "REVENUE OFF");
    if (stamp) stamp.textContent = parts.join(" · ");
    if (lede) {
      if (revOn && !autoOn) {
        lede.textContent = "Revenue is connected. Autopost is off. Clips wait for your Approve — nothing posts by itself.";
      } else if (revOn && autoOn) {
        lede.textContent = "Revenue is connected. Autopost is ON. Approve still gates each clip.";
      } else if (!revOn && !autoOn) {
        lede.textContent = "Autopost is off. Revenue not connected. Clips wait for your Approve.";
      } else {
        lede.textContent = "Autopost is ON. Revenue not connected. Approve still gates each clip.";
      }
    }
    if (ribbon) {
      ribbon.textContent = revOn
        ? ("REVENUE CONNECTED · $" + (Number(revenue.total_usd || 0).toFixed(2)) + " · AUTOPOST " + (autoOn ? "ON" : "OFF"))
        : ("REVENUE OFF · AUTOPOST " + (autoOn ? "ON" : "OFF") + " · NOTHING TRACKED");
    }
  }
function adoptChannels(s) { channels = s || { empty: true, channels: [] }; renderChannelsHome(); renderChannelsPane(); setSyncedLine("chan-synced", channels); setSyncedLine("chan-pane-synced", channels); }
  function adoptRevenue(s) { revenue = s || { empty: true, connected: false, total_usd: 0 }; renderRevenue(); }
  function renderRevenue() {
    var total = (revenue && revenue.total_usd != null) ? Number(revenue.total_usd) : 0;
    var connected = !!(revenue && revenue.connected);
    var hv = document.getElementById("rev-home-v");
    var hs = document.getElementById("rev-home-sub");
    var hc = document.getElementById("rev-home-chip");
    if (hv) hv.textContent = "$" + (Math.round(total * 100) / 100).toFixed(total % 1 ? 2 : 0);
    if (hs) hs.textContent = connected ? ("Whop · $" + total.toFixed(2) + " lifetime") : "Whop · not synced";
    if (hc) {
      hc.textContent = connected ? "Connected" : "Not synced";
      hc.className = connected ? "chip ok" : "chip dash";
    }
    setSyncedLine("rev-synced", revenue);
    // revenue pane
    updateShellTruth();
    var poolChip = document.querySelector('[data-pane="revenue"] .ptop .chip');
    var ptot = document.querySelector('[data-pane="revenue"] .ptot');
    if (poolChip) {
      poolChip.textContent = connected ? "Connected" : "Not connected";
      poolChip.className = connected ? "chip ok" : "chip dash";
    }
    if (ptot) ptot.textContent = "$" + total.toFixed(2);
    var syncNote = document.getElementById("rev-pane-synced");
    if (syncNote) syncNote.textContent = lastSyncedLabel(revenue);
    (revenue.sources || []).forEach(function (src) {
      var row = document.querySelector('[data-rev-src="' + src.id + '"]');
      if (!row) return;
      var chip = row.querySelector(".chip");
      var pa = row.querySelector(".pa");
      if (chip) {
        chip.textContent = src.label || (src.connected ? "Connected" : "Not connected");
        chip.className = src.connected ? "chip ok" : "chip dash";
      }
      if (pa && src.amount_usd != null) pa.textContent = "$" + Number(src.amount_usd).toFixed(2);
    });
    // youtube explicit
    var ytRow = document.querySelector('[data-rev-src="youtube-partner"]');
    if (ytRow && revenue.youtube == null) {
      var chip = ytRow.querySelector(".chip");
      if (chip) { chip.textContent = "No API path"; chip.className = "chip dash"; }
    }
  }

  function platformLabel(p) {
    var k = String(p || "").toUpperCase();
    if (k.indexOf("YOUTUBE") >= 0) return "YouTube";
    if (k.indexOf("TIKTOK") >= 0) return "TikTok";
    if (k.indexOf("INSTAGRAM") >= 0) return "Instagram";
    if (k.indexOf("FACEBOOK") >= 0) return "Facebook";
    return p || "Account";
  }
  function hubYtGrantForOpusRow(row) {
    // Map Opus YT row → MAIN/PAID via known channel ids in profile_url / name
    var url = String((row && row.profile_url) || "");
    var grants = (state && state.youtube_grants) || {};
    var main = grants.MAIN || {}, paid = grants.PAID || {};
    var which = null;
    if (url.indexOf("UCgMuVjQmB9WvZtSz4e23THw") >= 0) which = "MAIN";
    else if (url.indexOf("UC8TrAT8V-HacqYlqqqzIQKg") >= 0) which = "PAID";
    else if (/clips/i.test(String((row && row.name) || ""))) which = "PAID";
    else if (platformLabel(row && row.platform) === "YouTube") which = "MAIN"; // fallback ambiguous
    if (!which) return null;
    var g = grants[which] || {};
    return { key: which, present: !!g.present && !g.expired && !g.needs_regrant, meta: g };
  }
  function renderChannelsHome() {
    var n = (channels && channels.channels) ? channels.channels.length : 0;
    var v = $("#sum-channels") || document.querySelector('a.sum[data-go="channels"] .v');
    var sub = $("#sum-channels-sub") || document.querySelector('a.sum[data-go="channels"] .sub');
    var chip = $("#sum-channels-chip") || document.querySelector('a.sum[data-go="channels"] .chip');
    if (v) v.textContent = String(n);
    if (sub) sub.textContent = n ? (n + " in Opus") : "No Opus accounts synced";
    if (chip) {
      chip.textContent = n ? "Synced from Opus" : "Not synced";
      chip.className = n ? "chip ok" : "chip dash";
    }
  }
  function renderChannelsPane() {
    var empty = $("#channels-empty"), slots = $("#channels-slots"), lede = $("#channels-lede");
    if (!slots) return;
    var rows = (channels && channels.channels) || [];
    if (!rows.length) {
      if (empty) empty.hidden = false;
      slots.hidden = true; slots.textContent = "";
      if (lede) lede.textContent = "Opus posting accounts (synced) vs hub YouTube label grants (separate OAuth).";
      return;
    }
    if (empty) empty.hidden = true;
    slots.hidden = false;
    slots.textContent = "";
    if (lede) lede.textContent = "Opus accounts synced. Hub YouTube grant is separate (needed to label private→public).";
    rows.forEach(function (row, i) {
      var card = document.createElement("div");
      card.className = "glass slot channels-slot m-i";
      card.style.setProperty("--i", String((i % 6) + 1));
      var plat = platformLabel(row.platform);
      var name = esc(row.name || "Account");
      var opusChip = '<span class="chip ok">Connected in Opus</span>';
      var hubChip = "";
      if (plat === "YouTube") {
        var hg = hubYtGrantForOpusRow(row);
        if (hg && hg.present) hubChip = '<span class="chip ok">Hub YouTube grant · ' + esc(hg.key) + '</span>';
        else hubChip = '<span class="chip warn">Hub YouTube grant missing' + (hg ? (" · " + esc(hg.key)) : "") + '</span>';
      } else {
        hubChip = '<span class="chip dash">Hub grant N/A (manual label)</span>';
      }
      var href = safeHttpUrl(row.profile_url);
      var url = href
        ? ('<a class="chan-link" href="' + esc(href) + '" target="_blank" rel="noopener noreferrer">' + esc(href) + "</a>")
        : '<span class="chan-link muted">No profile URL</span>';
      // Block column: name → platform → wrapping badges → bounded link (no horizontal squeeze/overlap)
      card.innerHTML =
        '<div class="nm">' + name + "</div>" +
        '<div class="plat">' + esc(plat) + "</div>" +
        '<div class="chips">' + opusChip + hubChip + "</div>" + url;
      slots.appendChild(card);
    });
  }
  function renderCampaigns() {
    var cnt = $("#camp-count"), sub = $("#camp-sub"), chip = $("#camp-chip"), ul = $("#camp-list");
    var rows = campaigns.campaigns || [];
    if (campaigns.empty || !rows.length) {
      if (cnt) cnt.textContent = "0";
      if (sub) sub.textContent = campaigns.reason || "No campaigns synced yet";
      if (chip) { chip.textContent = "Not synced"; chip.className = "chip dash"; }
      if (ul) { ul.hidden = true; ul.innerHTML = ""; }
      return;
    }
    if (cnt) cnt.textContent = String(rows.length);
    if (sub) sub.textContent = "rate / status from Clipper";
    if (chip) { chip.textContent = "Synced" + asof; chip.className = "chip"; }
    if (!ul) return;
    ul.hidden = false;
    ul.innerHTML = rows.slice(0, 6).map(function (c) {
      var name = esc(c.name || "Campaign");
      var st = esc(c.status || "—");
      var rate = c.rate_per_1k != null ? ("$" + esc(c.rate_per_1k) + "/1K") : "";
      return '<li><span class="bt">' + name + (rate ? (" · " + rate) : "") + '</span><span class="chip dash bs">' + st + '</span></li>';
    }).join("");
  }

  function adoptScriptQueue(s) { scriptQueue = s || { empty: true, items: [] }; renderScriptQueue(); setSyncedLine("sq-synced", scriptQueue); }
  function renderScriptQueue() {
    var cnt = $("#sq-count"), sub = $("#sq-sub"), chip = $("#sq-chip"), ul = $("#sq-list");
    var items = scriptQueue.items || [];
    if (scriptQueue.empty || !items.length) {
      if (cnt) cnt.textContent = "0";
      if (sub) sub.textContent = scriptQueue.reason || "No scripts in queue yet";
      if (chip) { chip.textContent = "Not synced"; chip.className = "chip dash"; }
      if (ul) { ul.hidden = true; ul.innerHTML = ""; }
      return;
    }
    if (cnt) cnt.textContent = String(items.length);
    if (sub) sub.textContent = "hooks ready for voice / cut";
    if (chip) { chip.textContent = "Synced"; chip.className = "chip"; }
    if (!ul) return;
    ul.hidden = false;
    ul.innerHTML = items.slice(0, 6).map(function (it) {
      var title = (it.title || it.id || "Script").replace(/[<>]/g, "");
      var st = (it.status || "—").replace(/[<>]/g, "");
      return '<li><span class="bt">' + title + '</span><span class="chip dash bs">' + st + '</span></li>';
    }).join("");
  }

  function adoptCredits(s) { credits = s || { empty: true }; renderCredits(); }
  function renderCredits() {
    var chip = $("#cred-chip"), opus = $("#cred-opus"), sub = $("#cred-sub"), el = $("#cred-el");
    var asof = credits.as_of ? (" · " + String(credits.as_of).slice(5, 16).replace("T", " ")) : "";
    function elLabel(e) {
      e = e || {};
      var used = (e.used != null ? e.used : e.spent);
      if (e.label) return "ElevenLabs: " + e.label;
      if (used == null || e.source === "unavailable" || e.reason) {
        return "ElevenLabs: 30k/mo plan, usage unverified";
      }
      var rem = (e.remaining_today != null ? e.remaining_today : e.remaining);
      return "ElevenLabs: " + (rem != null ? rem : "—") + " / " + (e.monthly != null ? e.monthly : 30000);
    }
    if (credits.empty) {
      if (opus) opus.textContent = "—";
      if (sub) sub.textContent = credits.reason || "Waiting for Clipper credits.json";
      if (chip) { chip.textContent = "Not synced" + asof; chip.className = "chip dash"; }
      if (el) el.textContent = elLabel(credits.elevenlabs);
      setSyncedLine("cred-synced", credits);
      return;
    }
    var o = credits.opus || {};
    var rem = o.remaining != null ? o.remaining : o.remaining_today;
    if (opus) opus.textContent = rem != null ? String(rem) : "—";
    if (sub) sub.textContent = "Opus left this month (reserve " + (o.reserve != null ? o.reserve : 30) + ")";
    if (chip) { chip.textContent = "Synced" + asof; chip.className = "chip"; }
    if (el) el.textContent = elLabel(credits.elevenlabs);
    setSyncedLine("cred-synced", credits);
  }

  function adoptShorts(s) {
    shorts = s && typeof s === "object" ? s : { items: [], empty: true, reason: "" };
    renderBatch();
  }
  function renderBatch() {
    var list = (shorts.items || []);
    var empty = $("#batch-empty"), ul = $("#batch-list"), cnt = $("#batch-count");
    if (cnt) cnt.textContent = String(list.length);
    if (!list.length) {
      if (empty) { empty.hidden = false; empty.textContent = shorts.reason || "No Shorts synced yet. Clipper writes to the box; pull with tools/pull_clipper_data.sh."; }
      if (ul) { ul.hidden = true; ul.innerHTML = ""; }
      return;
    }
    if (empty) empty.hidden = true;
    if (!ul) return;
    ul.hidden = false;
    ul.innerHTML = list.map(function (it) {
      var st = esc(it.status || "—");
      var title = esc(it.title || it.id || "Short");
      return '<li><span class="bt">' + title + '</span><span class="chip dash bs">' + st + '</span></li>';
    }).join("");
  }

  /* ---------- Approvals inbox (Frankie queue; decide only) ---------- */
  function esc(s) {
    return String(s || "").replace(/[&<>"']/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]; });
  }
  function safeHttpUrl(u) {
    // href allowlist: http(s) only — esc() alone does not stop javascript: URLs
    var s = String(u || "").trim();
    if (!/^https?:\/\//i.test(s)) return "";
    return s;
  }
    function videoSrc(v) {
    if (!v) return "";
    // same-origin path only (Frankie writes /samples/...); never fetch off-box hosts
    if (v.charAt(0) === "/" && v.indexOf("//") !== 0) return v;
    if (v.indexOf("samples/") === 0) return "/" + v;
    return "";
  }

  function mirrorHomeApprovals() {
    var src = $("#appr-list"), dest = $("#home-appr-list"), empty = $("#home-appr-empty"), count = $("#home-appr-count");
    if (!dest) return;
    var list = (approvals.items || []).filter(function (i) { return i.status === "pending" || i.status === "label_pending"; });
    if (count) count.textContent = list.length + (list.length === 1 ? " waiting" : " waiting");
    if (!list.length) {
      dest.hidden = true; dest.textContent = "";
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;
    dest.hidden = false;
    // Reuse approvals cards markup by cloning rendered nodes when present
    if (src && !src.hidden && src.children.length) {
      dest.textContent = "";
      Array.prototype.forEach.call(src.children, function (node) {
        dest.appendChild(node.cloneNode(true));
      });
    }
  }
  function renderApprovals() {
    paintYtGrantChip(state.youtube_grants);
    var list = (approvals.items || []).filter(function (i) { return i.status === "pending"; });
    var empty = $("#appr-empty"), box = $("#appr-list"), count = $("#appr-count");
    if (!empty || !box) return;
    count.textContent = list.length + (list.length === 1 ? " waiting" : " waiting");
    empty.hidden = !!list.length; box.hidden = !list.length;
    var pane = document.querySelector('[data-pane="approvals"]'); if (pane) pane.classList.toggle("has-pending", list.length > 0);
    if (!list.length) { box.textContent = ""; renderEvents(); paintAlertsBtn(); return; }
    box.textContent = "";
    list.forEach(function (item) {
      var card = document.createElement("div");
      card.className = "glass appr-card m-i";
      card.setAttribute("data-appr-id", item.id);
      var src = videoSrc(item.video);
      var plats = (item.platforms || []).map(function (p) { return '<span class="chip dash">' + esc(p) + "</span>"; }).join("");
      var when = item.scheduled_at ? ("Scheduled " + esc(item.scheduled_at)) : "Schedule not set";
      var tgt = item.route_target || (item.is_ad || item.campaign_id ? "PAID" : "MAIN");
      var handle = item.route_handle || "";
      var paid = item.paid_promotion || tgt === "PAID";
      var needsDest = item.needs_destination === true;
      var held = item.held === true;
      var routeChip = needsDest
        ? '<span class="chip warn" data-needs-destination>Needs destination · ' + esc(item.destination_reason || "unassigned") + "</span>"
        : ('<span class="chip ' + (paid ? "warn" : "dash") + '">Posts to ' + esc(tgt)
          + (handle ? (" · " + esc(handle)) : "")
          + (paid ? " · #ad" : "") + "</span>");
      // Exact destination before Approve: channel name, handle, YouTube channel id, Opus account id.
      var destLine = needsDest
        ? '<div class="meta dest-line dest-block" data-dest-block>Needs destination: no channel assigned (' + esc(item.destination_reason || "unassigned") + '). Approve is off until the clip is re-made with a valid type.</div>'
        : ('<div class="meta dest-line" data-dest="' + esc(tgt) + '">Destination: <b>' + esc(item.route_name || tgt) + "</b>"
          + " · " + (handle ? esc(handle) : "no handle on file")
          + " · YouTube " + esc(item.route_channel_id || "?")
          + " · Opus " + esc(item.route_opus_post_account_id || "?")
          + (item.clip_type ? (" · type " + esc(item.clip_type)) : "") + "</div>");
      var aiOn = item.ai_disclosure !== false;
      var aiChip = '<span class="chip ' + (aiOn ? "ok" : "dash") + '">AI label: ' + (aiOn ? "on" : "off") + "</span>";
      var sbChip = item.storyblocks
        ? '<span class="chip warn">Storyblocks: main only</span>'
        : "";
      var pendingLabelChip = "";
      // Truthful per-clip Approve copy. Server approve_line is authoritative.
      // Absent grant: still says it waits. A grant that is on file does not say that.
      // Public-publish mode never calls a blocked or manual mark a public post.
      var grantOnFile = false;
      if (state && state.youtube_grants && state.youtube_grants[tgt]) {
        var gg = state.youtube_grants[tgt];
        grantOnFile = !!(gg.present && !gg.expired && !gg.needs_regrant);
      }
      var apprWhat = item.approve_line
        ? esc(item.approve_line)
        : ((item.needs_destination === true)
        ? "Approve = unavailable · needs destination"
        : item.route_blocked
        ? ("Approve = blocked for " + esc(tgt) + " (" + esc(item.route_block_reason || "route blocked") + "); it will be rejected, nothing uploads")
        : (aiOn
          ? ((state && state.label_step_enabled === true)
            ? ((tgt === "MAIN" || tgt === "PAID" || tgt === "GAMING")
              ? (grantOnFile
                ? ("Approve = uploads PRIVATE to " + esc(tgt) + " · hub YouTube grant for " + esc(tgt) + " is on file")
                : ("Approve = uploads PRIVATE to " + esc(tgt) + " when the hub YouTube grant exists; otherwise waits for the grant"))
              : ("Approve = marks PRIVATE + label-pending · no upload (no hub YouTube grant for " + esc(tgt) + ")"))
            : "Approve = marks PRIVATE + label-pending · no upload (label step off)")
          : "Approve = marks ready · you post manually"));
      card.innerHTML =
        (src ? '<video controls playsinline preload="metadata" src="' + esc(src) + '"></video>' : '<div class="meta">No preview file</div>') +
        '<div class="cap">' + esc(item.caption || "(no caption)") + "</div>" +
        '<div class="plats">' + (plats || '<span class="chip dash">No platforms</span>') + routeChip + aiChip + sbChip + pendingLabelChip + "</div>" +
        '<div class="meta">' + when + "</div>" +
        destLine +
        '<div class="meta appr-what" data-appr-what="' + (item.needs_destination === true ? "needs-destination" : item.route_blocked ? "blocked" : (aiOn ? "private" : "manual")) + '">' + apprWhat + "</div>" +
        '<div class="bt">' +
          (needsDest ? '<button type="button" class="btn pri m-press" disabled aria-disabled="true" title="Needs destination">Approve</button>'
                     : held ? '<button type="button" class="btn pri m-press" disabled aria-disabled="true" title="Held">Held</button>'
                     : (state && state.public_publish_enabled && !apprAction(item))
                       ? '<button type="button" class="btn pri m-press" disabled aria-disabled="true" title="Blocked">Blocked</button>'
                     : '<button type="button" class="btn pri m-press" data-appr-act="approved">Approve</button>') +
          '<button type="button" class="btn gl m-press" data-appr-act="rejected">Reject</button>' +
          '<button type="button" class="btn gl m-press" data-appr-act="change_requested">Request change</button>' +
        "</div>" +
        '<div class="appr-note" hidden data-appr-note-wrap>' +
          '<input type="text" maxlength="500" placeholder="What should change?" aria-label="Change note" data-appr-note>' +
          '<button type="button" class="btn pri m-press" data-appr-act="change_send">Send</button>' +
        "</div>";
      box.appendChild(card);
    });
    // Label-pending cards (waiting on YT step and/or TT+IG deep-link push)
    var pendingLabels = (approvals.items || []).filter(function (i) { return i.status === "label_pending"; });
    pendingLabels.forEach(function (item) {
      var card = document.createElement("div");
      card.className = "glass appr-card m-i";
      card.setAttribute("data-appr-id", item.id);
      var src = videoSrc(item.video);
      var plats = (item.platforms || []).map(function (p) { return '<span class="chip dash">' + esc(p) + "</span>"; }).join("");
      var tgt = item.route_target || (item.is_ad || item.campaign_id ? "PAID" : "MAIN");
      var handle = item.route_handle || "";
      var routeChip = '<span class="chip dash">Posts to ' + esc(tgt) + (handle ? (" · " + esc(handle)) : "") + "</span>";
      var aiChip = '<span class="chip ok">AI label: on</span>';
      var sbChip = item.storyblocks ? '<span class="chip warn">Storyblocks: main only</span>' : '';
      var labelChip = '<span class="chip warn">Label pending</span>';
      var yt = item.youtube_label_set ? '<span class="chip ok">YouTube labeled</span>' : '<span class="chip dash">YouTube waiting</span>';
      var ttig = (item.tiktok_label_set && item.instagram_label_set)
        ? '<span class="chip ok">TT+IG notified</span>'
        : '<span class="chip dash">TT+IG push pending</span>';
      card.innerHTML =
        (src ? '<video controls playsinline preload="metadata" src="' + esc(src) + '"></video>' : '<div class="meta">No preview file</div>') +
        '<div class="cap">' + esc(item.caption || "(no caption)") + "</div>" +
        '<div class="plats">' + (plats || "") + routeChip + aiChip + sbChip + labelChip + yt + ttig + "</div>" +
        '<div class="meta">Private until labels clear. TikTok + IG: follow the push deep links (no hub tap).</div>';
      box.appendChild(card);
    });
    if (pendingLabels.length) {
      empty.hidden = true; box.hidden = false;
      var pane = document.querySelector('[data-pane="approvals"]'); if (pane) pane.classList.add("has-pending");
    }
    mirrorHomeApprovals();
    renderEvents();
    paintAlertsBtn();
    paintApproveAll();
  }

  // ---- Approve All (pending only; same per-item server path; idempotent batch id) ----
  var aa = { batchId: "", entries: [], inFlight: false, done: false };
  function apprAction(item) {
    if (!item || item.status !== "pending" || item.needs_destination === true || item.route_blocked || item.held) return "";
    if (item.ledger_upload_reason) return "";
    if (state && state.public_publish_enabled) {
      var preview = item.public_preview || {};
      if (preview.record_kind === "dispatch" && preview.will_dispatch_any && preview.ui_kind === "public") return "public_review";
      if (preview.record_kind === "manual" && preview.ui_kind === "manual") return "manual";
      return "";
    }
    if (item.ai_disclosure === false) return "manual";
    return (state && state.label_step_enabled === true) ? "private_upload" : "private_no_upload";
  }
  function aaEligible() { return ((approvals && approvals.items) || []).filter(function (i) { return !!apprAction(i); }); }
  function aaSkipReason(item) {
    if (!item) return "missing";
    if (item.ledger_upload_reason) return String(item.ledger_upload_reason);
    if (item.status === "change_requested") return "change_requested";
    if (item.status !== "pending") return "status:" + (item.status || "unknown");
    if (item.needs_destination) return item.destination_reason || "needs_destination";
    if (item.held) return "held";
    if (item.route_blocked) return item.route_block_reason || "route_blocked";
    var preview = item.public_preview || {};
    var reasons = [];
    (preview.platforms || []).forEach(function (r) {
      if (r && r.reason) reasons.push((r.platform || r.key || "platform") + ": " + r.reason);
    });
    if (reasons.length) return reasons.join("; ");
    if (preview.refuse_reason) return String(preview.refuse_reason);
    if (preview.summary) return String(preview.summary);
    return "not_eligible";
  }
  function aaSkipped() {
    return ((approvals && approvals.items) || []).filter(function (i) {
      if (!i || apprAction(i)) return false;
      return i.status === "pending" || i.status === "change_requested";
    });
  }
  function aaDest(i) {
    var tgt = i.route_target || "?";
    return esc(i.route_name || tgt) + " · " + (i.route_handle ? esc(i.route_handle) : "no handle on file") + " · YouTube " + esc(i.route_channel_id || "?");
  }
  function aaNewId() {
    try { if (window.crypto && crypto.randomUUID) return crypto.randomUUID().replace(/[^A-Za-z0-9_-]/g, ""); } catch (e) {}
    return "b" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }
  function paintApproveAll() {
    var b = $("#appr-all"); if (!b) return;
    var n = aaEligible().length;
    b.hidden = (n + aaSkipped().length) < 1;
    b.textContent = "Approve all (" + n + ")";
  }
  function previewBlock(preview) {
    var rows = (preview && preview.platforms) || [];
    if (!rows.length) return '<p class="aa-note">' + esc((preview && preview.summary) || "Not a public post.") + "</p>";
    return rows.map(function (r) {
      var kind = r.public_action === "promote_existing" ? "PROMOTE existing" : (r.public_action === "private_upload" ? "PRIVATE upload" : (r.public_action === "public_publish" ? "PUBLIC publish" : (r.public_action === "not_public" ? "Not a public post" : "Blocked")));
      var disc = r.disclosures || {};
      var privacy = r.public_action === "promote_existing" ? "private to public" : (r.public_action === "private_upload" ? "private" : (r.public_action === "public_publish" ? "public" : "not a public post"));
      return '<div class="aa-priv" data-public-action="' + esc(r.public_action || "") + '"><h3 class="aa-sec">' + esc(kind) + "</h3><b>" +
        esc(r.platform || "") + "</b><span>" + esc(r.account_name || "no account") + " · " + esc(r.account_id || "no id") +
        " · " + esc(r.external_id || "no external id") + (r.existing_video_id ? " · video " + esc(r.existing_video_id) : "") + "</span><span>privacy " + esc(privacy) +
        " · AI " + (disc.ai ? "on" : "off") + " · paid " + (disc.paid ? "on" : "off") +
        "</span><span>sha256 " + esc(r.artifact_sha256 || "none") + "</span><span>" + esc(r.caption || "") +
        "</span><p>" + esc(r.line || "") + "</p></div>";
    }).join("");
  }
  function aaSkipHtml(items) {
    if (!items.length) return "";
    return '<h3 class="aa-sec">Skipped (' + items.length + ")</h3>" + items.map(function (i) {
      var reason = aaSkipReason(i);
      return '<div class="aa-skip" data-aa-skip="' + esc(i.id) + '" data-aa-reason="' + esc(reason) + '"><b>' +
        esc(i.caption || i.title || i.id) + "</b><span>" + aaDest(i) + "</span><p>Skipped: " + esc(reason) + "</p>" +
        previewBlock(i.public_preview) + "</div>";
    }).join("");
  }
  function openPublicOne(id) {
    var item = ((approvals && approvals.items) || []).filter(function (i) { return i.id === id; })[0];
    if (!item || !item.public_preview) return;
    var preview = item.public_preview;
    var platformRows = (preview.platforms || []).map(function (r) {
      return { key: r.key, row_hash: r.row_hash };
    });
    aa = { mode: "public_one", batchId: "", itemId: id, hash: preview.manifest_hash || "", platformRows: platformRows, entries: [], inFlight: false, done: false };
    var h = $("#aa-h"); if (h) h.textContent = "Confirm what Approve will do";
    var note = $("#aa-note");
    if (note) note.textContent = "Exact file, account, caption, and labels. A change cancels this confirmation. A blocked row is not a public post.";
    $("#aa-body").innerHTML = previewBlock(preview);
    var c = $("#aa-confirm");
    var armed = !!preview.will_dispatch_any && preview.ui_kind === "public";
    var manual = preview.record_kind === "manual" && preview.ui_kind !== "held";
    var heldPreview = preview.ui_kind === "held" || preview.record_kind === "held";
    c.hidden = false;
    c.disabled = heldPreview || (!armed && !manual);
    c.textContent = heldPreview ? "Held · excluded" : (armed ? "Publish publicly" : (manual ? "Mark ready (not a public post)" : "Nothing will be published"));
    $("#aa-cancel").textContent = "Cancel";
    $("#aa-result").hidden = true;
    $("#aa-sheet").hidden = false;
  }
  function confirmPublicOne() {
    if (aa.inFlight || aa.done || !aa.itemId) return;
    aa.inFlight = true;
    var c = $("#aa-confirm"); c.disabled = true;
    postApproval({ op: "decide", id: aa.itemId, status: "approved", confirm_public: true, manifest_hash: aa.hash, platform_rows: aa.platformRows || [], note: "" }).then(function (res) {
      aa.inFlight = false;
      var r = $("#aa-result"); r.hidden = false;
      if (!res.ok) {
        c.disabled = false;
        r.textContent = "Not published: " + ((res.body && res.body.error) || ("HTTP " + res.status)) + ".";
        return;
      }
      aa.done = true; c.hidden = true; $("#aa-cancel").textContent = "Close";
      var pub = res.body && res.body.public_publish;
      r.textContent = aaPubText(pub);
      adoptApprovals(res.body);
    }).catch(function () {
      aa.inFlight = false; c.disabled = false;
      var r = $("#aa-result"); r.hidden = false; r.textContent = "Network error. Nothing new was published.";
    });
  }
  function aaPubText(pub) {
    var plats = (pub && pub.platforms) || [];
    var lines = plats.map(function (p) {
      var rid = String(p.remote_id || "");
      if (!rid || rid.indexOf("http://") === 0 || rid.indexOf("https://") === 0 || rid.indexOf("upload_id") >= 0) rid = "";
      return (p.platform || p.key || "platform") + ": " + (p.status || "unknown") +
        (p.reason ? " (" + p.reason + ")" : "") + (rid ? " id " + rid : "");
    }).join("; ");
    if (!pub) return "Recorded. This was not a public post.";
    if (pub.partial) return "Partial. Not fully approved. " + lines;
    var blockedN = plats.filter(function (p) { return p.status === "blocked" || p.status === "not_public"; }).length;
    if (blockedN && blockedN === plats.length) return "Blocked " + blockedN + ". Not fully approved. " + lines;
    if (plats.some(function (p) { return p.status === "unknown"; })) {
      if (plats.some(function (p) { return p.status_query; })) {
        return "Unconfirmed. This approval sent one status query and did not start another upload. " + lines;
      }
      if (plats.some(function (p) { return p.later_status_query; })) {
        return "Unconfirmed. A later approval sends one status query to the stored session and does not start another upload. " + lines;
      }
      return "Unconfirmed. Not a confirmed publish. " + lines;
    }
    if (pub.kind === "manual") return "Recorded. This was not a public post. " + lines;
    if (pub.dispatched && pub.ok) return "Each confirmed platform finished. " + lines;
    return "Not fully approved. " + lines;
  }
  function openApproveAll() {
    var list = aaEligible();
    var skips = aaSkipped();
    if (!list.length && !skips.length) return;
    var h = $("#aa-h"); if (h) h.textContent = "Approve all";
    aa = { mode: "batch", batchId: aaNewId(), entries: list.map(function (i) {
      var e = { id: i.id, action: apprAction(i) };
      if (state && state.public_publish_enabled && i.public_preview) {
        e.manifest_hash = i.public_preview.manifest_hash;
        e.platform_rows = (i.public_preview.platforms || []).map(function (r) {
          return { key: r.key, row_hash: r.row_hash };
        });
      }
      return e;
    }), inFlight: false, done: false };
    var manual = list.filter(function (i) { return apprAction(i) === "manual"; });
    var priv = list.filter(function (i) { return apprAction(i) !== "manual"; });
    var html = "";
    if (state && state.public_publish_enabled) {
      list.forEach(function (i) {
        html += '<div data-aa-id="' + esc(i.id) + '" data-aa-action="' + esc(apprAction(i)) + '"><p>' + aaDest(i) + "</p>" + previewBlock(i.public_preview) + "</div>";
      });
      html += aaSkipHtml(skips);
      $("#aa-body").innerHTML = html;
      $("#aa-count").textContent = list.length + " ready · " + skips.length + " skipped";
      $("#aa-result").hidden = true; $("#aa-result").textContent = "";
      var c0 = $("#aa-confirm"); c0.disabled = !list.length; c0.textContent = list.length ? ("Confirm " + list.length) : "Nothing to submit"; c0.hidden = false;
      $("#aa-cancel").textContent = "Cancel";
      $("#aa-sheet").hidden = false;
      return;
    }
    priv.forEach(function (i) {
      var up = apprAction(i) === "private_upload";
      html += '<div class="aa-priv" data-aa-id="' + esc(i.id) + '" data-aa-action="' + apprAction(i) + '"><h3 class="aa-sec">' +
        (up ? "PRIVATE YouTube upload" : "PRIVATE · label-pending · no upload") + "</h3><b>" + esc(i.caption || i.title || i.id) + "</b><span>" + aaDest(i) + "</span><p>" +
        (up ? ("Uploads this clip PRIVATE to " + esc(i.route_target) + " through Opus when the hub YouTube grant exists; otherwise it waits for the grant. AI label set before it can go public.")
            : "Marks PRIVATE + label-pending. No upload (label step off).") + "</p></div>";
    });
    if (manual.length) {
      html += '<h3 class="aa-sec">Marks ready · you still post manually (' + manual.length + ")</h3><ul class=\"aa-list\">" +
        manual.map(function (i) { return '<li data-aa-id="' + esc(i.id) + '" data-aa-action="manual"><b>' + esc(i.caption || i.title || i.id) + '</b><span>' + aaDest(i) + "</span></li>"; }).join("") + "</ul>";
    }
    html += aaSkipHtml(skips);
    $("#aa-body").innerHTML = html;
    $("#aa-count").textContent = list.length + " clips";
    $("#aa-result").hidden = true; $("#aa-result").textContent = "";
    var c = $("#aa-confirm"); c.disabled = !list.length; c.textContent = list.length ? ("Approve " + list.length) : "Nothing to submit"; c.hidden = false;
    $("#aa-cancel").textContent = "Cancel";
    $("#aa-sheet").hidden = false;
  }
  function closeApproveAll() { if (aa.inFlight) return; $("#aa-sheet").hidden = true; renderAll(); }
  function confirmApproveAll() {
    if (aa.mode === "public_one") return confirmPublicOne();
    if (aa.inFlight || aa.done || !aa.entries.length) return;      // double tap: ignored client-side; server dedups by batch id too
    aa.inFlight = true;
    var c = $("#aa-confirm"); c.disabled = true; c.textContent = "Approving…";
    postApproval({ op: "approve_batch", batch_id: aa.batchId, items: aa.entries }).then(function (res) {
      aa.inFlight = false;
      var r = $("#aa-result"); r.hidden = false;
      if (!res.ok || !res.body || !res.body.batch) {
        c.disabled = false; c.textContent = "Retry (same batch)";
        r.textContent = "Not sent: " + ((res.body && res.body.error) || ("HTTP " + res.status)) + ". Nothing new was approved by this attempt.";
        return;
      }
      aa.done = true; c.hidden = true; $("#aa-cancel").textContent = "Close";
      var b = res.body.batch, bad = (b.results || []).filter(function (x) { return !x.ok && x.outcome !== "skipped"; });
      var skippedRows = (b.results || []).filter(function (x) { return x.outcome === "skipped"; });
      var warn = (b.results || []).filter(function (x) { return x.ok && x.warning; });
      var partialN = b.partial || 0, unknownN = b.unknown || 0, blockedN = b.blocked || 0;
      var privateN = b.private_uploaded || 0;
      var skippedN = b.skipped || skippedRows.length || 0;
      var headline = (privateN && !partialN && !unknownN && !blockedN && !(b.success || 0) && !(b.failed || 0) && !skippedN)
        ? (privateN + " private uploads. Not a public post." + (b.replayed ? " (already done)" : ""))
        : (partialN || unknownN || blockedN)
        ? ("Not fully approved. " + (b.success || 0) + " succeeded, " + partialN + " partial, " +
          unknownN + " unconfirmed, " + blockedN + " blocked, " + (b.failed || 0) + " failed" +
          (skippedN ? (", " + skippedN + " skipped") : "") +
          (b.replayed ? " (already done)" : ""))
        : (b.approved + " approved" + (skippedN ? (", " + skippedN + " skipped") : "") + (b.failed ? (", " + b.failed + " failed") : "") + (b.replayed ? " (already done)" : ""));
      var detail = (b.results || []).map(function (x) {
        var pub = x.public_publish;
        if (!pub || !pub.platforms) return "";
        return "<li>" + esc(x.id) + ": " + esc(x.outcome || (x.ok ? "ok" : "failed")) + " · " + esc(aaPubText(pub)) + "</li>";
      }).join("");
      r.innerHTML = "<b>" + headline + "</b>" +
        (skippedRows.length ? "<ul>" + skippedRows.map(function (x) { return "<li>" + esc(x.id) + ": skipped · " + esc(x.reason || x.error || "skipped") + "</li>"; }).join("") + "</ul>" : "") +
        (bad.length ? "<ul>" + bad.map(function (x) { return "<li>" + esc(x.id) + ": " + esc(x.error || x.outcome || "failed") + "</li>"; }).join("") + "</ul>" : "") +
        (warn.length ? "<ul>" + warn.map(function (x) { return "<li>" + esc(x.id) + ": approved; " + esc(x.warning) + "</li>"; }).join("") + "</ul>" : "") +
        (detail ? "<ul>" + detail + "</ul>" : "");
      adoptApprovals(res.body);
    }).catch(function () {
      aa.inFlight = false; c.disabled = false; c.textContent = "Retry (same batch)";
      var r = $("#aa-result"); r.hidden = false; r.textContent = "Network error. Retry uses the same batch id, so nothing is approved twice.";
    });
  }
  function decide(id, status, note) {
    postApproval({ op: "decide", id: id, status: status, note: note || "" }).then(function (res) {
      if (res.ok && res.body) {
        adoptApprovals(res.body);
        if (res.body.oauth_url) {
          // One-time YouTube consent; host allowlist only (accounts.google.com).
          try {
            var u = new URL(res.body.oauth_url, window.location.href);
            if (u.protocol === "https:" && u.hostname === "accounts.google.com") {
              window.location.href = u.href;
            }
          } catch (e) {}
          return;
        }
        renderAll();
      }
    });
  }

  function eventIsResolved(e) {
    var t = ((e && e.title) || "") + " " + ((e && e.body) || "");
    t = t.toLowerCase();
    // Auto-hide transient/resolved clipper status noise
    if (t.indexOf("fixing and will re-queue") >= 0) return true;
    if (t.indexOf("will re-queue once") >= 0) return true;
    if (t.indexOf("re-queued") >= 0 || t.indexOf("requeued") >= 0) return true;
    if (e && e.resolved) return true;
    return false;
  }
  function activeEvents() {
    return (events.events || []).filter(function (e) { return !eventIsResolved(e); });
  }
  function fillEventsBox(box, list) {
    if (!box) return;
    box.textContent = "";
    if (!list.length) {
      var p = document.createElement("div"); p.className = "ev-empty"; p.textContent = "No alerts."; box.appendChild(p); return;
    }
    list.slice().reverse().slice(0, 20).forEach(function (e) {
      var row = document.createElement("div");
      row.className = "ev"; row.setAttribute("role", "listitem");
      row.innerHTML = "<b>" + esc(e.title || e.type) + '</b><span class="when">' + esc(e.type) + (e.at ? " · " + esc(e.at) : "") + "</span>" +
        (e.body ? "<span>" + esc(e.body) + "</span>" : "");
      box.appendChild(row);
    });
  }
  function paintBellCounts(list) {
    var n = list.length;
    ["alerts-bell-count", "home-bell-count"].forEach(function (id) {
      var c = document.getElementById(id);
      if (c) { c.textContent = n > 99 ? "99+" : String(n); c.hidden = n < 1; }
    });
  }
  function closeAlertsDrawer() {
    var d = $("#alerts-drawer");
    if (d) { d.classList.remove("open"); d.hidden = true; d.setAttribute("aria-hidden", "true"); }
    var hd = $("#home-alerts-dd");
    if (hd) { hd.classList.remove("open"); hd.hidden = true; }
    document.querySelectorAll(".alerts-bell[aria-expanded='true']").forEach(function (el) {
      el.setAttribute("aria-expanded", "false");
    });
    // Legacy dropdown must stay hidden — never overlay videos
    var legacy = $("#alerts-dropdown");
    if (legacy) { legacy.hidden = true; legacy.classList.remove("open"); legacy.setAttribute("aria-hidden", "true"); }
  }
  function openAlertsDrawer() {
    fillEventsBox($("#events-list"), activeEvents());
    var d = $("#alerts-drawer");
    if (!d) return;
    d.hidden = false; d.classList.add("open"); d.setAttribute("aria-hidden", "false");
    var b = $("#alerts-bell"); if (b) b.setAttribute("aria-expanded", "true");
  }
  function renderEvents() {
    var list = activeEvents();
    paintBellCounts(list);
    // Drawer stays closed unless user opened it; refresh contents if open
    var d = $("#alerts-drawer");
    if (d && d.classList.contains("open")) fillEventsBox($("#events-list"), list);
    else closeAlertsDrawer();
  }
  function toggleBell(btn) {
    var d = $("#alerts-drawer");
    if (!d) return;
    if (d.classList.contains("open")) closeAlertsDrawer();
    else openAlertsDrawer();
  }

  /* ---------- Local alerts (no push server, no keys) ---------- */
  function alertsOn() { try { return localStorage.getItem("clippinghub.alerts") === "1"; } catch (e) { return false; } }
  function paintAlertsBtn() {
    var b = $("#alerts-toggle"), h = $("#alerts-hint"); if (!b) return;
    var supported = typeof Notification !== "undefined";
    var on = alertsOn() && supported && Notification.permission === "granted";
    b.textContent = on ? "Alerts on" : "Turn on alerts";
    // Hide once on; also hide when Notification API unavailable (no false CTA)
    b.hidden = !!on || !supported;
    if (h) {
      h.hidden = !!on;
      h.textContent = !supported
        ? "In-app alert list only (this shell has no notification permission API)."
        : (on
          ? "Local alerts while this hub is open. No push server."
          : "Phone + Mac · decisions save on the hub. Push via ntfy when configured.");
    }
  }
  function enableAlerts() {
    if (typeof Notification === "undefined") { paintAlertsBtn(); return; }
    Notification.requestPermission().then(function (p) {
      if (p === "granted") {
        try { localStorage.setItem("clippinghub.alerts", "1"); } catch (e) {}
        notifyNow("Clipping Hub alerts on", "You’ll see a local alert when something is waiting. Nothing is sent to platforms.");
      }
      paintAlertsBtn();
    });
  }
  function notifyNow(title, body, tag) {
    if (!alertsOn() || typeof Notification === "undefined" || Notification.permission !== "granted") return;
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({ type: "notify", title: title, body: body, tag: tag || "clipping-hub" });
    } else if (window.Notification) {
      try { new Notification(title, { body: body, tag: tag || "clipping-hub" }); } catch (e) {}
    }
  }
  function maybeNotifyNew() {
    if (!alertsOn()) return;
    var seen = {};
    try { seen = JSON.parse(localStorage.getItem("clippinghub.seenEvents") || "{}"); } catch (e) {}
    var changed = false;
    (events.events || []).forEach(function (e) {
      if (seen[e.id]) return;
      seen[e.id] = 1; changed = true;
      notifyNow(e.title || e.type, e.body || "", "ev-" + e.id);
    });
    if (changed) try { localStorage.setItem("clippinghub.seenEvents", JSON.stringify(seen)); } catch (e) {}
  }

  function onConnect(btn) {
    var chip = $("[data-status]", btn.closest(".slot"));
    chip.textContent = "Not connected yet";
  }

  document.addEventListener("click", function (e) {
    var t = e.target.closest("button, a[data-go], #q-scrim"); if (!t) return;
    if (t.hasAttribute("data-connect")) return onConnect(t);
    if (t.hasAttribute("data-theme-set")) return setTheme(t.getAttribute("data-theme-set"));
    if (t.hasAttribute("data-go")) { e.preventDefault(); return show(t.getAttribute("data-go"), true); }
    if (t.hasAttribute("data-qf")) { filter = t.getAttribute("data-qf"); idx = 0; notice = ""; return renderQueue(); }
    if (t.hasAttribute("data-act")) return act(t.getAttribute("data-act"));
    if (t.id === "q-undo") return act("undo");
    if (t.id === "q-checkopen") { sheetOpen = true; return placeCheck(); }
    if (t.id === "q-checkclose" || t.id === "q-scrim") { sheetOpen = false; return placeCheck(); }
    if (t.id === "q-prev") { idx = Math.max(0, idx - 1); notice = ""; return renderQueue(); }
    if (t.id === "q-next") { idx++; notice = ""; return renderQueue(); }
    if (t.id === "q-add") { filter = "pending"; return post({ op: "add_sample" }); }
    if (t.id === "q-clear") return post({ op: "clear_samples" });
    if (t.id === "alerts-toggle") return enableAlerts();
    if (t.id === "alerts-drawer-close") return closeAlertsDrawer();
    if (t.id === "alerts-bell" || (t.closest && t.closest("#alerts-bell"))) {
      return toggleBell($("#alerts-bell"));
    }
    if (t.id === "home-alerts-bell" || (t.closest && t.closest("#home-alerts-bell"))) {
      return toggleBell($("#home-alerts-bell"));
    }
    if (t.id === "appr-all") return openApproveAll();
    if (t.id === "aa-cancel") return closeApproveAll();
    if (t.id === "aa-confirm") return confirmApproveAll();
    if (t.hasAttribute("data-appr-act")) {
      var card = t.closest("[data-appr-id]"); if (!card) return;
      var id = card.getAttribute("data-appr-id"), actn = t.getAttribute("data-appr-act");
      if (actn === "change_requested") {
        var wrap = $("[data-appr-note-wrap]", card); wrap.hidden = false; $("[data-appr-note]", card).focus(); return;
      }
      if (actn === "change_send") {
        var note = ($("[data-appr-note]", card).value || "").trim();
        if (!note) return;
        return decide(id, "change_requested", note);
      }
      if (actn === "approved" && state && state.public_publish_enabled) {
        var heldItem = ((approvals && approvals.items) || []).filter(function (i) { return i.id === id; })[0];
        if (heldItem && heldItem.held) return;
        return openPublicOne(id);
      }
      return decide(id, actn, "");
    }
  });
  document.addEventListener("change", function (e) { var t = e.target; if (t && t.hasAttribute && t.hasAttribute("data-item")) tick(t.getAttribute("data-item"), t.checked); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && sheetOpen) { sheetOpen = false; placeCheck(); } });
  if (wide.addEventListener) wide.addEventListener("change", placeCheck);
  window.addEventListener("popstate", function () { show(PATHS[location.pathname] || "home", false); });
  paintTheme(currentTheme());
  show(PATHS[location.pathname] || "home", false);
  get().then(function () {
    try {
      var q = new URLSearchParams(location.search || "");
      var rg = q.get("yt_regrant");
      if (rg) {
        // Authorized re-grant: POST /api/youtube-oauth/start (X-Hub-Token), never bare callback.
        startYtRegrant(rg);
      }
    } catch (e) {}
  });
  if ("serviceWorker" in navigator && (location.hostname === "127.0.0.1" || location.protocol === "https:")) navigator.serviceWorker.register("/sw.js").catch(function () {});
})();
