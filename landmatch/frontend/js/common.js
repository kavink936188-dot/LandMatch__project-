/* Shared helpers: API client, auth session, formatting, nav, toast. */
const API = "/api";
const ACRE = 43560, CENT = 435.6;
const UNITS = { acre: ACRE, cent: CENT, sqft: 1 };

const Auth = {
  get token() { return localStorage.getItem("lm_token"); },
  get user() { try { return JSON.parse(localStorage.getItem("lm_user")); } catch { return null; } },
  save(token, user) { localStorage.setItem("lm_token", token); localStorage.setItem("lm_user", JSON.stringify(user)); },
  clear() { localStorage.removeItem("lm_token"); localStorage.removeItem("lm_user"); },
  home(role) { return { seller: "seller.html", buyer: "buyer.html", admin: "admin.html" }[role] || "index.html"; },
};

async function api(path, { method = "GET", body = null, form = null, auth = true } = {}) {
  const headers = {};
  if (auth && Auth.token) headers.Authorization = "Bearer " + Auth.token;
  let payload;
  if (form) payload = form;                       // FormData or URLSearchParams
  else if (body) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(API + path, { method, headers, body: payload });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && auth && Auth.token) { Auth.clear(); location.href = "login.html?next=" + encodeURIComponent(location.pathname.split("/").pop()); }
    let msg = data.detail || "Something went wrong. Try again.";
    if (Array.isArray(msg)) msg = msg.map(e => `${(e.loc || []).slice(-1)[0]}: ${e.msg}`).join("; ");
    throw new Error(msg);
  }
  return data;
}

function requireRole(role) {
  const u = Auth.user;
  if (!Auth.token || !u || (role && u.role !== role)) {
    location.href = "login.html?next=" + encodeURIComponent(location.pathname.split("/").pop());
    return null;
  }
  return u;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmtPrice(n) {
  if (n >= 1e7) return "₹" + (n / 1e7).toFixed(2).replace(/\.?0+$/, "") + " Cr";
  if (n >= 1e5) return "₹" + (n / 1e5).toFixed(2).replace(/\.?0+$/, "") + " L";
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

function fmtArea(sqft) {
  if (sqft >= ACRE) return (sqft / ACRE).toFixed(2).replace(/\.?0+$/, "") + " acres";
  if (sqft >= CENT * 5) return (sqft / CENT).toFixed(1).replace(/\.0$/, "") + " cents";
  return Math.round(sqft).toLocaleString("en-IN") + " sq ft";
}

function fmtDate(iso) { return new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }); }

function toast(msg, isErr = false) {
  let t = document.getElementById("toast");
  if (!t) { t = document.createElement("div"); t.id = "toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
  t.textContent = msg; t.className = "show" + (isErr ? " err" : "");
  clearTimeout(t._h); t._h = setTimeout(() => (t.className = ""), 3800);
}

function renderNav() {
  const u = Auth.user, page = location.pathname.split("/").pop() || "index.html";
  const link = (href, label) => `<a class="link ${page === href ? "active" : ""}" href="${href}">${label}</a>`;
  let html = `<a class="brand" href="index.html">Land<i>Match</i></a>` + link("index.html", "Browse land");
  if (u) {
    html += link(Auth.home(u.role), u.role === "admin" ? "Admin" : u.role === "seller" ? "My listings" : "My requirements");
    html += `<button class="btn small" id="logout">Log out</button>`;
  } else html += `<a class="btn small alt" href="login.html">Log in</a>`;
  const nav = document.getElementById("nav");
  nav.className = "nav";
  nav.innerHTML = `<div class="wrap">${html}</div>`;
  const out = document.getElementById("logout");
  if (out) out.onclick = () => { Auth.clear(); location.href = "index.html"; };
}

function landCard(l, extra = "") {
  const img = l.images && l.images[0] ? `style="background-image:url('${l.images[0].url}')"` : "";
  return `<a class="card land" href="land.html?id=${l.id}">
    <div class="thumb" ${img}>${img ? "" : "<span>No photo yet</span>"}<span class="chip">${esc(l.land_type)}</span></div>
    <div class="body"><h3>${esc(l.title)}</h3>
      <p class="loc">${esc([l.village, l.district].filter(Boolean).join(", "))}</p>
      <div class="meta"><strong>${fmtPrice(l.price)}</strong><span>${fmtArea(l.area_sqft)}</span></div>${extra}</div></a>`;
}

async function loadOptions(...selects) {
  const opts = await api("/lands/meta/options", { auth: false });
  selects.forEach(({ el, kind, blank }) => {
    const list = kind === "district" ? opts.districts : opts.land_types;
    el.innerHTML = (blank ? `<option value="">${blank}</option>` : "") +
      list.map(v => `<option value="${v}">${kind === "district" ? v : v[0].toUpperCase() + v.slice(1)}</option>`).join("");
  });
  return opts;
}

document.addEventListener("DOMContentLoaded", renderNav);
