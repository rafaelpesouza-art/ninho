from flask import render_template, request, redirect, url_for, flash, session, jsonify
from . import clinico_bp
from .model import (
    buscar_anamnese, salvar_anamnese,
    buscar_avaliacao_atual, listar_avaliacoes, salvar_avaliacao, concluir_avaliacao,
    buscar_devolutiva, salvar_devolutiva, marcar_enviada,
    buscar_plano_ativo, salvar_plano,
    listar_documentos, salvar_documento, excluir_documento,
    fazer_upload_documento, gerar_url_signed, BUCKET_DOCS,
    atualizar_fase_aluno, buscar_template_padrao,
)
from ..extensions import get_supabase
from ..auth.decorators import login_required
from ..alunos.model import buscar_aluno


def _sb():
    sb = get_supabase()
    token = session.get("access_token")
    if token:
        try:
            sb.postgrest.auth(token)
        except Exception:
            pass
    return sb


def _get_aluno_or_404(sb, professor_id, aluno_id):
    aluno = buscar_aluno(sb, professor_id, aluno_id)
    if not aluno:
        flash("Aluno não encontrado.", "warning")
        return None
    return aluno


# ─── ANAMNESE ────────────────────────────────────────────────────────────────

@clinico_bp.route("/<aluno_id>/anamnese", methods=["GET"])
@login_required
def anamnese(aluno_id):
    sb = _sb()
    pid = session["user_id"]
    aluno = _get_aluno_or_404(sb, pid, aluno_id)
    if not aluno:
        return redirect(url_for("alunos.lista"))

    anamnese_atual = buscar_anamnese(sb, pid, aluno_id)
    template_padrao = buscar_template_padrao(sb, pid, "anamnese")

    # Pré-carrega template se solicitado e não há anamnese ainda
    pre_secoes = None
    if not anamnese_atual and request.args.get("usar_template") and template_padrao:
        pre_secoes = template_padrao.get("secoes") or []

    return render_template(
        "clinico/anamnese.html",
        aluno=aluno,
        anamnese=anamnese_atual,
        template_padrao=template_padrao,
        pre_secoes=pre_secoes,
    )


@clinico_bp.route("/<aluno_id>/anamnese", methods=["POST"])
@login_required
def salvar_anamnese_route(aluno_id):
    sb = _sb()
    pid = session["user_id"]
    anamnese_id = request.form.get("anamnese_id") or None
    try:
        salvar_anamnese(sb, pid, aluno_id, request.form, anamnese_id)
        flash("Anamnese salva com sucesso!", "success")
        # Avança fase automaticamente: anamnese → avaliacao
        try:
            aluno = buscar_aluno(sb, pid, aluno_id)
            if (aluno or {}).get("fase_atual") == "anamnese":
                atualizar_fase_aluno(sb, pid, aluno_id, "avaliacao")
        except Exception:
            pass
    except Exception as e:
        flash(f"Erro ao salvar anamnese: {e}", "danger")
    return redirect(url_for("clinico.anamnese", aluno_id=aluno_id))


# ─── AVALIAÇÃO ───────────────────────────────────────────────────────────────

@clinico_bp.route("/<aluno_id>/avaliacao", methods=["GET"])
@login_required
def avaliacao(aluno_id):
    sb = _sb()
    pid = session["user_id"]
    aluno = _get_aluno_or_404(sb, pid, aluno_id)
    if not aluno:
        return redirect(url_for("alunos.lista"))

    avaliacao_atual = buscar_avaliacao_atual(sb, pid, aluno_id)
    historico       = listar_avaliacoes(sb, pid, aluno_id)
    template_padrao = buscar_template_padrao(sb, pid, "avaliacao")

    pre_areas = None
    if not avaliacao_atual and request.args.get("usar_template") and template_padrao:
        pre_areas = template_padrao.get("secoes") or []

    return render_template(
        "clinico/avaliacao.html",
        aluno=aluno,
        avaliacao=avaliacao_atual,
        historico=historico,
        template_padrao=template_padrao,
        pre_areas=pre_areas,
    )


@clinico_bp.route("/<aluno_id>/avaliacao", methods=["POST"])
@login_required
def salvar_avaliacao_route(aluno_id):
    sb = _sb()
    pid = session["user_id"]
    avaliacao_id = request.form.get("avaliacao_id") or None
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    try:
        avaliacao = salvar_avaliacao(sb, pid, aluno_id, request.form, avaliacao_id)
        if is_ajax:
            return jsonify({"ok": True, "avaliacao_id": avaliacao["id"]})
        flash("Avaliação salva!", "success")
    except Exception as e:
        if is_ajax:
            return jsonify({"ok": False, "erro": str(e)}), 400
        flash(f"Erro ao salvar avaliação: {e}", "danger")
    return redirect(url_for("clinico.avaliacao", aluno_id=aluno_id))


@clinico_bp.route("/<aluno_id>/avaliacao/<avaliacao_id>/concluir", methods=["POST"])
@login_required
def concluir_avaliacao_route(aluno_id, avaliacao_id):
    sb = _sb()
    pid = session["user_id"]
    try:
        concluir_avaliacao(sb, pid, avaliacao_id)
        flash("Avaliação marcada como concluída!", "success")
        # Avança fase automaticamente: avaliacao → intervencao
        try:
            aluno = buscar_aluno(sb, pid, aluno_id)
            if (aluno or {}).get("fase_atual") not in ("intervencao", "alta"):
                atualizar_fase_aluno(sb, pid, aluno_id, "intervencao")
        except Exception:
            pass
    except Exception as e:
        flash(f"Erro: {e}", "danger")
    return redirect(url_for("clinico.avaliacao", aluno_id=aluno_id))


# ─── DEVOLUTIVA ───────────────────────────────────────────────────────────────

@clinico_bp.route("/<aluno_id>/devolutiva", methods=["GET"])
@login_required
def devolutiva(aluno_id):
    sb = _sb()
    pid = session["user_id"]
    aluno = _get_aluno_or_404(sb, pid, aluno_id)
    if not aluno:
        return redirect(url_for("alunos.lista"))

    devolutiva_atual = buscar_devolutiva(sb, pid, aluno_id)
    avaliacoes       = listar_avaliacoes(sb, pid, aluno_id)
    anamnese_atual   = buscar_anamnese(sb, pid, aluno_id)

    return render_template(
        "clinico/devolutiva.html",
        aluno=aluno,
        devolutiva=devolutiva_atual,
        avaliacoes=avaliacoes,
        anamnese=anamnese_atual,
    )


@clinico_bp.route("/<aluno_id>/devolutiva", methods=["POST"])
@login_required
def salvar_devolutiva_route(aluno_id):
    sb = _sb()
    pid = session["user_id"]
    devolutiva_id = request.form.get("devolutiva_id") or None
    try:
        salvar_devolutiva(sb, pid, aluno_id, request.form, devolutiva_id)
        flash("Devolutiva salva!", "success")
    except Exception as e:
        flash(f"Erro ao salvar devolutiva: {e}", "danger")
    return redirect(url_for("clinico.devolutiva", aluno_id=aluno_id))


@clinico_bp.route("/<aluno_id>/devolutiva/<devolutiva_id>/enviada", methods=["POST"])
@login_required
def marcar_enviada_route(aluno_id, devolutiva_id):
    sb = _sb()
    campo = request.form.get("campo", "")
    try:
        marcar_enviada(sb, session["user_id"], devolutiva_id, campo)
        label = "família" if campo == "enviado_familia" else "escola"
        flash(f"Marcado como enviado para a {label}!", "success")
    except Exception as e:
        flash(f"Erro: {e}", "danger")
    return redirect(url_for("clinico.devolutiva", aluno_id=aluno_id))


# ─── PLANO DE INTERVENÇÃO ────────────────────────────────────────────────────

@clinico_bp.route("/<aluno_id>/plano", methods=["GET"])
@login_required
def plano(aluno_id):
    sb = _sb()
    pid = session["user_id"]
    aluno = _get_aluno_or_404(sb, pid, aluno_id)
    if not aluno:
        return redirect(url_for("alunos.lista"))

    plano_atual = buscar_plano_ativo(sb, pid, aluno_id)
    return render_template("clinico/plano.html", aluno=aluno, plano=plano_atual)


@clinico_bp.route("/<aluno_id>/plano", methods=["POST"])
@login_required
def salvar_plano_route(aluno_id):
    sb = _sb()
    pid = session["user_id"]
    plano_id = request.form.get("plano_id") or None
    novo = plano_id is None
    try:
        salvar_plano(sb, pid, aluno_id, request.form, plano_id)
        flash("Plano salvo!", "success")
        # Ao criar um novo plano ativo, avança fase automaticamente para Intervenção
        if novo and request.form.get("status", "ativo") == "ativo":
            try:
                aluno = buscar_aluno(sb, pid, aluno_id)
                fase_atual = (aluno or {}).get("fase_atual", "")
                if fase_atual not in ("intervencao", "alta"):
                    atualizar_fase_aluno(sb, pid, aluno_id, "intervencao")
                    flash("Fase atualizada para Intervenção.", "info")
            except Exception:
                pass
    except Exception as e:
        flash(f"Erro ao salvar plano: {e}", "danger")
    return redirect(url_for("clinico.plano", aluno_id=aluno_id))


# ─── DOCUMENTOS ──────────────────────────────────────────────────────────────

@clinico_bp.route("/<aluno_id>/documentos", methods=["GET"])
@login_required
def documentos(aluno_id):
    sb = _sb()
    pid = session["user_id"]
    aluno = _get_aluno_or_404(sb, pid, aluno_id)
    if not aluno:
        return redirect(url_for("alunos.lista"))

    docs = listar_documentos(sb, pid, aluno_id)
    # Gera URLs assinadas para cada documento
    for doc in docs:
        path = doc.get("arquivo_url", "") or ""
        if path and not path.startswith("http"):
            doc["_url_signed"] = gerar_url_signed(BUCKET_DOCS, path)
        else:
            doc["_url_signed"] = path  # já é URL completa

    return render_template("clinico/documentos.html", aluno=aluno, documentos=docs)


@clinico_bp.route("/<aluno_id>/documentos", methods=["POST"])
@login_required
def upload_documento(aluno_id):
    sb = _sb()
    pid = session["user_id"]
    titulo = request.form.get("titulo", "").strip()
    if not titulo:
        flash("Título é obrigatório.", "warning")
        return redirect(url_for("clinico.documentos", aluno_id=aluno_id))

    arquivo_url = None
    file = request.files.get("arquivo")
    if file and getattr(file, "filename", ""):
        try:
            path = fazer_upload_documento(pid, aluno_id, file)
            arquivo_url = path  # salva o path, gera URL signed na exibição
        except Exception as e:
            flash(f"Erro no upload: {e}", "danger")
            return redirect(url_for("clinico.documentos", aluno_id=aluno_id))

    dados = dict(request.form)
    dados["arquivo_url"] = arquivo_url
    try:
        salvar_documento(sb, pid, aluno_id, dados)
        flash("Documento adicionado!", "success")
    except Exception as e:
        flash(f"Erro ao salvar documento: {e}", "danger")

    return redirect(url_for("clinico.documentos", aluno_id=aluno_id))


@clinico_bp.route("/<aluno_id>/documentos/<doc_id>/excluir", methods=["POST"])
@login_required
def excluir_doc(aluno_id, doc_id):
    sb = _sb()
    try:
        excluir_documento(sb, session["user_id"], doc_id)
        flash("Documento removido.", "success")
    except Exception as e:
        flash(f"Erro: {e}", "danger")
    return redirect(url_for("clinico.documentos", aluno_id=aluno_id))


# ─── FASE ATUAL ──────────────────────────────────────────────────────────────

@clinico_bp.route("/<aluno_id>/fase", methods=["POST"])
@login_required
def atualizar_fase(aluno_id):
    sb = _sb()
    fase = request.form.get("fase", "")
    try:
        atualizar_fase_aluno(sb, session["user_id"], aluno_id, fase)
        flash("Fase atualizada!", "success")
    except Exception as e:
        flash(f"Erro: {e}", "danger")
    return redirect(request.referrer or url_for("alunos.ficha", aluno_id=aluno_id))
