from datetime import date, timedelta

from flask import render_template, request, redirect, url_for, flash, session, Response
from . import comunicacao_bp
from .model import (
    listar_registros_periodo, gerar_texto_devolutiva, gerar_texto_relatorio,
    salvar_comunicacao, listar_historico, buscar_comunicacao,
    HUMOR_LABELS, PARTICIPACAO_STARS, TIPO_LABELS,
)
import json
from ..extensions import get_supabase
from ..auth.decorators import login_required
from ..alunos.model import listar_alunos, buscar_aluno
from ..registros.model import buscar_foto_bytes


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
# FOTO PROXY (serve fotos do Storage com auth do usuário)
# ---------------------------------------------------------------------------

@comunicacao_bp.route("/foto/<path:storage_path>")
@login_required
def foto(storage_path):
    try:
        content, ct = buscar_foto_bytes(storage_path)
        return Response(content, content_type=ct,
                        headers={"Cache-Control": "public, max-age=3600"})
    except Exception:
        return "", 404


# ---------------------------------------------------------------------------
# INDEX — selecionar aluno
# ---------------------------------------------------------------------------

@comunicacao_bp.route("/")
@login_required
def index():
    sb = _sb()
    professor_id = session["user_id"]
    alunos = listar_alunos(sb, professor_id)
    historico_recente = listar_historico(sb, professor_id, limit=5)
    return render_template("comunicacao/index.html",
                           alunos=alunos,
                           historico_recente=historico_recente,
                           tipo_labels=TIPO_LABELS)


# ---------------------------------------------------------------------------
# DEVOLUTIVA
# ---------------------------------------------------------------------------

@comunicacao_bp.route("/devolutiva")
@login_required
def devolutiva():
    sb = _sb()
    professor_id = session["user_id"]

    aluno_id = request.args.get("aluno_id", "").strip()
    if not aluno_id:
        flash("Selecione um aluno.", "warning")
        return redirect(url_for("comunicacao.index"))

    aluno = buscar_aluno(sb, professor_id, aluno_id)
    if not aluno:
        flash("Aluno não encontrado.", "danger")
        return redirect(url_for("comunicacao.index"))

    hoje = date.today()
    try:
        ini = date.fromisoformat(request.args.get("data_inicio", ""))
    except ValueError:
        ini = hoje - timedelta(days=13)
    try:
        fim = date.fromisoformat(request.args.get("data_fim", ""))
    except ValueError:
        fim = hoje

    registros = listar_registros_periodo(
        sb, professor_id, aluno_id, ini.isoformat(), fim.isoformat()
    )

    # Enriquece com URL de foto para preview
    for r in registros:
        for f in r.get("fotos", []):
            f["url"] = url_for("comunicacao.foto", storage_path=f["storage_path"])

    texto_gerado = gerar_texto_devolutiva(registros, aluno["nome"], ini.isoformat(), fim.isoformat())

    return render_template(
        "comunicacao/devolutiva.html",
        aluno=aluno,
        registros=registros,
        texto_gerado=texto_gerado,
        periodo_inicio=ini.isoformat(),
        periodo_fim=fim.isoformat(),
        humor_labels=HUMOR_LABELS,
        participacao_stars=PARTICIPACAO_STARS,
    )


@comunicacao_bp.route("/devolutiva/salvar", methods=["POST"])
@login_required
def devolutiva_salvar():
    sb = _sb()
    professor_id = session["user_id"]
    aluno_id = request.form.get("aluno_id", "").strip()

    if not aluno_id:
        flash("Aluno inválido.", "danger")
        return redirect(url_for("comunicacao.index"))

    aluno = buscar_aluno(sb, professor_id, aluno_id)
    aluno_nome = aluno["nome"] if aluno else "Aluno"

    try:
        fotos_selecionadas = json.loads(request.form.get("fotos_selecionadas") or "[]")
    except Exception:
        fotos_selecionadas = []

    try:
        comm = salvar_comunicacao(sb, professor_id, aluno_id, {
            "titulo":         f"Devolutiva — {aluno_nome}",
            "periodo_inicio": request.form.get("periodo_inicio"),
            "periodo_fim":    request.form.get("periodo_fim"),
            "conteudo":       request.form.get("comentario_geral", ""),
            "proximos_passos": request.form.get("direcionamentos", ""),
            "texto_whatsapp": request.form.get("texto_whatsapp", ""),
            "fotos_selecionadas": fotos_selecionadas,
            "tipo":           "devolutiva",
        })
        flash("Devolutiva salva no histórico.", "success")
        return redirect(url_for("comunicacao.ver", comm_id=comm["id"]))
    except Exception as e:
        flash(f"Erro ao salvar: {e}", "danger")
        return redirect(url_for("comunicacao.devolutiva", aluno_id=aluno_id))


# ---------------------------------------------------------------------------
# RELATÓRIO DE EVOLUÇÃO
# ---------------------------------------------------------------------------

@comunicacao_bp.route("/relatorio", methods=["GET", "POST"])
@login_required
def relatorio():
    sb = _sb()
    professor_id = session["user_id"]

    aluno_id = (request.args.get("aluno_id") or request.form.get("aluno_id", "")).strip()
    if not aluno_id:
        flash("Selecione um aluno.", "warning")
        return redirect(url_for("comunicacao.index"))

    aluno = buscar_aluno(sb, professor_id, aluno_id)
    if not aluno:
        flash("Aluno não encontrado.", "danger")
        return redirect(url_for("comunicacao.index"))

    registros = []
    periodo_inicio = ""
    periodo_fim = ""

    if request.method == "POST":
        periodo_inicio = request.form.get("periodo_inicio", "").strip()
        periodo_fim    = request.form.get("periodo_fim", "").strip()

        if not periodo_inicio or not periodo_fim:
            flash("Informe o período.", "danger")
        else:
            try:
                registros = listar_registros_periodo(
                    sb, professor_id, aluno_id, periodo_inicio, periodo_fim
                )
                for r in registros:
                    for f in r.get("fotos", []):
                        f["url"] = url_for("comunicacao.foto",
                                           storage_path=f["storage_path"])
            except Exception as e:
                flash(f"Erro ao buscar registros: {e}", "danger")

    return render_template(
        "comunicacao/relatorio.html",
        aluno=aluno,
        registros=registros,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        humor_labels=HUMOR_LABELS,
        participacao_stars=PARTICIPACAO_STARS,
    )


@comunicacao_bp.route("/relatorio/salvar", methods=["POST"])
@login_required
def relatorio_salvar():
    sb = _sb()
    professor_id = session["user_id"]
    aluno_id = request.form.get("aluno_id", "").strip()

    if not aluno_id:
        flash("Aluno inválido.", "danger")
        return redirect(url_for("comunicacao.index"))

    aluno = buscar_aluno(sb, professor_id, aluno_id)
    aluno_nome = aluno["nome"] if aluno else "Aluno"

    titulo = request.form.get("titulo", "").strip() or f"Relatório — {aluno_nome}"
    pontos_fortes   = request.form.get("pontos_fortes", "").strip()
    pontos_atencao  = request.form.get("pontos_atencao", "").strip()
    proximos_passos = request.form.get("proximos_passos", "").strip()
    periodo_inicio  = request.form.get("periodo_inicio", "").strip()
    periodo_fim     = request.form.get("periodo_fim", "").strip()

    texto_wa = gerar_texto_relatorio(
        aluno_nome, periodo_inicio, periodo_fim,
        titulo, pontos_fortes, pontos_atencao, proximos_passos
    )

    try:
        fotos_selecionadas = json.loads(request.form.get("fotos_selecionadas") or "[]")
    except Exception:
        fotos_selecionadas = []

    try:
        comm = salvar_comunicacao(sb, professor_id, aluno_id, {
            "titulo":          titulo,
            "periodo_inicio":  periodo_inicio,
            "periodo_fim":     periodo_fim,
            "resumo":          request.form.get("resumo", "").strip(),
            "pontos_fortes":   pontos_fortes,
            "pontos_atencao":  pontos_atencao,
            "proximos_passos": proximos_passos,
            "fotos_selecionadas": fotos_selecionadas,
            "texto_whatsapp":  texto_wa,
            "tipo":            "relatorio",
        })
        flash("Relatório salvo com sucesso!", "success")
        
        # Redireciona para o PDF se foi clicado em 'gerar_pdf' (veremos isso no template)
        return redirect(url_for("comunicacao.ver_pdf", comm_id=comm["id"]))

    except Exception as e:
        flash(f"Erro ao salvar: {e}", "danger")
        return redirect(url_for("comunicacao.relatorio", aluno_id=aluno_id))


# ---------------------------------------------------------------------------
# VER COMUNICAÇÃO SALVA
# ---------------------------------------------------------------------------

@comunicacao_bp.route("/ver/<comm_id>")
@login_required
def ver(comm_id):
    sb = _sb()
    professor_id = session["user_id"]
    comm = buscar_comunicacao(sb, professor_id, comm_id)
    if not comm:
        flash("Comunicação não encontrada.", "danger")
        return redirect(url_for("comunicacao.index"))
    return render_template("comunicacao/ver.html", comm=comm,
                           tipo_labels=TIPO_LABELS)


@comunicacao_bp.route("/relatorio/<comm_id>/pdf")
@login_required
def ver_pdf(comm_id):
    sb = _sb()
    professor_id = session["user_id"]
    comm = buscar_comunicacao(sb, professor_id, comm_id)
    if not comm or comm.get("tipo") != "relatorio":
        flash("Relatório não encontrado ou acesso negado.", "danger")
        return redirect(url_for("comunicacao.index"))
        
    return render_template("comunicacao/ver_pdf.html", comm=comm)


# ---------------------------------------------------------------------------
# HISTÓRICO
# ---------------------------------------------------------------------------

@comunicacao_bp.route("/historico")
@login_required
def historico():
    sb = _sb()
    professor_id = session["user_id"]
    aluno_id = request.args.get("aluno_id", "").strip() or None

    alunos   = listar_alunos(sb, professor_id)
    lista    = listar_historico(sb, professor_id, aluno_id=aluno_id)
    aluno_sel = None
    if aluno_id:
        aluno_sel = next((a for a in alunos if a["id"] == aluno_id), None)

    return render_template("comunicacao/historico.html",
                           lista=lista,
                           alunos=alunos,
                           aluno_sel=aluno_sel,
                           tipo_labels=TIPO_LABELS)
