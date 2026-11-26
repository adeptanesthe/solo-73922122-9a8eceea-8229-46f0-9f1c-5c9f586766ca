"use strict";

const $ = (id) => document.getElementById(id);
const PREVIEW_LIMIT = 50;

let exampleData = null;
let lastResult = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function parseHzText(text, { minimum = 0, maxItems = null, field = "数值" } = {}) {
  const tokens = (text || "")
    .split(/[\s,;，；、]+/u)
    .map((token) => token.trim())
    .filter(Boolean);

  if (maxItems !== null && tokens.length > maxItems) {
    throw new Error(`${field}最多 ${maxItems} 项，当前有 ${tokens.length} 项`);
  }

  const values = [];
  for (const token of tokens) {
    if (!/^[+-]?\d+$/u.test(token)) {
      throw new Error(`${field}中的“${token}”不是整数 Hz`);
    }
    const number = Number(token);
    if (!Number.isSafeInteger(number)) {
      throw new Error(`${field}中的“${token}”超出安全整数范围`);
    }
    if (number < minimum) {
      throw new Error(`${field}中的 ${number} 小于允许的最小值 ${minimum}`);
    }
    values.push(number);
  }
  return values;
}

function showMessage(element, kind, message, issues = null) {
  element.className = `message ${kind || ""}`.trim();
  element.replaceChildren();

  if (message) {
    const text = document.createElement("div");
    text.textContent = message;
    element.appendChild(text);
  }

  if (Array.isArray(issues) && issues.length) {
    const list = document.createElement("ul");
    list.className = "issue-list";
    for (const issue of issues) {
      const item = document.createElement("li");
      item.textContent = issue.message || String(issue);
      list.appendChild(item);
    }
    element.appendChild(list);
  }

  if (!message && !(issues && issues.length)) {
    element.className = "message";
  }
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = { error: `服务返回了无法解析的响应（HTTP ${response.status}）` };
  }
  return { ok: response.ok, status: response.status, data };
}

function addObservationRow(observation = { sample_rate: "", peaks: [] }) {
  const row = document.createElement("div");
  row.className = "observation-row";

  const rateInput = document.createElement("input");
  rateInput.className = "obs-rate";
  rateInput.type = "number";
  rateInput.min = "1";
  rateInput.step = "1";
  rateInput.placeholder = "采样率 Hz";
  rateInput.value = observation.sample_rate ?? "";

  const peaksInput = document.createElement("input");
  peaksInput.className = "obs-peaks";
  peaksInput.type = "text";
  peaksInput.placeholder = "完整峰表，如 1400, 2000, 2300";
  peaksInput.value = Array.isArray(observation.peaks) ? observation.peaks.join(", ") : "";

  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.className = "danger-icon";
  removeButton.textContent = "删除";
  removeButton.addEventListener("click", () => row.remove());

  row.append(rateInput, peaksInput, removeButton);
  $("observationsList").appendChild(row);
  return row;
}

function appendObservationToForm(observation) {
  const rows = [...document.querySelectorAll(".observation-row")];
  const emptyRow = rows.find((row) => {
    return !row.querySelector(".obs-rate").value.trim() && !row.querySelector(".obs-peaks").value.trim();
  });

  if (emptyRow) {
    emptyRow.querySelector(".obs-rate").value = observation.sample_rate;
    emptyRow.querySelector(".obs-peaks").value = observation.peaks.join(", ");
  } else {
    addObservationRow(observation);
  }
}

function readObservationRows() {
  const observations = [];
  const rows = document.querySelectorAll(".observation-row");

  rows.forEach((row, index) => {
    const rateText = row.querySelector(".obs-rate").value.trim();
    const peaksText = row.querySelector(".obs-peaks").value.trim();
    if (!rateText && !peaksText) return;

    if (!rateText) {
      throw new Error(`第 ${index + 1} 个档位缺少采样率`);
    }
    const rates = parseHzText(rateText, { minimum: 1, field: `第 ${index + 1} 档采样率` });
    if (rates.length !== 1) {
      throw new Error(`第 ${index + 1} 档采样率只能填写一个整数`);
    }
    const sampleRate = rates[0];
    const peaks = parseHzText(peaksText, {
      minimum: 0,
      field: `第 ${index + 1} 档峰表`,
    });
    for (const peak of peaks) {
      if (2 * peak > sampleRate) {
        throw new Error(
          `第 ${index + 1} 档峰 ${peak} Hz 超出采样率 ${sampleRate} Hz 的 0～${sampleRate / 2} Hz 范围`,
        );
      }
    }
    observations.push({ sample_rate: sampleRate, peaks });
  });

  return observations;
}

function readFormPayload() {
  const suspects = parseHzText($("suspectsInput").value, {
    minimum: 0,
    maxItems: 32,
    field: "疑似干扰频率",
  });
  if (!suspects.length) {
    throw new Error("请至少输入一个疑似干扰频率");
  }

  const observations = readObservationRows();
  const availableRates = parseHzText($("availableRatesInput").value, {
    minimum: 1,
    field: "可用复测采样率",
  });

  return { suspects, observations, available_rates: availableRates };
}

function fillForm(data) {
  $("suspectsInput").value = (data.suspects || []).join(", ");
  $("observationsList").replaceChildren();
  (data.observations || []).forEach((obs) => addObservationRow(obs));
  if (!(data.observations || []).length) addObservationRow();
  $("availableRatesInput").value = (data.available_rates || []).join(", ");
}

function renderWarnings(result) {
  const container = $("warningsContainer");
  container.replaceChildren();
  if (!result.warnings || !result.warnings.length) return;

  const list = document.createElement("ul");
  list.className = "warning-list";
  for (const warning of result.warnings) {
    const item = document.createElement("li");
    item.textContent = warning.message || String(warning);
    list.appendChild(item);
  }
  container.appendChild(list);
}

function renderFrequencies(result) {
  const container = $("frequencyContainer");
  container.replaceChildren();

  const labels = {
    mandatory: "必有",
    possible_only: "仅可能有",
    excluded: "可排除",
    indeterminate: "无解/待定",
  };

  const legend = document.createElement("div");
  legend.className = "legend";
  legend.innerHTML = `
    <span><i class="legend-dot" style="background:var(--danger)"></i>所有可行组合均含</span>
    <span><i class="legend-dot" style="background:var(--warning)"></i>部分组合含、部分不含</span>
    <span><i class="legend-dot" style="background:var(--line)"></i>所有组合均不含</span>
  `;
  container.appendChild(legend);

  for (const item of result.frequency_report || []) {
    const badge = document.createElement("span");
    badge.className = `freq-badge ${escapeHtml(item.status)}`;
    const total = result.candidate_count || 0;
    const countText =
      item.status === "mandatory"
        ? `${total}/${total}`
        : item.status === "possible_only"
          ? `${item.candidate_count}/${total}`
          : item.status === "excluded"
            ? `0/${total}`
            : "—";
    badge.title = `在 ${total} 个可行组合中出现 ${item.candidate_count} 次`;
    badge.innerHTML = `<strong>${escapeHtml(labels[item.status] || item.status)}</strong> ${item.frequency} Hz <small>${countText}</small>`;
    container.appendChild(badge);
  }
}

function renderSummary(result) {
  const className = !result.feasible ? "bad" : result.candidate_count === 1 ? "good" : "";
  $("summaryContainer").innerHTML = `
    <p class="summary-headline ${className}">${escapeHtml(result.summary)}</p>
    <div class="button-row wrap">
      <span class="pill">可行组合 ${result.candidate_count}</span>
      <span class="pill">实测档位 ${(result.observations || []).length}</span>
      <span class="pill">可用档位 ${(result.available_rates || []).length}</span>
    </div>
  `;
}

function gearReportsTable(reports) {
  if (!reports || !reports.length) {
    return `<p class="more-note">未提供可用复测档位。</p>`;
  }

  const rows = reports
    .slice(0, PREVIEW_LIMIT)
    .map((report) => {
      const conclusion = report.distinguishes_all
        ? '<strong style="color:var(--success)">可一次分清</strong>'
        : '<span style="color:var(--warning)">存在重合</span>';
      return `
        <tr>
          <td class="mono">${report.sample_rate} Hz</td>
          <td class="mono">${report.distinct_table_count}/${report.candidate_count}</td>
          <td>${conclusion}</td>
          <td class="mono">${report.collision_group_count} 组 / 最大 ${report.largest_collision_group_size}</td>
        </tr>`;
    })
    .join("");

  const more =
    reports.length > PREVIEW_LIMIT
      ? `<p class="more-note">仅预览前 ${PREVIEW_LIMIT} 个档位；完整结果见 JSON API。</p>`
      : "";

  return `
    <details class="table-wrap" ${reports.length <= 8 ? "open" : ""}>
      <summary style="padding:.65rem .75rem;cursor:pointer;font-weight:700">查看各可用档位的分辨能力（${reports.length}）</summary>
      <table>
        <thead><tr><th>采样率</th><th>不同峰表/候选数</th><th>结论</th><th>重合情况</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </details>
    ${more}
  `;
}

function renderRecommendation(result) {
  const container = $("recommendationContainer");
  const recommendation = result.recommendation || {};

  if (recommendation.status === "recommended") {
    const signatureRows = (recommendation.signatures || [])
      .slice(0, PREVIEW_LIMIT)
      .map(
        (signature) => `
          <tr>
            <td class="mono">${signature.frequencies.join(", ")} Hz</td>
            <td class="mono">${signature.expected_peaks.join(", ")} Hz</td>
          </tr>`,
      )
      .join("");

    container.innerHTML = `
      <div class="recommend-hero">
        <div class="hint">最低可用且能一次分清全部组合的档位</div>
        <div class="recommend-rate">${recommendation.sample_rate} Hz</div>
        <p class="recommend-message">${escapeHtml(recommendation.message)}</p>
        <div class="button-row wrap" style="margin-top:.75rem">
          <button id="chooseRecommendedBtn" type="button" class="primary small">将 ${recommendation.sample_rate} Hz 填入补录</button>
        </div>
      </div>
      <details class="table-wrap" open>
        <summary style="padding:.65rem .75rem;cursor:pointer;font-weight:700">
          该档位下各候选的预期峰表（${recommendation.signatures?.length || 0}，均互不相同）
        </summary>
        <table>
          <thead><tr><th>候选频率 Hz</th><th>折叠后的完整峰表 Hz</th></tr></thead>
          <tbody>${signatureRows}</tbody>
        </table>
      </details>
      ${
        (recommendation.signatures?.length || 0) > PREVIEW_LIMIT
          ? `<p class="more-note">页面仅预览前 ${PREVIEW_LIMIT} 条；API 返回全部签名。</p>`
          : ""
      }
      ${gearReportsTable(recommendation.gear_reports)}
    `;
    $("chooseRecommendedBtn")?.addEventListener("click", () => {
      $("supplementRateInput").value = recommendation.sample_rate;
      $("supplementPeaksInput").focus();
      showMessage($("supplementMessage"), "info", `已填入推荐采样率 ${recommendation.sample_rate} Hz，请输入实测完整峰表。`);
    });
    return;
  }

  if (recommendation.status === "already_unique") {
    container.innerHTML = `
      <div class="recommend-hero ok">
        <div class="recommend-rate">无需复测</div>
        <p class="recommend-message">${escapeHtml(recommendation.message)}</p>
      </div>`;
    return;
  }

  const title =
    recommendation.status === "no_candidates"
      ? "当前无解"
      : recommendation.reason === "no_available_rates"
        ? "未提供合适档位"
        : "无合适复测档位";
  container.innerHTML = `
    <div class="recommend-hero no-fit">
      <div class="hint">推荐结果</div>
      <div class="recommend-rate">${escapeHtml(title)}</div>
      <p class="recommend-message">${escapeHtml(recommendation.message || "无法给出推荐。")}</p>
    </div>
    ${gearReportsTable(recommendation.gear_reports)}
  `;
}

function renderCandidates(result) {
  const container = $("candidatesContainer");
  $("candidateCountPill").textContent = String(result.candidate_count || 0);
  container.replaceChildren();

  if (!result.candidates || !result.candidates.length) {
    const empty = document.createElement("p");
    empty.className = "more-note";
    empty.textContent = "没有可行组合。补录若导致此状态，后端会拒绝并保留原结果。";
    container.appendChild(empty);
    return;
  }

  for (const [index, candidate] of result.candidates.slice(0, PREVIEW_LIMIT).entries()) {
    const card = document.createElement("div");
    card.className = "candidate-card";

    const tables = (candidate.folded_tables || [])
      .map(
        (table) =>
          `<div><span class="mono">${table.sample_rate} Hz</span> → <span class="mono">[${table.peaks.join(", ")}] Hz</span></div>`,
      )
      .join("");

    card.innerHTML = `
      <div class="candidate-title">
        <span class="candidate-index">#${index + 1}</span>
        <span class="pill">${candidate.size} 个</span>
        <span class="freq-list mono">[${candidate.frequencies.join(", ")}] Hz</span>
      </div>
      <div class="mini-tables">${tables}</div>
    `;
    container.appendChild(card);
  }

  if (result.candidates.length > PREVIEW_LIMIT) {
    const note = document.createElement("p");
    note.className = "more-note";
    note.textContent = `页面仅显示前 ${PREVIEW_LIMIT} 个候选；后端 /api/analyze 会返回全部 ${result.candidates.length} 个。`;
    container.appendChild(note);
  }
}

function renderResult(result) {
  lastResult = result;
  renderSummary(result);
  renderWarnings(result);
  renderFrequencies(result);
  renderRecommendation(result);
  renderCandidates(result);
}

async function handleAnalyze() {
  const formMessage = $("formMessage");
  showMessage(formMessage, "");
  let payload;
  try {
    payload = readFormPayload();
  } catch (error) {
    showMessage(formMessage, "error", error.message);
    return;
  }

  $("analyzeBtn").disabled = true;
  $("analyzeBtn").textContent = "诊断中…";
  try {
    const { ok, data } = await postJson("/api/analyze", payload);
    if (!ok) {
      showMessage(formMessage, "error", data.error || "诊断失败", data.issues);
      return;
    }
    renderResult(data);
    showMessage($("globalMessage"), "success", "诊断已更新。");
    setTimeout(() => {
      if ($("globalMessage").textContent === "诊断已更新。") {
        $("globalMessage").replaceChildren();
        $("globalMessage").className = "global-message";
      }
    }, 2500);
  } catch (error) {
    showMessage(formMessage, "error", `无法连接诊断服务：${error.message}`);
  } finally {
    $("analyzeBtn").disabled = false;
    $("analyzeBtn").textContent = "开始诊断";
  }
}

async function handleSupplement() {
  const formMessage = $("formMessage");
  const supplementMessage = $("supplementMessage");
  const globalMessage = $("globalMessage");
  showMessage(formMessage, "");
  showMessage(supplementMessage, "");
  globalMessage.replaceChildren();
  globalMessage.className = "global-message";

  let payload;
  let sampleRate;
  let peaks;
  try {
    payload = readFormPayload();
    const rates = parseHzText($("supplementRateInput").value, { minimum: 1, field: "补录采样率" });
    if (rates.length !== 1) throw new Error("补录采样率必须是一个整数");
    sampleRate = rates[0];
    peaks = parseHzText($("supplementPeaksInput").value, { minimum: 0, field: "补录峰表" });
    for (const peak of peaks) {
      if (2 * peak > sampleRate) {
        throw new Error(`补录峰 ${peak} Hz 超出采样率 ${sampleRate} Hz 的 0～${sampleRate / 2} Hz 范围`);
      }
    }
  } catch (error) {
    showMessage(supplementMessage, "error", error.message);
    return;
  }

  $("supplementBtn").disabled = true;
  $("supplementBtn").textContent = "校验补录中…";
  try {
    const { status, data } = await postJson("/api/supplement", {
      ...payload,
      new_observation: { sample_rate: sampleRate, peaks },
    });

    if (status === 409 && data.original) {
      renderResult(data.original);
      showMessage(supplementMessage, "error", data.error || "补录无解，已拒绝并保留原结果。");
      globalMessage.className = "global-message error";
      globalMessage.textContent = "补录已被拒绝：页面保留的是补录前原诊断。";
      return;
    }

    if (status === 400 || !data || data.feasible === false) {
      showMessage(supplementMessage, "error", data?.error || "补录校验失败", data?.issues || null);
      return;
    }

    appendObservationToForm({ sample_rate: sampleRate, peaks });
    $("supplementPeaksInput").value = "";
    renderResult(data);
    showMessage(supplementMessage, "success", "补录可接受，诊断和推荐已更新。");
  } catch (error) {
    showMessage(supplementMessage, "error", `无法连接补录服务：${error.message}`);
  } finally {
    $("supplementBtn").disabled = false;
    $("supplementBtn").textContent = "提交补录并更新诊断";
  }
}

async function loadExample() {
  if (!exampleData) {
    const response = await fetch("/api/example");
    if (!response.ok) throw new Error("无法载入内置示例");
    exampleData = await response.json();
  }
  fillForm(exampleData);
  $("supplementRateInput").value = "";
  $("supplementPeaksInput").value = "";
  showMessage($("supplementMessage"), "");
  await handleAnalyze();
}

function resetForm() {
  $("suspectsInput").value = "";
  $("availableRatesInput").value = "";
  $("observationsList").replaceChildren();
  addObservationRow();
  $("supplementRateInput").value = "";
  $("supplementPeaksInput").value = "";
  $("formMessage").replaceChildren();
  $("supplementMessage").replaceChildren();
  $("globalMessage").replaceChildren();
  $("summaryContainer").textContent = "请输入数据或载入内置示例。";
  $("recommendationContainer").textContent = "尚无诊断结果。";
  $("frequencyContainer").replaceChildren();
  $("warningsContainer").replaceChildren();
  $("candidatesContainer").replaceChildren();
  $("candidateCountPill").textContent = "0";
  lastResult = null;
}

function initializeEvents() {
  $("analyzeBtn").addEventListener("click", handleAnalyze);
  $("supplementBtn").addEventListener("click", handleSupplement);
  $("addObservationBtn").addEventListener("click", () => addObservationRow());
  $("loadExampleBtn").addEventListener("click", () => {
    loadExample().catch((error) => showMessage($("formMessage"), "error", error.message));
  });
  $("resetBtn").addEventListener("click", resetForm);

  $("noGearDemoBtn").addEventListener("click", async () => {
    try {
      await loadExample();
      $("availableRatesInput").value = "8000";
      await handleAnalyze();
    } catch (error) {
      showMessage($("formMessage"), "error", error.message);
    }
  });

  $("useRecommendedBtn").addEventListener("click", () => {
    const rate = lastResult?.recommendation?.sample_rate;
    if (!rate) {
      showMessage($("supplementMessage"), "info", "当前没有“可一次分清全部组合”的推荐档位。");
      return;
    }
    $("supplementRateInput").value = rate;
    $("supplementPeaksInput").focus();
  });

  $("fillValidDemoBtn").addEventListener("click", async () => {
    try {
      if (!exampleData) {
        const response = await fetch("/api/example");
        exampleData = await response.json();
      }
      const obs = exampleData.suggested_observation;
      $("supplementRateInput").value = obs.sample_rate;
      $("supplementPeaksInput").value = obs.peaks.join(", ");
      showMessage($("supplementMessage"), "info", obs.label || "已填入有效演示峰表。");
    } catch (error) {
      showMessage($("supplementMessage"), "error", error.message);
    }
  });

  $("fillInvalidDemoBtn").addEventListener("click", async () => {
    try {
      if (!exampleData) {
        const response = await fetch("/api/example");
        exampleData = await response.json();
      }
      const obs = exampleData.invalid_observation;
      $("supplementRateInput").value = obs.sample_rate;
      $("supplementPeaksInput").value = obs.peaks.join(", ");
      showMessage($("supplementMessage"), "info", "已填入矛盾演示峰表；提交后应被拒绝且原结果不变。");
    } catch (error) {
      showMessage($("supplementMessage"), "error", error.message);
    }
  });
}

initializeEvents();
loadExample().catch((error) => {
  $("summaryContainer").textContent = `内置示例载入失败：${error.message}`;
});
