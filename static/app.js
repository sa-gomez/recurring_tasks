"use strict";

const TODAY = new Date().toISOString().slice(0, 10);

// ---- State ----------------------------------------------------------------

let allTasks = [];
let activeTab = "due";

// ---- API ------------------------------------------------------------------

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (res.status === 204) return null;
  return res.json();
}

async function loadTasks() {
  allTasks = await api("GET", "/api/tasks");
  renderActiveTab();
}

// ---- Rendering ------------------------------------------------------------

function formatDate(iso) {
  // Display as Month Day, Year
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

function daysUntil(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const then = new Date(y, m - 1, d);
  const now = new Date(TODAY + "T00:00:00");
  return Math.round((then - now) / 86400000);
}

function intervalLabel(days) {
  if (days < 7)  return `${days}d`;
  if (days < 30) return `${Math.round(days / 7)}w`;
  if (days < 365) return `${Math.round(days / 30)}mo`;
  return `${(days / 365).toFixed(1)}y`;
}

function buildCard(task) {
  const li = document.createElement("li");
  li.className = "task-card" +
    (task.is_overdue ? " overdue" : task.is_due_today ? " due-today" : "");
  li.dataset.id = task.id;

  const due = daysUntil(task.next_due_date);
  let badge = "";
  if (task.is_overdue) {
    const n = Math.abs(due);
    badge = `<span class="badge overdue">${n}d overdue</span>`;
  } else if (task.is_due_today) {
    badge = `<span class="badge due-today">Due today</span>`;
  } else {
    badge = `<span class="badge upcoming">in ${intervalLabel(due)}</span>`;
  }

  const nextLabel = intervalLabel(task.next_interval_days);
  const curLabel  = intervalLabel(task.current_interval_days);

  li.innerHTML = `
    <div class="task-header">
      <span class="task-name">${escHtml(task.name)}</span>
      <div class="task-actions">
        <button class="btn-icon complete" title="Mark complete" data-id="${task.id}">✓</button>
        <button class="btn-icon history" title="View history" data-id="${task.id}">↻</button>
        <button class="btn-icon delete"  title="Delete task"  data-id="${task.id}">✕</button>
      </div>
    </div>
    ${task.description ? `<p class="task-desc">${escHtml(task.description)}</p>` : ""}
    <div class="task-meta">
      ${badge}
      <span class="badge" title="Current interval">every ${curLabel}</span>
      <span class="badge" title="Next interval after completion">→ ${nextLabel}</span>
    </div>
  `;

  li.querySelector(".complete").addEventListener("click", () => completeTask(task.id));
  li.querySelector(".history").addEventListener("click", () => showHistory(task.id, task.name));
  li.querySelector(".delete").addEventListener("click", () => deleteTask(task.id));

  return li;
}

function renderList(listEl, emptyEl, tasks) {
  listEl.innerHTML = "";
  if (tasks.length === 0) {
    emptyEl.style.display = "";
    return;
  }
  emptyEl.style.display = "none";
  tasks.forEach(t => listEl.appendChild(buildCard(t)));
}

function renderActiveTab() {
  const today = allTasks.filter(t => t.is_due_today || t.is_overdue);
  const upcoming = allTasks.filter(t => !t.is_due_today && !t.is_overdue);

  renderList(
    document.getElementById("due-list"),
    document.getElementById("due-empty"),
    today,
  );
  renderList(
    document.getElementById("upcoming-list"),
    document.getElementById("upcoming-empty"),
    upcoming,
  );
  renderList(
    document.getElementById("all-list"),
    document.getElementById("all-empty"),
    allTasks,
  );

  // Update tab badge for due count
  const dueTab = document.querySelector('[data-tab="due"]');
  dueTab.textContent = today.length > 0 ? `Due (${today.length})` : "Due";
}

// ---- Actions --------------------------------------------------------------

async function completeTask(id) {
  const result = await api("POST", `/api/tasks/${id}/complete`);
  if (result.error) { alert(result.error); return; }
  await loadTasks();
}

async function deleteTask(id) {
  if (!confirm("Delete this task?")) return;
  await api("DELETE", `/api/tasks/${id}`);
  await loadTasks();
}

async function showHistory(id, name) {
  const data = await api("GET", `/api/tasks/${id}/history`);
  document.getElementById("history-title").textContent = `History: ${name}`;
  const list = document.getElementById("history-list");
  list.innerHTML = "";
  if (data.length === 0) {
    list.innerHTML = "<li style='justify-content:center'>No completions yet.</li>";
  } else {
    data.forEach(c => {
      const li = document.createElement("li");
      li.innerHTML = `
        <span>${formatDate(c.completed_at.slice(0, 10))}</span>
        <span>interval was ${intervalLabel(c.interval_days)}</span>
      `;
      list.appendChild(li);
    });
  }
  document.getElementById("history-modal").style.display = "flex";
}

// ---- Add task form --------------------------------------------------------

document.getElementById("open-add-modal").addEventListener("click", () => {
  document.getElementById("task-start").value = TODAY;
  document.getElementById("add-modal").style.display = "flex";
  document.getElementById("task-name").focus();
});

document.getElementById("close-add-modal").addEventListener("click", () => {
  document.getElementById("add-modal").style.display = "none";
  document.getElementById("add-form").reset();
});

document.getElementById("add-modal").addEventListener("click", e => {
  if (e.target === e.currentTarget) e.currentTarget.style.display = "none";
});

document.getElementById("add-form").addEventListener("submit", async e => {
  e.preventDefault();
  const name  = document.getElementById("task-name").value.trim();
  const desc  = document.getElementById("task-desc").value.trim();
  const start = document.getElementById("task-start").value;
  if (!name) return;

  const result = await api("POST", "/api/tasks", { name, description: desc, start_date: start });
  if (result.error) { alert(result.error); return; }

  document.getElementById("add-modal").style.display = "none";
  document.getElementById("add-form").reset();
  await loadTasks();

  // Switch to "due" or "upcoming" tab depending on start date
  switchTab(result.is_due_today || result.is_overdue ? "due" : "upcoming");
});

// ---- History modal --------------------------------------------------------

document.getElementById("close-history-modal").addEventListener("click", () => {
  document.getElementById("history-modal").style.display = "none";
});

document.getElementById("history-modal").addEventListener("click", e => {
  if (e.target === e.currentTarget) e.currentTarget.style.display = "none";
});

// ---- Tabs -----------------------------------------------------------------

function switchTab(name) {
  activeTab = name;
  document.querySelectorAll(".tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === name);
  });
  document.querySelectorAll(".tab-panel").forEach(panel => {
    panel.style.display = panel.id === `tab-${name}` ? "" : "none";
  });
}

document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

// ---- Utils ----------------------------------------------------------------

function escHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ---- Init -----------------------------------------------------------------

loadTasks();
