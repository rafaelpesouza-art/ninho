from flask import render_template, request, redirect, url_for, flash, session, Response
from . import registros_bp
from .model import (
    criar_registro, buscar_registro, atualizar_registro, registro_ja_existe,
    fazer_upload_foto, listar_fotos_registro, listar_fotos_aluno, deletar_foto,
    buscar_foto_bytes,
)
from ..extensions import get_supabase
from ..auth.decorators import login_required
from ..agenda.model import buscar_aula
from ..planejamento.model import MATERIAS as MATERIAS_PLANEJAMENTO


HUMORES = [
    ("animado",    "Animado 😄"),
    ("engajado",   "Engajado 🙂"),
    ("neutro",     "Neutro 😐"),
    ("cansado",    "Cansado 😴"),
    ("resistente", "Resistente 😤"),
]


def _sb():
    sb = get_supabase()
    token = session.get("access_token")
    if token:
        try:
            sb.postgrest.auth(token)
        except Exception:
            pass
        # Nota: Storage usa httpx direto em model.py (_st_headers) — não precisa do SDK aqui
    return sb


def _processar_fotos(sb, professor_id, registro_id, aluno_id):
    """Processa arquivos de `request.files['fotos']`. Retorna quantidade enviada."""
    files = request.files.getlist("fotos")
    enviadas = 0
    for file in files:
        if file and getattr(file, "filename", ""):
            try:
                fazer_upload_foto(sb, professor_id, registro_id, aluno_id, file)
                enviadas += 1
            except Exception as e:
                flash(f"Foto '{file.filename}' não enviada: {e}", "warning")
    return enviadas


# ---------------------------------------------------------------------------
# NOVO REGISTRO (vindo da agenda após marcar como realizada)
# ---------------------------------------------------------------------------

@registros_bp.route("/novo", methods=["GET"])
@login_required
def novo():
    aula_id = request.args.get("aula_id", "").strip()
    if not aula_id:
        flash("Aula não especificada.", "danger")
        return redirect(url_for("agenda.index"))

    sb = _sb()
    professor_id = session["user_id"]

    # Verifica se já existe registro para essa aula
    existente = registro_ja_existe(sb, professor_id, aula_id)
    if existente:
        if not request.args.get("auto"):
            flash("Esta aula já possui um registro. Editando o existente.", "info")
        return redirect(url_for("registros.editar", registro_id=existente["id"]))

    aula = buscar_aula(sb, professor_id, aula_id)
    if not aula:
        flash("Aula não encontrada.", "danger")
        return redirect(url_for("agenda.index"))

    if aula.get("status") != "realizada":
        flash("A aula precisa estar marcada como 'realizada' para registrar.", "warning")
        return redirect(url_for("agenda.index"))

    # Sugestões Inteligentes
    aluno_id = aula.get("aluno_id")
    sugestoes = []
    if aluno_id:
        try:
            res_aluno = sb.table("alunos").select("materia_foco, serie").eq("id", aluno_id).maybe_single().execute()
            if res_aluno.data:
                m_foco = res_aluno.data.get("materia_foco")
                s_foco = res_aluno.data.get("serie")
                
                query = sb.table("atividades").select("*").eq("professor_id", professor_id)
                if m_foco:
                    query = query.eq("materia", m_foco)
                if s_foco:
                    query = query.eq("serie", s_foco)
                res_sug = query.order("criado_em", desc=True).limit(4).execute()
                sugestoes = res_sug.data or []
        except Exception:
            pass

    return render_template(
        "registros/form.html",
        aula=aula,
        registro=None,
        humores=HUMORES,
        fotos=[],
        materias_planejamento=MATERIAS_PLANEJAMENTO,
        sugestoes=sugestoes,
    )


@registros_bp.route("/novo", methods=["POST"])
@login_required
def criar():
    sb = _sb()
    professor_id = session["user_id"]

    aula_id  = request.form.get("aula_id", "").strip()
    aluno_id = request.form.get("aluno_id", "").strip()

    if not aula_id or not aluno_id:
        flash("Dados inválidos.", "danger")
        return redirect(url_for("agenda.index"))

    try:
        registro = criar_registro(sb, professor_id, request.form)
        fotos_ok = _processar_fotos(sb, professor_id, registro["id"], aluno_id)
        if fotos_ok:
            flash(f"Registro salvo com {fotos_ok} foto(s)! ✓", "success")
            return redirect(url_for("registros.editar", registro_id=registro["id"]))
        flash("Registro de aula salvo com sucesso!", "success")
        return redirect(url_for("alunos.ficha", aluno_id=aluno_id))
    except Exception as e:
        flash(f"Erro ao salvar registro: {e}", "danger")
        aula = buscar_aula(sb, professor_id, aula_id)
        return render_template(
            "registros/form.html",
            aula=aula,
            registro=None,
            humores=HUMORES,
            form_data=request.form,
            fotos=[],
            materias_planejamento=MATERIAS_PLANEJAMENTO,
        )


# ---------------------------------------------------------------------------
# EDITAR REGISTRO
# ---------------------------------------------------------------------------

@registros_bp.route("/<registro_id>/editar", methods=["GET"])
@login_required
def editar(registro_id):
    sb = _sb()
    professor_id = session["user_id"]
    registro = buscar_registro(sb, professor_id, registro_id)
    if not registro:
        flash("Registro não encontrado.", "danger")
        return redirect(url_for("agenda.index"))

    aula_id = registro.get("aula_id")
    aula = buscar_aula(sb, professor_id, aula_id) if aula_id else None
    fotos = listar_fotos_registro(sb, professor_id, registro_id)

    return render_template(
        "registros/form.html",
        aula=aula,
        registro=registro,
        humores=HUMORES,
        fotos=fotos,
        materias_planejamento=MATERIAS_PLANEJAMENTO,
    )


@registros_bp.route("/<registro_id>/editar", methods=["POST"])
@login_required
def salvar_edicao(registro_id):
    sb = _sb()
    professor_id = session["user_id"]

    try:
        atualizar_registro(sb, professor_id, registro_id, request.form)
        aluno_id = request.form.get("aluno_id", "")
        fotos_ok = _processar_fotos(sb, professor_id, registro_id, aluno_id)
        if fotos_ok:
            flash(f"Registro atualizado com {fotos_ok} foto(s) nova(s)! ✓", "success")
            return redirect(url_for("registros.editar", registro_id=registro_id))
        flash("Registro atualizado!", "success")
        if aluno_id:
            return redirect(url_for("alunos.ficha", aluno_id=aluno_id))
        return redirect(url_for("agenda.index"))
    except Exception as e:
        flash(f"Erro ao salvar: {e}", "danger")
        registro = buscar_registro(sb, professor_id, registro_id)
        aula_id = registro.get("aula_id") if registro else None
        aula = buscar_aula(sb, professor_id, aula_id) if aula_id else None
        fotos = listar_fotos_registro(sb, professor_id, registro_id)
        return render_template(
            "registros/form.html",
            aula=aula,
            registro=registro,
            humores=HUMORES,
            form_data=request.form,
            fotos=fotos,
            materias_planejamento=MATERIAS_PLANEJAMENTO,
        )


# ---------------------------------------------------------------------------
# UPLOAD DE FOTOS
# ---------------------------------------------------------------------------

@registros_bp.route("/<registro_id>/fotos", methods=["POST"])
@login_required
def upload_foto(registro_id):
    sb = _sb()
    professor_id = session["user_id"]

    registro = buscar_registro(sb, professor_id, registro_id)
    if not registro:
        flash("Registro não encontrado.", "danger")
        return redirect(url_for("agenda.index"))

    aluno_id = request.form.get("aluno_id", "") or registro.get("aluno_id", "")
    legenda  = request.form.get("legenda", "").strip()
    files    = request.files.getlist("fotos")

    enviadas = 0
    for file in files:
        if file and file.filename:
            try:
                fazer_upload_foto(sb, professor_id, registro_id, aluno_id, file, legenda)
                enviadas += 1
            except Exception as e:
                flash(f"Erro ao enviar '{file.filename}': {e}", "warning")

    if enviadas:
        flash(f"{enviadas} foto(s) enviada(s) com sucesso!", "success")

    return redirect(url_for("registros.editar", registro_id=registro_id))


@registros_bp.route("/fotos/<foto_id>/deletar", methods=["POST"])
@login_required
def deletar_foto_view(foto_id):
    sb = _sb()
    professor_id = session["user_id"]
    registro_id = request.form.get("registro_id", "")
    aluno_id    = request.form.get("aluno_id", "")

    try:
        info = deletar_foto(sb, professor_id, foto_id)
        flash("Foto removida.", "success")
        registro_id = registro_id or info.get("registro_id") or ""
        aluno_id    = aluno_id    or info.get("aluno_id")    or ""
    except Exception as e:
        flash(f"Erro ao remover foto: {e}", "danger")

    if registro_id:
        return redirect(url_for("registros.editar", registro_id=registro_id))
    if aluno_id:
        return redirect(url_for("registros.galeria", aluno_id=aluno_id))
    return redirect(url_for("agenda.index"))


# ---------------------------------------------------------------------------
# SERVIR FOTO (proxy autenticado — evita problemas com signed URLs no browser)
# ---------------------------------------------------------------------------

@registros_bp.route("/fotos/<foto_id>/img")
@login_required
def servir_foto(foto_id):
    """Busca foto no Supabase Storage via JWT do servidor e serve ao browser."""
    sb = _sb()
    professor_id = session["user_id"]

    res = (
        sb.table("fotos_sessao")
        .select("storage_path")
        .eq("professor_id", professor_id)
        .eq("id", foto_id)
        .maybe_single()
        .execute()
    )
    if not res.data:
        return "", 404

    try:
        content, content_type = buscar_foto_bytes(res.data["storage_path"])
    except Exception:
        return "", 404

    return Response(
        content,
        status=200,
        content_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


# ---------------------------------------------------------------------------
# GALERIA DE FOTOS POR ALUNO
# ---------------------------------------------------------------------------

@registros_bp.route("/galeria/<aluno_id>")
@login_required
def galeria(aluno_id):
    sb = _sb()
    professor_id = session["user_id"]

    try:
        res = (
            sb.table("alunos")
            .select("id, nome, ativo")
            .eq("professor_id", professor_id)
            .eq("id", aluno_id)
            .limit(1)
            .execute()
        )
        aluno = res.data[0] if res.data else None
    except Exception as e:
        flash(f"Erro ao abrir galeria: {e}", "danger")
        return redirect(url_for("alunos.lista"))

    if not aluno:
        flash("Aluno não encontrado.", "danger")
        return redirect(url_for("alunos.lista"))

    fotos = listar_fotos_aluno(sb, professor_id, aluno_id)
    return render_template("registros/galeria.html", aluno=aluno, fotos=fotos)
