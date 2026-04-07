from datetime import date, timedelta

from flask import jsonify, render_template, redirect, url_for, session, request
from . import main_bp
from ..auth.decorators import login_required
from ..extensions import get_supabase
from ..financeiro.model import resumo_financeiro, MESES_PT, MESES_PT_ABREV, fmt_valor


def _sb():
    sb = get_supabase()
    token = session.get("access_token")
    if token:
        try:
            sb.postgrest.auth(token)
        except Exception:
            pass
    return sb


@main_bp.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login_page"))


@main_bp.route("/dashboard")
@login_required
def dashboard():
    sb = _sb()
    professor_id = session.get("user_id")

    hoje = date.today()
    mes_atual = hoje.month
    ano_atual = hoje.year
    inicio_mes = date(ano_atual, mes_atual, 1)
    if mes_atual == 12:
        fim_mes = date(ano_atual + 1, 1, 1)
    else:
        fim_mes = date(ano_atual, mes_atual + 1, 1)

    # -----------------------------------------------------------------------
    # AULAS DE HOJE
    # -----------------------------------------------------------------------
    aulas_hoje = []
    try:
        r = (
            sb.table("aulas")
            .select("id, data_hora, duracao_min, status, alunos(nome)")
            .eq("professor_id", professor_id)
            .in_("status", ["agendada", "realizada"])
            .gte("data_hora", hoje.isoformat() + "T00:00:00")
            .lte("data_hora", hoje.isoformat() + "T23:59:59")
            .order("data_hora")
            .execute()
        )
        aulas_hoje = r.data or []
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # ALUNOS — uma única query para total_ativos, fases, inativos e IDs
    # -----------------------------------------------------------------------
    fases_count = {"anamnese": 0, "avaliacao": 0, "intervencao": 0, "alta": 0}
    aluno_ids_ativos: list = []
    alunos_inativos = 0
    try:
        r = (
            sb.table("alunos")
            .select("id, fase_atual, ativo")
            .eq("professor_id", professor_id)
            .execute()
        )
        for a in (r.data or []):
            if a.get("ativo"):
                aluno_ids_ativos.append(a["id"])
                f = a.get("fase_atual") or "anamnese"
                if f in fases_count:
                    fases_count[f] += 1
            else:
                alunos_inativos += 1
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # STATS BÁSICAS (KPIs) — total_alunos derivado da query acima
    # -----------------------------------------------------------------------
    stats = {
        "total_alunos": len(aluno_ids_ativos),
        "aulas_hoje": len(aulas_hoje),
        "faturas_abertas": 0,
        "inadimplentes": 0,
    }

    try:
        r = (
            sb.table("faturas")
            .select("id", count="exact")
            .eq("professor_id", professor_id)
            .in_("status", ["pendente", "parcial", "vencida"])
            .execute()
        )
        stats["faturas_abertas"] = r.count or 0
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # RESUMO DO MÊS
    # -----------------------------------------------------------------------
    resumo_fin = resumo_financeiro(sb, professor_id, mes_atual, ano_atual)
    stats["inadimplentes"] = resumo_fin["inadimplente"]

    aulas_realizadas = 0
    try:
        r = (
            sb.table("aulas")
            .select("id", count="exact")
            .eq("professor_id", professor_id)
            .eq("status", "realizada")
            .gte("data_hora", inicio_mes.isoformat())
            .lt("data_hora", fim_mes.isoformat())
            .execute()
        )
        aulas_realizadas = r.count or 0
    except Exception:
        pass

    receita_faturada = round(resumo_fin["receita"] + resumo_fin["pendente"], 2)
    resumo_mes = {
        "aulas_realizadas": aulas_realizadas,
        "receita_faturada": receita_faturada,
        "receita_recebida": resumo_fin["receita"],
        "inadimplentes": resumo_fin["inadimplente"],
        "a_vencer": resumo_fin["a_vencer"],
    }

    # -----------------------------------------------------------------------
    # ANAMNESES PENDENTES — alunos ativos sem anamnese preenchida
    # -----------------------------------------------------------------------
    anamneses_pendentes = 0
    try:
        if aluno_ids_ativos:
            r_anam = (
                sb.table("anamneses")
                .select("aluno_id")
                .eq("professor_id", professor_id)
                .in_("aluno_id", aluno_ids_ativos)
                .execute()
            )
            ids_com_anamnese = {a["aluno_id"] for a in (r_anam.data or [])}
            anamneses_pendentes = sum(
                1 for i in aluno_ids_ativos if i not in ids_com_anamnese
            )
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # LEMBRETES DE AMANHÃ
    # -----------------------------------------------------------------------
    amanha = hoje + timedelta(days=1)
    lembretes_amanha = []
    try:
        r = (
            sb.table("aulas")
            .select("id, data_hora, alunos(nome)")
            .eq("professor_id", professor_id)
            .eq("status", "agendada")
            .gte("data_hora", amanha.isoformat() + "T00:00:00")
            .lte("data_hora", amanha.isoformat() + "T23:59:59")
            .order("data_hora")
            .execute()
        )
        lembretes_amanha = r.data or []
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # ALERTAS
    # -----------------------------------------------------------------------
    alertas = []

    if resumo_fin["inadimplente"] > 0:
        n = resumo_fin["inadimplente"]
        alertas.append({
            "tipo": "danger",
            "icone": "alert-circle",
            "texto": f'{n} fatura{"s" if n > 1 else ""} vencida{"s" if n > 1 else ""} sem pagamento',
            "link": url_for("financeiro.faturas", status="vencida"),
        })

    # Sessões pendentes de registro: realizadas sem registro + agendadas já passadas (30 dias)
    sessoes_sem_registro = 0
    try:
        inicio_30 = (hoje - timedelta(days=30)).isoformat()
        agora_iso = hoje.isoformat() + "T23:59:59"

        # Sessões marcadas como realizadas mas sem registro
        r_real = (
            sb.table("aulas")
            .select("id")
            .eq("professor_id", professor_id)
            .eq("status", "realizada")
            .gte("data_hora", inicio_30 + "T00:00:00")
            .lte("data_hora", agora_iso)
            .execute()
        )
        ids_realizadas = [a["id"] for a in (r_real.data or [])]

        # Sessões agendadas cuja data já passou (não foram confirmadas nem canceladas)
        r_aged = (
            sb.table("aulas")
            .select("id")
            .eq("professor_id", professor_id)
            .eq("status", "agendada")
            .gte("data_hora", inicio_30 + "T00:00:00")
            .lt("data_hora", hoje.isoformat() + "T00:00:00")
            .execute()
        )
        ids_agendadas_passadas = [a["id"] for a in (r_aged.data or [])]

        todos_ids = ids_realizadas + ids_agendadas_passadas
        if todos_ids:
            r_reg = (
                sb.table("registros_sessao")
                .select("aula_id")
                .eq("professor_id", professor_id)
                .in_("aula_id", todos_ids)
                .execute()
            )
            ids_com_registro = {a["aula_id"] for a in (r_reg.data or [])}
            sessoes_sem_registro = len([i for i in todos_ids if i not in ids_com_registro])
    except Exception:
        pass

    if sessoes_sem_registro > 0:
        n = sessoes_sem_registro
        alertas.append({
            "tipo": "warning",
            "icone": "clipboard-x",
            "texto": f'{n} sessão{"ões" if n > 1 else ""} realizada{"s" if n > 1 else ""} sem registro de atendimento (últimos 30 dias)',
            "link": url_for("main.pendencias", tab="sessoes"),
        })

    if anamneses_pendentes > 0:
        n = anamneses_pendentes
        alertas.append({
            "tipo": "warning",
            "icone": "file-question",
            "texto": f'{n} aluno{"s" if n > 1 else ""} sem anamnese preenchida',
            "link": url_for("main.pendencias", tab="anamneses"),
        })

    if alunos_inativos > 0:
        alertas.append({
            "tipo": "info",
            "icone": "user-x",
            "texto": f'{alunos_inativos} aluno{"s" if alunos_inativos > 1 else ""} inativo{"s" if alunos_inativos > 1 else ""}',
            "link": url_for("alunos.lista"),
        })

    # -----------------------------------------------------------------------
    # GRÁFICO: RECEITA ÚLTIMOS 6 MESES — uma única query em vez de 6
    # -----------------------------------------------------------------------
    # Monta a lista ordenada dos 6 meses (ano, mes)
    _meses_grafico = []
    for i in range(5, -1, -1):
        _m, _a = mes_atual - i, ano_atual
        while _m <= 0:
            _m += 12
            _a -= 1
        _meses_grafico.append((_a, _m))

    _primeiro_mes = date(_meses_grafico[0][0], _meses_grafico[0][1], 1).isoformat()

    receita_grafico = []
    try:
        r = (
            sb.table("faturas")
            .select("mes_referencia, valor, valor_pago, status")
            .eq("professor_id", professor_id)
            .gte("mes_referencia", _primeiro_mes)
            .neq("status", "cancelada")
            .execute()
        )
        # Agrupa por "YYYY-MM"
        _por_mes: dict = {}
        for f in (r.data or []):
            k = (f.get("mes_referencia") or "")[:7]   # "2025-03"
            if k not in _por_mes:
                _por_mes[k] = [0.0, 0.0]
            _por_mes[k][0] += float(f.get("valor") or 0)
            # Para faturas pagas sem valor_pago preenchido, usa valor como fallback
            if f.get("status") in ("paga", "parcial"):
                recebido = float(f.get("valor_pago") or f.get("valor") or 0)
            else:
                recebido = float(f.get("valor_pago") or 0)
            _por_mes[k][1] += recebido
    except Exception:
        _por_mes = {}

    for _a, _m in _meses_grafico:
        k = f"{_a:04d}-{_m:02d}"
        vals = _por_mes.get(k, [0.0, 0.0])
        receita_grafico.append({
            "label":    MESES_PT_ABREV[_m],
            "faturado": round(vals[0], 2),
            "recebido": round(vals[1], 2),
        })

    # -----------------------------------------------------------------------
    # AULAS POR ALUNO (mês atual, realizadas)
    # -----------------------------------------------------------------------
    aulas_por_aluno = []
    try:
        r = (
            sb.table("aulas")
            .select("aluno_id, alunos(nome)")
            .eq("professor_id", professor_id)
            .eq("status", "realizada")
            .gte("data_hora", inicio_mes.isoformat())
            .lt("data_hora", fim_mes.isoformat())
            .execute()
        )
        contagem: dict = {}
        for aula in (r.data or []):
            nome = (aula.get("alunos") or {}).get("nome") or "Desconhecido"
            contagem[nome] = contagem.get(nome, 0) + 1
        aulas_por_aluno = sorted(
            [{"nome": n, "count": c} for n, c in contagem.items()],
            key=lambda x: x["count"],
            reverse=True,
        )
    except Exception:
        pass

    max_aulas = aulas_por_aluno[0]["count"] if aulas_por_aluno else 1

    return render_template(
        "main/dashboard.html",
        stats=stats,
        aulas_hoje=aulas_hoje,
        resumo_mes=resumo_mes,
        alertas=alertas,
        receita_grafico=receita_grafico,
        aulas_por_aluno=aulas_por_aluno,
        max_aulas=max_aulas,
        mes_nome=MESES_PT[mes_atual],
        fmt_valor=fmt_valor,
        hoje=hoje,
        amanha=amanha,
        fases_count=fases_count,
        anamneses_pendentes=anamneses_pendentes,
        sessoes_sem_registro=sessoes_sem_registro,
        lembretes_amanha=lembretes_amanha,
    )


@main_bp.route("/pendencias")
@login_required
def pendencias():
    sb = _sb()
    professor_id = session.get("user_id")
    tab = request.args.get("tab", "sessoes")

    hoje = date.today()

    # 1. Sessões sem registro: realizadas sem registro + agendadas já passadas
    sessoes_sem_registro_lista = []
    try:
        inicio_30 = (hoje - timedelta(days=30)).isoformat()

        r_real = (
            sb.table("aulas")
            .select("id, data_hora, status, alunos(id, nome)")
            .eq("professor_id", professor_id)
            .eq("status", "realizada")
            .gte("data_hora", inicio_30 + "T00:00:00")
            .lte("data_hora", hoje.isoformat() + "T23:59:59")
            .order("data_hora", desc=True)
            .execute()
        )
        r_aged = (
            sb.table("aulas")
            .select("id, data_hora, status, alunos(id, nome)")
            .eq("professor_id", professor_id)
            .eq("status", "agendada")
            .gte("data_hora", inicio_30 + "T00:00:00")
            .lt("data_hora", hoje.isoformat() + "T00:00:00")
            .order("data_hora", desc=True)
            .execute()
        )
        todas_aulas = (r_real.data or []) + (r_aged.data or [])
        todos_ids = [a["id"] for a in todas_aulas]

        if todos_ids:
            r_reg = (
                sb.table("registros_sessao")
                .select("aula_id")
                .eq("professor_id", professor_id)
                .in_("aula_id", todos_ids)
                .execute()
            )
            ids_com_registro = {a["aula_id"] for a in (r_reg.data or [])}
            sessoes_sem_registro_lista = [a for a in todas_aulas if a["id"] not in ids_com_registro]
            sessoes_sem_registro_lista.sort(key=lambda a: a["data_hora"], reverse=True)
    except Exception:
        pass

    # 2. Anamneses pendentes
    alunos_pendentes_anamnese = []
    try:
        r = (
            sb.table("alunos")
            .select("id, nome")
            .eq("professor_id", professor_id)
            .eq("ativo", True)
            .order("nome")
            .execute()
        )
        alunos_ativos = r.data or []

        if alunos_ativos:
            r_anam = (
                sb.table("anamneses")
                .select("aluno_id")
                .eq("professor_id", professor_id)
                .in_("aluno_id", [a["id"] for a in alunos_ativos])
                .execute()
            )
            ids_com_anamnese = {a["aluno_id"] for a in (r_anam.data or [])}
            alunos_pendentes_anamnese = [a for a in alunos_ativos if a["id"] not in ids_com_anamnese]
    except Exception as e:
        pass

    return render_template(
        "main/pendencias.html",
        tab=tab,
        sessoes_pendentes=sessoes_sem_registro_lista,
        anamneses_pendentes=alunos_pendentes_anamnese,
    )


@main_bp.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@main_bp.route("/debug/supabase")
def debug_supabase():
    sb = _sb()
    results = {}
    for table in ["alunos", "aulas", "faturas"]:
        try:
            sb.table(table).select("id").limit(1).execute()
            results[table] = "OK"
        except Exception as e:
            results[table] = str(e)
    return jsonify(results)
