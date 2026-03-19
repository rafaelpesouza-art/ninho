from datetime import date
from flask import render_template, request, redirect, url_for, flash, session
from . import financeiro_bp
from .model import (
    buscar_config, salvar_config,
    calcular_fechamento, gerar_faturas, gerar_fatura_grupo,
    listar_faturas, buscar_fatura, editar_fatura,
    registrar_pagamento, cancelar_fatura,
    atualizar_vencidas, listar_inadimplentes,
    resumo_financeiro, buscar_aulas_fatura,
    gerar_texto_whatsapp, fmt_valor, MESES_PT,
)
from ..extensions import get_supabase
from ..auth.decorators import login_required


def _sb():
    sb = get_supabase()
    token = session.get("access_token")
    if token:
        try:
            sb.postgrest.auth(token)
        except Exception:
            pass
    return sb


def _mes_ano_atual():
    hoje = date.today()
    return hoje.month, hoje.year


def _mes_anterior(mes, ano):
    if mes == 1:
        return 12, ano - 1
    return mes - 1, ano


def _proximo_mes(mes, ano):
    if mes == 12:
        return 1, ano + 1
    return mes + 1, ano


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------

@financeiro_bp.route("/")
@login_required
def index():
    sb = _sb()
    professor_id = session["user_id"]

    mes_atual, ano_atual = _mes_ano_atual()
    mes  = int(request.args.get("mes",  mes_atual))
    ano  = int(request.args.get("ano",  ano_atual))

    atualizar_vencidas(sb, professor_id)

    resumo = resumo_financeiro(sb, professor_id, mes, ano)
    inadimplentes = listar_inadimplentes(sb, professor_id)

    # Faturas do mês selecionado
    faturas_mes = listar_faturas(sb, professor_id, mes=mes, ano=ano)

    mes_ant  = _mes_anterior(mes, ano)
    mes_prox = _proximo_mes(mes, ano)

    config = buscar_config(sb, professor_id)

    return render_template(
        "financeiro/index.html",
        resumo=resumo,
        faturas_mes=faturas_mes,
        inadimplentes=inadimplentes,
        mes=mes, ano=ano,
        mes_ant=mes_ant, mes_prox=mes_prox,
        mes_nome=MESES_PT[mes],
        config=config,
        fmt_valor=fmt_valor,
    )


# ---------------------------------------------------------------------------
# FECHAMENTO MENSAL
# ---------------------------------------------------------------------------

@financeiro_bp.route("/fechamento")
@login_required
def fechamento():
    sb = _sb()
    professor_id = session["user_id"]

    mes_atual, ano_atual = _mes_ano_atual()
    # Default: mês anterior (fechamento do mês passado)
    mes_def, ano_def = _mes_anterior(mes_atual, ano_atual)

    mes = int(request.args.get("mes", mes_def))
    ano = int(request.args.get("ano", ano_def))

    grupos = calcular_fechamento(sb, professor_id, mes, ano)

    n_novos     = sum(1 for g in grupos if not g["fatura_existente"] and g["total"] > 0)
    total_geral = sum(g["total"] for g in grupos if not g["fatura_existente"] and g["total"] > 0)

    mes_ant  = _mes_anterior(mes, ano)
    mes_prox = _proximo_mes(mes, ano)

    return render_template(
        "financeiro/fechamento.html",
        grupos=grupos,
        mes=mes, ano=ano,
        mes_nome=MESES_PT[mes],
        mes_ant=mes_ant, mes_prox=mes_prox,
        n_novos=n_novos,
        total_geral=total_geral,
        fmt_valor=fmt_valor,
    )


@financeiro_bp.route("/fechamento/gerar", methods=["POST"])
@login_required
def gerar_fechamento():
    sb = _sb()
    professor_id = session["user_id"]

    mes = int(request.form.get("mes", 1))
    ano = int(request.form.get("ano", date.today().year))

    try:
        criadas, ignoradas = gerar_faturas(sb, professor_id, mes, ano)
        if criadas:
            flash(f"{criadas} fatura(s) gerada(s) para {MESES_PT[mes]}/{ano}!", "success")
        else:
            flash(f"Nenhuma fatura nova gerada para {MESES_PT[mes]}/{ano}. "
                  f"({ignoradas} grupo(s) já faturados ou sem valor)", "info")
    except Exception as e:
        flash(f"Erro ao gerar faturas: {e}", "danger")

    return redirect(url_for("financeiro.faturas", mes=mes, ano=ano))


@financeiro_bp.route("/fechamento/gerar-um", methods=["POST"])
@login_required
def gerar_fatura_individual():
    sb = _sb()
    professor_id = session["user_id"]

    mes       = int(request.form.get("mes", 1))
    ano       = int(request.form.get("ano", date.today().year))
    aluno_id  = request.form.get("aluno_id", "")
    familia_id = request.form.get("familia_id") or None

    try:
        fatura = gerar_fatura_grupo(sb, professor_id, mes, ano, aluno_id, familia_id)
        flash("Fatura gerada!", "success")
        return redirect(url_for("financeiro.fatura_detalhe", fatura_id=fatura["id"]))
    except Exception as e:
        flash(f"Erro: {e}", "danger")
        return redirect(url_for("financeiro.fechamento", mes=mes, ano=ano))


# ---------------------------------------------------------------------------
# LISTA DE FATURAS
# ---------------------------------------------------------------------------

@financeiro_bp.route("/faturas")
@login_required
def faturas():
    sb = _sb()
    professor_id = session["user_id"]

    status = request.args.get("status", "todas")
    mes    = request.args.get("mes", "")
    ano    = request.args.get("ano", "")

    mes_int = int(mes) if mes.isdigit() else None
    ano_int = int(ano) if ano.isdigit() else None

    atualizar_vencidas(sb, professor_id)
    lista = listar_faturas(sb, professor_id, status=status, mes=mes_int, ano=ano_int)

    # Ano atual + 2 anteriores para filtro
    ano_atual = date.today().year
    anos = [ano_atual, ano_atual - 1, ano_atual - 2]

    return render_template(
        "financeiro/faturas.html",
        faturas=lista,
        status_filtro=status,
        mes_filtro=mes,
        ano_filtro=ano,
        anos=anos,
        meses=MESES_PT,
        fmt_valor=fmt_valor,
    )


# ---------------------------------------------------------------------------
# DETALHE DA FATURA
# ---------------------------------------------------------------------------

@financeiro_bp.route("/faturas/<fatura_id>")
@login_required
def fatura_detalhe(fatura_id):
    sb = _sb()
    professor_id = session["user_id"]

    fatura = buscar_fatura(sb, professor_id, fatura_id)
    if not fatura:
        flash("Fatura não encontrada.", "danger")
        return redirect(url_for("financeiro.faturas"))

    aulas  = buscar_aulas_fatura(sb, professor_id, fatura)
    config = buscar_config(sb, professor_id)
    texto_wa = gerar_texto_whatsapp(sb, professor_id, fatura)

    # Telefone para link direto do WhatsApp
    aluno = fatura.get("alunos") or {}
    tel   = (aluno.get("telefone") or "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if tel and not tel.startswith("55"):
        tel = "55" + tel

    import urllib.parse
    texto_wa_encoded = urllib.parse.quote(texto_wa)

    return render_template(
        "financeiro/fatura.html",
        fatura=fatura,
        aulas=aulas,
        config=config,
        texto_wa=texto_wa,
        texto_wa_encoded=texto_wa_encoded,
        tel_wa=tel,
        fmt_valor=fmt_valor,
        MESES_PT=MESES_PT,
    )


# ---------------------------------------------------------------------------
# EDITAR FATURA
# ---------------------------------------------------------------------------

@financeiro_bp.route("/faturas/<fatura_id>/editar", methods=["POST"])
@login_required
def editar_fatura_route(fatura_id):
    sb = _sb()
    professor_id = session["user_id"]

    try:
        editar_fatura(sb, professor_id, fatura_id, request.form)
        flash("Fatura atualizada!", "success")
    except Exception as e:
        flash(f"Erro ao editar fatura: {e}", "danger")

    return redirect(url_for("financeiro.fatura_detalhe", fatura_id=fatura_id))


# ---------------------------------------------------------------------------
# REGISTRAR PAGAMENTO
# ---------------------------------------------------------------------------

@financeiro_bp.route("/faturas/<fatura_id>/pagar", methods=["POST"])
@login_required
def pagar_fatura(fatura_id):
    sb = _sb()
    professor_id = session["user_id"]

    try:
        registrar_pagamento(sb, professor_id, fatura_id, request.form)
        flash("Pagamento registrado!", "success")
    except Exception as e:
        flash(f"Erro ao registrar pagamento: {e}", "danger")

    return redirect(url_for("financeiro.fatura_detalhe", fatura_id=fatura_id))


# ---------------------------------------------------------------------------
# CANCELAR FATURA
# ---------------------------------------------------------------------------

@financeiro_bp.route("/faturas/<fatura_id>/cancelar", methods=["POST"])
@login_required
def cancelar(fatura_id):
    sb = _sb()
    professor_id = session["user_id"]

    try:
        cancelar_fatura(sb, professor_id, fatura_id)
        flash("Fatura cancelada.", "success")
    except Exception as e:
        flash(f"Erro: {e}", "danger")

    return redirect(url_for("financeiro.faturas"))


# ---------------------------------------------------------------------------
# CONFIGURAÇÕES
# ---------------------------------------------------------------------------

@financeiro_bp.route("/configuracoes", methods=["GET", "POST"])
@login_required
def configuracoes():
    sb = _sb()
    professor_id = session["user_id"]

    if request.method == "POST":
        try:
            salvar_config(sb, professor_id, request.form)
            flash("Configurações salvas!", "success")
        except Exception as e:
            flash(f"Erro ao salvar: {e}", "danger")
        return redirect(url_for("financeiro.configuracoes"))

    config = buscar_config(sb, professor_id)
    return render_template("financeiro/configuracoes.html", config=config)
