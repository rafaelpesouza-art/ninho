from datetime import date, timedelta
from flask import render_template, request, redirect, url_for, flash, session, jsonify
from . import agenda_bp
from .model import (
    listar_aulas_mes, listar_aulas_dia, buscar_aula,
    criar_aula_avulsa, cancelar_aula, reagendar_aula, marcar_realizada,
    listar_feriados, criar_feriado, deletar_feriado, cancelar_aulas_em_feriado,
    gerar_aulas_mes_todos_alunos, montar_calendario, _navegar_mes, MESES, STATUS_LABELS,
)
from .lembretes import (
    buscar_config_lembrete, salvar_config_lembrete,
    listar_sessoes_amanha, marcar_lembrete_enviado, enriquecer_sessoes,
    MSG_LEMBRETE_PADRAO, MSG_CONFIRMACAO_PADRAO, MSG_CANCELAMENTO_PADRAO,
)
from ..extensions import get_supabase
from ..auth.decorators import login_required
from ..alunos.model import listar_alunos


def _sb():
    sb = get_supabase()
    token = session.get("access_token")
    if token:
        try:
            sb.postgrest.auth(token)
        except Exception:
            pass
    return sb


# ---------------------------------------------------------------------------
# CALENDÁRIO MENSAL
# ---------------------------------------------------------------------------

@agenda_bp.route("/")
@login_required
def index():
    sb = _sb()
    professor_id = session["user_id"]
    hoje = date.today()

    try:
        ano = int(request.args.get("ano", hoje.year))
        mes = int(request.args.get("mes", hoje.month))
        ano = max(2020, min(ano, 2100))
        mes = max(1, min(mes, 12))
    except (ValueError, TypeError):
        ano, mes = hoje.year, hoje.month

    # Dia selecionado para o painel lateral
    data_sel_str = request.args.get("data", "")
    if not data_sel_str and "ano" not in request.args and "mes" not in request.args:
        data_sel_str = hoje.isoformat()
        
    data_selecionada = None
    aulas_dia = []
    
    if data_sel_str:
        try:
            data_selecionada = date.fromisoformat(data_sel_str)
            aulas_dia = listar_aulas_dia(sb, professor_id, data_selecionada)
        except ValueError:
            pass

    # Dados do mês
    aulas_mes = listar_aulas_mes(sb, professor_id, ano, mes)
    cal = montar_calendario(aulas_mes, ano, mes)
    anterior, proximo = _navegar_mes(ano, mes)

    # Feriados do ano (inclui recorrentes com mesmo mês-dia)
    feriados_raw = listar_feriados(sb, professor_id, ano)
    feriados_set = set()
    for f in feriados_raw:
        feriados_set.add(f["data"])
        if f.get("recorrente"):
            feriados_set.add(f"{ano}-{f['data'][5:]}")

    alunos = listar_alunos(sb, professor_id)

    from datetime import timedelta
    return render_template(
        "agenda/index.html",
        ano=ano, mes=mes,
        semanas=cal["semanas"],
        por_dia=cal["por_dia"],
        data_selecionada=data_selecionada,
        aulas_dia=aulas_dia,
        anterior=anterior,
        proximo=proximo,
        hoje=hoje,
        feriados_set=feriados_set,
        alunos=alunos,
        nomes_meses=MESES,
        status_labels=STATUS_LABELS,
        timedelta=timedelta,
    )


# ---------------------------------------------------------------------------
# NOVA AULA AVULSA
# ---------------------------------------------------------------------------

@agenda_bp.route("/aula/nova", methods=["POST"])
@login_required
def nova_aula():
    sb = _sb()
    professor_id = session["user_id"]
    try:
        aula = criar_aula_avulsa(sb, professor_id, request.form)
        flash(f"Aula criada para {aula['data_hora'][:10]} às {aula['data_hora'][11:16]}.", "success")
    except Exception as e:
        flash(f"Erro ao criar aula: {e}", "danger")

    # Volta para o mês da aula criada (ou mês atual)
    data_hora = request.form.get("data_hora", "")
    if data_hora and "T" in data_hora:
        partes = data_hora.split("T")[0].split("-")
        return redirect(url_for("agenda.index", ano=partes[0], mes=int(partes[1])))
    return redirect(url_for("agenda.index"))


# ---------------------------------------------------------------------------
# CANCELAR AULA
# ---------------------------------------------------------------------------

@agenda_bp.route("/aula/<aula_id>/cancelar", methods=["POST"])
@login_required
def cancelar(aula_id):
    sb = _sb()
    professor_id = session["user_id"]
    motivo = request.form.get("motivo", "").strip()
    tipo = request.form.get("tipo", "cancelada_professor")

    if tipo not in ("cancelada_professor", "cancelada_aluno", "cancelada"):
        tipo = "cancelada_professor"

    try:
        cancelar_aula(sb, professor_id, aula_id, motivo=motivo, tipo=tipo)
        flash("Aula cancelada.", "warning")
    except Exception as e:
        flash(f"Erro ao cancelar: {e}", "danger")

    return redirect(request.referrer or url_for("agenda.index"))


# ---------------------------------------------------------------------------
# REAGENDAR AULA
# ---------------------------------------------------------------------------

@agenda_bp.route("/aula/<aula_id>/reagendar", methods=["POST"])
@login_required
def reagendar(aula_id):
    sb = _sb()
    professor_id = session["user_id"]
    nova_data_hora = request.form.get("nova_data_hora", "").strip()
    motivo = request.form.get("motivo", "").strip()

    if not nova_data_hora:
        flash("Informe a nova data e horário.", "danger")
        return redirect(request.referrer or url_for("agenda.index"))

    try:
        nova = reagendar_aula(sb, professor_id, aula_id, nova_data_hora, motivo=motivo)
        flash(f"Aula remarcada para {nova['data_hora'][:10]} às {nova['data_hora'][11:16]}.", "success")
    except Exception as e:
        flash(f"Erro ao reagendar: {e}", "danger")

    return redirect(request.referrer or url_for("agenda.index"))


# ---------------------------------------------------------------------------
# MARCAR COMO REALIZADA
# ---------------------------------------------------------------------------

@agenda_bp.route("/aula/<aula_id>/realizada", methods=["POST"])
@login_required
def realizada(aula_id):
    sb = _sb()
    professor_id = session["user_id"]
    try:
        marcar_realizada(sb, professor_id, aula_id)
        flash("Aula marcada como realizada! Documente a sessão abaixo.", "success")
        return redirect(url_for("registros.novo", aula_id=aula_id))
    except Exception as e:
        flash(f"Erro: {e}", "danger")
        return redirect(request.referrer or url_for("agenda.index"))


# ---------------------------------------------------------------------------
# GERAR MÊS (aulas recorrentes de todos os alunos)
# ---------------------------------------------------------------------------

@agenda_bp.route("/gerar-mes", methods=["POST"])
@login_required
def gerar_mes():
    sb = _sb()
    professor_id = session["user_id"]
    hoje = date.today()
    try:
        ano = int(request.form.get("ano", hoje.year))
        mes = int(request.form.get("mes", hoje.month))
    except (ValueError, TypeError):
        ano, mes = hoje.year, hoje.month

    try:
        resultado = gerar_aulas_mes_todos_alunos(sb, professor_id, ano, mes)
        geradas = resultado["geradas"]
        erros = resultado["erros"]
        if geradas:
            flash(f"{geradas} aula(s) gerada(s) para {MESES[mes]}/{ano}.", "success")
        else:
            flash(f"Nenhuma aula nova gerada para {MESES[mes]}/{ano} (já existem ou nenhum aluno com dia fixo).", "info")
        for e in erros:
            flash(f"Erro ao gerar para {e['aluno']}: {e['erro']}", "warning")
    except Exception as e:
        flash(f"Erro ao gerar aulas: {e}", "danger")

    return redirect(url_for("agenda.index", ano=ano, mes=mes))


# ---------------------------------------------------------------------------
# FERIADOS
# ---------------------------------------------------------------------------

@agenda_bp.route("/feriados", methods=["GET", "POST"])
@login_required
def feriados():
    sb = _sb()
    professor_id = session["user_id"]
    hoje = date.today()

    if request.method == "POST":
        try:
            feriado = criar_feriado(sb, professor_id, request.form)
            # Se solicitado, cancela aulas do dia
            if request.form.get("cancelar_aulas") == "on":
                cancelados = cancelar_aulas_em_feriado(sb, professor_id, feriado["data"])
                if cancelados:
                    flash(f"{len(cancelados)} aula(s) cancelada(s) pelo feriado.", "warning")
            flash(f"Feriado '{feriado['nome']}' adicionado.", "success")
        except Exception as e:
            flash(f"Erro: {e}", "danger")
        return redirect(url_for("agenda.feriados"))

    lista = listar_feriados(sb, professor_id)
    return render_template("agenda/feriados.html", feriados=lista, hoje=hoje, nomes_meses=MESES)


@agenda_bp.route("/feriados/<feriado_id>/deletar", methods=["POST"])
@login_required
def deletar_feriado_view(feriado_id):
    sb = _sb()
    professor_id = session["user_id"]
    try:
        deletar_feriado(sb, professor_id, feriado_id)
        flash("Feriado removido.", "success")
    except Exception as e:
        flash(f"Erro: {e}", "danger")
    return redirect(url_for("agenda.feriados"))


@agenda_bp.route("/feriados/<feriado_id>/cancelar-aulas", methods=["POST"])
@login_required
def cancelar_aulas_feriado_view(feriado_id):
    sb = _sb()
    professor_id = session["user_id"]
    try:
        from .model import listar_feriados as _lf
        todos = _lf(sb, professor_id)
        feriado = next((f for f in todos if f["id"] == feriado_id), None)
        if not feriado:
            flash("Feriado não encontrado.", "danger")
            return redirect(url_for("agenda.feriados"))
        cancelados = cancelar_aulas_em_feriado(sb, professor_id, feriado["data"])
        flash(f"{len(cancelados)} aula(s) cancelada(s) pelo feriado '{feriado['nome']}'.", "warning")
    except Exception as e:
        flash(f"Erro: {e}", "danger")
    return redirect(url_for("agenda.feriados"))


# ---------------------------------------------------------------------------
# LEMBRETES DE SESSÃO
# ---------------------------------------------------------------------------

@agenda_bp.route("/lembretes")
@login_required
def lembretes():
    sb = _sb()
    professor_id = session["user_id"]
    config  = buscar_config_lembrete(sb, professor_id)
    sessoes_raw = listar_sessoes_amanha(sb, professor_id)
    sessoes = enriquecer_sessoes(sessoes_raw, config, tipo="lembrete")
    amanha  = date.today() + timedelta(days=1)
    return render_template(
        "agenda/lembretes.html",
        sessoes=sessoes,
        config=config,
        amanha=amanha,
        msg_lembrete_padrao=MSG_LEMBRETE_PADRAO,
        msg_confirmacao_padrao=MSG_CONFIRMACAO_PADRAO,
        msg_cancelamento_padrao=MSG_CANCELAMENTO_PADRAO,
    )


@agenda_bp.route("/lembretes/config", methods=["POST"])
@login_required
def salvar_config_lembretes():
    sb = _sb()
    professor_id = session["user_id"]
    try:
        salvar_config_lembrete(sb, professor_id, request.form)
        flash("Configurações de lembrete salvas!", "success")
    except Exception as e:
        flash(f"Erro ao salvar: {e}", "danger")
    return redirect(url_for("agenda.lembretes"))


@agenda_bp.route("/aula/<aula_id>/lembrete/enviado", methods=["POST"])
@login_required
def marcar_lembrete(aula_id):
    sb = _sb()
    professor_id = session["user_id"]
    try:
        marcar_lembrete_enviado(sb, professor_id, aula_id)
    except Exception:
        pass
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True})
    return redirect(request.referrer or url_for("agenda.lembretes"))
