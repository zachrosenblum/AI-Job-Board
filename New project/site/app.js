const jobsContainer = document.getElementById("jobs");
const resultsCount = document.getElementById("results-count");
const jobTemplate = document.getElementById("job-card");

const searchInput = document.getElementById("search");
const companySelect = document.getElementById("company");
const locationSelect = document.getElementById("location");
const entryOnly = document.getElementById("entry-only");

const statJobs = document.getElementById("stat-jobs");
const statCompanies = document.getElementById("stat-companies");
const statUpdated = document.getElementById("stat-updated");

let allJobs = [];
let metadata = null;

function normalize(value) {
  return (value || "").toLowerCase().trim();
}

function formatDate(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderOptions(select, values) {
  const existing = new Set(Array.from(select.options).map((o) => o.value));
  values.forEach((value) => {
    if (!existing.has(value)) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    }
  });
}

function applyFilters() {
  const q = normalize(searchInput.value);
  const company = normalize(companySelect.value);
  const location = normalize(locationSelect.value);
  const entry = entryOnly.checked;

  const filtered = allJobs.filter((job) => {
    const title = normalize(job.title);
    const companyName = normalize(job.company);
    const loc = normalize(job.location);
    if (q && !title.includes(q)) return false;
    if (company && companyName !== company) return false;
    if (location && loc !== location) return false;
    if (entry && !job.entry_level) return false;
    return true;
  });

  renderJobs(filtered);
}

function renderJobs(jobs) {
  jobsContainer.innerHTML = "";
  resultsCount.textContent = `${jobs.length} role${jobs.length === 1 ? "" : "s"}`;

  if (!jobs.length) {
    const empty = document.createElement("div");
    empty.className = "card";
    empty.innerHTML = "<p>No roles match your filters yet.</p>";
    jobsContainer.appendChild(empty);
    return;
  }

  jobs.forEach((job) => {
    const node = jobTemplate.content.cloneNode(true);
    node.querySelector(".job-title").textContent = job.title;
    node.querySelector(".job-company").textContent = job.company;
    node.querySelector(".job-meta").textContent = job.location || "Location not listed";
    node.querySelector(".job-tag").textContent = job.entry_level ? "Entry" : `Up to ${job.min_years ?? 2} yrs`;
    const link = node.querySelector(".job-link");
    link.href = job.url || job.careers_url;
    jobsContainer.appendChild(node);
  });
}

function hydrateStats() {
  statJobs.textContent = metadata?.total_jobs ?? allJobs.length;
  statCompanies.textContent = metadata?.company_count ?? "—";
  statUpdated.textContent = formatDate(metadata?.generated_at);
}

function hydrateFilters() {
  const companies = [...new Set(allJobs.map((job) => job.company).filter(Boolean))].sort();
  const locations = [...new Set(allJobs.map((job) => job.location).filter(Boolean))].sort();
  renderOptions(companySelect, companies);
  renderOptions(locationSelect, locations);
}

async function loadData() {
  try {
    const [jobsRes, metaRes] = await Promise.all([
      fetch("../output/jobs.json"),
      fetch("../output/metadata.json"),
    ]);

    if (!jobsRes.ok) throw new Error("Unable to load jobs.json");
    allJobs = await jobsRes.json();

    if (metaRes.ok) {
      metadata = await metaRes.json();
    }

    hydrateStats();
    hydrateFilters();
    renderJobs(allJobs);
  } catch (err) {
    jobsContainer.innerHTML = "";
    const error = document.createElement("div");
    error.className = "card";
    error.innerHTML = "<p>Could not load jobs data. Run the scraper to generate output/jobs.json.</p>";
    jobsContainer.appendChild(error);
  }
}

[searchInput, companySelect, locationSelect, entryOnly].forEach((el) => {
  el.addEventListener("input", applyFilters);
  el.addEventListener("change", applyFilters);
});

loadData();
