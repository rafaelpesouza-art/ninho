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
    Busca aulas realizadas no período com seus registros e fotos.
    inicio/fim: 'YYYY-MM-DD'
    """
    aulas_res = (
        sb.table("aulas")
        .select("id, data_hora, duracao_min")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .eq("status", "realizada")
        .gte("data_hora", inicio + "T00:00:00")
        .lte("data_hora", fim + "T23:59:59")
        .order("data_hora")
        .execute()
    )
    aulas = aulas_res.data or []
    if not aulas:
        return []

    aula_ids = [a["id"] for a in aulas]
    aulas_map = {a["id"]: a for a in aulas}

    reg_res = (
        sb.table("registros_aula")
        .select("*, fotos_sessao(id, storage_path, legenda)")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .in_("aula_id", aula_ids)
        .order("criado_em")
        .execute()
    )
    registros = reg_res.data or []

    for r in registros:
        aula = aulas_map.get(r["aula_id"], {})
        r["data_hora"]  = aula.get("data_hora", "")
        r["duracao_min"] = aula.get("duracao_min", 0)
        r["fotos"]      = r.pop("fotos_sessao", None) or []

    return registros


# ---------------------------------------------------------------------------
# TEXTO WHATSAPP
# ---------------------------------------------------------------------------

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
    titulo: str, pontos_fortes: str, pontos_atencao: str, proximos_passos: str
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
    if pontos_fortes:
        linhas += ["*💪 PONTOS FORTES:*", pontos_fortes, ""]
    if pontos_atencao:
        linhas += ["*⚠️ PONTOS DE ATENÇÃO:*", pontos_atencao, ""]
    if proximos_passos:
        linhas += ["*🎯 RECOMENDAÇÕES:*", proximos_passos, ""]

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
