// Job Hunt Agent — Liquid Glass dashboard
const API = location.origin;
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

let PROVIDERS = {};
const APPS_PAGE_SIZE = 10;
let appsState = { all: [], page: 1, status: "all" };
const FEED_CAP = 50;
const jobsHistory = [];

function toast(msg, type = "success") {
  const t = document.createElement("div");
  t.className = `lg-toast ${type}`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}

// ─── Tab navigation ───
function activatePanel(name) {
  $$(".lg-tab[data-panel]").forEach(b => b.classList.toggle("active", b.dataset.panel === name));
  $$(".lg-sidebar .nav-item").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  $$(".lg-panel").forEach(p => p.hidden = p.id !== `panel-${name}`);
  if (name === "profile") renderProfile();
  if (name === "applications") renderApplications();
  if (name === "settings") fillSettingsForm();
}
$$(".lg-tab[data-panel]").forEach(b => b.onclick = () => activatePanel(b.dataset.panel));
$$(".lg-sidebar .nav-item").forEach(b => b.onclick = () => activatePanel(b.dataset.tab));

// ─── Sparkline (simple polyline) ───
function drawSparkline(svgId, values) {
  const svg = document.getElementById(svgId);
  if (!svg) return;
  if (values.length < 2) { svg.innerHTML = ""; return; }
  const max = Math.max(...values, 1);
  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * 100;
    const y = 30 - (v / max) * 26 - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  svg.innerHTML = `
    <defs>
      <linearGradient id="sparkGrad-${svgId}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.4"/>
        <stop offset="100%" stop-color="#3b82f6" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <polygon points="0,30 ${points} 100,30" fill="url(#sparkGrad-${svgId})"/>
    <polyline points="${points}" fill="none" stroke="#3b82f6" stroke-width="1.5"/>
  `;
}

// ─── Progress ring ───
function setRing(percent) {
  const ring = $("#ringFg");
  const text = $("#ringText");
  if (!ring || !text) return;
  const C = 2 * Math.PI * 50; // 314.16
  ring.setAttribute("stroke-dashoffset", String(C * (1 - percent / 100)));
  text.textContent = `${Math.round(percent)}%`;
}

// ─── Status polling ───
async function updateStatus() {
  try {
    const r = await fetch(`${API}/api/status`);
    const s = await r.json();
    $("#statJobs").textContent = s.total_jobs;
    $("#statApplied").textContent = s.auto_applied;
    $("#statSemi").textContent = s.semi_auto;

    const total = s.auto_applied + s.semi_auto + s.manual_flag;
    const rate = total ? Math.round((s.auto_applied / total) * 100) : 0;
    $("#statRate").textContent = `${rate}%`;
    setRing(rate);

    const badge = $("#statusBadge");
    if (s.running && s.paused) {
      badge.className = "lg-pill yellow"; badge.textContent = "PAUSED";
    } else if (s.running) {
      badge.className = "lg-pill blue"; badge.textContent = "SEARCHING";
    } else {
      badge.className = "lg-pill gray"; badge.textContent = "IDLE";
    }

    $("#btnStart").disabled = s.running;
    $("#btnPause").disabled = !s.running || s.paused;
    $("#btnResume").disabled = !s.paused;
    $("#btnStop").disabled = !s.running;

    const mins = Math.floor(s.elapsed_seconds / 60);
    const secs = s.elapsed_seconds % 60;
    $("#elapsedTime").textContent = `${String(mins).padStart(2,"0")}:${String(secs).padStart(2,"0")}`;

    jobsHistory.push(s.total_jobs);
    if (jobsHistory.length > 30) jobsHistory.shift();
    drawSparkline("sparkJobs", jobsHistory);
  } catch (e) { console.error(e); }
}
setInterval(updateStatus, 2500);
updateStatus();

// ─── Controls ───
$("#btnStart").onclick = async () => {
  const duration = parseInt($("#durationInput").value) || 30;
  const r = await fetch(`${API}/api/search/start?duration_minutes=${duration}`, { method: "POST" });
  if (r.ok) { toast(`Search started — ${duration} min`); $("#feedList").innerHTML = ""; }
  else { const err = await r.json(); toast(err.detail || "Failed to start", "error"); }
};
$("#btnPause").onclick = async () => { await fetch(`${API}/api/search/pause`, { method: "POST" }); toast("Paused", "warning"); };
$("#btnResume").onclick = async () => { await fetch(`${API}/api/search/resume`, { method: "POST" }); toast("Resumed"); };
$("#btnStop").onclick = async () => { await fetch(`${API}/api/search/stop`, { method: "POST" }); toast("Stopped"); };

// ─── SSE for live events ───
const sse = new EventSource(`${API}/api/events`);
sse.addEventListener("update", e => {
  const evt = JSON.parse(e.data);
  const feed = $("#feedList");

  if (evt.type === "job") {
    const empty = feed.querySelector("[style*='No high-match']");
    if (empty) empty.parentElement.remove();

    const card = document.createElement("div");
    card.className = `lg-job ${evt.tier}`;
    const salary = (evt.salary_min && evt.salary_max)
      ? ` · $${Math.round(evt.salary_min).toLocaleString()}–${Math.round(evt.salary_max).toLocaleString()}`
      : "";
    card.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
        <div style="flex:1">
          <div class="lg-job-title">${escapeHtml(evt.title)}</div>
          <div class="lg-job-meta">${escapeHtml(evt.company)} · ${escapeHtml(evt.location)} · ${escapeHtml(evt.source)}${salary}</div>
        </div>
        <div class="lg-job-score ${evt.tier}">${evt.score}</div>
      </div>
      ${evt.reason ? `<div style="margin-top:8px;font-size:13px;color:var(--lg-text-2);font-style:italic">${escapeHtml(evt.reason)}</div>` : ""}
      ${evt.matched_skills?.length ? `<div style="margin-top:6px;font-size:12px;color:#16a34a">✓ ${evt.matched_skills.slice(0,5).map(escapeHtml).join(", ")}</div>` : ""}
      <div style="margin-top:10px"><a href="${escapeHtml(evt.url)}" target="_blank" rel="noreferrer" style="color:var(--lg-blue-deep);font-size:13px;font-weight:600;text-decoration:none">View job →</a></div>
    `;
    feed.insertBefore(card, feed.firstChild);
    while (feed.children.length > FEED_CAP) feed.removeChild(feed.lastElementChild);
  } else if (evt.type === "diagnostics") {
    const d = evt.data;
    const sources = Object.entries(d.discovered_per_source || {})
      .map(([k, v]) => `${k}:${v}`).join(" · ");
    $("#diagBox").hidden = false;
    $("#diagBox").innerHTML = `
      <strong>Last cycle funnel:</strong>
      ${d.discovered_total} discovered → ${d.deduped_count} unique → ${d.passed_salary} passed salary → ${d.passed_relevance} passed relevance → ${d.returned} sent to AI<br>
      <strong>Sources:</strong> ${sources}
    `;
  } else if (evt.type === "info" || evt.type === "warning") {
    addFeedLine(evt.message);
  } else if (evt.type === "error") {
    toast(evt.message, "error");
  } else if (evt.type === "complete") {
    toast(`Search complete · ${evt.stats.applied} applied`);
  }
});

function addFeedLine(text) {
  const feed = $("#feedList");
  const empty = feed.querySelector("[style*='No high-match']");
  if (empty) empty.parentElement.remove();
  const line = document.createElement("div");
  line.className = "lg-job";
  line.style.borderLeftColor = "var(--lg-blue)";
  line.style.fontSize = "13px"; line.style.color = "var(--lg-text-2)";
  line.textContent = text;
  feed.insertBefore(line, feed.firstChild);
  while (feed.children.length > FEED_CAP) feed.removeChild(feed.lastElementChild);
}

// ─── Provider hint ───
async function loadProviders() {
  const r = await fetch(`${API}/api/providers`);
  const data = await r.json();
  PROVIDERS = Object.fromEntries(data.providers.map(p => [p.id, p]));
  updateProviderHint();
}
function updateProviderHint() {
  const sel = $("#providerSelect");
  if (!sel) return;
  const p = PROVIDERS[sel.value];
  if (p) {
    $("#providerHint").innerHTML = `Format: <code>${p.key_hint}</code> · Get a key at <a href="${p.key_url}" target="_blank" style="color:var(--lg-blue-deep)">${p.key_url.replace(/^https?:\/\//,"")}</a>`;
    if ($("#apiKeyInput")) $("#apiKeyInput").placeholder = p.key_hint;
  }
}
document.addEventListener("change", e => {
  if (e.target.id === "providerSelect") {
    updateProviderHint();
    // Reset model dropdown when provider changes
    const sel = $("#llmModelSelect");
    if (sel) sel.innerHTML = '<option value="">— use provider default —</option>';
  }
});
loadProviders();

// ─── Model discovery ───
async function discoverModels() {
  const btn = $("#discoverModelsBtn");
  const provider = $("#providerSelect")?.value || "gemini";
  const apiKey = $("#apiKeyInput")?.value || null;

  if (!btn) return;
  btn.disabled = true; btn.textContent = "Discovering…";
  $("#modelHint").textContent = "Querying provider for available models…";

  try {
    const r = await fetch(`${API}/api/llm/models`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({provider, api_key: apiKey}),
    });
    if (!r.ok) {
      const err = await r.json();
      throw new Error(err.detail || "Discovery failed");
    }
    const { models, default: defaultModel } = await r.json();
    const sel = $("#llmModelSelect");
    sel.innerHTML = '<option value="">— use provider default —</option>';
    for (const m of models) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.recommended ? `★ ${m.label}` : m.label;
      sel.appendChild(opt);
    }
    $("#modelHint").innerHTML = `Found <strong>${models.length}</strong> models. Default: <code>${defaultModel}</code>. ★ = recommended.`;
    toast(`Found ${models.length} models for ${provider}`);
  } catch (e) {
    $("#modelHint").innerHTML = `<span style="color:#dc2626">${escapeHtml(e.message)}</span>`;
    toast("Discovery failed: " + e.message, "error");
  } finally {
    btn.disabled = false; btn.textContent = "Discover available models";
  }
}
document.addEventListener("click", e => {
  if (e.target.id === "discoverModelsBtn") discoverModels();
});

// ─── Profile view ───
let profileCache = null;

function paintProfile(profile) {
  const view = $("#profileView");
  if (!view) return;
  if (!profile) {
    view.innerHTML = `<p style="color:var(--lg-text-dim)">No profile yet. Open Settings to create one.</p>`;
    return;
  }
  const rows = [
    ["Name", profile.name],
    ["Email", profile.email],
    ["Current Role", profile.current_role || "—"],
    ["Experience", `${profile.years_experience} years`],
    ["Desired Jobs", (profile.desired_roles || []).join(", ") || "—"],
    ["Locations", (profile.preferred_locations || []).join(", ") || "—"],
    ["Remote", profile.remote_preference],
    ["Current Salary", profile.current_salary
      ? `${profile.salary_currency} ${Math.round(profile.current_salary).toLocaleString()}` : "—"],
    ["Expected Hike", `${profile.hike_percent_min}% – ${profile.hike_percent_max}%`],
    ["Expected Range", (profile.salary_min && profile.salary_max)
      ? `${profile.salary_currency} ${Math.round(profile.salary_min).toLocaleString()} – ${Math.round(profile.salary_max).toLocaleString()}` : "—"],
    ["Skills", (profile.skills || []).slice(0, 8).join(", ") || "—"],
    ["Strict Salary Filter", profile.strict_salary_filter ? "On ✓" : "Off"],
    ["Auto-Apply", profile.auto_apply_enabled ? "On ✓" : "Off"],
    ["AI Provider", PROVIDERS[profile.llm_provider]?.label || profile.llm_provider || "—"],
    ["AI Model", profile.llm_model || `(default: ${PROVIDERS[profile.llm_provider]?.default_model || "—"})`],
    ["API Key", profile.llm_api_key ? `Saved (${profile.llm_api_key})` : "Not set"],
  ];
  view.innerHTML = `
    <table class="lg-table">
      ${rows.map(([k, v]) => `<tr><td style="color:var(--lg-text-dim);width:38%">${k}</td><td style="font-weight:600">${escapeHtml(v)}</td></tr>`).join("")}
    </table>
  `;
}

let _profileFetching = false;

async function renderProfile() {
  // If we have a cache, paint it immediately and DO NOT re-fetch unless cache is stale (>30s)
  const view = $("#profileView");
  if (!view) return;

  if (profileCache !== null) {
    paintProfile(profileCache);
    // Only revalidate if last fetch was more than 30s ago AND nothing else is fetching
    const stale = !view.dataset.lastFetch || (Date.now() - parseInt(view.dataset.lastFetch)) > 30000;
    if (!stale || _profileFetching) return;
  } else if (!view.dataset.painted) {
    view.innerHTML = `<div class="lg-shimmer" style="height:280px;border-radius:12px;background:rgba(255,255,255,0.3)"></div>`;
  }

  if (_profileFetching) return;
  _profileFetching = true;

  try {
    const r = await fetch(`${API}/api/profile`);
    const { profile } = await r.json();
    const freshStr = JSON.stringify(profile);
    if (JSON.stringify(profileCache) !== freshStr) {
      profileCache = profile;
      paintProfile(profile);
    }
    view.dataset.painted = "1";
    view.dataset.lastFetch = String(Date.now());
  } catch (e) {
    console.error("renderProfile failed:", e);
  } finally {
    _profileFetching = false;
  }
}

// ─── Settings form ───
async function fillSettingsForm() {
  const r = await fetch(`${API}/api/profile`);
  const { profile } = await r.json();
  const form = $("#profileForm");
  if (!profile) { updateProviderHint(); return; }
  form.name.value = profile.name || "";
  form.email.value = profile.email || "";
  form.current_role.value = profile.current_role || "";
  form.years_experience.value = profile.years_experience || 0;
  form.desired_roles.value = (profile.desired_roles || []).join(", ");
  form.preferred_locations.value = (profile.preferred_locations || []).join(", ");
  form.skills.value = (profile.skills || []).join(", ");
  form.remote_preference.value = profile.remote_preference || "any";
  form.salary_currency.value = profile.salary_currency || "USD";
  form.current_salary.value = profile.current_salary || "";
  form.hike_percent_min.value = profile.hike_percent_min ?? 20;
  form.hike_percent_max.value = profile.hike_percent_max ?? 40;
  form.willing_to_relocate.checked = !!profile.willing_to_relocate;
  form.auto_apply_enabled.checked = profile.auto_apply_enabled !== false;
  form.strict_salary_filter.checked = profile.strict_salary_filter !== false;
  if (form.llm_provider) form.llm_provider.value = profile.llm_provider || "gemini";
  if (form.llm_api_key) {
    form.llm_api_key.value = "";
    form.llm_api_key.placeholder = profile.llm_api_key
      ? `Saved: ${profile.llm_api_key} (paste new to replace)`
      : (PROVIDERS[profile.llm_provider]?.key_hint || "Paste your key");
  }
  // Show currently-saved model in dropdown
  if (form.llm_model) {
    const sel = $("#llmModelSelect");
    if (profile.llm_model) {
      // Inject the saved model as an option even if user hasn't discovered yet
      const exists = [...sel.options].some(o => o.value === profile.llm_model);
      if (!exists) {
        const opt = document.createElement("option");
        opt.value = profile.llm_model;
        opt.textContent = `${profile.llm_model} (saved)`;
        sel.appendChild(opt);
      }
      sel.value = profile.llm_model;
    }
  }
  updateProviderHint();
  updateSalaryPreview();

  const res = await fetch(`${API}/api/resume`);
  const info = await res.json();
  $("#resumeInfo").innerHTML = info.exists
    ? `<strong>${escapeHtml(info.filename)}</strong> · ${Math.round(info.size_bytes/1024)}KB · ${new Date(info.modified).toLocaleString()}`
    : `<span style="color:var(--lg-text-dim)">No resume uploaded yet.</span>`;
}

function updateSalaryPreview() {
  const form = $("#profileForm");
  const cs = parseFloat(form.current_salary.value) || 0;
  const hmin = parseFloat(form.hike_percent_min.value) || 0;
  const hmax = parseFloat(form.hike_percent_max.value) || 0;
  const curr = form.salary_currency.value;
  if (cs > 0) {
    const emin = cs * (1 + hmin / 100);
    const emax = cs * (1 + hmax / 100);
    $("#salaryRangeText").textContent = ` ${curr} ${Math.round(emin).toLocaleString()} – ${Math.round(emax).toLocaleString()}`;
    $("#salaryPreview").hidden = false;
  } else {
    $("#salaryPreview").hidden = true;
  }
}
document.addEventListener("input", e => {
  if (["current_salary","hike_percent_min","hike_percent_max","salary_currency"].includes(e.target.name)) {
    updateSalaryPreview();
  }
});

$("#profileForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  const payload = {
    name: f.name.value,
    email: f.email.value,
    current_role: f.current_role.value || null,
    years_experience: parseInt(f.years_experience.value) || 0,
    desired_roles: f.desired_roles.value.split(",").map(s => s.trim()).filter(Boolean),
    preferred_locations: f.preferred_locations.value.split(",").map(s => s.trim()).filter(Boolean),
    skills: f.skills.value.split(",").map(s => s.trim()).filter(Boolean),
    remote_preference: f.remote_preference.value,
    salary_currency: f.salary_currency.value,
    current_salary: parseFloat(f.current_salary.value),
    hike_percent_min: parseFloat(f.hike_percent_min.value),
    hike_percent_max: parseFloat(f.hike_percent_max.value),
    willing_to_relocate: f.willing_to_relocate.checked,
    auto_apply_enabled: f.auto_apply_enabled.checked,
    strict_salary_filter: f.strict_salary_filter.checked,
    llm_provider: f.llm_provider?.value || "gemini",
    llm_api_key: f.llm_api_key?.value || null,
    llm_model: f.llm_model?.value || null,
  };
  const r = await fetch(`${API}/api/profile`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  if (r.ok) {
    toast("Profile saved");
    profileCache = null;  // invalidate cache so re-render shows the saved data
    renderProfile();
  } else {
    toast("Save failed", "error");
  }
};

$("#resumeForm").onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const submitBtn = e.target.querySelector("button[type='submit']");
  if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "Uploading…"; }

  try {
    const r = await fetch(`${API}/api/resume`, { method: "POST", body: fd });
    if (!r.ok) {
      const err = await r.json();
      toast(err.detail || "Upload failed", "error");
      return;
    }
    const info = await r.json();
    toast(`Resume uploaded (${info.chars} chars)`);

    // Apply AI-suggested profile fields if returned
    if (info.suggested_profile) {
      // First switch to settings, fill form, then re-paint
      activatePanel("settings");
      // Wait one tick for the panel to be visible before filling
      await new Promise(r => setTimeout(r, 50));
      applySuggestedProfile(info.suggested_profile);
      toast("✨ Profile fields auto-filled from resume — review and click Save", "success");
    } else if (info.autofill_status === "no_api_key") {
      toast("Resume uploaded. Add an LLM API key in Settings to auto-fill the form next time", "warning");
      fillSettingsForm();
    } else if (info.autofill_status === "ai_timeout") {
      toast("Resume uploaded but AI autofill timed out — fill the form manually", "warning");
      fillSettingsForm();
    } else {
      toast(`Resume uploaded. AI autofill: ${info.autofill_status || "skipped"}`, "warning");
      fillSettingsForm();
    }
  } finally {
    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = "📄 Upload Resume"; }
  }
};

function applySuggestedProfile(s) {
  const f = $("#profileForm");
  if (!f) {
    console.warn("Profile form not found; cannot apply suggested values");
    return;
  }
  let filled = 0;
  const setIfEmpty = (name, value) => {
    if (!f[name]) return;
    if (value && !f[name].value) {
      f[name].value = value;
      filled++;
    }
  };
  setIfEmpty("name", s.name);
  setIfEmpty("email", s.email);
  setIfEmpty("current_role", s.current_role);
  setIfEmpty("years_experience", s.years_experience);
  setIfEmpty("desired_roles", (s.desired_roles || []).join(", "));
  setIfEmpty("preferred_locations", (s.preferred_locations || []).join(", "));
  setIfEmpty("skills", (s.skills || []).join(", "));
  if (s.remote_preference && f.remote_preference?.value === "any") {
    f.remote_preference.value = s.remote_preference;
    filled++;
  }
  console.log(`applySuggestedProfile: filled ${filled} field(s)`);
  $("#profileForm")?.scrollIntoView({behavior: "smooth", block: "start"});
}

// ─── Applications ───
async function renderApplications(status = null) {
  if (status !== null) { appsState.status = status; appsState.page = 1; }
  const qs = appsState.status && appsState.status !== "all" ? `?status=${appsState.status}` : "";
  const r = await fetch(`${API}/api/applications${qs}`);
  const { applications } = await r.json();
  appsState.all = applications;
  renderAppsPage();
}

function renderAppsPage() {
  const list = $("#appsList");
  const { all, page } = appsState;
  if (!all.length) {
    list.innerHTML = `<div style="padding:40px;text-align:center;color:var(--lg-text-dim)">No applications above 50 score yet.</div>`;
    return;
  }
  const totalPages = Math.max(1, Math.ceil(all.length / APPS_PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const start = (currentPage - 1) * APPS_PAGE_SIZE;
  const slice = all.slice(start, start + APPS_PAGE_SIZE);

  const rows = slice.map(a => {
    const isApplied = a.status === "auto_applied" || a.status === "semi_auto_applied";
    const tierClass = a.match_score >= 85 ? "auto" : (a.match_score >= 70 ? "semi_auto" : "manual");
    const pill = isApplied ? "green" : (a.status === "pending" ? "yellow" : "red");
    const action = isApplied
      ? `<span style="color:#16a34a;font-weight:600">✓ Applied</span>`
      : `<button class="lg-btn small mark-applied" data-id="${a.id}">Mark Applied</button>`;
    return `
      <tr>
        <td>${escapeHtml(a.job_title)}</td>
        <td style="color:var(--lg-text-dim)">${escapeHtml(a.company)}</td>
        <td><span class="lg-job-score ${tierClass}" style="font-size:16px">${a.match_score}</span></td>
        <td><span class="lg-pill ${pill}">${escapeHtml(a.status.replace(/_/g," "))}</span></td>
        <td style="color:var(--lg-text-dim);font-size:13px">${a.created_at ? new Date(a.created_at).toLocaleDateString() : "—"}</td>
        <td>${action}</td>
      </tr>
    `;
  }).join("");

  list.innerHTML = `
    <div style="overflow-x:auto;border-radius:12px;border:1px solid rgba(15,23,42,0.06)">
      <table class="lg-table">
        <thead><tr>
          <th>Job Title</th><th>Company</th><th>Score</th><th>Status</th><th>Date</th><th>Actions</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;margin-top:14px">
      <button class="lg-btn" id="appsPrev" ${currentPage <= 1 ? "disabled" : ""}>← Prev</button>
      <span style="color:var(--lg-text-dim);font-size:13px">Page ${currentPage} of ${totalPages} · ${all.length} total (score &gt; 50)</span>
      <button class="lg-btn" id="appsNext" ${currentPage >= totalPages ? "disabled" : ""}>Next →</button>
    </div>
  `;

  const prev = $("#appsPrev"), next = $("#appsNext");
  if (prev) prev.onclick = () => { appsState.page = Math.max(1, appsState.page - 1); renderAppsPage(); };
  if (next) next.onclick = () => { appsState.page = Math.min(totalPages, appsState.page + 1); renderAppsPage(); };

  $$(".mark-applied").forEach(btn => {
    btn.onclick = async () => {
      btn.disabled = true; btn.textContent = "Marking…";
      try {
        const r = await fetch(`${API}/api/applications/${btn.dataset.id}/status`, {
          method: "PATCH",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({status: "auto_applied", notes: "Marked applied externally via UI"}),
        });
        if (!r.ok) throw new Error();
        toast("Marked as applied");
        renderApplications();
      } catch { toast("Failed", "error"); btn.disabled = false; btn.textContent = "Mark Applied"; }
    };
  });
}

$$(".sub-btn").forEach(btn => {
  btn.onclick = () => {
    $$(".sub-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    renderApplications(btn.dataset.status);
  };
});

// ─── Auth ───
async function loadAuthState() {
  try {
    const r = await fetch(`${API}/api/auth/me`);
    const { user } = await r.json();
    if (!user) { location.href = "/login"; return; }
    const av = $("#userAvatar");
    if (av) av.textContent = (user.name || user.email)[0].toUpperCase();
  } catch (e) { console.error("Auth check failed", e); }
}
$("#btnLogout").onclick = async () => {
  await fetch(`${API}/api/auth/logout`, { method: "POST" });
  location.href = "/";
};

loadAuthState();
renderProfile();
