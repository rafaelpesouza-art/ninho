from flask import render_template, request, redirect, url_for, flash, session, jsonify
from . import planejamento_bp
from .model import (
    listar_atividades, buscar_atividade, salvar_atividade,
    atualizar_atividade, excluir_atividade,
    listar_planos, buscar_plano, salvar_plano, atualizar_plano, excluir_plano,
    MATERIAS, SERIES, DIFICULDADES,
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
# INDEX
# ---------------------------------------------------------------------------

@planejamento_bp.route("/")
@login_required
def index():
    sb = _sb()
    professor_id = session["user_id"]
    atividades_recentes = listar_atividades(sb, professor_id)[:6]
    planos_recentes = listar_planos(sb, professor_id)[:6]
    return render_template(
        "planejamento/index.html",
        atividades_recentes=atividades_recentes,
        planos_recentes=planos_recentes,
        total_atividades=len(listar_atividades(sb, professor_id)),
        total_planos=len(listar_planos(sb, professor_id)),
        dificuldades=DIFICULDADES,
    )


# ---------------------------------------------------------------------------
# ATIVIDADES
# ---------------------------------------------------------------------------

@planejamento_bp.route("/atividades")
@login_required
def atividades():
    sb = _sb()
    professor_id = session["user_id"]
    materia = request.args.get("materia", "")
    serie   = request.args.get("serie", "")
    tag     = request.args.get("tag", "")
    q       = request.args.get("q", "")
    lista = listar_atividades(
        sb, professor_id,
        materia or None, serie or None, tag or None, q or None,
    )
    return render_template(
        "planejamento/atividades.html",
        lista=lista, materia=materia, serie=serie, tag=tag, q=q,
        materias=MATERIAS, series=SERIES, dificuldades=DIFICULDADES,
    )


@planejamento_bp.route("/atividades/api")
@login_required
def atividades_api():
    """JSON endpoint usado pelo seletor no formulário de registro."""
    sb = _sb()
    professor_id = session["user_id"]
    materia = request.args.get("materia", "")
    q       = request.args.get("q", "")
    lista = listar_atividades(sb, professor_id, materia or None, q=q or None)
    return jsonify([{
        "id":          a["id"],
        "titulo":      a["titulo"],
        "descricao":   a.get("descricao") or "",
        "materia":     a.get("materia") or "",
        "serie":       a.get("serie") or "",
        "dificuldade": a.get("dificuldade") or "",
        "tags":        a.get("tags") or [],
    } for a in lista])


@planejamento_bp.route("/atividades/nova", methods=["GET", "POST"])
@login_required
def atividade_nova():
    sb = _sb()
    professor_id = session["user_id"]
    if request.method == "POST":
        try:
            salvar_atividade(sb, professor_id, request.form)
            flash("Atividade salva no banco!", "success")
            return redirect(url_for("planejamento.atividades"))
        except Exception as e:
            flash(f"Erro: {e}", "danger")
    return render_template(
        "planejamento/atividade_form.html",
        atividade=None, materias=MATERIAS, series=SERIES, dificuldades=DIFICULDADES,
    )


@planejamento_bp.route("/atividades/<atividade_id>/editar", methods=["GET", "POST"])
@login_required
def atividade_editar(atividade_id):
    sb = _sb()
    professor_id = session["user_id"]
    atividade = buscar_atividade(sb, professor_id, atividade_id)
    if not atividade:
        flash("Atividade não encontrada.", "danger")
        return redirect(url_for("planejamento.atividades"))
    if request.method == "POST":
        try:
            atualizar_atividade(sb, professor_id, atividade_id, request.form)
            flash("Atividade atualizada!", "success")
            return redirect(url_for("planejamento.atividades"))
        except Exception as e:
            flash(f"Erro: {e}", "danger")
    return render_template(
        "planejamento/atividade_form.html",
        atividade=atividade, materias=MATERIAS, series=SERIES, dificuldades=DIFICULDADES,
    )


@planejamento_bp.route("/atividades/<atividade_id>/excluir", methods=["POST"])
@login_required
def atividade_excluir(atividade_id):
    sb = _sb()
    try:
        excluir_atividade(sb, session["user_id"], atividade_id)
        flash("Atividade excluída.", "success")
    except Exception as e:
        flash(f"Erro: {e}", "danger")
    return redirect(url_for("planejamento.atividades"))


# ---------------------------------------------------------------------------
# PLANOS DE AULA
# ---------------------------------------------------------------------------

@planejamento_bp.route("/planos")
@login_required
def planos():
    sb = _sb()
    professor_id = session["user_id"]
    aluno_id = request.args.get("aluno_id", "")
    alunos = listar_alunos(sb, professor_id)
    lista  = listar_planos(sb, professor_id, aluno_id or None)
    return render_template(
        "planejamento/planos.html",
        lista=lista, alunos=alunos, aluno_id_sel=aluno_id,
    )


@planejamento_bp.route("/planos/novo", methods=["GET", "POST"])
@login_required
def plano_novo():
    sb = _sb()
    professor_id = session["user_id"]
    alunos = listar_alunos(sb, professor_id)
    todas_atividades = listar_atividades(sb, professor_id)
    if request.method == "POST":
        try:
            dados = dict(request.form)
            dados["atividade_ids"] = request.form.getlist("atividade_ids")
            plano = salvar_plano(sb, professor_id, dados)
            flash("Plano criado!", "success")
            return redirect(url_for("planejamento.plano_ver", plano_id=plano["id"]))
        except Exception as e:
            flash(f"Erro: {e}", "danger")
    return render_template(
        "planejamento/plano_form.html",
        plano=None, alunos=alunos, todas_atividades=todas_atividades,
        materias=MATERIAS, series=SERIES,
    )


@planejamento_bp.route("/planos/<plano_id>")
@login_required
def plano_ver(plano_id):
    sb = _sb()
    plano = buscar_plano(sb, session["user_id"], plano_id)
    if not plano:
        flash("Plano não encontrado.", "danger")
        return redirect(url_for("planejamento.planos"))
    return render_template("planejamento/plano_ver.html", plano=plano, dificuldades=DIFICULDADES)


@planejamento_bp.route("/planos/<plano_id>/editar", methods=["GET", "POST"])
@login_required
def plano_editar(plano_id):
    sb = _sb()
    professor_id = session["user_id"]
    plano = buscar_plano(sb, professor_id, plano_id)
    if not plano:
        flash("Plano não encontrado.", "danger")
        return redirect(url_for("planejamento.planos"))
    alunos = listar_alunos(sb, professor_id)
    todas_atividades = listar_atividades(sb, professor_id)
    if request.method == "POST":
        try:
            dados = dict(request.form)
            dados["atividade_ids"] = request.form.getlist("atividade_ids")
            atualizar_plano(sb, professor_id, plano_id, dados)
            flash("Plano atualizado!", "success")
            return redirect(url_for("planejamento.plano_ver", plano_id=plano_id))
        except Exception as e:
            flash(f"Erro: {e}", "danger")
    return render_template(
        "planejamento/plano_form.html",
        plano=plano, alunos=alunos, todas_atividades=todas_atividades,
        materias=MATERIAS, series=SERIES,
    )


@planejamento_bp.route("/planos/<plano_id>/excluir", methods=["POST"])
@login_required
def plano_excluir(plano_id):
    sb = _sb()
    try:
        excluir_plano(sb, session["user_id"], plano_id)
        flash("Plano excluído.", "success")
    except Exception as e:
        flash(f"Erro: {e}", "danger")
    return redirect(url_for("planejamento.planos"))
