from flask import render_template, request, redirect, url_for, flash, session
from . import configuracoes_bp
from ..clinico.model import listar_templates, salvar_template, excluir_template
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


@configuracoes_bp.route("/templates", methods=["GET"])
@login_required
def templates():
    sb = _sb()
    pid = session["user_id"]
    todos = listar_templates(sb, pid)
    anamnese_tpls  = [t for t in todos if t["tipo"] == "anamnese"]
    avaliacao_tpls = [t for t in todos if t["tipo"] == "avaliacao"]
    return render_template(
        "configuracoes/templates.html",
        anamnese_tpls=anamnese_tpls,
        avaliacao_tpls=avaliacao_tpls,
    )


@configuracoes_bp.route("/templates", methods=["POST"])
@login_required
def criar_template():
    sb = _sb()
    pid = session["user_id"]
    try:
        salvar_template(sb, pid, request.form)
        flash("Template criado!", "success")
    except Exception as e:
        flash(f"Erro ao criar template: {e}", "danger")
    return redirect(url_for("configuracoes.templates"))


@configuracoes_bp.route("/templates/<template_id>/editar", methods=["POST"])
@login_required
def editar_template(template_id):
    sb = _sb()
    pid = session["user_id"]
    try:
        salvar_template(sb, pid, request.form, template_id=template_id)
        flash("Template atualizado!", "success")
    except Exception as e:
        flash(f"Erro ao editar template: {e}", "danger")
    return redirect(url_for("configuracoes.templates"))


@configuracoes_bp.route("/templates/<template_id>/excluir", methods=["POST"])
@login_required
def excluir_template_route(template_id):
    sb = _sb()
    try:
        excluir_template(sb, session["user_id"], template_id)
        flash("Template removido.", "success")
    except Exception as e:
        flash(f"Erro: {e}", "danger")
    return redirect(url_for("configuracoes.templates"))
