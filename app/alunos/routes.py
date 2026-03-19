from flask import render_template, request, redirect, url_for, flash, session
from . import alunos_bp
from .model import (
    listar_alunos, buscar_aluno, criar_aluno,
    atualizar_aluno, desativar_aluno, reativar_aluno, ficha_aluno,
)
from ..extensions import get_supabase
from ..auth.decorators import login_required
from ..planejamento.model import MATERIAS, SERIES

DIAS_SEMANA = [
    (0, "Segunda-feira"),
    (1, "Terça-feira"),
    (2, "Quarta-feira"),
    (3, "Quinta-feira"),
    (4, "Sexta-feira"),
    (5, "Sábado"),
    (6, "Domingo"),
]


def _sb():
    """Retorna o cliente Supabase autenticado com o JWT do usuário logado."""
    sb = get_supabase()
    token = session.get("access_token")
    if token:
        try:
            sb.postgrest.auth(token)
        except Exception:
            pass
    return sb


# ---------------------------------------------------------------------------
# LISTAGEM
# ---------------------------------------------------------------------------

@alunos_bp.route("/")
@login_required
def lista():
    mostrar_inativos = request.args.get("inativos") == "1"
    sb = _sb()
    professor_id = session["user_id"]

    if mostrar_inativos:
        alunos = listar_alunos(sb, professor_id, apenas_ativos=False)
    else:
        alunos = listar_alunos(sb, professor_id, apenas_ativos=True)

    return render_template(
        "alunos/lista.html",
        alunos=alunos,
        mostrar_inativos=mostrar_inativos,
    )


# ---------------------------------------------------------------------------
# CRIAR
# ---------------------------------------------------------------------------

@alunos_bp.route("/novo", methods=["GET"])
@login_required
def novo():
    sb = _sb()
    alunos_lista = listar_alunos(sb, session["user_id"])
    return render_template("alunos/form.html", aluno=None, dias_semana=DIAS_SEMANA, alunos_cadastrados=alunos_lista,
                           materias=MATERIAS, series=SERIES)


@alunos_bp.route("/novo", methods=["POST"])
@login_required
def criar():
    nome = request.form.get("nome", "").strip()
    if not nome:
        flash("O nome do aluno é obrigatório.", "danger")
        return render_template("alunos/form.html", aluno=None, dias_semana=DIAS_SEMANA,
                               form_data=request.form, materias=MATERIAS, series=SERIES)

    sb = _sb()
    professor_id = session["user_id"]
    try:
        aluno = criar_aluno(sb, professor_id, request.form)
        flash(f"Aluno '{aluno['nome']}' criado com sucesso!", "success")
        return redirect(url_for("alunos.ficha", aluno_id=aluno["id"]))
    except Exception as e:
        flash(f"Erro ao criar aluno: {e}", "danger")
        return render_template("alunos/form.html", aluno=None, dias_semana=DIAS_SEMANA,
                               form_data=request.form, materias=MATERIAS, series=SERIES)


# ---------------------------------------------------------------------------
# EDITAR
# ---------------------------------------------------------------------------

@alunos_bp.route("/<aluno_id>/editar", methods=["GET"])
@login_required
def editar(aluno_id):
    sb = _sb()
    professor_id = session["user_id"]
    aluno = buscar_aluno(sb, professor_id, aluno_id)
    if not aluno:
        flash("Aluno não encontrado.", "warning")
        return redirect(url_for("alunos.lista"))
        
    todos_alunos = listar_alunos(sb, professor_id)
    alunos_cadastrados = [a for a in todos_alunos if str(a["id"]) != str(aluno_id)]
        
    return render_template("alunos/form.html", aluno=aluno, dias_semana=DIAS_SEMANA, alunos_cadastrados=alunos_cadastrados,
                           materias=MATERIAS, series=SERIES)


@alunos_bp.route("/<aluno_id>/editar", methods=["POST"])
@login_required
def salvar_edicao(aluno_id):
    nome = request.form.get("nome", "").strip()
    if not nome:
        flash("O nome do aluno é obrigatório.", "danger")
        sb = _sb()
        aluno = buscar_aluno(sb, session["user_id"], aluno_id)
        return render_template("alunos/form.html", aluno=aluno, dias_semana=DIAS_SEMANA,
                               form_data=request.form, materias=MATERIAS, series=SERIES)

    sb = _sb()
    professor_id = session["user_id"]
    try:
        atualizar_aluno(sb, professor_id, aluno_id, request.form)
        flash("Dados atualizados com sucesso!", "success")
        return redirect(url_for("alunos.ficha", aluno_id=aluno_id))
    except Exception as e:
        flash(f"Erro ao salvar: {e}", "danger")
        aluno = buscar_aluno(sb, professor_id, aluno_id)
        return render_template("alunos/form.html", aluno=aluno, dias_semana=DIAS_SEMANA,
                               form_data=request.form, materias=MATERIAS, series=SERIES)


# ---------------------------------------------------------------------------
# FICHA
# ---------------------------------------------------------------------------

@alunos_bp.route("/<aluno_id>")
@login_required
def ficha(aluno_id):
    sb = _sb()
    professor_id = session["user_id"]
    dados = ficha_aluno(sb, professor_id, aluno_id)
    if not dados:
        flash("Aluno não encontrado.", "warning")
        return redirect(url_for("alunos.lista"))
    return render_template("alunos/ficha.html", **dados, dias_semana={k: v for k, v in DIAS_SEMANA})


# ---------------------------------------------------------------------------
# DESATIVAR
# ---------------------------------------------------------------------------

@alunos_bp.route("/<aluno_id>/desativar", methods=["POST"])
@login_required
def desativar(aluno_id):
    sb = _sb()
    professor_id = session["user_id"]
    try:
        aluno = desativar_aluno(sb, professor_id, aluno_id)
        nome = aluno["nome"] if aluno else "Aluno"
        flash(f"'{nome}' foi desativado.", "warning")
    except Exception as e:
        flash(f"Erro ao desativar: {e}", "danger")
    return redirect(url_for("alunos.lista"))


@alunos_bp.route("/<aluno_id>/reativar", methods=["POST"])
@login_required
def reativar(aluno_id):
    sb = _sb()
    professor_id = session["user_id"]
    try:
        aluno = reativar_aluno(sb, professor_id, aluno_id)
        nome = aluno["nome"] if aluno else "Aluno"
        flash(f"'{nome}' foi reativado.", "success")
    except Exception as e:
        flash(f"Erro ao reativar: {e}", "danger")
    return redirect(url_for("alunos.lista"))
