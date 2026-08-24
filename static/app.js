const state = {
  settings: {},
  applyingProfile: false,
  audiobook: { query: "", results: [], imports: [], openJobId: null },
  ebook: { query: "", results: [], imports: [], openJobId: null },
};

const SURFACES = {
  audiobook: {
    mediaType: "audiobook",
    resultsBody: "#results-body",
    resultCount: "#result-count",
    searchMessage: "#search-message",
    importsContainer: "#imports",
    query: "#query",
    format: "#format-filter",
    language: "#language-filter",
    seeders: "#seeders-filter",
    relevance: "#relevance-filter",
    availability: "#availability-filter",
    category: "#category-filter",
    disabledLabel: "Audio only",
    disabledTitle: "Dewey imports audiobook formats on this tab.",
  },
  ebook: {
    mediaType: "ebook",
    resultsBody: "#ebook-results-body",
    resultCount: "#ebook-result-count",
    searchMessage: "#ebook-search-message",
    importsContainer: "#ebook-imports",
    query: "#ebook-query",
    format: "#ebook-format-filter",
    language: "#ebook-language-filter",
    seeders: "#ebook-seeders-filter",
    relevance: "#ebook-relevance-filter",
    availability: "#ebook-availability-filter",
    category: null,
    disabledLabel: "Ebook only",
    disabledTitle: "This tab imports ebook formats only.",
  },
};

const DEFAULT_SEARCH_PROFILES = [
  { id: "m4b-english", name: "M4B English", format: "m4b", language: "ENG", min_seeders: 1, min_relevance: 55, search_type: "active", category: "13" },
  { id: "m4b-non-vip", name: "M4B non-VIP", format: "m4b", language: "ENG", min_seeders: 1, min_relevance: 55, search_type: "nVIP", category: "13" },
  { id: "freeleech-m4b", name: "Freeleech M4B", format: "m4b", language: "ENG", min_seeders: 0, min_relevance: 50, search_type: "fl", category: "13" },
  { id: "broad-audio", name: "Broad audiobook", format: "", language: "ENG", min_seeders: 0, min_relevance: 45, search_type: "active", category: "13" },
];

const VIEW_TITLES = {
  search: "Audiobooks",
  ebooks: "Ebooks",
  account: "Account",
  profiles: "Profiles",
  diagnostics: "Diagnostics",
  settings: "Settings",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function surfaceState(surface) {
  return state[surface.mediaType];
}

function setMessage(id, text, isError = false) {
  const node = $(id);
  if (!node) return;
  node.textContent = text || "";
  node.classList.toggle("is-error", isError);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      detail = response.statusText;
    }
    if (response.status === 401 && !String(path).startsWith("/api/auth/")) {
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = `/login?next=${next}`;
    }
    throw new Error(detail);
  }
  return response.json();
}

function activateView(name) {
  $$("[data-view]").forEach((view) => view.classList.toggle("is-active", view.dataset.view === name));
  $$("[data-view-button]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.viewButton === name);
  });
  const title = $("#workspace-title");
  if (title) title.textContent = VIEW_TITLES[name] || "Dewey";
}

function bytes(value) {
  if (!value) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = Number(value);
  if (Number.isNaN(size)) return "";
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function resultMeta(result) {
  return [
    result.author ? `Author: ${result.author}` : "",
    result.narrator ? `Narrator: ${result.narrator}` : "",
    result.series ? `Series: ${result.series}` : "",
    result.language ? `Language: ${result.language}` : "",
    result.duration ? `Duration: ${result.duration}` : "",
    result.bitrate ? `Bitrate: ${result.bitrate}` : "",
  ].filter(Boolean);
}

function activityMeta(result) {
  return [
    result.seeders !== null && result.seeders !== undefined ? `${result.seeders} seed` : "",
    result.leechers !== null && result.leechers !== undefined ? `${result.leechers} leech` : "",
    result.snatches !== null && result.snatches !== undefined ? `${result.snatches} snatched` : "",
    result.comments !== null && result.comments !== undefined ? `${result.comments} comments` : "",
    result.thanks !== null && result.thanks !== undefined ? `${result.thanks} thanks` : "",
  ].filter(Boolean);
}

function isVipResult(result) {
  const flags = (result.flags || []).map((flag) => String(flag).toLowerCase());
  return result.vip_only === true || flags.includes("vip");
}

function canImportVipResult() {
  return state.settings.mam_vip_status === "active" || state.settings.mam_block_vip_when_inactive === false;
}

function hasFormatToken(result, tokens) {
  const values = [
    result.format,
    result.category,
    result.title,
    result.description,
    ...(result.tags || []),
  ];
  const text = values.filter(Boolean).join(" ").toLowerCase();
  return tokens.some((token) => new RegExp(`(^|[^a-z0-9])${token}([^a-z0-9]|$)`).test(text));
}

const AUDIO_FORMAT_TOKENS = ["aac", "flac", "m4a", "m4b", "mp3", "ogg", "opus", "wav", "audiobook", "audiobooks"];
const EBOOK_FORMAT_TOKENS = ["azw", "azw3", "cb7", "cbr", "cbz", "epub", "mobi", "pdf", "ebook", "ebooks"];

function isAudioImportable(result) {
  if (hasFormatToken({ format: result.format }, EBOOK_FORMAT_TOKENS)) return false;
  if (hasFormatToken({ format: result.format }, AUDIO_FORMAT_TOKENS)) return true;
  if (hasFormatToken(result, EBOOK_FORMAT_TOKENS)) return false;
  if (hasFormatToken(result, AUDIO_FORMAT_TOKENS)) return true;
  return true;
}

function isEbookImportable(result) {
  if (hasFormatToken({ format: result.format }, EBOOK_FORMAT_TOKENS)) return true;
  if (hasFormatToken({ format: result.format }, AUDIO_FORMAT_TOKENS)) return false;
  if (hasFormatToken(result, EBOOK_FORMAT_TOKENS)) return true;
  if (hasFormatToken(result, AUDIO_FORMAT_TOKENS)) return false;
  return true;
}

function isImportable(result, surface) {
  return surface.mediaType === "ebook" ? isEbookImportable(result) : isAudioImportable(result);
}

function mamStoreUrl() {
  return state.settings.mam_vip_store_url || "https://www.myanonamouse.net/store.php";
}

function displayValue(value, fallback = "Unknown") {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "number") return value.toLocaleString();
  return String(value);
}

function displayDate(value) {
  if (!value) return "Never";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}

function renderAccountSummary() {
  const node = $("#account-summary");
  if (!node) return;
  const settings = state.settings || {};
  const stats = [
    ["VIP", displayValue(settings.mam_vip_status)],
    ["Class", displayValue(settings.mam_account_class)],
    ["VIP until", displayValue(settings.mam_vip_until)],
    ["Points", displayValue(settings.mam_bonus_points)],
    ["Wedges", displayValue(settings.mam_freeleech_wedges)],
    ["Refreshed", displayDate(settings.mam_account_last_refresh)],
  ];
  node.innerHTML = stats
    .map(([label, value]) => `<div class="account-stat"><span>${escapeHtml(label)}</span><span>${escapeHtml(value)}</span></div>`)
    .join("");
}

function renderResults(surface) {
  const body = $(surface.resultsBody);
  const results = surfaceState(surface).results;
  $(surface.resultCount).textContent = results.length ? `${results.length} found` : "";
  if (!results.length) {
    body.innerHTML = `<tr class="empty-row"><td colspan="6" class="empty">No results.</td></tr>`;
    return;
  }

  body.innerHTML = "";
  results.forEach((result) => {
    const row = document.createElement("tr");
    row.className = "result-row";

    const titleCell = document.createElement("td");
    titleCell.dataset.label = "Title";
    const title = document.createElement("div");
    title.className = "result-title";
    title.textContent = result.title;
    titleCell.appendChild(title);
    if (result.description) {
      const description = document.createElement("div");
      description.className = "result-description";
      description.textContent = result.description;
      titleCell.appendChild(description);
    }
    if (result.info_url) {
      const link = document.createElement("a");
      link.href = result.info_url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = "Open listing";
      titleCell.appendChild(link);
    }
    if (result.uploaded_at || result.file_count) {
      const extra = document.createElement("div");
      extra.className = "result-submeta";
      extra.textContent = [result.uploaded_at ? `Uploaded ${result.uploaded_at}` : "", result.file_count ? `${result.file_count} files` : ""].filter(Boolean).join(" | ");
      titleCell.appendChild(extra);
    }
    if (result.library_matches?.length) {
      const duplicate = document.createElement("div");
      duplicate.className = "result-duplicate";
      duplicate.textContent = `Possible library match: ${result.library_matches[0]}`;
      titleCell.appendChild(duplicate);
    }

    const bookCell = document.createElement("td");
    bookCell.dataset.label = "Book";
    const bookMeta = resultMeta(result);
    bookCell.innerHTML = bookMeta.length
      ? bookMeta.map((line) => `<div>${escapeHtml(line)}</div>`).join("")
      : `<span class="muted">No book metadata</span>`;

    const sizeCell = document.createElement("td");
    sizeCell.dataset.label = "Size";
    sizeCell.textContent = bytes(result.size);

    const activityCell = document.createElement("td");
    activityCell.dataset.label = "Activity";
    const activity = activityMeta(result);
    activityCell.innerHTML = activity.length
      ? activity.map((line) => `<div>${escapeHtml(line)}</div>`).join("")
      : `<span class="muted">No swarm data</span>`;

    const sourceCell = document.createElement("td");
    sourceCell.dataset.label = "Source";
    const badges = [
      result.library_matches?.length ? "In library" : "",
      result.relevance !== null && result.relevance !== undefined ? `${result.relevance}% match` : "",
      result.indexer || result.provider,
      result.category,
      result.format || result.protocol,
      ...(result.flags || []),
      ...(result.tags || []).slice(0, 4),
    ].filter(Boolean);
    sourceCell.innerHTML = badges.map((badge) => `<span class="badge">${escapeHtml(badge)}</span>`).join("");

    const action = document.createElement("td");
    action.dataset.label = "Action";
    const importButton = document.createElement("button");
    let secondaryAction = null;
    importButton.type = "button";
    if (!isImportable(result, surface)) {
      importButton.disabled = true;
      importButton.textContent = surface.disabledLabel;
      importButton.title = surface.disabledTitle;
    } else if (isVipResult(result) && !canImportVipResult()) {
      importButton.textContent = "Buy VIP";
      importButton.title = "Buy 4 weeks of VIP with bonus points, then import.";
      importButton.addEventListener("click", () => buyVipAndImport(result, importButton, surface));
      const storeLink = document.createElement("a");
      storeLink.href = mamStoreUrl();
      storeLink.target = "_blank";
      storeLink.rel = "noreferrer";
      storeLink.className = "action-link";
      storeLink.textContent = "Open store";
      secondaryAction = storeLink;
    } else {
      importButton.textContent = "Import";
      importButton.addEventListener("click", () => importResult(result, importButton, surface));
    }
    action.appendChild(importButton);
    if (secondaryAction) action.appendChild(secondaryAction);

    [titleCell, bookCell, sizeCell, activityCell, sourceCell, action].forEach((cell) => row.appendChild(cell));
    body.appendChild(row);
  });
}

function renderAllResults() {
  Object.values(SURFACES).forEach((surface) => renderResults(surface));
}

function searchProfiles() {
  const source = Array.isArray(state.settings.search_profiles)
    ? state.settings.search_profiles
    : DEFAULT_SEARCH_PROFILES;
  return source.map(normalizeProfile).filter((profile) => profile.name);
}

function normalizeProfile(profile, index = 0) {
  return {
    id: String(profile.id || `profile-${index}`),
    name: String(profile.name || `Profile ${index + 1}`),
    format: String(profile.format || ""),
    language: String(profile.language || ""),
    min_seeders: profile.min_seeders === null || profile.min_seeders === undefined || profile.min_seeders === "" ? "" : Number(profile.min_seeders),
    min_relevance: profile.min_relevance === null || profile.min_relevance === undefined || profile.min_relevance === "" ? "" : Number(profile.min_relevance),
    search_type: String(profile.search_type || "all"),
    category: String(profile.category || state.settings.mam_audiobook_category || "13"),
  };
}

function profilePayload(profile) {
  return {
    id: profile.id,
    name: profile.name,
    format: profile.format,
    language: profile.language,
    min_seeders: profile.min_seeders === "" ? null : Number(profile.min_seeders),
    min_relevance: profile.min_relevance === "" ? null : Number(profile.min_relevance),
    search_type: profile.search_type || "all",
    category: profile.category || "13",
  };
}

function renderSearchProfileOptions(selected = "custom") {
  const select = $("#profile-filter");
  if (!select) return;
  const current = selected || select.value || "custom";
  const options = [`<option value="custom">Custom</option>`].concat(
    searchProfiles().map((profile) => `<option value="${escapeHtml(profile.id)}">${escapeHtml(profile.name)}</option>`)
  );
  select.innerHTML = options.join("");
  select.value = searchProfiles().some((profile) => profile.id === current) ? current : "custom";
}

function applySearchProfile(profileId) {
  if (profileId === "custom") return;
  const profile = searchProfiles().find((item) => item.id === profileId);
  if (!profile) return;
  state.applyingProfile = true;
  $("#format-filter").value = profile.format;
  $("#language-filter").value = profile.language;
  $("#seeders-filter").value = profile.min_seeders ?? "";
  $("#relevance-filter").value = profile.min_relevance ?? "";
  $("#availability-filter").value = profile.search_type || "all";
  $("#category-filter").value = profile.category || "13";
  state.applyingProfile = false;
}

function renderProfileEditor(selectedId = null) {
  const list = $("#profile-editor-list");
  if (!list) return;
  const profiles = searchProfiles();
  const selected = selectedId || list.value || profiles[0]?.id || "";
  list.innerHTML = profiles.map((profile) => `<option value="${escapeHtml(profile.id)}">${escapeHtml(profile.name)}</option>`).join("");
  list.value = profiles.some((profile) => profile.id === selected) ? selected : profiles[0]?.id || "";

  const profile = profiles.find((item) => item.id === list.value);
  const disabled = !profile;
  $("#profile-name").disabled = disabled;
  $("#profile-format").disabled = disabled;
  $("#profile-language").disabled = disabled;
  $("#profile-min-seeders").disabled = disabled;
  $("#profile-min-relevance").disabled = disabled;
  $("#profile-search-type").disabled = disabled;
  $("#profile-category").disabled = disabled;
  $("#save-profile").disabled = disabled;
  $("#delete-profile").disabled = disabled;
  if (!profile) {
    $("#profile-name").value = "";
    $("#profile-format").value = "";
    $("#profile-language").value = "";
    $("#profile-min-seeders").value = "";
    $("#profile-min-relevance").value = "";
    $("#profile-search-type").value = "all";
    $("#profile-category").value = state.settings.mam_audiobook_category || "13";
    return;
  }

  $("#profile-name").value = profile.name;
  $("#profile-format").value = profile.format;
  $("#profile-language").value = profile.language;
  $("#profile-min-seeders").value = profile.min_seeders ?? "";
  $("#profile-min-relevance").value = profile.min_relevance ?? "";
  $("#profile-search-type").value = profile.search_type || "all";
  $("#profile-category").value = profile.category || "13";
}

function statusLabel(status) {
  return String(status || "unknown").toUpperCase();
}

function renderDiagnostics(payload) {
  const summary = $("#diagnostics-summary");
  const list = $("#diagnostics-list");
  const checks = payload?.checks || [];
  summary.innerHTML = `
    <div class="diagnostics-overall ${escapeHtml(payload?.overall_status || "unknown")}">
      <span>${escapeHtml(statusLabel(payload?.overall_status))}</span>
      <strong>${checks.length} checks</strong>
      <small>${escapeHtml(displayDate(payload?.generated_at))}</small>
    </div>
  `;
  list.innerHTML = checks.map((check) => {
    const values = Object.entries(check.values || {})
      .map(([key, value]) => `<span>${escapeHtml(key.replaceAll("_", " "))}: ${escapeHtml(displayValue(value, ""))}</span>`)
      .join("");
    return `
      <article class="diagnostic-item ${escapeHtml(check.status)}">
        <div>
          <span class="status-pill ${escapeHtml(check.status)}">${escapeHtml(statusLabel(check.status))}</span>
          <strong>${escapeHtml(check.name)}</strong>
        </div>
        <p>${escapeHtml(check.summary)}</p>
        ${check.detail ? `<p class="diagnostic-detail">${escapeHtml(check.detail)}</p>` : ""}
        ${values ? `<div class="diagnostic-values">${values}</div>` : ""}
      </article>
    `;
  }).join("");
}

async function loadDiagnostics(button = null) {
  if (button) {
    button.disabled = true;
    button.textContent = "Running";
  }
  setMessage("#diagnostics-message", "Running diagnostics...");
  try {
    const payload = await api("/api/diagnostics");
    renderDiagnostics(payload);
    setMessage("#diagnostics-message", "");
  } catch (error) {
    setMessage("#diagnostics-message", error.message, true);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Run Checks";
    }
  }
}

function readProfileForm(existingId) {
  return profilePayload({
    id: existingId || `profile-${Date.now()}`,
    name: $("#profile-name").value.trim() || "New Profile",
    format: $("#profile-format").value,
    language: $("#profile-language").value.trim(),
    min_seeders: $("#profile-min-seeders").value,
    min_relevance: $("#profile-min-relevance").value,
    search_type: $("#profile-search-type").value,
    category: $("#profile-category").value,
  });
}

async function saveSearchProfiles(profiles, selectedId) {
  setMessage("#profiles-message", "Saving...");
  try {
    const response = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ search_profiles: profiles.map(profilePayload) }),
    });
    state.settings = response.settings || {};
    renderSearchProfileOptions($("#profile-filter").value);
    renderProfileEditor(selectedId);
    setMessage("#profiles-message", "Saved.");
  } catch (error) {
    setMessage("#profiles-message", error.message, true);
  }
}

function addProfile() {
  const profiles = searchProfiles().map(profilePayload);
  const profile = {
    id: `profile-${Date.now()}`,
    name: "New Profile",
    format: "m4b",
    language: state.settings.mam_default_language || "ENG",
    min_seeders: state.settings.mam_min_seeders ?? 0,
    min_relevance: state.settings.mam_min_relevance ?? 45,
    search_type: state.settings.mam_default_search_type || "active",
    category: state.settings.mam_audiobook_category || "13",
  };
  state.settings.search_profiles = profiles.concat([profile]);
  renderSearchProfileOptions();
  renderProfileEditor(profile.id);
  setMessage("#profiles-message", "");
}

async function saveCurrentProfile() {
  const selectedId = $("#profile-editor-list").value;
  const profiles = searchProfiles().map(profilePayload);
  const profile = readProfileForm(selectedId);
  const next = profiles.some((item) => item.id === selectedId)
    ? profiles.map((item) => (item.id === selectedId ? profile : item))
    : profiles.concat([profile]);
  await saveSearchProfiles(next, profile.id);
}

async function deleteCurrentProfile() {
  const selectedId = $("#profile-editor-list").value;
  if (!selectedId) return;
  if (!window.confirm("Delete this search profile?")) return;
  const next = searchProfiles().filter((profile) => profile.id !== selectedId).map(profilePayload);
  await saveSearchProfiles(next, next[0]?.id || null);
}

async function runSearch(event, surface) {
  event.preventDefault();
  const query = $(surface.query).value.trim();
  const format = $(surface.format).value;
  const language = $(surface.language).value.trim();
  const minSeeders = $(surface.seeders).value;
  const minRelevance = $(surface.relevance).value;
  const availability = $(surface.availability).value;
  const category = surface.category
    ? $(surface.category).value.trim()
    : state.settings.ebook_search_category || "14";
  if (!query) return;

  const local = surfaceState(surface);
  local.query = query;
  local.results = [];
  renderResults(surface);
  setMessage(surface.searchMessage, "Searching MyAnonamouse...");
  try {
    const params = new URLSearchParams({ q: query });
    if (format) params.set("format", format);
    if (language) params.set("language", language);
    if (minSeeders !== "") params.set("min_seeders", minSeeders);
    if (minRelevance !== "") params.set("min_relevance", minRelevance);
    if (availability && availability !== "all") params.set("search_type", availability);
    if (category) params.set("category", category);
    const payload = await api(`/api/search?${params.toString()}`);
    local.results = payload.results || [];
    renderResults(surface);
    setMessage(surface.searchMessage, local.results.length ? "" : "No results returned.");
  } catch (error) {
    setMessage(surface.searchMessage, error.message, true);
  }
}

async function buyVipAndImport(result, button, surface) {
  const confirmed = window.confirm("Buy 4 weeks of MyAnonamouse VIP with bonus points, then import this torrent?");
  if (!confirmed) return;
  button.disabled = true;
  button.textContent = "Buying VIP";
  setMessage(surface.searchMessage, "Buying 4 weeks of MyAnonamouse VIP...");
  try {
    const response = await api("/api/mam/vip", {
      method: "POST",
      body: JSON.stringify({ duration: "4" }),
    });
    populateSettings(response.settings || {});
    renderAllResults();
    setMessage(surface.searchMessage, "VIP purchase complete; queueing import.");
    await importResult(result, button, surface);
  } catch (error) {
    button.disabled = false;
    button.textContent = "Buy VIP";
    setMessage(surface.searchMessage, error.message, true);
  }
}

async function importResult(result, button, surface) {
  button.disabled = true;
  button.textContent = "Queued";
  try {
    await api("/api/imports", {
      method: "POST",
      body: JSON.stringify({ query: surfaceState(surface).query, result, media_type: surface.mediaType }),
    });
    await loadImports(surface);
  } catch (error) {
    button.disabled = false;
    button.textContent = "Import";
    setMessage(surface.searchMessage, error.message, true);
  }
}

function renderImports(surface) {
  const container = $(surface.importsContainer);
  const local = surfaceState(surface);
  container.innerHTML = "";
  if (!local.imports.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No imports yet.";
    container.appendChild(empty);
    return;
  }

  const template = $("#import-template");
  local.imports.forEach((job) => {
    const node = template.content.firstElementChild.cloneNode(true);
    const status = node.querySelector(".status-pill");
    const summary = node.querySelector(".import-summary");
    const title = node.querySelector(".import-title");
    const meta = node.querySelector(".import-meta");
    const progress = node.querySelector(".progress span");
    const details = node.querySelector(".import-details");

    status.textContent = job.status;
    status.classList.add(job.status);
    title.textContent = job.torrent_title;
    meta.textContent = [job.source_indexer, bytes(job.size), job.destination_path ? "Imported" : ""].filter(Boolean).join(" | ");
    progress.style.width = `${Math.round((job.progress || 0) * 100)}%`;

    if (job.id === local.openJobId) node.classList.add("is-open");
    summary.addEventListener("click", async () => {
      local.openJobId = local.openJobId === job.id ? null : job.id;
      if (local.openJobId) await loadImportDetail(job.id, surface);
      renderImports(surface);
    });

    details.innerHTML = renderJobDetails(job);
    if (job.status === "review" || job.needs_review) {
      details.appendChild(renderReviewForm(job, surface));
    }
    details.appendChild(renderImportActions(job, surface));
    container.appendChild(node);
  });
}

function renderReviewForm(job, surface) {
  const form = document.createElement("form");
  form.className = "review-form";
  form.innerHTML = `
    <label>Author<input name="author" value="${escapeHtml(job.canonical_author || "")}" required /></label>
    <label>Title<input name="title" value="${escapeHtml(job.book_title || job.torrent_title || "")}" required /></label>
    <button type="submit">Apply Review</button>
  `;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    resolveReview(job.id, event.currentTarget, surface);
  });
  return form;
}

function renderImportActions(job, surface) {
  const actions = document.createElement("div");
  actions.className = "import-actions";

  if (["error", "review"].includes(job.status)) {
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "secondary";
    retry.textContent = "Retry";
    retry.addEventListener("click", () => retryImport(job.id, retry, surface));
    actions.appendChild(retry);
  }

  if (!["queued", "downloading", "importing", "scanning"].includes(job.status)) {
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "secondary danger";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => removeImport(job.id, remove, surface));
    actions.appendChild(remove);
  }

  return actions;
}

function renderJobDetails(job) {
  const lines = [];
  if (job.canonical_author || job.book_title) {
    lines.push(`<div><strong>Book:</strong> ${escapeHtml([job.canonical_author, job.book_title].filter(Boolean).join(" - "))}</div>`);
  }
  if (job.download_path) lines.push(`<div><strong>Download:</strong> ${escapeHtml(job.download_path)}</div>`);
  if (job.destination_path) lines.push(`<div><strong>Path:</strong> ${escapeHtml(job.destination_path)}</div>`);
  if (job.file_count) lines.push(`<div><strong>Files:</strong> ${job.file_count}</div>`);
  if (job.error) lines.push(`<div class="event error"><strong>Error:</strong> ${escapeHtml(job.error)}</div>`);
  if (job.warnings?.length) {
    lines.push(...job.warnings.map((warning) => `<div class="event warning">${escapeHtml(warning)}</div>`));
  }
  if (job.events?.length) {
    const events = job.events
      .map((event) => `<div class="event ${event.level}">${escapeHtml(event.created_at)} | ${escapeHtml(event.message)}</div>`)
      .join("");
    lines.push(`<div class="event-list">${events}</div>`);
  }
  return lines.join("") || `<div class="event">No detail yet.</div>`;
}

async function resolveReview(jobId, form, surface) {
  const button = form.querySelector("button");
  const payload = {
    author: form.elements.author.value.trim(),
    title: form.elements.title.value.trim(),
  };
  if (!payload.author || !payload.title) return;
  button.disabled = true;
  button.textContent = "Applying";
  try {
    const detail = await api(`/api/imports/${jobId}/review`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const local = surfaceState(surface);
    local.imports = local.imports.map((job) => (job.id === jobId ? detail : job));
    local.openJobId = jobId;
    renderImports(surface);
  } catch (error) {
    button.disabled = false;
    button.textContent = "Apply Review";
    console.error(error);
  }
}

async function retryImport(jobId, button, surface) {
  button.disabled = true;
  button.textContent = "Retrying";
  try {
    const detail = await api(`/api/imports/${jobId}/retry`, { method: "POST" });
    const local = surfaceState(surface);
    local.imports = local.imports.map((job) => (job.id === jobId ? detail : job));
    local.openJobId = jobId;
    renderImports(surface);
  } catch (error) {
    button.disabled = false;
    button.textContent = "Retry";
    console.error(error);
  }
}

async function removeImport(jobId, button, surface) {
  if (!window.confirm("Remove this import from Dewey history?")) return;
  button.disabled = true;
  button.textContent = "Removing";
  try {
    await api(`/api/imports/${jobId}`, { method: "DELETE" });
    const local = surfaceState(surface);
    local.imports = local.imports.filter((job) => job.id !== jobId);
    if (local.openJobId === jobId) local.openJobId = null;
    renderImports(surface);
  } catch (error) {
    button.disabled = false;
    button.textContent = "Remove";
    console.error(error);
  }
}

async function clearFinishedImports(surface) {
  if (!window.confirm("Clear completed, errored, and review imports from Dewey history?")) return;
  try {
    await api(`/api/imports?status=terminal`, { method: "DELETE" });
    const local = surfaceState(surface);
    local.openJobId = null;
    await Promise.all(Object.values(SURFACES).map((item) => loadImports(item)));
  } catch (error) {
    console.error(error);
  }
}

async function loadImports(surface) {
  try {
    const summaries = await api(`/api/imports?media_type=${surface.mediaType}`);
    const local = surfaceState(surface);
    const previous = new Map(local.imports.map((job) => [job.id, job]));
    local.imports = summaries.map((job) => {
      const old = previous.get(job.id);
      if (old?.events?.length && job.id === local.openJobId) {
        return { ...old, ...job, events: old.events, warnings: old.warnings };
      }
      return job;
    });
    if (local.openJobId && local.imports.some((job) => job.id === local.openJobId)) {
      await loadImportDetail(local.openJobId, surface);
    }
    renderImports(surface);
  } catch (error) {
    console.error(error);
  }
}

function loadAllImports() {
  return Promise.all(Object.values(SURFACES).map((surface) => loadImports(surface)));
}

async function loadImportDetail(jobId, surface) {
  try {
    const detail = await api(`/api/imports/${jobId}`);
    const local = surfaceState(surface);
    local.imports = local.imports.map((job) => (job.id === jobId ? detail : job));
  } catch (error) {
    console.error(error);
  }
}

function applySearchDefaults(settings) {
  renderSearchProfileOptions("custom");
  $("#profile-filter").value = "custom";
  $("#format-filter").value = settings.mam_default_format || "";
  $("#language-filter").value = settings.mam_default_language || "";
  $("#seeders-filter").value = settings.mam_min_seeders ?? "";
  $("#relevance-filter").value = settings.mam_min_relevance ?? "";
  $("#availability-filter").value = settings.mam_default_search_type || "all";
  $("#category-filter").value = settings.mam_audiobook_category || "13";
}

function applyEbookDefaults(settings) {
  $("#ebook-format-filter").value = settings.ebook_default_format || "";
  $("#ebook-language-filter").value = settings.ebook_default_language || "";
  $("#ebook-seeders-filter").value = settings.mam_min_seeders ?? "";
  $("#ebook-relevance-filter").value = settings.mam_min_relevance ?? "";
  $("#ebook-availability-filter").value = settings.mam_default_search_type || "all";
}

function populateSettings(settings) {
  state.settings = settings;
  const form = $("#settings-form");
  Object.entries(settings).forEach(([key, value]) => {
    const input = form.elements[key];
    if (!input) return;
    if (input.type === "checkbox") {
      input.checked = Boolean(value);
    } else {
      input.value = value ?? "";
    }
  });
  renderSecretHints(settings);
  applySearchDefaults(settings);
  applyEbookDefaults(settings);
  renderAccountSummary();
  renderProfileEditor();
}

function renderSecretHints(settings) {
  const labels = {
    mam_id: "MAM cookie",
    qbittorrent_password: "qBittorrent password",
    audiobookshelf_api_key: "Audiobookshelf API key",
    auth_password: "Dewey login password",
  };
  Object.entries(labels).forEach(([key, label]) => {
    const configured = Boolean(settings[`${key}_configured`]);
    const input = document.querySelector(`[data-secret-placeholder="${key}"]`);
    const hint = document.querySelector(`[data-secret-hint="${key}"]`);
    if (input) {
      input.placeholder = configured ? "Saved - leave blank to keep" : `Enter ${label}`;
      input.title = configured
        ? "The saved value is hidden. Leave this blank when saving to keep it."
        : `Enter ${label}.`;
    }
    if (hint) {
      hint.textContent = configured
        ? "Saved value is hidden. Leave blank to keep it."
        : "Not saved yet.";
    }
  });
}

function setAdvancedSettingsVisible(visible) {
  $("#settings-form").classList.toggle("show-advanced", visible);
  $("#advanced-settings-toggle").checked = visible;
  window.localStorage.setItem("dewey.showAdvancedSettings", visible ? "1" : "0");
}

async function loadSettings() {
  try {
    const payload = await api("/api/settings");
    populateSettings(payload.settings || {});
  } catch (error) {
    setMessage("#settings-message", error.message, true);
  }
}

async function loadAuthStatus() {
  try {
    const status = await api("/api/auth/status");
    const logout = $("#logout-button");
    if (logout) logout.hidden = !(status.enabled && status.authenticated);
  } catch (error) {
    console.error(error);
  }
}

async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } finally {
    window.location.href = "/login";
  }
}

async function refreshMamAccount(button) {
  const originalText = button.textContent;
  const messageId = "#account-message";
  button.disabled = true;
  button.textContent = "Refreshing";
  setMessage(messageId, "Refreshing MyAnonamouse account status...");
  try {
    const response = await api("/api/mam/account", { method: "POST" });
    populateSettings(response.settings || {});
    renderAllResults();
    setMessage(messageId, "MyAnonamouse account status refreshed.");
  } catch (error) {
    setMessage(messageId, error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

async function saveSettings(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = {};
  Array.from(form.elements).forEach((input) => {
    if (!input.name) return;
    if (input.type === "checkbox") {
      payload[input.name] = input.checked;
    } else if (input.type === "number") {
      payload[input.name] = input.value === "" ? null : Number(input.value);
    } else {
      payload[input.name] = input.value;
    }
  });

  setMessage("#settings-message", "Saving...");
  try {
    const response = await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
    populateSettings(response.settings || {});
    renderAllResults();
    setMessage("#settings-message", "Saved.");
  } catch (error) {
    setMessage("#settings-message", error.message, true);
  }
}

function setup() {
  $("#search-form").addEventListener("submit", (event) => runSearch(event, SURFACES.audiobook));
  $("#ebook-search-form").addEventListener("submit", (event) => runSearch(event, SURFACES.ebook));
  $("#settings-form").addEventListener("submit", saveSettings);
  $("#profile-filter").addEventListener("change", (event) => {
    applySearchProfile(event.currentTarget.value);
  });
  ["#format-filter", "#language-filter", "#seeders-filter", "#relevance-filter", "#availability-filter", "#category-filter"].forEach((selector) => {
    ["input", "change"].forEach((eventName) => {
      $(selector).addEventListener(eventName, () => {
        if (!state.applyingProfile) $("#profile-filter").value = "custom";
      });
    });
  });
  $("#refresh-mam-account").addEventListener("click", (event) => {
    refreshMamAccount(event.currentTarget);
  });
  $("#refresh-diagnostics").addEventListener("click", (event) => loadDiagnostics(event.currentTarget));
  $("#logout-button").addEventListener("click", logout);
  $("#profile-editor-list").addEventListener("change", (event) => renderProfileEditor(event.currentTarget.value));
  $("#add-profile").addEventListener("click", addProfile);
  $("#save-profile").addEventListener("click", saveCurrentProfile);
  $("#delete-profile").addEventListener("click", deleteCurrentProfile);
  $("#advanced-settings-toggle").addEventListener("change", (event) => {
    setAdvancedSettingsVisible(event.currentTarget.checked);
  });
  $("#refresh-imports").addEventListener("click", () => loadImports(SURFACES.audiobook));
  $("#clear-imports").addEventListener("click", () => clearFinishedImports(SURFACES.audiobook));
  $("#ebook-refresh-imports").addEventListener("click", () => loadImports(SURFACES.ebook));
  $("#ebook-clear-imports").addEventListener("click", () => clearFinishedImports(SURFACES.ebook));
  $$("[data-view-button]").forEach((button) => {
    button.addEventListener("click", () => {
      activateView(button.dataset.viewButton);
      if (button.dataset.viewButton === "diagnostics") loadDiagnostics();
    });
  });
  setAdvancedSettingsVisible(window.localStorage.getItem("dewey.showAdvancedSettings") === "1");
  loadAuthStatus();
  loadSettings();
  loadAllImports();
  setInterval(loadAllImports, 5000);
}

document.addEventListener("DOMContentLoaded", setup);
