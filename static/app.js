"use strict";
/* فرانت‌اند مأموریت نجات — هیچ منطق بازی اینجا نیست؛ همه‌چیز از API سرور می‌آید. */
const $ = id => document.getElementById(id);
const FA = "۰۱۲۳۴۵۶۷۸۹";
const faNum = n => String(n).replace(/\d/g, d => FA[d]);
const faPct = n => faNum(Math.round(n)) + "٪";
const LEVEL_NAME = { normal: "عادی", urgent: "فوری", critical: "بحرانی" };
const LEVEL_COLOR = { critical: "#d64545", urgent: "#e8a13a", normal: "#2f9e6e" };
const LEVEL_EMOJI = { critical: "🆘", urgent: "🤕", normal: "🧑" };

let META = null;
let rules = [
  { id: "full", action: "toBase" },
  { id: "batteryBelow", threshold: 30, action: "toCharger" },
  { id: "criticalNear", threshold: 3, action: "rescueUrgent" }
];
let mapSeed = 7;
let trace = null;          // نتیجهٔ کامل شبیه‌سازی از سرور
let stepIdx = 0;           // قدم فعلی نمایش
let playing = false, playTimer = null;
let replayMode = false, rpIdx = 0, rpTimer = null;
let stage = 1;
let adminCode = null;      // رمز ادمین در حافظهٔ همین جلسه
let compareResult = null;
let dualIdx = 0, dualTimer = null;

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json", ...(opts.headers || {}) }, ...opts });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "خطا در ارتباط با سرور");
  return data;
}
const adminHeaders = () => adminCode ? { "X-Admin-Code": adminCode } : {};

/* ---------- رندر تخته روی Canvas ---------- */
function drawBoard(canvas, map, step, trail) {
  const ctx = canvas.getContext("2d");
  const W = canvas.width, cell = W / 12;
  const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const cellBg = dark ? "#1b2b31" : "#e8efec";
  const line = dark ? "#26383f" : "#d3ddd8";
  ctx.clearRect(0, 0, W, W);
  const obstacles = new Set(map.obstacles), danger = new Set(map.danger);
  for (let y = 0; y < 12; y++) for (let x = 0; x < 12; x++) {
    const k = y * 12 + x;
    const px = x * cell, py = y * cell;
    // گرادیان ملایم هر خانه
    const g = ctx.createLinearGradient(px, py, px + cell, py + cell);
    if (obstacles.has(k)) { g.addColorStop(0, "#8b9a94"); g.addColorStop(1, "#6f7f79"); }
    else if (danger.has(k)) { g.addColorStop(0, "#f6d9c8"); g.addColorStop(1, "#eec3a8"); }
    else if (x === map.base.x && y === map.base.y) { g.addColorStop(0, "#bfe3e8"); g.addColorStop(1, "#8fcbd4"); }
    else if (map.chargers.some(c => c.x === x && c.y === y)) { g.addColorStop(0, "#fbe7b8"); g.addColorStop(1, "#f2cd7e"); }
    else { g.addColorStop(0, cellBg); g.addColorStop(1, dark ? "#16242a" : "#dce7e1"); }
    ctx.fillStyle = g;
    ctx.fillRect(px + 1, py + 1, cell - 2, cell - 2);
    if (danger.has(k) && !obstacles.has(k)) {
      ctx.strokeStyle = "rgba(214,69,69,.45)"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(px + 6, py + cell - 6); ctx.lineTo(px + cell - 6, py + 6); ctx.stroke();
    }
    ctx.strokeStyle = line; ctx.lineWidth = 1;
    ctx.strokeRect(px + .5, py + .5, cell - 1, cell - 1);
  }
  // ردّ مسیر ربات
  if (trail && trail.length > 1) {
    ctx.strokeStyle = "rgba(228,87,46,.55)"; ctx.lineWidth = 3; ctx.lineJoin = "round";
    ctx.beginPath();
    trail.forEach((p, i) => { const cx = (p.x + .5) * cell, cy = (p.y + .5) * cell; i ? ctx.lineTo(cx, cy) : ctx.moveTo(cx, cy); });
    ctx.stroke();
  }
  const emoji = (ch, cx, cy, size) => { ctx.font = `${size}px sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(ch, cx, cy + 1); };
  // پایگاه و شارژر
  emoji("🏠", (map.base.x + .5) * cell, (map.base.y + .5) * cell, cell * .62);
  map.chargers.forEach(c => emoji("⚡", (c.x + .5) * cell, (c.y + .5) * cell, cell * .58));
  // مصدومان
  (step.survivors || []).forEach(s => {
    if (s.picked || s.delivered) return;
    const cx = (s.x + .5) * cell, cy = (s.y + .5) * cell;
    ctx.beginPath(); ctx.arc(cx, cy, cell * .36, 0, Math.PI * 2);
    ctx.fillStyle = LEVEL_COLOR[s.level]; ctx.globalAlpha = .25; ctx.fill(); ctx.globalAlpha = 1;
    ctx.strokeStyle = LEVEL_COLOR[s.level]; ctx.lineWidth = 2; ctx.stroke();
    emoji(LEVEL_EMOJI[s.level], cx, cy, cell * .5);
  });
  // ربات با سایه
  const rx = (step.robot.x + .5) * cell, ry = (step.robot.y + .5) * cell;
  ctx.beginPath(); ctx.ellipse(rx, ry + cell * .28, cell * .34, cell * .12, 0, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0,0,0,.25)"; ctx.fill();
  ctx.beginPath(); ctx.arc(rx, ry, cell * .36, 0, Math.PI * 2);
  ctx.fillStyle = "#e4572e"; ctx.fill();
  ctx.strokeStyle = "#fff"; ctx.lineWidth = 2.5; ctx.stroke();
  emoji("🤖", rx, ry, cell * .52);
  // نشان تعداد حمل‌شده
  if (step.carrying && step.carrying.length) {
    ctx.beginPath(); ctx.arc(rx + cell * .3, ry - cell * .3, cell * .2, 0, Math.PI * 2);
    ctx.fillStyle = "#0b7285"; ctx.fill(); ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = "#fff"; ctx.font = `bold ${cell * .28}px sans-serif`;
    ctx.fillText(faNum(step.carrying.length), rx + cell * .3, ry - cell * .3 + 1);
  }
}

function renderHUD(step, map) {
  $("hudScore").textContent = faNum(step.score);
  $("hudRescued").textContent = faNum(step.deliveredCount) + " از " + faNum(step.survivors.length);
  $("hudCarry").textContent = faNum(step.carrying.length) + " از " + faNum(map ? (META.settings.capacity) : 2);
  $("hudTime").textContent = faNum(step.time) + " از " + faNum(META.settings.maxTime);
  $("hudBattTxt").textContent = faPct(Math.max(0, step.battery));
  const fill = $("hudBatt");
  fill.style.width = Math.max(0, step.battery) + "%";
  fill.className = "batt-fill" + (step.battery < 25 ? " low" : step.battery < 50 ? " mid" : "");
}

function showStep(idx) {
  if (!trace) return;
  stepIdx = Math.max(0, Math.min(trace.steps.length - 1, idx));
  const step = trace.steps[stepIdx];
  const trail = trace.steps.slice(0, stepIdx + 1).map(s => s.robot);
  drawBoard($("board"), trace.map, step, trail);
  renderHUD(step, trace.map);
  renderInspector(step.decision, step.time);
  renderMissionMsg(step);
  $("replayBtn").disabled = trace.steps.length < 2;
  $("rpSlider").max = trace.steps.length - 1;
}

function renderMissionMsg(step) {
  const m = $("missionMsg");
  if (!step.over) { m.className = "mission-msg"; m.textContent = ""; return; }
  if (step.result === "win") {
    m.className = "mission-msg win";
    m.textContent = "مأموریت کامل شد! همهٔ مصدومان نجات یافتند. امتیاز: " + faNum(step.score) + " — حالا استراتژی‌ات را عوض کن و دوباره امتحان کن؛ آیا می‌توانی با باتری و زمان کمتر هم موفق شوی؟";
  } else if (step.result === "battery") {
    m.className = "mission-msg lose";
    m.textContent = "باتری ربات تمام شد و مأموریت ناتمام ماند. در بازرس تصمیم قدم‌های آخر را ببین: آیا قانون شارژ باید اولویت بالاتری می‌داشت؟";
  } else {
    m.className = "mission-msg lose";
    m.textContent = "زمان مأموریت تمام شد. مصدوم تحویل‌شده: " + faNum(step.deliveredCount) + " از " + faNum(step.survivors.length) + ". شاید اولویت‌بندی قانون‌ها نیاز به بازنگری دارد.";
  }
}

function renderInspector(dec, snapTime) {
  const obsList = $("obsList"), checkList = $("checkList"), chosen = $("chosenBox");
  if (!dec) {
    obsList.innerHTML = '<li><span>وضعیت ربات</span><b>آمادهٔ شروع</b></li>';
    checkList.innerHTML = ""; chosen.textContent = "";
    document.querySelectorAll(".rule-card").forEach(c => c.classList.remove("active"));
    return;
  }
  const o = dec.obs || {};
  const fmtD = d => d === null || d === undefined ? "—" : faNum(d) + " خانه";
  obsList.innerHTML =
    '<li><span>باتری</span><b>' + faPct(o.battery ?? 0) + '</b></li>' +
    '<li><span>ظرفیت حمل</span><b>' + faNum(o.carrying ?? 0) + " از " + faNum(o.capacity ?? 2) + '</b></li>' +
    '<li><span>نزدیک‌ترین مصدوم</span><b>' + (o.nearestD == null ? "مصدومی نمانده" : fmtD(o.nearestD) + (o.nearestLevel ? " (" + LEVEL_NAME[o.nearestLevel] + ")" : "")) + '</b></li>' +
    '<li><span>مصدوم بحرانی</span><b>' + (o.critD == null ? "ندارد" : fmtD(o.critD)) + '</b></li>' +
    '<li><span>فاصله تا پایگاه</span><b>' + fmtD(o.baseD) + ' (هزینهٔ باتری: ' + faNum(o.baseCost ?? 0) + ')</b></li>' +
    '<li><span>مصدوم فوری نزدیک</span><b>' + (o.urgD == null ? "ندارد" : fmtD(o.urgD)) + '</b></li>' +
    '<li><span>فاصله تا نزدیک‌ترین شارژر</span><b>' + (o.chargerD == null ? "—" : fmtD(o.chargerD)) + '</b></li>' +
    '<li><span>زمان</span><b>' + faNum(snapTime ?? 0) + ' (باقی‌مانده: ' + faNum(Math.max(0, o.timeLeft ?? 0)) + ' قدم)</b></li>';
  checkList.innerHTML = "";
  (dec.evals || []).forEach((e, i) => {
    const div = document.createElement("div");
    let cls, badge;
    if (dec.ruleIndex === i) { cls = "yes"; badge = "بله ← اجرا شد"; }
    else if (dec.ruleIndex !== -1 && i > dec.ruleIndex) { cls = "skip"; badge = "نرسید"; }
    else { cls = e.match ? "yes" : "no"; badge = e.match ? "بله" : "خیر"; }
    div.className = "check " + cls;
    div.innerHTML = '<span class="badge">' + badge + '</span><span><b>قانون ' + faNum(i + 1) + ":</b> " + e.label + "؟</span>";
    checkList.appendChild(div);
  });
  const actLabel = id => (META.actions.find(a => a.id === id) || {}).label || id;
  chosen.textContent = dec.fallback
    ? "هیچ قانونی برقرار نبود ← رفتار پیش‌فرض: " + actLabel(dec.actionId)
    : "قانون " + faNum(dec.ruleIndex + 1) + " فعال شد ← اقدام: " + actLabel(dec.actionId);
  if (dec.ineffective && dec.event) chosen.textContent += " — " + dec.event;
  document.querySelectorAll(".rule-card").forEach((c, i) => c.classList.toggle("active", i === dec.ruleIndex));
  const log = $("decisionLog");
  const li = document.createElement("li");
  li.innerHTML = "<b>قدم " + faNum(snapTime ?? 0) + ":</b> " + (dec.fallback ? "پیش‌فرض" : "قانون " + faNum(dec.ruleIndex + 1)) + " ← " + actLabel(dec.actionId) + (dec.event ? " — " + dec.event : "");
  log.prepend(li);
  while (log.children.length > 40) log.lastChild.remove();
}

/* ---------- سازنده استراتژی ---------- */
function condDef(id) { return META.conditions.find(c => c.id === id); }
function ruleNum(rule) {
  const def = condDef(rule.id);
  if (!def || !def.param) return null;
  let v = rule.threshold;
  if (v === undefined || v === null) v = rule.value;
  v = Number(v);
  if (!isFinite(v)) v = def.param.def;
  return Math.min(def.param.max, Math.max(def.param.min, Math.round(v)));
}
function renderRules() {
  const list = $("rulesList"); list.innerHTML = "";
  rules.forEach((r, i) => {
    const card = document.createElement("div"); card.className = "rule-card";
    const condOpts = META.conditions.map(c => '<option value="' + c.id + '"' + (c.id === r.id ? " selected" : "") + ">" + c.label + "</option>").join("");
    const actOpts = META.actions.map(a => '<option value="' + a.id + '"' + (a.id === r.action ? " selected" : "") + ">" + a.label + "</option>").join("");
    const cond = condDef(r.id);
    let thresh = "";
    if (cond.param) {
      const p = cond.param;
      thresh = '<div class="thresh-row"><span>' + p.inputLabel + '</span>' +
        '<input type="number" data-thresh="' + i + '" value="' + ruleNum(r) + '" min="' + p.min + '" max="' + p.max + '" step="' + p.step + '" aria-label="عدد شرط قانون ' + faNum(i + 1) + '" />' +
        '<span class="unit">' + p.unit + '</span>' +
        '<span>(پیش‌فرض: ' + faNum(p.def) + ')</span></div>';
    }
    card.innerHTML =
      '<div class="rule-head"><span class="prio">' + faNum(i + 1) + '</span><span class="rtitle">قانون ' + faNum(i + 1) + '</span>' +
      '<span class="rule-tools">' +
      '<button class="icon-btn" data-up="' + i + '" type="button" aria-label="بالا بردن اولویت" ' + (i === 0 ? "disabled" : "") + '>↑</button>' +
      '<button class="icon-btn" data-down="' + i + '" type="button" aria-label="پایین بردن اولویت" ' + (i === rules.length - 1 ? "disabled" : "") + '>↓</button>' +
      '<button class="icon-btn del" data-del="' + i + '" type="button" aria-label="حذف قانون">✕</button></span></div>' +
      '<div class="ifthen"><span class="tag if">اگر</span><select data-cond="' + i + '" aria-label="شرط قانون ' + faNum(i + 1) + '">' + condOpts + '</select>' + thresh +
      '<span class="tag then">آنگاه</span><select data-act="' + i + '" aria-label="اقدام قانون ' + faNum(i + 1) + '">' + actOpts + '</select></div>';
    list.appendChild(card);
  });
  list.querySelectorAll("[data-cond]").forEach(s => s.addEventListener("change", e => {
    const i = Number(e.target.dataset.cond); rules[i].id = e.target.value;
    const d = condDef(rules[i].id);
    if (d && d.param) rules[i].threshold = d.param.def; else delete rules[i].threshold;
    renderRules();
  }));
  list.querySelectorAll("[data-act]").forEach(s => s.addEventListener("change", e => { rules[Number(e.target.dataset.act)].action = e.target.value; }));
  list.querySelectorAll("[data-thresh]").forEach(s => s.addEventListener("change", e => {
    const i = Number(e.target.dataset.thresh);
    const def = condDef(rules[i].id);
    rules[i].threshold = Math.min(def.param.max, Math.max(def.param.min, Math.round(Number(e.target.value))));
    e.target.value = rules[i].threshold;
  }));
  list.querySelectorAll("[data-up]").forEach(b => b.addEventListener("click", () => { const i = Number(b.dataset.up); [rules[i - 1], rules[i]] = [rules[i], rules[i - 1]]; renderRules(); }));
  list.querySelectorAll("[data-down]").forEach(b => b.addEventListener("click", () => { const i = Number(b.dataset.down); [rules[i + 1], rules[i]] = [rules[i], rules[i + 1]]; renderRules(); }));
  list.querySelectorAll("[data-del]").forEach(b => b.addEventListener("click", () => { rules.splice(Number(b.dataset.del), 1); renderRules(); }));
  $("ruleCount").innerHTML = faNum(rules.length) + " قانون تعریف شده — " + (rules.length ? "<b>استراتژی آماده است</b>" : "هنوز قانونی نداری؛ ربات فقط با رفتار پیش‌فرض کار می‌کند.");
}

function renderPresets() {
  const row = $("presetRow"); row.innerHTML = "";
  const show = META.showPresets;
  row.style.display = show ? "" : "none";
  $("presetNote").style.display = show ? "" : "none";
  if (!show) return;
  META.presets.forEach(p => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "preset";
    if (p.id === "7") { b.style.gridColumn = "1 / -1"; b.style.borderColor = "var(--orange)"; }
    b.innerHTML = "<b></b><small></small>";
    b.querySelector("b").textContent = (p.id === "7" ? "🏆 " : "") + p.name;
    b.querySelector("small").textContent = p.desc;
    b.addEventListener("click", () => { rules = JSON.parse(JSON.stringify(p.rules)); renderRules(); });
    row.appendChild(b);
  });
}

async function renderSaved() {
  const items = (await api("/api/strategies")).strategies;
  const box = $("savedList"); box.innerHTML = "";
  items.forEach(s => {
    const div = document.createElement("div"); div.className = "saved-item";
    div.innerHTML = '<span class="nm"></span><span class="cnt">' + faNum(s.rules.length) + ' قانون</span><span class="sp"></span>' +
      '<button class="btn small" type="button">بارگذاری</button><button class="icon-btn del" type="button" aria-label="حذف استراتژی ذخیره‌شده">✕</button>';
    div.querySelector(".nm").textContent = s.name;
    div.querySelector(".btn").addEventListener("click", () => { rules = JSON.parse(JSON.stringify(s.rules)); renderRules(); });
    div.querySelector(".del").addEventListener("click", async () => { await api("/api/strategies/" + encodeURIComponent(s.name), { method: "DELETE" }); renderSaved(); });
    box.appendChild(div);
  });
}

$("addRule").addEventListener("click", () => { rules.push({ id: "survivorNear", threshold: 3, action: "rescueNearest" }); renderRules(); });
$("checkStrategy").addEventListener("click", async () => {
  const data = await api("/api/simulate", { method: "POST", body: JSON.stringify({ rules, seed: mapSeed }) });
  $("warnBox").innerHTML = data.warnings.length ? data.warnings.map(w => "⚠ " + w).join("<br>") : "✓ استراتژی‌ات از نظر منطقی سالم است. حالا اجرایش کن و نتیجه را ببین!";
});
$("saveStrat").addEventListener("click", async () => {
  const name = $("stratName").value.trim() || "استراتژی";
  await api("/api/strategies", { method: "POST", body: JSON.stringify({ name, rules }) });
  $("stratName").value = ""; renderSaved();
});

/* ---------- اجرای مأموریت ---------- */
async function loadTrace(seed) {
  if (seed !== undefined) mapSeed = seed;
  stopPlay(); exitReplay();
  $("decisionLog").innerHTML = "";
  trace = await api("/api/simulate", { method: "POST", body: JSON.stringify({ rules, seed: mapSeed }) });
  stepIdx = 0;
  showStep(0);
}
function stopPlay() { playing = false; if (playTimer) { clearInterval(playTimer); playTimer = null; } $("playBtn").textContent = "▶ اجرای آزمایشی"; }
function startPlay() {
  if (!trace || trace.steps[trace.steps.length - 1].over && stepIdx >= trace.steps.length - 1) return;
  playing = true; $("playBtn").textContent = "⏸ توقف";
  playTimer = setInterval(() => {
    if (stepIdx >= trace.steps.length - 1) { stopPlay(); return; }
    showStep(stepIdx + 1);
  }, Number($("speedSel").value));
}
$("playBtn").addEventListener("click", () => playing ? stopPlay() : startPlay());
$("stepBtn").addEventListener("click", () => { stopPlay(); showStep(stepIdx + 1); });
$("speedSel").addEventListener("change", () => { if (playing) { stopPlay(); startPlay(); } });
$("resetBtn").addEventListener("click", () => loadTrace());
$("newMapBtn").addEventListener("click", () => loadTrace(Math.floor(Math.random() * 90000) + 10));

/* ---------- بازپخش ---------- */
function enterReplay() {
  if (!trace || trace.steps.length < 2) return;
  stopPlay(); replayMode = true; rpIdx = 0;
  $("replayBar").classList.add("on");
  $("rpSlider").max = trace.steps.length - 1;
  showReplay();
}
function exitReplay() {
  replayMode = false; if (rpTimer) { clearInterval(rpTimer); rpTimer = null; }
  $("replayBar").classList.remove("on"); $("rpPlay").textContent = "پخش";
}
function showReplay() {
  const step = trace.steps[rpIdx]; if (!step) return;
  const trail = trace.steps.slice(0, rpIdx + 1).map(s => s.robot);
  drawBoard($("board"), trace.map, step, trail);
  renderHUD(step, trace.map);
  $("rpSlider").value = rpIdx;
  const actLabel = id => (META.actions.find(a => a.id === id) || {}).label || id;
  $("replayInfo").textContent = "قدم " + faNum(rpIdx) + " از " + faNum(trace.steps.length - 1) + (step.decision ? " — " + (step.decision.fallback ? "رفتار پیش‌فرض" : "قانون " + faNum(step.decision.ruleIndex + 1)) + ": " + actLabel(step.decision.actionId) : " — شروع مأموریت");
  if (step.decision) renderInspector(step.decision, step.time); else renderInspector(null);
}
$("replayBtn").addEventListener("click", enterReplay);
$("replayExit").addEventListener("click", () => { exitReplay(); showStep(stepIdx); });
$("rpSlider").addEventListener("input", e => { rpIdx = Number(e.target.value); showReplay(); });
$("rpPrev").addEventListener("click", () => { rpIdx = Math.max(0, rpIdx - 1); showReplay(); });
$("rpNext").addEventListener("click", () => { rpIdx = Math.min(trace.steps.length - 1, rpIdx + 1); showReplay(); });
$("rpPlay").addEventListener("click", () => {
  if (rpTimer) { clearInterval(rpTimer); rpTimer = null; $("rpPlay").textContent = "پخش"; return; }
  if (rpIdx >= trace.steps.length - 1) rpIdx = 0;
  $("rpPlay").textContent = "توقف";
  rpTimer = setInterval(() => {
    rpIdx++;
    if (rpIdx >= trace.steps.length - 1) { rpIdx = trace.steps.length - 1; clearInterval(rpTimer); rpTimer = null; $("rpPlay").textContent = "پخش"; }
    showReplay();
  }, 420);
});

/* ---------- تغییر محیط و سناریوها ---------- */
function shockLabelText(scenario, diffs) {
  return diffs.map(d => (META.shockLabels[d.key] || d.key) + " " + faNum(d.from) + " ← " + faNum(d.to)).join("، ");
}
function showShockBanner(scenario, diffs, restored) {
  const banner = $("shockBanner");
  if (restored) {
    banner.className = "shock-banner restored";
    banner.innerHTML = '<div class="shock-title">↩ به محیط عادی برگشتیم</div><p>همهٔ پارامترها به مقدارهای پیش‌فرض برگشتند و مأموریت تازه از اول شروع شد.</p>';
  } else {
    banner.className = "shock-banner";
    banner.innerHTML =
      '<div class="shock-title">⚠ محیط ناگهان عوض شد! — ' + scenario.title + '</div>' +
      '<div class="shock-changes">چه چیزهایی عوض شد؟<br>' + shockLabelText(scenario, diffs) + '</div>' +
      '<p><b>استراتژی قبلی‌ات دیگر تضمین‌شده نیست.</b> قانون‌هایت را دست نزدیم تا خودت ببینی در محیط جدید چطور عمل می‌کنند.</p>' +
      '<p><b>یادآوری دربارهٔ عامل یادگیرنده:</b> عامل یادگیرنده هم روی محیط قبلی آموزش دیده است؛ تا دکمهٔ «یادگیری دوباره در محیط جدید» را نزنی، امتیازش در این محیط تازه احتمالاً افت می‌کند.</p>';
  }
  banner.hidden = false;
}
$("shockBtn").addEventListener("click", async () => {
  const data = await api("/api/shock", { method: "POST", body: JSON.stringify({}) });
  META.settings = data.settings;
  $("restoreEnvBtn").disabled = false;
  await loadTrace(Math.floor(Math.random() * 90000) + 10);
  showShockBanner(data.scenario, data.changes, false);
  $("evalNote").textContent = "محیط عوض شده است! اول مأموریت را با همین قانون‌های فعلی اجرا کن و افت نتیجه را ببین.";
});
$("restoreEnvBtn").addEventListener("click", async () => {
  const data = await api("/api/restore-env", { method: "POST", body: JSON.stringify({}) });
  META.settings = data.settings;
  $("restoreEnvBtn").disabled = true;
  await loadTrace(Math.floor(Math.random() * 90000) + 10);
  showShockBanner(null, [], true);
});

async function renderScenarios() {
  const data = await api("/api/scenarios");
  const box = $("scenarioList"); box.innerHTML = "";
  data.all.forEach((sc, i) => {
    const card = document.createElement("div"); card.className = "scn-card";
    const changesTxt = Object.entries(sc.changes).map(([k, v]) => (META.shockLabels[k] || k) + ": " + faNum(v)).join("، ");
    card.innerHTML = '<div class="row"><b></b><span style="flex:1"></span><button class="btn small primary" type="button">اعمال</button></div><div class="note" style="margin-top:6px"></div>';
    card.querySelector("b").textContent = sc.title;
    card.querySelector(".note").textContent = changesTxt;
    card.querySelector("button").addEventListener("click", async () => {
      const res = await api("/api/shock", { method: "POST", body: JSON.stringify({ index: i }) });
      META.settings = res.settings;
      $("restoreEnvBtn").disabled = false;
      await loadTrace(Math.floor(Math.random() * 90000) + 10);
      showShockBanner(res.scenario, res.changes, false);
    });
    box.appendChild(card);
  });
}
$("scnNewBtn").addEventListener("click", async () => {
  const name = $("scnNewName").value.trim() || "سناریوی تازه";
  const data = await api("/api/scenarios");
  const customs = data.customs.concat([{ title: name, changes: { capacity: 1 } }]);
  await api("/api/scenarios", { method: "PUT", headers: adminHeaders(), body: JSON.stringify({ edited: data.edited, customs }) });
  $("scnNewName").value = "";
  $("scenarioMsg").textContent = "سناریوی تازهٔ «" + name + "» ذخیره شد.";
  renderScenarios();
});

/* ---------- مرحله‌بندی ---------- */
function applyStage(s) {
  stage = s;
  try { if (s === 2) localStorage.setItem("rescueMission.stage.v1", "2"); else localStorage.removeItem("rescueMission.stage.v1"); } catch (e) {}
  $("comparePanel").classList.toggle("hidden", s !== 2);
  $("stageLockCard").classList.toggle("hidden", s === 2);
  $("stageBadge").textContent = s === 2 ? "مرحله ۲: آزمایش و مقایسه" : "مرحله ۱: ساخت استراتژی";
  if (s === 2) { $("comparePanel").open = true; refreshTrainStatus(); }
}
$("stageUnlockBtn").addEventListener("click", async () => {
  try {
    await api("/api/unlock", { method: "POST", body: JSON.stringify({ code: $("stageCodeInput").value, kind: "stage" }) });
    $("stageCodeErr").textContent = ""; $("stageCodeInput").value = "";
    applyStage(2);
  } catch (e) { $("stageCodeErr").textContent = "رمز درست نیست — از آموزگار بپرس."; }
});
$("stageCodeInput").addEventListener("keydown", e => { if (e.key === "Enter") $("stageUnlockBtn").click(); });

/* ---------- آزمایش بزرگ ---------- */
function drawCurve(curve) {
  const c = $("trainChart"), ctx = c.getContext("2d");
  ctx.clearRect(0, 0, c.width, c.height);
  if (curve.length < 2) return;
  const min = Math.min(...curve), max = Math.max(...curve), rng = (max - min) || 1;
  ctx.strokeStyle = "#0b7285"; ctx.lineWidth = 2.5; ctx.beginPath();
  curve.forEach((v, i) => {
    const x = i / (curve.length - 1) * (c.width - 8) + 4;
    const y = c.height - 12 - (v - min) / rng * (c.height - 30);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.stroke();
  ctx.fillStyle = "#888"; ctx.font = "16px sans-serif";
  ctx.fillText("میانگین پاداش در هر ۲۵ مأموریت تمرینی", 8, 18);
}
function renderModelStrategy(list) {
  const box = $("modelStrategy");
  if (!list || !list.length) { box.innerHTML = '<p class="note">هنوز چیزی برای نمایش نیست — اول عامل یادگیرنده را آموزش بده.</p>'; return; }
  box.innerHTML = '<div class="model-list">' + list.map(r =>
    '<div class="model-row"><span class="if-part">اگر ' + r.phrase + '</span> ← <span class="then-part">آنگاه: ' + r.actionLabel + '</span></div>').join("") + '</div>';
}
async function refreshTrainStatus() {
  const s = await api("/api/train/status");
  $("trainProg").style.width = s.trained ? "100%" : "0%";
  $("trainInfo").textContent = s.trained
    ? "آموزش تمام شد: " + faNum(s.episodes) + " مأموریت تمرینی، " + faNum(s.states) + " حالت در جدول یادگیری." + (s.bestValidationScore != null ? " بهترین امتیاز اعتبارسنجی: " + faNum(Number(s.bestValidationScore).toFixed(1)) : "")
    : "هنوز آموزشی انجام نشده است.";
  drawCurve(s.curve);
  renderModelStrategy(s.modelStrategy);
  $("evalBtn").disabled = !s.trained;
  $("finetuneBtn").disabled = !s.trained;
  $("trainBtn").textContent = "آموزش عامل یادگیرنده (" + faNum(META.settings.trainEpisodes) + " مأموریت تمرینی)";
  $("evalBtn").textContent = "اجرای مقایسه روی " + faNum(META.settings.evalMaps) + " نقشهٔ یکسان";
  $("evalMapsLbl").textContent = faNum(META.settings.evalMaps) + " نقشهٔ یکسان";
}
$("trainBtn").addEventListener("click", async () => {
  $("trainBtn").disabled = true; $("trainBtn").textContent = "⏳ در حال آموزش…";
  $("trainInfo").textContent = "در حال آموزش… این کار چند ثانیه طول می‌کشد.";
  try {
    const s = await api("/api/train", { method: "POST", body: JSON.stringify({}) });
    $("trainInfo").textContent = "آموزش تمام شد: " + faNum(s.episodes) + " مأموریت تمرینی، " + faNum(s.states) + " حالت در جدول یادگیری. بهترین امتیاز اعتبارسنجی: " + faNum(Number(s.bestValidationScore).toFixed(1)) + (s.restoredBest ? " (بهترین نسخهٔ دیده‌شده حفظ شد.)" : "");
    drawCurve(s.curve);
    renderModelStrategy(s.modelStrategy);
    $("evalBtn").disabled = false; $("finetuneBtn").disabled = false;
  } finally { $("trainBtn").disabled = false; $("trainBtn").textContent = "آموزش عامل یادگیرنده (" + faNum(META.settings.trainEpisodes) + " مأموریت تمرینی)"; }
});
$("resetTrainBtn").addEventListener("click", async () => {
  await api("/api/train/reset", { method: "POST", body: JSON.stringify({}) });
  refreshTrainStatus();
  $("evalOut").innerHTML = ""; $("dualBoards").classList.add("hidden");
});
function renderCompare(data) {
  const total = META.settings.survivorsCritical + META.settings.survivorsUrgent + META.settings.survivorsNormal;
  const rows = [
    { name: "استراتژی تو", color: "var(--orange)", r: data.human },
    { name: "عامل یادگیرنده", color: "var(--teal)", r: data.rl }
  ];
  const maxScore = Math.max(...rows.map(x => x.r.score)) || 1;
  let html = '<table class="results"><tr><th>عامل</th><th>میانگین امتیاز</th><th>مصدوم نجات‌یافته (از ' + faNum(total) + ')</th><th>تکمیل مأموریت</th><th>باتری باقی‌مانده</th><th>زمان مصرفی</th></tr>';
  rows.forEach(row => {
    html += "<tr><td>" + row.name + "</td><td>" + faNum(row.r.score.toFixed(1)) + "</td><td>" + faNum(row.r.rescued.toFixed(1)) + "</td><td>" + faPct(row.r.winRate) + "</td><td>" + faPct(row.r.battery) + "</td><td>" + faNum(Math.round(row.r.time)) + "</td></tr>";
  });
  html += "</table>";
  html += '<div class="bars">' + rows.map(row =>
    '<div class="bar-row"><span>' + row.name + '</span><div class="bar-track"><div class="bar-fill" style="width:' + Math.round(row.r.score / maxScore * 100) + '%; background:' + row.color + '"></div></div><b>' + faNum(row.r.score.toFixed(1)) + "</b></div>").join("") + "</div>";
  html += '<p class="note" style="margin-top:10px">محیط آزمایش: ظرفیت حمل ' + faNum(data.capacity) + ' نفر — هر دو عامل دقیقاً روی همان ' + faNum(data.evalMaps) + ' نقشه (بذرهای یکسان) اجرا شدند.</p>';
  $("evalOut").innerHTML = html;
  $("evalNote").textContent = data.capacity === 1
    ? "ظرفیت حمل حالا ۱ نفر است: ربات باید مدام به پایگاه برگردد. اگر امتیازها افت کرده‌اند، تعجب نکن — استراتژی‌ای که برای ظرفیت ۲ عالی بود، شاید اینجا دیگر بهترین نباشد. دکمهٔ «یادگیری دوباره» را بزن و تفاوت را ببین."
    : "نتیجه را ببین و از خودت بپرس: قانون‌های من کجا از ربات یادگیرنده بهترند و کجا بدتر؟ بعد قانون‌ها را اصلاح کن و مقایسه را تکرار کن.";
  // دو تختهٔ همزمان
  compareResult = data;
  dualIdx = 0;
  $("dualBoards").classList.remove("hidden");
  showDual(0);
  renderModelStrategy(data.modelStrategy);
}
function showDual(idx) {
  if (!compareResult) return;
  const h = compareResult.humanTrace, r = compareResult.rlTrace;
  const n = Math.min(h.steps.length, r.steps.length);
  dualIdx = Math.max(0, Math.min(n - 1, idx));
  const hs = h.steps[dualIdx], rs = r.steps[dualIdx];
  drawBoard($("boardHuman"), h.map, hs, h.steps.slice(0, dualIdx + 1).map(s => s.robot));
  drawBoard($("boardRL"), r.map, rs, r.steps.slice(0, dualIdx + 1).map(s => s.robot));
  $("hudHuman").textContent = "امتیاز " + faNum(hs.score) + " · تحویل‌شده " + faNum(hs.deliveredCount) + " · باتری " + faPct(hs.battery) + " · زمان " + faNum(hs.time);
  $("hudRL").textContent = "امتیاز " + faNum(rs.score) + " · تحویل‌شده " + faNum(rs.deliveredCount) + " · باتری " + faPct(rs.battery) + " · زمان " + faNum(rs.time);
  $("dualSlider").max = n - 1;
  $("dualSlider").value = dualIdx;
  $("dualInfo").textContent = "قدم " + faNum(dualIdx) + " از " + faNum(n - 1);
}
$("evalBtn").addEventListener("click", async () => {
  $("evalBtn").disabled = true;
  $("evalNote").textContent = "در حال اجرای مقایسه روی نقشه‌های یکسان…";
  try {
    const data = await api("/api/compare", { method: "POST", body: JSON.stringify({ rules, capacity: Number($("capSel").value) }) });
    renderCompare(data);
  } finally { $("evalBtn").disabled = false; }
});
$("finetuneBtn").addEventListener("click", async () => {
  $("finetuneBtn").disabled = true;
  $("evalNote").textContent = "عامل یادگیرنده دارد در محیط جدید دوباره تمرین می‌کند…";
  try {
    const data = await api("/api/finetune", { method: "POST", body: JSON.stringify({ rules, capacity: Number($("capSel").value) }) });
    renderCompare(data);
  } finally { $("finetuneBtn").disabled = false; }
});
$("dualPlayBtn").addEventListener("click", () => {
  if (dualTimer) { clearInterval(dualTimer); dualTimer = null; $("dualPlayBtn").textContent = "▶ پخش همزمان دو تخته"; return; }
  if (!compareResult) return;
  const n = Math.min(compareResult.humanTrace.steps.length, compareResult.rlTrace.steps.length);
  if (dualIdx >= n - 1) dualIdx = 0;
  $("dualPlayBtn").textContent = "⏸ توقف";
  dualTimer = setInterval(() => {
    dualIdx++;
    if (dualIdx >= n - 1) { dualIdx = n - 1; clearInterval(dualTimer); dualTimer = null; $("dualPlayBtn").textContent = "▶ پخش همزمان دو تخته"; }
    showDual(dualIdx);
  }, 380);
});
$("dualSlider").addEventListener("input", e => { if (dualTimer) { clearInterval(dualTimer); dualTimer = null; $("dualPlayBtn").textContent = "▶ پخش همزمان دو تخته"; } showDual(Number(e.target.value)); });

/* ---------- پنل ادمین ---------- */
function openAdmin() {
  $("adminOverlay").classList.add("on");
  $("adminGate").hidden = false; $("adminPanel").hidden = true;
  $("adminCodeInput").value = ""; $("adminCodeErr").textContent = "";
  $("adminCodeInput").focus();
}
function closeAdmin() { $("adminOverlay").classList.remove("on"); }
async function showAdminPanel() {
  $("adminOk").textContent = ""; $("adminPanelErr").textContent = "";
  buildAdminFields();
  renderAdminPresets();
  $("showPresetsToggle").checked = META.showPresets;
}
function buildAdminFields() {
  const box = $("adminFields"); box.innerHTML = "";
  let grid = null;
  META.paramFields.forEach(f => {
    if (f.sec) {
      const h = document.createElement("div"); h.className = "admin-sec"; h.textContent = f.sec; box.appendChild(h);
      grid = document.createElement("div"); grid.className = "admin-grid"; box.appendChild(grid);
      return;
    }
    const wrap = document.createElement("div"); wrap.className = "admin-field";
    wrap.innerHTML = '<label for="pf-' + f.key + '"></label>' +
      '<input type="number" id="pf-' + f.key + '" min="' + f.min + '" max="' + f.max + '" step="' + f.step + '" value="' + META.settings[f.key] + '" />' +
      (f.hint ? '<span class="hint"></span>' : "");
    wrap.querySelector("label").textContent = f.label;
    if (f.hint) wrap.querySelector(".hint").textContent = f.hint;
    grid.appendChild(wrap);
  });
}
function readAdminForm() {
  const next = { ...META.settings };
  META.paramFields.forEach(f => {
    if (!f.key) return;
    const el = $("pf-" + f.key); if (!el) return;
    next[f.key] = Number(el.value);
    el.value = next[f.key];
  });
  return next;
}
async function renderAdminPresets() {
  const data = await api("/api/admin-presets", { headers: adminHeaders() });
  const box = $("adminPresetList"); box.innerHTML = "";
  if (!data.presets.length) {
    box.innerHTML = '<p class="note">هنوز تنظیمی ذخیره نکرده‌ای؛ عددهای بالا را ست کن، یک اسم بده و «ذخیرهٔ تنظیم فعلی» را بزن.</p>';
    return;
  }
  data.presets.forEach(pr => {
    const card = document.createElement("div"); card.className = "admin-preset-card";
    const p = pr.params;
    card.innerHTML = '<div class="admin-preset-head"><span class="nm"></span><span class="sp"></span>' +
      '<button class="btn small primary" type="button">اعمال</button><button class="btn small" type="button">حذف</button></div>' +
      '<div class="admin-preset-sum">ظرفیت حمل ' + faNum(p.capacity) + ' نفر · سقف قدم ' + faNum(p.maxTime) + ' · باتری شروع ' + faNum(p.startBattery) + '٪ · موانع ' + faNum(p.obstacles) + ' · خانهٔ خطرناک ' + faNum(p.dangerCells) + ' · هزینهٔ خطر ' + faNum(p.dangerCost) + ' · شارژ هر قدم ' + faNum(p.chargeRate) + '٪ · مصدومان: بحرانی ' + faNum(p.survivorsCritical) + '، فوری ' + faNum(p.survivorsUrgent) + '، عادی ' + faNum(p.survivorsNormal) + ' · مأموریت تمرینی ' + faNum(p.trainEpisodes) + ' · نقشهٔ مقایسه ' + faNum(p.evalMaps) + '</div>';
    card.querySelector(".nm").textContent = pr.name;
    card.querySelector(".primary").addEventListener("click", async () => {
      const res = await api("/api/admin-presets/" + encodeURIComponent(pr.name) + "/apply", { method: "POST", headers: adminHeaders() });
      META.settings = res.settings;
      buildAdminFields();
      await loadTrace();
      $("adminOk").textContent = "تنظیم «" + pr.name + "» اعمال شد و مأموریت از اول شروع شد.";
    });
    card.querySelectorAll(".btn")[1].addEventListener("click", async () => {
      await api("/api/admin-presets/" + encodeURIComponent(pr.name), { method: "DELETE", headers: adminHeaders() });
      renderAdminPresets();
    });
    box.appendChild(card);
  });
}
$("adminOpen").addEventListener("click", openAdmin);
$("adminUnlockBtn").addEventListener("click", async () => {
  try {
    await api("/api/unlock", { method: "POST", body: JSON.stringify({ code: $("adminCodeInput").value, kind: "admin" }) });
    adminCode = $("adminCodeInput").value;
    $("adminCodeInput").value = ""; $("adminCodeErr").textContent = "";
    $("adminGate").hidden = true; $("adminPanel").hidden = false;
    showAdminPanel();
  } catch (e) { $("adminCodeErr").textContent = "رمز درست نیست — از آموزگار بپرس."; }
});
$("adminCodeInput").addEventListener("keydown", e => { if (e.key === "Enter") $("adminUnlockBtn").click(); });
$("adminGateClose").addEventListener("click", closeAdmin);
$("adminClose").addEventListener("click", closeAdmin);
$("adminOverlay").addEventListener("click", e => { if (e.target === $("adminOverlay")) closeAdmin(); });
$("showPresetsToggle").addEventListener("change", async e => {
  await api("/api/flags", { method: "PUT", headers: adminHeaders(), body: JSON.stringify({ showPresets: e.target.checked }) });
  META.showPresets = e.target.checked;
  renderPresets();
});
$("adminPresetSave").addEventListener("click", async () => {
  const name = $("adminPresetName").value.trim() || "تنظیم";
  await api("/api/admin-presets", { method: "POST", headers: adminHeaders(), body: JSON.stringify({ name, params: readAdminForm() }) });
  $("adminPresetName").value = "";
  $("adminOk").textContent = "تنظیم «" + name + "» ذخیره شد.";
  renderAdminPresets();
});
async function applyAdminParams(fromDefaults) {
  const next = fromDefaults ? { ...META.paramDefaults } : readAdminForm();
  try {
    const res = await api("/api/settings", { method: "PUT", headers: adminHeaders(), body: JSON.stringify(next) });
    META.settings = res.settings;
    buildAdminFields();
    await loadTrace();
    $("adminPanelErr").textContent = "";
    $("adminOk").textContent = "پارامترها اعمال و ذخیره شدند و مأموریت از اول شروع شد. برای همه اعمال شد.";
  } catch (e) {
    $("adminPanelErr").textContent = e.message;
    $("adminOk").textContent = "";
  }
}
$("adminApply").addEventListener("click", () => applyAdminParams(false));
$("adminDefaults").addEventListener("click", () => applyAdminParams(true));
$("adminRelockBtn").addEventListener("click", () => { applyStage(1); closeAdmin(); });

/* ---------- شروع ---------- */
(async function init() {
  META = await api("/api/meta");
  renderPresets();
  renderRules();
  renderSaved();
  renderScenarios();
  await loadTrace(7);
  let savedStage = 1;
  try { savedStage = localStorage.getItem("rescueMission.stage.v1") === "2" ? 2 : 1; } catch (e) {}
  applyStage(savedStage);
})();
