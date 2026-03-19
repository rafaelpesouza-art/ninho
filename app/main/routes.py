from datetime import date, timedelta

from flask import jsonify, render_template, redirect, url_for, session
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
    # STATS BÁSICAS (KPIs)
    # -----------------------------------------------------------------------
    stats = {
        "total_alunos": 0,
        "aulas_hoje": len(aulas_hoje),
        "faturas_abertas": 0,
        "inadimplentes": 0,
    }

    try:
        r = (
            sb.table("alunos")
            .select("id", count="exact")
            .eq("professor_id", professor_id)
            .eq("ativo", True)
            .execute()
        )
        stats["total_alunos"] = r.count or 0
    except Exception:
        pass

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
    aulas_canceladas = 0
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

    try:
        r = (
            sb.table("aulas")
            .select("id", count="exact")
            .eq("professor_id", professor_id)
            .in_("status", ["cancelada", "cancelada_aluno", "cancelada_professor"])
            .gte("data_hora", inicio_mes.isoformat())
            .lt("data_hora", fim_mes.isoformat())
            .execute()
        )
        aulas_canceladas = r.count or 0
    except Exception:
        pass

    receita_faturada = round(resumo_fin["receita"] + resumo_fin["pendente"], 2)
    resumo_mes = {
        "aulas_realizadas": aulas_realizadas,
        "aulas_canceladas": aulas_canceladas,
        "receita_faturada": receita_faturada,
        "receita_recebida": resumo_fin["receita"],
        "inadimplentes": resumo_fin["inadimplente"],
        "a_vencer": resumo_fin["a_vencer"],
    }

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

    # Aulas realizadas sem registro (últimos 30 dias)
    aulas_sem_registro = []
    try:
        inicio_30 = (hoje - timedelta(days=30)).isoformat()
        r_real = (
            sb.table("aulas")
            .select("id, data_hora, aluno_id, alunos(nome)")
            .eq("professor_id", professor_id)
            .eq("status", "realizada")
            .gte("data_hora", inicio_30 + "T00:00:00")
            .lte("data_hora", hoje.isoformat() + "T23:59:59")
            .execute()
        )
        aulas_real = r_real.data or []
        ids_realizadas = [a["id"] for a in aulas_real]
        if ids_realizadas:
            r_reg = (
                sb.table("registros_aula")
                .select("aula_id")
                .eq("professor_id", professor_id)
                .in_("aula_id", ids_realizadas)
                .execute()
            )
            ids_com_registro = {a["aula_id"] for a in (r_reg.data or [])}
            aulas_sem_registro = [a for a in aulas_real if a["id"] not in ids_com_registro]
    except Exception:
        pass

    for a in aulas_sem_registro:
        nome_aluno = (a.get("alunos") or {}).get("nome", "Aluno")
        data_str = a["data_hora"][8:10] + "/" + a["data_hora"][5:7]
        alertas.append({
            "tipo": "warning",
            "icone": "clipboard-x",
            "texto": f'Aula de {nome_aluno} ({data_str}) realizada sem registro',
            "link": url_for("registros.novo", aula_id=a["id"]),
        })

    # Alunos inativos
    try:
        r = (
            sb.table("alunos")
            .select("id", count="exact")
            .eq("professor_id", professor_id)
            .eq("ativo", False)
            .execute()
        )
        alunos_inativos = r.count or 0
    except Exception:
        alunos_inativos = 0

    if alunos_inativos > 0:
        alertas.append({
            "tipo": "info",
            "icone": "user-x",
            "texto": f'{alunos_inativos} aluno{"s" if alunos_inativos > 1 else ""} inativo{"s" if alunos_inativos > 1 else ""}',
            "link": url_for("alunos.lista"),
        })

    # -----------------------------------------------------------------------
    # GRÁFICO: RECEITA ÚLTIMOS 6 MESES
    # -----------------------------------------------------------------------
    receita_grafico = []
    for i in range(5, -1, -1):
        m = mes_atual - i
        a = ano_atual
        while m <= 0:
            m += 12
            a -= 1
        mes_ref = date(a, m, 1).isoformat()
        try:
            r = (
                sb.table("faturas")
                .select("valor, valor_pago, status")
                .eq("professor_id", professor_id)
                .eq("mes_referencia", mes_ref)
                .neq("status", "cancelada")
                .execute()
            )
            faturado = sum(float(f.get("valor") or 0) for f in (r.data or []))
            recebido = sum(float(f.get("valor_pago") or 0) for f in (r.data or []))
            receita_grafico.append({
                "label": MESES_PT_ABREV[m],
                "faturado": round(faturado, 2),
                "recebido": round(recebido, 2),
            })
        except Exception:
            receita_grafico.append({
                "label": MESES_PT_ABREV[m],
                "faturado": 0,
                "recebido": 0,
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
