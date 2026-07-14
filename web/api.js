// Cliente mínimo de la API REST de Supabase (solo lectura, anon key + RLS).

async function sb(recurso, params) {
  const url = `${CONFIG.SUPABASE_URL}/rest/v1/${recurso}?${params}`;
  const r = await fetch(url, {
    headers: {
      apikey: CONFIG.SUPABASE_ANON_KEY,
      Authorization: `Bearer ${CONFIG.SUPABASE_ANON_KEY}`,
    },
  });
  if (!r.ok) throw new Error(`API ${r.status}: ${await r.text()}`);
  return r.json();
}

function fotoUrl(fotoPath) {
  if (!fotoPath) return null;
  return `${CONFIG.SUPABASE_URL}/storage/v1/object/public/fotos/${fotoPath}`;
}

// "UNIÓN POR LA PATRIA" -> "Unión Por La Patria"
function titulo(s) {
  if (!s) return "";
  return s.toLowerCase().replace(/(^|\s|-|\.)\p{L}/gu, (c) => c.toUpperCase());
}

const CARGOS = {
  presidente: "Presidente",
  senador: "Senador/a",
  diputado: "Diputado/a",
  gobernador: "Gobernador/a",
  ministro: "Ministro/a",
  jefe_gabinete: "Jefe de Gabinete",
  funcionario: "Funcionario/a",
  intendente: "Intendente/a",
};

function fechaCorta(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

// Meses completos transcurridos entre dos fechas ISO (para estimar dieta cobrada).
function mesesEntre(inicioIso, finIso) {
  const inicio = new Date(inicioIso);
  const fin = new Date(finIso);
  let meses = (fin.getFullYear() - inicio.getFullYear()) * 12 + (fin.getMonth() - inicio.getMonth());
  if (fin.getDate() < inicio.getDate()) meses--;
  return Math.max(0, meses);
}

// Componente <Fuente>: toda card con dato externo muestra su fuente con link.
function htmlFuente(url, nombre, fechaCaptura) {
  if (!url) return "";
  const f = fechaCaptura ? ` · capturado ${fechaCorta(fechaCaptura)}` : "";
  const nom = nombre || new URL(url).hostname;
  return `<div class="fuente">&#128196; Fuente: <a href="${url}" target="_blank" rel="noopener">${nom}</a>${f}</div>`;
}

function escaparHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function cardPersona(p) {
  const foto = fotoUrl(p.foto_path);
  const img = foto
    ? `<img src="${foto}" alt="${escaparHtml(p.nombre)} ${escaparHtml(p.apellido)}" loading="lazy"
         onerror="this.outerHTML='<div class=\'sin-foto\'>&#128100;</div>'">`
    : `<div class="sin-foto">&#128100;</div>`;
  const detalle = [titulo(p.provincia), titulo(p.bloque || p.ministerio)].filter(Boolean).join(" · ");
  return `<a class="card" href="persona.html?slug=${encodeURIComponent(p.slug)}">
    ${img}
    <div class="cuerpo">
      <span class="badge ${p.cargo}">${CARGOS[p.cargo] || p.cargo}</span>
      <div class="nombre">${escaparHtml(p.nombre)} ${escaparHtml(p.apellido)}</div>
      <div class="detalle">${escaparHtml(detalle)}</div>
    </div>
  </a>`;
}
