"""Camada de dados para o módulo de comunicação."""
from datetime import date

HUMOR_LABELS = {
    "animado":    "Animado 😊",
    "bem":        "Bem 🙂",
    "neutro":     "Neutro 😐",
    "cansado":    "Cansado 😴",
    "resistente": "Resistente 😤",
    "ansioso":    "Ansioso 😰",
    "triste":     "Triste 😢",
}

PARTICIPACAO_STARS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}

TIPO_LABELS = {
    "devolutiva": "Devolutiva",
    "relatorio":  "Relatório",
}


# ---------------------------------------------------------------------------
# REGISTROS
# ---------------------------------------------------------------------------

def listar_registros_periodo(
    sb, professor_id: str, aluno_id: str, inicio: str, fim: str
) -> list:
    """
    Busca registros de sessão no período com seus dados de aula e fotos.
    inicio/fim: 'YYYY-MM-DD'
    """
    reg_res = (
        sb.table("registros_sessao")
        .select("*, aulas(id, data_hora, duracao_min), fotos_sessao(id, storage_path, legenda)")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .execute()
    )
    registros_raw = reg_res.data or []

    # Filtra por data no Python para evitar problemas de formato de timezone
    inicio_pfx = inicio          # "YYYY-MM-DD"
    fim_pfx    = fim             # "YYYY-MM-DD"

    registros = []
    for r in registros_raw:
        aula = r.pop("aulas", None) or {}
        data_hora = aula.get("data_hora", "") or ""
        # Compara apenas os primeiros 10 chars (data) para robustez com timezones
        data_pfx = data_hora[:10]
        if not data_pfx or not (inicio_pfx <= data_pfx <= fim_pfx):
            continue
        r["data_hora"]   = data_hora
        r["duracao_min"] = aula.get("duracao_min", 0)
        r["fotos"]       = r.pop("fotos_sessao", None) or []
        registros.append(r)

    registros.sort(key=lambda r: r.get("data_hora", ""))
    return registros


# ---------------------------------------------------------------------------
# TEXTO WHATSAPP
# ---------------------------------------------------------------------------

def gerar_prefill_relatorio(registros: list, aluno_nome: str, periodo_ini: str, periodo_fim: str) -> dict:
    """
    Pré-preenche campos do relatório a partir dos registros do período.
    Retrocompatível: usa descricao, conteudo_trabalhado (antigo), proximos_passos, observacoes_familia.
    """
    n = len(registros)
    try:
        d_ini = date.fromisoformat(periodo_ini).strftime("%d/%m/%Y")
        d_fim = date.fromisoformat(periodo_fim).strftime("%d/%m/%Y")
    except Exception:
        d_ini, d_fim = periodo_ini, periodo_fim

    # Resumo: lista por sessão com o que foi trabalhado
    linhas_resumo = [f"Neste período ({d_ini} a {d_fim}) foram realizadas {n} sessão(ões) com {aluno_nome}.\n"]
    for r in registros:
        dh = r.get("data_hora", "")
        try:
            label = date.fromisoformat(dh[:10]).strftime("%d/%m")
        except Exception:
            label = ""
        desc = (r.get("descricao") or r.get("conteudo_trabalhado") or "").strip()
        if desc:
            linhas_resumo.append(f"• {label}: {desc}")
    resumo = "\n".join(linhas_resumo)

    # Pontos fortes: proximos_passos de cada sessão (o que foi avançando)
    fortes = []
    for r in registros:
        pp = (r.get("proximos_passos") or "").strip()
        if pp:
            dh = r.get("data_hora", "")
            try:
                label = date.fromisoformat(dh[:10]).strftime("%d/%m")
            except Exception:
                label = ""
            fortes.append(f"• {label}: {pp}" if label else f"• {pp}")
    pontos_fortes = "\n".join(fortes)

    # Recomendações para casa: observacoes_familia de cada sessão
    recs = []
    for r in registros:
        obs = (r.get("observacoes_familia") or "").strip()
        if obs:
            dh = r.get("data_hora", "")
            try:
                label = date.fromisoformat(dh[:10]).strftime("%d/%m")
            except Exception:
                label = ""
            recs.append(f"• {label}: {obs}" if label else f"• {obs}")
    recomendacoes = "\n".join(recs)

    return {
        "resumo":         resumo,
        "pontos_fortes":  pontos_fortes,
        "pontos_atencao": "",  # profissional preenche
        "proximos_passos": recomendacoes,
    }


def gerar_texto_devolutiva(registros: list, aluno_nome: str, periodo_ini: str = "", periodo_fim: str = "") -> str:
    linhas = [f"📚 *DEVOLUTIVA — {aluno_nome.upper()}*", ""]

    try:
        d_ini = date.fromisoformat(periodo_ini).strftime("%d/%m/%Y")
        d_fim = date.fromisoformat(periodo_fim).strftime("%d/%m/%Y")
        linhas += [f"📅 Período: {d_ini} a {d_fim}", ""]
    except Exception:
        pass

    for r in registros:
        dh = r.get("data_hora", "")
        label = ""
        if dh:
            try:
                label = date.fromisoformat(dh[:10]).strftime("%d/%m")
            except Exception:
                pass

        linhas.append(f"*📗 Sessão — {label}*")

        if r.get("descricao"):
            linhas.append(f"🎯 Atividades: {r['descricao']}")
        if r.get("evolucao"):
            linhas.append(f"✨ Evolução: {r['evolucao']}")
        humor = HUMOR_LABELS.get(r.get("humor", ""), r.get("humor", ""))
        if humor:
            linhas.append(f"😊 Humor: {humor}")
        if r.get("observacoes"):
            linhas.append(f"📝 Direcionamentos para casa: {r['observacoes']}")
        linhas.append("")

    linhas.append("Qualquer dúvida, estou à disposição! 🤗")
    return "\n".join(linhas)


def gerar_texto_relatorio(
    aluno_nome: str, periodo_ini: str, periodo_fim: str,
    titulo: str, pontos_fortes: str, pontos_atencao: str, proximos_passos: str,
    resumo: str = "",
) -> str:
    try:
        d_ini = date.fromisoformat(periodo_ini).strftime("%d/%m/%Y")
        d_fim = date.fromisoformat(periodo_fim).strftime("%d/%m/%Y")
    except Exception:
        d_ini, d_fim = periodo_ini, periodo_fim

    linhas = [
        f"📊 *{titulo.upper()}*",
        f"👤 Aluno(a): {aluno_nome}",
        f"📅 Período: {d_ini} a {d_fim}",
        "",
    ]
    if resumo:
        linhas += ["*📝 RESUMO:*", resumo, ""]
    if pontos_fortes:
        linhas += ["*💪 ÁREAS AVANÇADAS:*", pontos_fortes, ""]
    if pontos_atencao:
        linhas += ["*⚠️ ÁREAS DE ATENÇÃO:*", pontos_atencao, ""]
    if proximos_passos:
        linhas += ["*🏠 RECOMENDAÇÕES PARA CASA:*", proximos_passos, ""]

    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# PERSISTÊNCIA
# ---------------------------------------------------------------------------

def salvar_comunicacao(
    sb, professor_id: str, aluno_id: str, dados: dict
) -> dict:
    payload = {
        "professor_id":    professor_id,
        "aluno_id":        aluno_id,
        "titulo":          (dados.get("titulo") or "").strip() or "Comunicação",
        "periodo_inicio":  dados.get("periodo_inicio"),
        "periodo_fim":     dados.get("periodo_fim"),
        "conteudo":        dados.get("conteudo", ""),
        "objetivos_met":   dados.get("pontos_fortes", ""),
        "pontos_atencao":  dados.get("pontos_atencao", ""),
        "proximos_passos": dados.get("proximos_passos", ""),
        "tipo":            dados.get("tipo", "relatorio"),
        "texto_whatsapp":  dados.get("texto_whatsapp", ""),
        "resumo":          dados.get("resumo", ""),
        "fotos_selecionadas": dados.get("fotos_selecionadas", []),
    }
    res = sb.table("relatorios_evolucao").insert(payload).execute()
    return (res.data or [{}])[0]


def atualizar_comunicacao(sb, professor_id: str, comm_id: str, dados: dict) -> dict:
    payload = {
        "titulo":          (dados.get("titulo") or "").strip() or "Comunicação",
        "conteudo":        dados.get("conteudo", ""),
        "objetivos_met":   dados.get("objetivos_met", ""),
        "pontos_atencao":  dados.get("pontos_atencao", ""),
        "proximos_passos": dados.get("proximos_passos", ""),
        "texto_whatsapp":  dados.get("texto_whatsapp", ""),
        "resumo":          dados.get("resumo", ""),
    }
    res = (
        sb.table("relatorios_evolucao")
        .update(payload)
        .eq("id", comm_id)
        .eq("professor_id", professor_id)
        .execute()
    )
    return (res.data or [{}])[0]


def listar_historico(
    sb, professor_id: str, aluno_id: str | None = None, limit: int = 60
) -> list:
    q = (
        sb.table("relatorios_evolucao")
        .select("id, titulo, tipo, periodo_inicio, periodo_fim, criado_em, alunos(id, nome)")
        .eq("professor_id", professor_id)
        .order("criado_em", desc=True)
        .limit(limit)
    )
    if aluno_id:
        q = q.eq("aluno_id", aluno_id)
    return q.execute().data or []


def buscar_comunicacao(sb, professor_id: str, comm_id: str) -> dict | None:
    try:
        res = (
            sb.table("relatorios_evolucao")
            .select("*, alunos(id, nome)")
            .eq("professor_id", professor_id)
            .eq("id", comm_id)
            .maybe_single()
            .execute()
        )
        return res.data
    except Exception:
        return None
