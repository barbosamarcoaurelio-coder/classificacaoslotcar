let classificationExports = [];
let classificationShareBusy = false;

function exportFilenamePart(value) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "") || "gt";
}

function clearClassificationExports() {
  classificationExports.forEach(item => URL.revokeObjectURL(item.url));
  classificationExports = [];
  document.getElementById("exportPreviews").replaceChildren();
}

async function renderClassificationPNG(info, generatedAt) {
  const lastStage = Math.max(0, ...info.etapas_info.filter(e => e.realizada).map(e => e.etapa));
  const exportInfo = { ...info, etapas_info: info.etapas_info.filter(e => e.etapa <= lastStage) };
  const container = document.createElement("div");
  container.className = "classification-export";
  container.setAttribute("aria-hidden", "true");
  container.style.width = `${Math.max(900, 620 + exportInfo.etapas_info.length * 90)}px`;
  const header = document.createElement("div");
  header.className = "export-header";
  const logo = document.createElement("img");
  logo.src = "/static/logo-gt.jpeg";
  logo.alt = "GT Racing";
  const heading = document.createElement("div");
  const title = document.createElement("h2");
  title.textContent = `${info.campeonato} · ${info.subdivisao}`;
  const metadata = document.createElement("p");
  metadata.textContent = `Disputadas ${info.etapas_disputadas}/${info.total_etapas} · Descartes ${info.descartes_aplicados} (de ${info.descartes_configurados}) · Gerado em ${generatedAt}`;
  heading.append(title, metadata);
  if (info.regras_confirmadas === false) {
    const pending = document.createElement("p");
    pending.className = "alert-error";
    pending.textContent = "Histórico com regras pendentes · Pontuação provisória";
    heading.appendChild(pending);
  }
  header.append(logo, heading);
  const table = document.createElement("div");
  table.innerHTML = buildClassificationTable(exportInfo);
  const legend = document.querySelector(".classification-legend").cloneNode(true);
  legend.querySelector("#legendPromotion").style.display = info.sobem > 0 ? "inline-flex" : "none";
  legend.querySelector("#legendRelegation").style.display = info.rebaixados > 0 ? "inline-flex" : "none";
  legend.querySelectorAll("[id]").forEach(el => el.removeAttribute("id"));
  container.append(header, table, legend);
  document.body.appendChild(container);
  try {
    if (!logo.complete) {
      await new Promise((resolve, reject) => {
        logo.onload = resolve;
        logo.onerror = () => reject(new Error("Não foi possível carregar o logo GT Racing."));
      });
    }
    if (!logo.naturalWidth) throw new Error("Não foi possível carregar o logo GT Racing.");
    await document.fonts.ready;
    container.style.width = `${Math.max(container.offsetWidth, container.scrollWidth + 48)}px`;
    const canvas = await html2canvas(container, {
      scale: 2,
      backgroundColor: "#121212",
      logging: false,
      onclone: cloned => {
        // Export always uses the dark palette, without changing the user's theme.
        cloned.body.classList.remove("theme-light");
        cloned.body.classList.add("theme-dark");
      }
    });
    return await new Promise((resolve, reject) => canvas.toBlob(blob => {
      if (blob && blob.size) resolve(blob);
      else reject(new Error("Não foi possível criar o PNG. Tente novamente."));
    }, "image/png"));
  } finally {
    container.remove();
  }
}

async function exportClassification() {
  const button = document.getElementById("btnExportClassification");
  const status = document.getElementById("exportStatus");
  const camp = state.data.championships.find(c => c.id == state.selectedCampId);
  if (!camp) {
    status.textContent = "Selecione um campeonato para exportar.";
    return;
  }
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  status.className = "loading-spinner";
  status.textContent = "Gerando imagens da classificação...";
  document.getElementById("modalClassificationExport").classList.add("hidden");
  clearClassificationExports();
  const generatedAt = new Date().toLocaleString("pt-BR");
  try {
    for (const sub of camp.subdivisoes) {
      status.textContent = `Gerando imagem ${sub.subdivisao}...`;
      const response = await fetch(`/api/classification/${camp.id}/${encodeURIComponent(sub.subdivisao)}?simulacao=false`);
      if (!response.ok) throw new Error(`Não foi possível carregar ${sub.subdivisao} (HTTP ${response.status}).`);
      const info = await response.json();
      if (!info.classificacao.length) continue;
      const blob = await renderClassificationPNG(info, generatedAt);
      const name = `classificacao_${exportFilenamePart(camp.nome)}_${exportFilenamePart(sub.subdivisao)}.png`;
      classificationExports.push({
        file: new File([blob], name, { type: "image/png" }),
        url: URL.createObjectURL(blob),
        subdiv: sub.subdivisao
      });
    }
    if (!classificationExports.length) throw new Error("Este campeonato não tem pilotos com resultados para exportar.");
    showClassificationPreviews();
    status.textContent = "";
    openModal("modalClassificationExport");
    document.getElementById("btnShareClassification").focus();
  } catch (error) {
    console.error("Erro ao exportar classificação:", error);
    clearClassificationExports();
    status.className = "alert-error";
    status.textContent = `Erro ao gerar classificação: ${error.message}`;
  } finally {
    button.disabled = !state.selectedCampId;
    button.removeAttribute("aria-busy");
  }
}

function showClassificationPreviews() {
  const status = document.getElementById("exportShareStatus");
  status.className = "";
  status.textContent = 'No iPhone, use Compartilhar para escolher WhatsApp ou "Salvar imagem". Para salvar todas, use os botões de cada subdivisão.';
  const previews = document.getElementById("exportPreviews");
  classificationExports.forEach(item => {
    const section = document.createElement("section");
    section.className = "export-preview";
    const title = document.createElement("h4");
    title.textContent = item.subdiv;
    const image = document.createElement("img");
    image.src = item.url;
    image.alt = `Classificação completa ${item.subdiv}`;
    section.append(title, image);
    if (classificationExports.length > 1) {
      const actions = document.createElement("div");
      actions.className = "export-actions";
      [["Compartilhar", false], ["Salvar imagem", true]].forEach(([label, save]) => {
        const button = document.createElement("button");
        button.className = "btn btn-outline";
        button.textContent = `${label} ${item.subdiv}`;
        button.onclick = () => shareClassificationImages([item], save);
        actions.appendChild(button);
      });
      section.appendChild(actions);
    }
    previews.appendChild(section);
  });
  document.getElementById("btnShareClassification").onclick = () => shareClassificationImages(classificationExports, false);
  document.getElementById("btnSaveClassification").onclick = () => shareClassificationImages([classificationExports[0]], true);
}

async function shareClassificationImages(items, save) {
  if (classificationShareBusy) return;
  const status = document.getElementById("exportShareStatus");
  status.className = "";
  classificationShareBusy = true;
  try {
    let selected = items;
    if (items.length > 1 && (!navigator.canShare || !navigator.canShare({ files: items.map(item => item.file) }))) {
      selected = [items[0]];
      status.textContent = "Este navegador envia uma imagem por vez. Depois desta, use Compartilhar em cada subdivisão.";
    }
    const files = selected.map(item => item.file);
    if (navigator.share && navigator.canShare && navigator.canShare({ files })) {
      if (save) status.textContent = 'Escolha "Salvar imagem" na folha de compartilhamento. Para as demais, use Salvar imagem em cada subdivisão.';
      // Keep share in the tap handler: iOS requires an active user gesture.
      await navigator.share({ files });
    } else {
      selected.forEach(item => {
        const link = document.createElement("a");
        link.href = item.url;
        link.download = item.file.name;
        document.body.appendChild(link);
        link.click();
        link.remove();
      });
      status.textContent = "PNG baixado. Abra em Downloads/Arquivos e use Compartilhar → Salvar imagem ou WhatsApp. Use os botões de cada subdivisão para as demais.";
    }
  } catch (error) {
    if (error.name === "AbortError") {
      status.textContent = "Compartilhamento cancelado. As imagens continuam disponíveis.";
    } else {
      console.error("Erro ao compartilhar classificação:", error);
      status.className = "alert-error";
      status.textContent = `Não foi possível compartilhar: ${error.message}. Tente uma subdivisão por vez.`;
    }
  } finally {
    classificationShareBusy = false;
  }
}
