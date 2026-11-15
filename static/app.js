// Classificação Geral · GT Racing Slot Car - Frontend Engine
let state = {
  user: { authenticated: false, is_admin: false, email: "" },
  data: { categories: [], championships: [], pilots: [], scoring_tables: [] },
  selectedCampId: null,
  selectedSubdiv: "GT1",
  isSimulating: false,
  wizardParsedData: null,
  theme: localStorage.getItem("gt_theme") || "dark"
};

// Inicialização
document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  initNavigation();
  initModals();
  await checkAuth();
  await loadInitialData();
  setupEventListeners();
});

// Tema Claro / Escuro
function initTheme() {
  document.body.className = state.theme === "light" ? "theme-light" : "theme-dark";
  const icon = document.getElementById("themeIcon");
  if (icon) icon.textContent = state.theme === "light" ? "🌙" : "☀️";
}

function toggleTheme() {
  state.theme = state.theme === "light" ? "dark" : "light";
  localStorage.setItem("gt_theme", state.theme);
  initTheme();
}

// Navegação pelas Abas Inferiores
function initNavigation() {
  document.getElementById("filterCampSituacao").addEventListener("change", renderChampionshipsList);
  document.getElementById("filterCampCategoria").addEventListener("change", renderChampionshipsList);
  document.getElementById("selectRankingCategory").addEventListener("change", loadRanking);
  document.getElementById("btnRefreshRanking").addEventListener("click", loadRanking);
  const navButtons = document.querySelectorAll(".bottom-nav .nav-item");
  navButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      navButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
      const targetPanel = document.getElementById(targetId);
      if (targetPanel) targetPanel.classList.add("active");

      // Atualizar dados da aba
      if (targetId === "tabChampionships") renderChampionshipsList();
      if (targetId === "tabPilots") renderPilotsList();
      if (targetId === "tabScoring") renderScoringTablesList();
      if (targetId === "tabCategories") renderCategoriesList();
      if (targetId === "tabRanking") loadRanking();
    });
  });
}

// Checagem de Autenticação
async function checkAuth() {
  try {
    const res = await fetch("/api/auth/me");
    if (res.ok) {
      state.user = await res.json();
    }
  } catch (e) {
    console.error("Erro ao verificar auth:", e);
  }
  updateAuthUI();
}

function updateAuthUI() {
  const authLabel = document.getElementById("authLabel");
  const adminElements = document.querySelectorAll(".admin-only");
  
  if (state.user.authenticated && state.user.is_admin) {
    if (authLabel) authLabel.textContent = "Sair (" + state.user.email.split("@")[0] + ")";
    adminElements.forEach(el => el.classList.remove("hidden"));
  } else {
    if (authLabel) authLabel.textContent = "Login Admin";
    adminElements.forEach(el => el.classList.add("hidden"));
  }
}

// Carregamento de Dados Iniciais
async function loadInitialData() {
  try {
    const res = await fetch("/api/data");
    if (res.ok) {
      state.data = await res.json();
      const activeChampionships = state.data.championships.filter(c => c.situacao === "em_andamento");
      populateChampionshipSelect(activeChampionships);
      if (activeChampionships.length > 0) {
        const stored = localStorage.getItem("gt_selected_camp");
        const found = activeChampionships.find(c => c.id == stored);
        if (found) {
          state.selectedCampId = found.id;
        } else {
          // Selecionar por padrão o campeonato com mais etapas carregadas
          let maxEtapas = -1;
          let best = activeChampionships[0];
          activeChampionships.forEach(c => {
            let total = 0;
            Object.values(c.resultados).forEach(arr => total += arr.length);
            if (total > maxEtapas) {
              maxEtapas = total;
              best = c;
            }
          });
          state.selectedCampId = best.id;
        }
        localStorage.setItem("gt_selected_camp", state.selectedCampId);
        const sel = document.getElementById("selectChampionship");
        if (sel) sel.value = state.selectedCampId;
        updateSubdivPills();
        await loadClassification();
      } else {
        state.selectedCampId = null;
        state.selectedSubdiv = null;
        localStorage.removeItem("gt_selected_camp");
        document.getElementById("subdivPills").replaceChildren();
        document.getElementById("classificationPending").classList.add("hidden");
        document.getElementById("classificationTableWrapper").textContent = "Nenhum campeonato em andamento.";
        document.getElementById("infoCategory").textContent = "-";
        document.getElementById("infoCorte").textContent = "-";
        document.getElementById("infoEtapas").textContent = "0/0";
        document.getElementById("infoDescartes").textContent = "0";
      }
    }
  } catch (e) {
    console.error("Erro ao carregar dados:", e);
  }
}

let rankingRequest = 0;

async function loadRanking() {
  const request = ++rankingRequest;
  const category = document.getElementById("selectRankingCategory").value;
  const wrapper = document.getElementById("rankingTableWrapper");
  const warnings = document.getElementById("rankingWarnings");
  wrapper.textContent = "Carregando ranking...";
  warnings.replaceChildren();
  try {
    const res = await fetch("/api/rankings", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Não foi possível carregar o ranking.");
    if (request !== rankingRequest) return;
    data.avisos.forEach(message => {
      const notice = document.createElement("p");
      notice.className = "alert-error";
      notice.textContent = message;
      warnings.appendChild(notice);
    });
    const rows = data.rankings[category];
    if (!rows.length) {
      wrapper.textContent = "Nenhuma participação registrada nesta categoria desde 01/08/2026.";
      return;
    }
    wrapper.innerHTML = `<table class="pilot-ranking-table">
      <caption>Ranking de ${document.getElementById("selectRankingCategory").selectedOptions[0].textContent}</caption>
      <thead><tr><th scope="col">Pos.</th><th scope="col">Piloto</th>
      <th scope="col">Corridas</th><th scope="col">Pontos de ranking</th></tr></thead><tbody></tbody></table>`;
    const body = wrapper.querySelector("tbody");
    rows.forEach(row => {
      const tr = document.createElement("tr");
      if (row.pos <= 3) tr.className = ["", "row-first", "row-second", "row-third"][row.pos];
      [row.pos + "º", row.piloto, row.participacoes,
        row.indice.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      ].forEach(value => {
        const td = document.createElement("td");
        td.textContent = value;
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
  } catch (error) {
    if (request !== rankingRequest) return;
    wrapper.replaceChildren();
    const message = document.createElement("p");
    message.className = "alert-error";
    message.textContent = error.message;
    wrapper.appendChild(message);
  }
}

// Popula Seletor de Campeonatos
function populateChampionshipSelect(championships) {
  const sel = document.getElementById("selectChampionship");
  if (!sel) return;
  sel.innerHTML = "";
  sel.disabled = championships.length === 0;
  document.getElementById("btnSearchBlog").disabled = sel.disabled;
  document.getElementById("btnNewStageWizard").disabled = sel.disabled;
  if (!championships.length) {
    const opt = document.createElement("option");
    opt.textContent = "Nenhum campeonato em andamento";
    opt.value = "";
    sel.appendChild(opt);
  }
  championships.forEach(c => {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = `${c.nome} (${c.categoria})`;
    sel.appendChild(opt);
  });
}

// Atualiza Pílulas de Subdivisões
function updateSubdivPills() {
  const pillsContainer = document.getElementById("subdivPills");
  if (!pillsContainer) return;
  pillsContainer.innerHTML = "";

  const camp = state.data.championships.find(c => c.id == state.selectedCampId);
  const subdivs = camp ? camp.subdivisoes.map(s => s.subdivisao) : ["GT1", "GT2", "GT3"];

  if (!subdivs.includes(state.selectedSubdiv)) {
    state.selectedSubdiv = subdivs[0] || "GT1";
  }

  subdivs.forEach(sub => {
    const btn = document.createElement("button");
    btn.className = `pill-btn ${sub === state.selectedSubdiv ? "active" : ""}`;
    btn.textContent = sub;
    btn.addEventListener("click", () => {
      state.selectedSubdiv = sub;
      updateSubdivPills();
      loadClassification();
    });
    pillsContainer.appendChild(btn);
  });
}

// Carregar e Renderizar Classificação Oficial
async function loadClassification() {
  if (!state.selectedCampId || !state.selectedSubdiv) return;
  const campId = state.selectedCampId;
  const subdiv = state.selectedSubdiv;
  
  const wrapper = document.getElementById("classificationTableWrapper");
  if (wrapper) wrapper.innerHTML = '<div class="loading-spinner">Calculando classificação oficial...</div>';

  try {
    const url = `/api/classification/${state.selectedCampId}/${state.selectedSubdiv}?simulacao=${state.isSimulating}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Erro ao buscar classificação.");
    const data = await res.json();
    if (state.selectedCampId !== campId || state.selectedSubdiv !== subdiv) return;
    renderClassificationTable(data);
  } catch (e) {
    if (state.selectedCampId !== campId || state.selectedSubdiv !== subdiv) return;
    if (wrapper) wrapper.innerHTML = `<div class="alert-error">Erro ao carregar classificação: ${e.message}</div>`;
  }
}

// Renderização da Tabela de Classificação
function renderClassificationTable(info) {
  document.getElementById("classificationPending").classList.toggle("hidden", info.regras_confirmadas !== false);
  // Atualizar info cards
  document.getElementById("infoCategory").textContent = info.categoria || "-";
  document.getElementById("infoCorte").textContent = info.tempo_de_corte || "Sem corte";
  document.getElementById("infoEtapas").textContent = `${info.etapas_disputadas}/${info.total_etapas}`;
  document.getElementById("infoDescartes").textContent = `${info.descartes_aplicados} (de ${info.descartes_configurados})`;

  // Banner de Simulação (se existir no DOM)
  const simBanner = document.getElementById("simBanner");
  if (simBanner) {
    if (info.simulacao) {
      simBanner.classList.remove("hidden");
    } else {
      simBanner.classList.add("hidden");
    }
  }

  // Cabeçalhos das Etapas (todas do campeonato, incluindo faltantes)
  const etapasTh = info.etapas_info.map(e => {
    const date = /^(\d{4})-(\d{2})-(\d{2})$/.exec(e.data || "");
    const dateLabel = date ? `${date[3]}-${date[2]}` : "--";
    const dateTitle = date ? (e.realizada && !e.simulada ? "Data da corrida" : "Data prevista") : "Data não informada";
    return `<th>E${e.etapa}${e.is_ultima ? ' <span class="font-double">×2</span>' : ''}${e.simulada ? ' <span style="font-size:9px;">🎲</span>' : ''}
      <span class="stage-date" title="${dateTitle}">${dateLabel}</span></th>`;
  }).join("");

  // Linhas dos Pilotos
  const rows = info.classificacao.map(l => {
    let rowClass = "";
    let badge = "";

    if (l.pos === 1) rowClass = "row-first";
    else if (l.pos === 2) rowClass = "row-second";
    else if (l.pos === 3) rowClass = "row-third";
    else if (l.status === "sobe") {
      rowClass = "row-promotion";
      badge = ' <span style="color:#F57F17;font-weight:bold;">↑</span>';
    } else if (l.status === "rebaixa") {
      rowClass = "row-relegation";
      badge = ' <span style="color:#D32F2F;font-weight:bold;">↓</span>';
    }

    // Badges de Probabilidade de Subir e Cair
    const chanceSubir = l.chance_acesso !== undefined ? l.chance_acesso : 0;
    let badgeSubirClass = "risk-zero";
    if (chanceSubir >= 60) badgeSubirClass = "prob-up-high";
    else if (chanceSubir >= 25) badgeSubirClass = "prob-up-med";
    else if (chanceSubir > 0) badgeSubirClass = "prob-up-low";
    const subirBadge = `<span class="risk-badge ${badgeSubirClass}">${chanceSubir}%</span>`;

    const chanceQueda = l.chance_rebaixamento !== undefined ? l.chance_rebaixamento : 0;
    let badgeQuedaClass = "risk-zero";
    if (chanceQueda >= 60) badgeQuedaClass = "risk-high";
    else if (chanceQueda >= 25) badgeQuedaClass = "risk-medium";
    else if (chanceQueda > 0) badgeQuedaClass = "risk-low";
    const quedaBadge = `<span class="risk-badge ${badgeQuedaClass}">${chanceQueda}%</span>`;

    const cellsEtapas = info.etapas_info.map(e => {
      const ep = l.etapas[e.etapa] || {};
      if (!ep.realizada) {
        return '<td><span class="stage-pending">-</span></td>';
      }
      if (!ep.presente) {
        if (ep.descartada) {
          return '<td><span class="discarded-pts"><s>0</s></span></td>';
        }
        return '<td><span class="absent-mark">0</span></td>';
      }
      const posStr = ep.posicao ? `<small class="stage-pos">(${ep.posicao}º)</small>` : '';
      if (ep.descartada) {
        return `<td><span class="discarded-pts"><s>${ep.pontos}</s></span> ${posStr}</td>`;
      }
      return `<td><strong>${ep.pontos}</strong> ${posStr}</td>`;
    }).join("");

    return `
      <tr class="${rowClass}">
        <td style="font-weight:bold;">${l.pos}º</td>
        <td class="td-pilot">${l.piloto}${badge}</td>
        <td class="td-total-col td-total-bruto">${l.total_sem_descarte}</td>
        <td class="td-total-col td-total-liquido">${l.total_com_descarte}</td>
        <td class="td-prob">${subirBadge}</td>
        <td class="td-prob">${quedaBadge}</td>
        ${cellsEtapas}
      </tr>
    `;
  }).join("");

  const tableHtml = `
    <table class="ranking-table">
      <thead>
        <tr>
          <th style="width:40px;">Pos</th>
          <th class="th-pilot">Piloto</th>
          <th class="th-total-col">Total</th>
          <th class="th-total-col th-total-header">Total<br>c/ Descarte</th>
          <th class="th-prob">% Subir</th>
          <th class="th-prob">% Queda</th>
          ${etapasTh}
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>
  `;

  document.getElementById("classificationTableWrapper").innerHTML = tableHtml;

  // Ajustar legenda se sobem/rebaixados forem 0
  const legProm = document.getElementById("legendPromotion");
  const legReleg = document.getElementById("legendRelegation");
  if (legProm) legProm.style.display = info.sobem > 0 ? "inline-flex" : "none";
  if (legReleg) legReleg.style.display = info.rebaixados > 0 ? "inline-flex" : "none";
}

// ABA 2: RENDERIZAR CAMPEONATOS
function renderChampionshipsList() {
  const container = document.getElementById("championshipsList");
  if (!container) return;
  container.innerHTML = "";

  const situacao = document.getElementById("filterCampSituacao").value;
  const categoria = document.getElementById("filterCampCategoria").value;
  const filtered = state.data.championships.filter(c =>
    (!situacao || (c.situacao || "em_andamento") === situacao) &&
    (!categoria || c.ranking_categoria === categoria));
  document.getElementById("championshipsCount").textContent =
    `${filtered.length} de ${state.data.championships.length} campeonatos`;
  if (!filtered.length) container.textContent = "Nenhum campeonato encontrado com estes filtros.";
  filtered.forEach(c => {
    const card = document.createElement("div");
    card.className = "card-item";

    // Subdivisões resumo
    const subsHtml = c.subdivisoes.map(s => `
      <span style="background:var(--bg-input);padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;">
        <strong>${s.subdivisao}</strong>: Corte ${s.tempo_de_corte || 'Nenhum'} | Sobem: ${s.sobem} | Rebaixados: ${s.rebaixados}
      </span>
    `).join("");

    // Etapas e Resultados
    let etapasHtml = "";
    c.datas_das_etapas.forEach((dt, idx) => {
      const eNum = idx + 1;
      const hasRes = Object.values(c.resultados).some(subRes => subRes.some(r => r.etapa === eNum));
      const hasBlog = c.fontes_blog && c.fontes_blog[String(eNum)];
      
      etapasHtml += `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border-color);font-size:12px;">
          <span>
            <strong>Etapa ${eNum}</strong> (${dt}): 
            ${hasRes ? '<span style="color:#4caf50;font-weight:bold;">Concluída</span>' : '<span style="color:var(--text-muted);">Aguardando</span>'}
          </span>
          <div style="display:flex;gap:4px;">
            ${hasBlog || hasRes ? `<button class="btn btn-sm btn-outline" onclick="openAuditModal(${c.id}, ${eNum})">Auditoria</button>` : ''}
            ${state.user.is_admin ? `<button class="btn btn-sm btn-outline" onclick="openRescheduleModal(${c.id}, ${eNum}, '${dt}')">Data</button>` : ''}
          </div>
        </div>
      `;
    });

    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <div class="card-title">${c.nome}</div>
          <div class="card-subtitle">${c.situacao === "encerrado" ? "Encerrado" : "Em andamento"} · ${c.incluir_no_ranking === false ? "Não compõe o ranking" : (c.regras_confirmadas === false ? "Ranking aguarda conferência" : "Compõe o ranking")}</div>
          ${c.regras_confirmadas === false ? '<p class="alert-error">Regras pendentes · fora do ranking</p>' : ''}
          <div class="card-subtitle">Categoria: ${c.categoria} | Tabela: ${c.tabela_pontuacao}</div>
        </div>
        ${state.user.is_admin ? `
          <div style="display:flex;gap:6px;">
            <button class="btn btn-sm btn-outline" onclick="openEditChampionshipModal(${c.id})">Editar</button>
            <button class="btn btn-sm btn-danger" onclick="deleteChampionship(${c.id}, '${c.nome}')">Excluir</button>
          </div>
        ` : ''}
      </div>

      <div class="card-details-grid">
        <div><strong>Início:</strong> ${c.inicio}</div>
        <div><strong>Etapas:</strong> ${c.etapas}</div>
        <div><strong>Descartes:</strong> ${c.descartes}</div>
        <div><strong>Periodicidade:</strong> ${c.periodicidade}</div>
        <div><strong>Dobro na Última:</strong> ${c.ultima_etapa_em_dobro ? 'Sim (×2)' : 'Não'}</div>
      </div>

      <div style="margin: 8px 0;">${subsHtml}</div>

      <div style="margin-top:12px;">
        <strong style="font-size:12px;display:block;margin-bottom:6px;">Calendário e Resultados das Etapas:</strong>
        ${etapasHtml}
      </div>
    `;

    container.appendChild(card);
  });
}

// ABA 3: RENDERIZAR PILOTOS
function renderPilotsList() {
  const container = document.getElementById("pilotsList");
  const countBadge = document.getElementById("pilotsCount");
  const searchTerm = (document.getElementById("inputSearchPilot")?.value || "").toLowerCase().trim();
  if (!container) return;
  container.innerHTML = "";

  const filtered = state.data.pilots.filter(p => {
    if (!searchTerm) return true;
    if (p.nome.toLowerCase().includes(searchTerm)) return true;
    if (p.apelidos_no_blog.some(a => a.toLowerCase().includes(searchTerm))) return true;
    return false;
  });

  if (countBadge) countBadge.textContent = `Mostrando ${filtered.length} de ${state.data.pilots.length} pilotos`;

  filtered.forEach(p => {
    const card = document.createElement("div");
    card.className = "card-item";

    const provasHtml = p.provas.map(pr => `
      <span style="background:var(--bg-card-alt);padding:3px 8px;border-radius:6px;font-size:12px;margin-right:6px;border:1px solid var(--border-color);">
        🏎️ <strong>${pr.categoria}:</strong> ${pr.subdivisao}
      </span>
    `).join("") || '<span class="text-muted">Nenhuma prova cadastrada</span>';

    const apelidosStr = p.apelidos_no_blog.length > 0 
      ? p.apelidos_no_blog.join(", ") 
      : '<span class="text-muted">Nenhum apelido</span>';

    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <div class="card-title">${p.nome}</div>
          <div class="card-subtitle">Apelidos no Blog: ${apelidosStr}</div>
        </div>
        ${state.user.is_admin ? `
          <div style="display:flex;gap:6px;">
            <button class="btn btn-sm btn-outline" onclick="openEditPilotModal(${p.id})">Editar</button>
            <button class="btn btn-sm btn-danger" onclick="deletePilot(${p.id}, '${p.nome}')">Excluir</button>
          </div>
        ` : ''}
      </div>
      <div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;">
        ${provasHtml}
      </div>
    `;

    container.appendChild(card);
  });
}

// ABA 4: RENDERIZAR TABELAS DE PONTUAÇÃO
function renderScoringTablesList() {
  const container = document.getElementById("scoringTablesList");
  if (!container) return;
  container.innerHTML = "";

  state.data.scoring_tables.forEach(t => {
    const card = document.createElement("div");
    card.className = "card-item";

    const pontosGrid = t.pontos_por_posicao.map((pts, i) => `
      <span style="display:inline-block;padding:2px 6px;margin:2px;background:var(--bg-card-alt);border-radius:4px;font-size:11px;">
        ${i + 1}º: <strong>${pts}</strong> pts
      </span>
    `).join("");

    card.innerHTML = `
      <div class="card-title">${t.nome}</div>
      <div class="card-subtitle">${t.regra_alem_da_tabela || 'Posições acima: 0 pts'}</div>
      <div style="margin-top:10px;line-height:1.8;">
        ${pontosGrid}
      </div>
    `;
    container.appendChild(card);
  });
}

// ABA 5: RENDERIZAR CATEGORIAS
function renderCategoriesList() {
  const container = document.getElementById("categoriesList");
  if (!container) return;
  container.innerHTML = "";

  state.data.categories.forEach(cat => {
    const card = document.createElement("div");
    card.className = "card-item";

    const subs = cat.subdivisoes.map(s => `
      <span style="background:var(--bg-card-alt);padding:4px 10px;border-radius:6px;font-size:12px;margin-right:6px;font-weight:700;">
        ${s}
      </span>
    `).join("");

    card.innerHTML = `
      <div class="card-title">${cat.nome}</div>
      <div style="margin-top:10px;">
        <span class="text-muted" style="font-size:12px;display:block;margin-bottom:6px;">Subdivisões oficiais:</span>
        ${subs}
      </div>
    `;
    container.appendChild(card);
  });
}

// CONFIGURAÇÃO DE EVENT LISTENERS
function setupEventListeners() {
  // Alternar Tema
  document.getElementById("btnThemeToggle")?.addEventListener("click", toggleTheme);

  // Login / Logout
  document.getElementById("btnAuth")?.addEventListener("click", () => {
    if (state.user.authenticated) {
      if (confirm("Deseja encerrar a sessão de administrador?")) {
        fetch("/api/auth/logout", { method: "POST" }).then(() => {
          state.user = { authenticated: false, is_admin: false, email: "" };
          updateAuthUI();
          loadClassification();
        });
      }
    } else {
      openModal("modalLogin");
    }
  });

  document.getElementById("formLogin")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("loginEmail").value;
    const password = document.getElementById("loginPassword").value;
    const errorEl = document.getElementById("loginError");

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
      });
      if (!res.ok) {
        const err = await res.json();
        errorEl.textContent = err.detail || "Erro ao entrar.";
        errorEl.classList.remove("hidden");
        return;
      }
      const data = await res.json();
      state.user = { authenticated: true, is_admin: data.is_admin, email: data.email };
      closeModal("modalLogin");
      errorEl.classList.add("hidden");
      updateAuthUI();
      loadClassification();
    } catch (err) {
      errorEl.textContent = "Erro de conexão: " + err.message;
      errorEl.classList.remove("hidden");
    }
  });

  // Mudança de Campeonato
  document.getElementById("selectChampionship")?.addEventListener("change", (e) => {
    state.selectedCampId = parseInt(e.target.value);
    localStorage.setItem("gt_selected_camp", state.selectedCampId);
    updateSubdivPills();
    loadClassification();
  });

  // Busca de Pilotos
  document.getElementById("inputSearchPilot")?.addEventListener("input", renderPilotsList);

  // WIZARD DE ETAPA
  document.getElementById("btnNewStageWizard")?.addEventListener("click", openNewStageWizard);
  document.getElementById("btnSearchBlog")?.addEventListener("click", () => {
    openNewStageWizard();
    discoverBlogPosts();
  });
  document.getElementById("btnDiscoverBlog")?.addEventListener("click", discoverBlogPosts);
  document.getElementById("btnFetchBlog")?.addEventListener("click", handleFetchBlog);
  document.getElementById("btnParseText")?.addEventListener("click", handleParseRawText);
  document.getElementById("btnWizardBack")?.addEventListener("click", () => {
    document.getElementById("wizardStep2").classList.add("hidden");
    document.getElementById("wizardStep1").classList.remove("hidden");
  });
  document.getElementById("btnWizardSave")?.addEventListener("click", handleSaveWizardResults);

  // Reagendamento de Etapas
  document.getElementById("formReschedule")?.addEventListener("submit", handleRescheduleSubmit);

  // Backup e Restauração
  document.getElementById("btnBackupModal")?.addEventListener("click", () => openModal("modalBackup"));
  document.getElementById("btnDownloadBackup")?.addEventListener("click", () => {
    window.location.href = "/api/backup/export";
  });
  document.getElementById("btnUploadRestore")?.addEventListener("click", handleRestoreBackup);

  // Cadastros
  document.getElementById("btnNewChampionship")?.addEventListener("click", () => openEditChampionshipModal(null));
  document.getElementById("formChampionship")?.addEventListener("submit", handleChampionshipSubmit);
  document.getElementById("btnNewPilot")?.addEventListener("click", () => openEditPilotModal(null));
  document.getElementById("formPilot")?.addEventListener("submit", handlePilotSubmit);
}

// MODAL CONTROLS
function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove("hidden");
}

function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add("hidden");
}

function initModals() {
  document.querySelectorAll(".modal-backdrop").forEach(backdrop => {
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) backdrop.classList.add("hidden");
    });
  });
}

// WIZARD DE LANÇAMENTO E IMPORTAÇÃO DO BLOG
function openNewStageWizard() {
  const camp = state.data.championships.find(c => c.id == state.selectedCampId);
  if (!camp) return;
  state.wizardParsedData = null;
  state.wizardCampId = camp.id;
  document.getElementById("wizardBlogResults").replaceChildren();

  document.getElementById("wizardCampName").value = camp.nome;

  // Próxima etapa sugerida
  let maxEtapa = 0;
  Object.values(camp.resultados).forEach(subList => {
    subList.forEach(r => { if (r.etapa > maxEtapa) maxEtapa = r.etapa; });
  });
  const nextEtapa = maxEtapa + 1;
  document.getElementById("wizardEtapaNum").value = nextEtapa;

  // Data sugerida
  const datas = camp.datas_das_etapas;
  const suggestedDate = (datas && datas[nextEtapa - 1]) ? datas[nextEtapa - 1] : new Date().toISOString().split("T")[0];
  document.getElementById("wizardEtapaData").value = suggestedDate;

  document.getElementById("wizardBlogUrl").value = "";
  document.getElementById("wizardRawText").value = "";
  document.getElementById("wizardStep1Error").classList.add("hidden");

  document.getElementById("wizardStep1").classList.remove("hidden");
  document.getElementById("wizardStep2").classList.add("hidden");

  openModal("modalStageWizard");
}

async function handleFetchBlog() {
  const url = document.getElementById("wizardBlogUrl").value.trim();
  const errorEl = document.getElementById("wizardStep1Error");
  if (!url) {
    errorEl.textContent = "Por favor, informe a URL do post do blog.";
    errorEl.classList.remove("hidden");
    return;
  }
  errorEl.classList.add("hidden");
  await executeParseBlog({ url });
}

async function discoverBlogPosts() {
  const campId = state.wizardCampId;
  const results = document.getElementById("wizardBlogResults");
  const button = document.getElementById("btnDiscoverBlog");
  button.disabled = true;
  results.classList.remove("alert-error");
  results.textContent = "Procurando publicações do campeonato...";
  try {
    const response = await fetch(`/api/championships/${campId}/blog-search`, { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Não foi possível consultar o blog.");
    if (state.wizardCampId !== campId) return;
    results.replaceChildren();
    if (!data.posts.length) {
      results.textContent = "Nenhuma etapa identificada com este nome e edição. Você ainda pode colar o link abaixo.";
    }
    data.posts.forEach(post => {
      const card = document.createElement("div");
      card.className = "card-option";
      const title = document.createElement("p");
      title.textContent = post.titulo;
      const status = document.createElement("p");
      status.className = "text-muted";
      status.textContent = `Etapa ${post.etapa} · ${post.ja_cadastrada ? "Já tem resultados: confira antes de substituir" : "Sem resultados cadastrados"}`;
      const review = document.createElement("button");
      review.className = "btn btn-outline";
      review.textContent = "Conferir resultado";
      review.addEventListener("click", async () => {
        if (document.getElementById("btnFetchBlog").disabled) return;
        document.getElementById("wizardBlogUrl").value = post.url;
        await handleFetchBlog();
      });
      card.append(title, status, review);
      results.appendChild(card);
    });
  } catch (error) {
    if (state.wizardCampId !== campId) return;
    results.textContent = error.message;
    results.classList.add("alert-error");
  } finally {
    button.disabled = false;
  }
}

async function handleParseRawText() {
  const raw_text = document.getElementById("wizardRawText").value.trim();
  const errorEl = document.getElementById("wizardStep1Error");
  if (!raw_text) {
    errorEl.textContent = "Por favor, cole o texto da página.";
    errorEl.classList.remove("hidden");
    return;
  }
  errorEl.classList.add("hidden");
  await executeParseBlog({ raw_text });
}

async function executeParseBlog(payload) {
  const campId = state.wizardCampId;
  const btn = document.getElementById("btnFetchBlog");
  if (btn?.disabled) return;
  const reviewButtons = document.querySelectorAll("#wizardBlogResults button, #btnParseText");
  reviewButtons.forEach(button => { button.disabled = true; });
  if (btn) {
    btn.textContent = "Buscando...";
    btn.disabled = true;
  }

  try {
    const res = await fetch("/api/blog/fetch-and-parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...payload,
        championship_id: campId
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Falha na leitura do blog.");
    }

    const data = await res.json();
    if (state.wizardCampId !== campId) return;
    state.wizardParsedData = data;

    // Atualizar etapa se veio no título
    if (data.etapa_num) {
      document.getElementById("wizardEtapaNum").value = data.etapa_num;
    }
    if (data.data_etapa) document.getElementById("wizardEtapaData").value = data.data_etapa;

    // Renderizar Passo 2
    renderWizardStep2(data);
  } catch (err) {
    const errorEl = document.getElementById("wizardStep1Error");
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  } finally {
    reviewButtons.forEach(button => { button.disabled = false; });
    if (btn) {
      btn.textContent = "Ler do Blog";
      btn.disabled = false;
    }
  }
}

function renderWizardStep2(parsed) {
  document.getElementById("wizardStep1").classList.add("hidden");
  document.getElementById("wizardStep2").classList.remove("hidden");
  document.getElementById("wizardReviewStage").textContent =
    `Etapa ${document.getElementById("wizardEtapaNum").value} · Data: ${document.getElementById("wizardEtapaData").value}`;

  // Alerta de campeonato
  const alertEl = document.getElementById("wizardPostAlert");
  if (parsed.alerta_campeonato) {
    alertEl.textContent = parsed.alerta_campeonato;
    alertEl.classList.remove("hidden");
  } else {
    alertEl.classList.add("hidden");
  }

  const container = document.getElementById("wizardSubdivisionsContainer");
  container.innerHTML = "";

  const camp = state.data.championships.find(c => c.id == state.wizardCampId);
  const subsEsperadas = camp ? camp.subdivisoes.map(s => s.subdivisao) : ["GT1", "GT2", "GT3"];

  subsEsperadas.forEach(sub => {
    const pilotosNaSub = parsed.subdivisoes[sub] || [];
    const sec = document.createElement("div");
    sec.className = "card-option";
    sec.style.marginBottom = "14px";

    sec.innerHTML = `
      <h4 style="color:var(--flag-yellow);margin-bottom:8px;">Subdivisão ${sub} (${pilotosNaSub.length} pilotos encontrados)</h4>
      <div class="table-responsive">
        <table class="ranking-table" style="font-size:12px;">
          <thead>
            <tr>
              <th style="width:30px;">Pos</th>
              <th>Nome no Blog</th>
              <th>Piloto Vinculado</th>
              <th>Status Reconhecimento</th>
              <th>Novo Apelido?</th>
            </tr>
          </thead>
          <tbody id="wizardTableBody_${sub}"></tbody>
        </table>
      </div>
    `;

    container.appendChild(sec);
    const tbody = sec.querySelector(`#wizardTableBody_${sub}`);

    pilotosNaSub.forEach((p, idx) => {
      const tr = document.createElement("tr");

      // Opções do Select
      let optionsHtml = `<option value="__NEW__" ${!p.reconhecido ? 'selected' : ''}>+ Criar novo piloto: "${p.nome_no_blog}"</option>`;
      state.data.pilots.forEach(cad => {
        const isSel = p.piloto === cad.nome ? 'selected' : '';
        optionsHtml += `<option value="${cad.nome}" ${isSel}>${cad.nome}</option>`;
      });

      const warningHtml = p.aviso ? `<div style="color:#d32f2f;font-size:11px;margin-top:2px;">⚠️ ${p.aviso}</div>` : '';

      tr.innerHTML = `
        <td>${p.pos_no_blog}º</td>
        <td><strong>${p.nome_no_blog}</strong> ${p.total_voltas ? `<small>(${p.total_voltas})</small>` : ''}</td>
        <td>
          <select class="form-control wizard-pilot-select" data-sub="${sub}" data-pos="${p.pos_no_blog}" data-nome-blog="${p.nome_no_blog}">
            ${optionsHtml}
          </select>
          ${warningHtml}
        </td>
        <td>
          ${p.reconhecido 
            ? `<span style="color:#4caf50;">✓ ${p.metodo}</span>` 
            : `<span style="color:#ff9800;">Atenção</span>`}
        </td>
        <td>
          <input type="checkbox" class="wizard-save-nickname" data-nome-blog="${p.nome_no_blog}" checked title="Salvar como apelido para futuras importações">
        </td>
      `;
      tbody.appendChild(tr);
    });
  });
}

// Salvar Resultados do Wizard
async function handleSaveWizardResults() {
  const etapa = parseInt(document.getElementById("wizardEtapaNum").value);
  const data = document.getElementById("wizardEtapaData").value;
  const url_blog = document.getElementById("wizardBlogUrl").value.trim();

  // Coletar ordem por subdivisão
  const camp = state.data.championships.find(c => c.id == state.wizardCampId);
  const subsEsperadas = camp ? camp.subdivisoes.map(s => s.subdivisao) : ["GT1", "GT2", "GT3"];

  const resultados_por_subdivisao = {};
  const auditoria_detalhes = {};
  const novos_apelidos = {};

  for (const sub of subsEsperadas) {
    const selects = document.querySelectorAll(`.wizard-pilot-select[data-sub="${sub}"]`);
    const ordem = [];
    const auditList = [];

    selects.forEach(sel => {
      const val = sel.value;
      const nomeBlog = sel.getAttribute("data-nome-blog");
      const pos = parseInt(sel.getAttribute("data-pos"));

      const finalNome = val === "__NEW__" ? nomeBlog : val;
      ordem.push(finalNome);

      auditList.push({
        pos_no_blog: pos,
        nome_no_blog: nomeBlog,
        piloto: finalNome
      });

      // Verificar se salva apelido
      const chk = document.querySelector(`.wizard-save-nickname[data-nome-blog="${nomeBlog}"]`);
      if (chk && chk.checked && val !== "__NEW__" && val !== nomeBlog) {
        novos_apelidos[val] = nomeBlog;
      }
    });

    if (ordem.length > 0) {
      resultados_por_subdivisao[sub] = ordem;
      auditoria_detalhes[sub] = auditList;
    }
  }

  if (!Number.isInteger(etapa) || etapa < 1 || !data || !Object.keys(resultados_por_subdivisao).length) {
    alert("Confira o número, a data e os resultados da etapa antes de salvar.");
    return;
  }
  const existing = Object.keys(resultados_por_subdivisao).some(sub =>
    (camp.resultados[sub] || []).some(result => result.etapa === etapa));
  if (existing && !confirm("Esta etapa já tem resultados cadastrados. Deseja substituir os resultados das subdivisões conferidas?")) return;
  const btn = document.getElementById("btnWizardSave");
  btn.disabled = true;
  btn.textContent = "Gravando...";

  try {
    const res = await fetch("/api/stages/save-results", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        championship_id: state.wizardCampId,
        etapa,
        data,
        resultados_por_subdivisao,
        origem: url_blog ? "blog" : "manual",
        url_blog: url_blog || null,
        auditoria_detalhes,
        novos_apelidos,
        substituir_existentes: existing
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Erro ao gravar resultado.");
    }

    closeModal("modalStageWizard");
    alert("Resultado da Etapa " + etapa + " gravado com sucesso!");
    await loadInitialData();
  } catch (err) {
    alert("Erro ao salvar: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Salvar Resultado Oficial";
  }
}

// AUDITORIA DA ETAPA
async function openAuditModal(championshipId, etapa) {
  openModal("modalAudit");
  const content = document.getElementById("auditContent");
  content.innerHTML = '<div class="loading-spinner">Carregando dados de auditoria...</div>';

  try {
    const res = await fetch(`/api/stages/audit/${championshipId}/${etapa}`);
    if (!res.ok) throw new Error("Auditoria não encontrada.");
    const audit = await res.json();

    let subsAuditHtml = "";
    if (audit.por_subdivisao) {
      Object.entries(audit.por_subdivisao).forEach(([sub, list]) => {
        const rows = list.map(item => `
          <tr>
            <td>${item.pos_no_blog}º</td>
            <td><strong>${item.nome_no_blog}</strong></td>
            <td style="color:var(--flag-yellow);">${item.piloto}</td>
          </tr>
        `).join("");

        subsAuditHtml += `
          <div style="margin-top:12px;">
            <h4 style="color:var(--flag-yellow);margin-bottom:6px;">Subdivisão ${sub}</h4>
            <table class="ranking-table" style="font-size:12px;">
              <thead>
                <tr>
                  <th style="width:30px;">Pos</th>
                  <th>Nome Lido no Blog</th>
                  <th>Piloto Atribuído</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        `;
      });
    }

    content.innerHTML = `
      <div class="card-details-grid">
        <div><strong>Origem:</strong> ${audit.origem || 'Não especificada'}</div>
        <div><strong>Registrado em:</strong> ${audit.registrado_em || '-'}</div>
        <div><strong>Editado Manualmente:</strong> ${audit.editado_manualmente ? '<span style="color:#f44336;font-weight:bold;">Sim</span>' : 'Não'}</div>
      </div>
      ${audit.url ? `<p style="font-size:12px;margin:8px 0;"><strong>Link do Blog:</strong> <a href="${audit.url}" target="_blank" rel="noopener" style="color:var(--flag-yellow);">${audit.url}</a></p>` : ''}
      ${subsAuditHtml || '<p class="text-muted">Sem detalhes de pilotos registrados para esta etapa.</p>'}
    `;
  } catch (err) {
    content.innerHTML = `<div class="alert-error">${err.message}</div>`;
  }
}

// REAGENDAMENTO DE ETAPA
function openRescheduleModal(championshipId, etapa, dataAtual) {
  document.getElementById("rescheduleCampId").value = championshipId;
  document.getElementById("rescheduleEtapaNum").value = etapa;
  document.getElementById("rescheduleEtapaLabel").textContent = `Etapa ${etapa}:`;
  document.getElementById("rescheduleNewDate").value = dataAtual;
  document.getElementById("rescheduleShiftFollow").checked = true;
  openModal("modalReschedule");
}

async function handleRescheduleSubmit(e) {
  e.preventDefault();
  const campId = document.getElementById("rescheduleCampId").value;
  const etapa = parseInt(document.getElementById("rescheduleEtapaNum").value);
  const nova_data = document.getElementById("rescheduleNewDate").value;
  const reajustar_seguintes = document.getElementById("rescheduleShiftFollow").checked;

  try {
    const res = await fetch(`/api/championships/${campId}/reschedule-stage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ etapa, nova_data, reajustar_seguintes })
    });
    if (!res.ok) throw new Error("Erro ao reagendar data.");
    closeModal("modalReschedule");
    alert("Data atualizada com sucesso!");
    await loadInitialData();
    renderChampionshipsList();
  } catch (err) {
    alert(err.message);
  }
}

// CADASTRO / EDIÇÃO DE CAMPEONATOS
function openEditChampionshipModal(campId) {
  const title = document.getElementById("modalCampTitle");
  const catSel = document.getElementById("campCategoria");
  const tabSel = document.getElementById("campTabelaPontuacao");

  catSel.innerHTML = state.data.categories.map(c => `<option value="${c.nome}">${c.nome}</option>`).join("");
  tabSel.innerHTML = state.data.scoring_tables.map(t => `<option value="${t.nome}">${t.nome}</option>`).join("");

  document.getElementById("editCampId").value = campId || "";

  if (campId) {
    title.textContent = "Editar Campeonato";
    const c = state.data.championships.find(item => item.id == campId);
    if (c) {
      document.getElementById("campNome").value = c.nome;
      catSel.value = c.categoria;
      document.getElementById("campInicio").value = c.inicio;
      document.getElementById("campEtapas").value = c.etapas;
      document.getElementById("campDescartes").value = c.descartes;
      document.getElementById("campPeriodicidade").value = c.periodicidade;
      tabSel.value = c.tabela_pontuacao;
      document.getElementById("campDobroUltima").checked = c.ultima_etapa_em_dobro;
      document.getElementById("campRankingCategoria").value = c.ranking_categoria || "";
      document.getElementById("campRegrasConfirmadas").checked = c.regras_confirmadas !== false;
      document.getElementById("campSituacao").value = c.situacao || "em_andamento";
      document.getElementById("campIncluirRanking").checked = c.incluir_no_ranking !== false;
      renderSubdivInputs(c.subdivisoes);
    }
  } else {
    title.textContent = "Novo Campeonato";
    document.getElementById("campNome").value = "";
    document.getElementById("campInicio").value = new Date().toISOString().split("T")[0];
    document.getElementById("campEtapas").value = 6;
    document.getElementById("campDescartes").value = 1;
    document.getElementById("campPeriodicidade").value = "semanal";
    document.getElementById("campDobroUltima").checked = true;
    document.getElementById("campRankingCategoria").value = "";
    document.getElementById("campRegrasConfirmadas").checked = true;
    document.getElementById("campSituacao").value = "em_andamento";
    document.getElementById("campIncluirRanking").checked = true;
    renderSubdivInputs([
      { subdivisao: "GT1", tempo_de_corte: "5.9s", sobem: 0, rebaixados: 3 },
      { subdivisao: "GT2", tempo_de_corte: "6.1s", sobem: 3, rebaixados: 3 },
      { subdivisao: "GT3", tempo_de_corte: "6.2s", sobem: 3, rebaixados: 0 }
    ]);
  }

  openModal("modalChampionshipEdit");
}

function renderSubdivInputs(subdivs) {
  const container = document.getElementById("campSubdivsContainer");
  container.innerHTML = "";

  subdivs.forEach((s, idx) => {
    const row = document.createElement("div");
    row.className = "form-row";
    row.style.marginBottom = "8px";
    row.innerHTML = `
      <div class="form-group col-quarter">
        <label>Subdivisão</label>
        <input type="text" class="form-control camp-sub-nome" value="${s.subdivisao}" required>
      </div>
      <div class="form-group col-quarter">
        <label>Tempo de Corte</label>
        <input type="text" class="form-control camp-sub-corte" value="${s.tempo_de_corte || ''}" placeholder="Ex: 5.9s">
      </div>
      <div class="form-group col-quarter">
        <label>Sobem (Acesso)</label>
        <input type="number" class="form-control camp-sub-sobem" value="${s.sobem || 0}" min="0">
      </div>
      <div class="form-group col-quarter">
        <label>Rebaixados</label>
        <input type="number" class="form-control camp-sub-rebaixados" value="${s.rebaixados || 0}" min="0">
      </div>
    `;
    container.appendChild(row);
  });
}

async function handleChampionshipSubmit(e) {
  e.preventDefault();
  const campId = document.getElementById("editCampId").value;
  const nome = document.getElementById("campNome").value.trim();
  const categoria = document.getElementById("campCategoria").value;
  const inicio = document.getElementById("campInicio").value;
  const etapas = parseInt(document.getElementById("campEtapas").value);
  const descartes = parseInt(document.getElementById("campDescartes").value);
  const periodicidade = document.getElementById("campPeriodicidade").value;
  const tabela_pontuacao = document.getElementById("campTabelaPontuacao").value;
  const ultima_etapa_em_dobro = document.getElementById("campDobroUltima").checked;

  const subdivRows = document.querySelectorAll("#campSubdivsContainer .form-row");
  const subdivisoes = [];
  subdivRows.forEach(r => {
    subdivisoes.push({
      subdivisao: r.querySelector(".camp-sub-nome").value.trim(),
      tempo_de_corte: r.querySelector(".camp-sub-corte").value.trim() || null,
      sobem: parseInt(r.querySelector(".camp-sub-sobem").value) || 0,
      rebaixados: parseInt(r.querySelector(".camp-sub-rebaixados").value) || 0
    });
  });

  const payload = {
    nome, categoria, inicio, etapas, descartes, periodicidade,
    tabela_pontuacao, ultima_etapa_em_dobro, subdivisoes,
    ranking_categoria: document.getElementById("campRankingCategoria").value || null,
    regras_confirmadas: document.getElementById("campRegrasConfirmadas").checked,
    situacao: document.getElementById("campSituacao").value,
    incluir_no_ranking: document.getElementById("campIncluirRanking").checked
  };

  const url = campId ? `/api/championships/${campId}` : `/api/championships`;
  const method = campId ? "PUT" : "POST";

  try {
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const error = await res.json();
      throw new Error(typeof error.detail === "string" ? error.detail : "Confira os dados do campeonato.");
    }
    closeModal("modalChampionshipEdit");
    alert("Campeonato salvo com sucesso!");
    await loadInitialData();
    renderChampionshipsList();
  } catch (err) {
    alert(err.message);
  }
}

async function deleteChampionship(campId, nome) {
  if (!confirm(`Tem certeza que deseja excluir o campeonato "${nome}"? Esta ação não pode ser desfeita.`)) return;
  try {
    const res = await fetch(`/api/championships/${campId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Erro ao excluir campeonato.");
    alert("Campeonato excluído.");
    await loadInitialData();
    renderChampionshipsList();
  } catch (err) {
    alert(err.message);
  }
}

// CADASTRO / EDIÇÃO DE PILOTOS
function openEditPilotModal(pilotId) {
  const title = document.getElementById("modalPilotTitle");
  document.getElementById("editPilotId").value = pilotId || "";

  const container = document.getElementById("pilotProvasContainer");
  container.innerHTML = "";

  let currentPilot = null;
  if (pilotId) {
    currentPilot = state.data.pilots.find(p => p.id == pilotId);
    title.textContent = "Editar Piloto";
    document.getElementById("pilotNome").value = currentPilot.nome;
    document.getElementById("pilotApelidos").value = currentPilot.apelidos_no_blog.join(", ");
  } else {
    title.textContent = "Novo Piloto";
    document.getElementById("pilotNome").value = "";
    document.getElementById("pilotApelidos").value = "";
  }

  // Criar seletor de subdivisão para CADA categoria cadastrada
  state.data.categories.forEach(cat => {
    const provaExistente = currentPilot ? currentPilot.provas.find(pr => pr.categoria === cat.nome) : null;
    const currentSub = provaExistente ? provaExistente.subdivisao : "";

    const row = document.createElement("div");
    row.style.display = "flex";
    row.style.justifyContent = "space-between";
    row.style.alignItems = "center";
    row.style.padding = "6px 0";
    row.style.borderBottom = "1px solid var(--border-color)";

    let optionsHtml = '<option value="">(Não corre nesta categoria)</option>';
    cat.subdivisoes.forEach(s => {
      optionsHtml += `<option value="${s}" ${currentSub === s ? 'selected' : ''}>${s}</option>`;
    });

    row.innerHTML = `
      <span style="font-size:13px;font-weight:600;">${cat.nome}</span>
      <select class="form-control pilot-cat-sub" data-cat="${cat.nome}" style="width:160px;padding:6px 8px;">
        ${optionsHtml}
      </select>
    `;
    container.appendChild(row);
  });

  openModal("modalPilotEdit");
}

async function handlePilotSubmit(e) {
  e.preventDefault();
  const pilotId = document.getElementById("editPilotId").value;
  const nome = document.getElementById("pilotNome").value.trim();
  const apelidosRaw = document.getElementById("pilotApelidos").value;
  const apelidos_no_blog = apelidosRaw.split(",").map(a => a.trim()).filter(a => a.length > 0);

  const provas = [];
  document.querySelectorAll(".pilot-cat-sub").forEach(sel => {
    const sub = sel.value;
    const cat = sel.getAttribute("data-cat");
    if (sub) {
      provas.push({ categoria: cat, subdivisao: sub });
    }
  });

  const payload = { nome, apelidos_no_blog, provas };
  const url = pilotId ? `/api/pilots/${pilotId}` : `/api/pilots`;
  const method = pilotId ? "PUT" : "POST";

  try {
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error("Erro ao salvar piloto.");
    closeModal("modalPilotEdit");
    alert("Piloto salvo com sucesso!");
    await loadInitialData();
    renderPilotsList();
  } catch (err) {
    alert(err.message);
  }
}

async function deletePilot(pilotId, nome) {
  if (!confirm(`Deseja realmente excluir o piloto "${nome}"?`)) return;
  try {
    const res = await fetch(`/api/pilots/${pilotId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Erro ao excluir piloto.");
    alert("Piloto excluído.");
    await loadInitialData();
    renderPilotsList();
  } catch (err) {
    alert(err.message);
  }
}

// RESTAURAÇÃO DE BACKUP
async function handleRestoreBackup() {
  const fileInput = document.getElementById("inputRestoreFile");
  if (!fileInput.files || fileInput.files.length === 0) {
    alert("Selecione um arquivo de backup em JSON.");
    return;
  }
  const file = fileInput.files[0];
  const reader = new FileReader();

  reader.onload = async (e) => {
    try {
      const json = JSON.parse(e.target.result);
      if (!confirm("ATENÇÃO: A restauração substituirá todos os dados do banco atual pelo conteúdo do arquivo. Continuar?")) return;

      const res = await fetch("/api/backup/restore", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(json)
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Falha na restauração.");
      }
      alert("Backup restaurado com sucesso!");
      closeModal("modalBackup");
      await loadInitialData();
    } catch (err) {
      alert("Erro ao restaurar: " + err.message);
    }
  };
  reader.readAsText(file);
}
