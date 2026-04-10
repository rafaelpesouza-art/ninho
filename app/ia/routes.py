"""Rotas da API de IA — transcrições e chat com Gemini."""
from flask import request, jsonify, session
from . import ia_bp
from .model import (
    salvar_transcricao, atualizar_resumo,
    buscar_transcricao_por_referencia, buscar_transcricao,
    buscar_todas_transcricoes, buscar_transcricoes_aluno,
    buscar_historico, salvar_mensagem,
    gerar_resumo, gerar_resposta_chat,
)
from ..auth.decorators import login_required
from ..extensions import get_supabase


def _formatar_nota(t: dict, idx: int) -> str:
    """Formata uma transcrição com data e tipo para o contexto da IA."""
    data = t.get("data_sessao") or ""
    if data:
        try:
            from datetime import date
            d = date.fromisoformat(data)
            data = d.strftime("%d/%m/%Y")
        except Exception:
            pass
    tipo = t.get("tipo", "registro").capitalize()
    cabecalho = f"[{tipo} — {data}]" if data else f"[{tipo} — nota {idx + 1}]"
    return f"{cabecalho}\n{t['texto']}"


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
# POST /api/transcricoes
# ---------------------------------------------------------------------------

@ia_bp.route("/transcricoes", methods=["POST"])
@login_required
def criar_transcricao():
    sb = _sb()
    professor_id = session["user_id"]
    data = request.get_json(silent=True) or {}

    tipo = data.get("tipo", "").strip()
    texto = data.get("texto", "").strip()
    aluno_id = data.get("aluno_id", "").strip()
    referencia_id = (data.get("referencia_id") or "").strip() or None
    data_sessao = (data.get("data_sessao") or "").strip() or None

    if not tipo or not texto or not aluno_id:
        return jsonify({"erro": "Campos obrigatórios: tipo, texto, aluno_id"}), 400

    if tipo not in ("anamnese", "avaliacao", "registro"):
        return jsonify({"erro": "Tipo inválido. Use: anamnese, avaliacao ou registro"}), 400

    # Busca nome do aluno para o prompt
    nome_aluno = "o aluno"
    try:
        r = sb.table("alunos").select("nome").eq("id", aluno_id).eq("professor_id", professor_id).maybe_single().execute()
        if r.data:
            nome_aluno = r.data.get("nome", nome_aluno)
    except Exception:
        pass

    # Salva transcrição
    try:
        transcricao = salvar_transcricao(sb, professor_id, {
            "aluno_id": aluno_id,
            "tipo": tipo,
            "referencia_id": referencia_id,
            "texto": texto,
            "data_sessao": data_sessao,
        })
    except Exception as e:
        return jsonify({"erro": f"Erro ao salvar transcrição: {e}"}), 500

    transcricao_id = transcricao["id"]

    # Gera resumo via Gemini
    try:
        resumo = gerar_resumo(tipo, nome_aluno, texto)
        atualizar_resumo(sb, transcricao_id, resumo)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 503
    except Exception as e:
        erro_str = str(e).lower()
        if "quota" in erro_str or "rate" in erro_str:
            return jsonify({"erro": "Limite de uso da IA atingido. Tente novamente em instantes."}), 429
        if "timeout" in erro_str:
            return jsonify({"erro": "A IA demorou muito para responder. Tente novamente."}), 504
        return jsonify({"erro": f"Erro ao gerar resumo: {e}"}), 500

    return jsonify({"transcricao_id": transcricao_id, "resumo": resumo}), 201


# ---------------------------------------------------------------------------
# GET /api/transcricoes/<referencia_id>?tipo=<tipo>
# ---------------------------------------------------------------------------

@ia_bp.route("/transcricoes/<referencia_id>", methods=["GET"])
@login_required
def verificar_transcricao(referencia_id):
    sb = _sb()
    professor_id = session["user_id"]
    tipo = request.args.get("tipo", "").strip()

    if not tipo:
        return jsonify({"erro": "Parâmetro 'tipo' obrigatório"}), 400

    transcricao = buscar_transcricao_por_referencia(sb, professor_id, referencia_id, tipo)

    if not transcricao:
        return jsonify({"existe": False})

    return jsonify({
        "existe": True,
        "transcricao_id": transcricao["id"],
        "resumo": transcricao.get("resumo"),
    })


# ---------------------------------------------------------------------------
# POST /api/chat-ia
# ---------------------------------------------------------------------------

@ia_bp.route("/chat-ia", methods=["POST"])
@login_required
def chat():
    sb = _sb()
    professor_id = session["user_id"]
    data = request.get_json(silent=True) or {}

    transcricao_id = (data.get("transcricao_id") or "").strip()
    mensagem = (data.get("mensagem") or "").strip()
    historico_frontend = data.get("historico", [])  # histórico passado pelo frontend quando sem transcricao_id

    if not mensagem:
        return jsonify({"erro": "Campo obrigatório: mensagem"}), 400

    if transcricao_id:
        # Com transcrição — valida e monta contexto completo
        transcricao = buscar_transcricao(sb, professor_id, transcricao_id)
        if not transcricao:
            return jsonify({"erro": "Transcrição não encontrada"}), 404

        tipo = transcricao.get("tipo", "registro")
        referencia_id = transcricao.get("referencia_id")

        if referencia_id:
            todas = buscar_todas_transcricoes(sb, professor_id, referencia_id, tipo)
            if todas:
                partes = [_formatar_nota(t, i) for i, t in enumerate(todas)]
                texto = "\n\n---\n\n".join(partes)
            else:
                texto = transcricao.get("texto", "")
        else:
            texto = transcricao.get("texto", "")

        historico = buscar_historico(sb, transcricao_id)
    else:
        # Sem transcricao_id — busca todas as notas do aluno como contexto
        tipo = "registro"
        historico = historico_frontend
        aluno_id = (data.get("aluno_id") or "").strip()
        if aluno_id:
            todas = buscar_transcricoes_aluno(sb, professor_id, aluno_id)
            if todas:
                partes = [_formatar_nota(t, i) for i, t in enumerate(todas)]
                texto = "\n\n---\n\n".join(partes)
            else:
                texto = ""
        else:
            texto = ""

    # Gera resposta via Gemini
    try:
        resposta = gerar_resposta_chat(tipo, texto, historico, mensagem)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 503
    except Exception as e:
        erro_str = str(e).lower()
        if "quota" in erro_str or "rate" in erro_str:
            return jsonify({"erro": "Limite de uso da IA atingido. Tente novamente em instantes."}), 429
        if "timeout" in erro_str:
            return jsonify({"erro": "A IA demorou muito para responder. Tente novamente."}), 504
        return jsonify({"erro": f"Erro na IA: {e}"}), 500

    # Persiste pergunta e resposta (apenas quando há transcricao_id)
    if transcricao_id:
        try:
            salvar_mensagem(sb, transcricao_id, "user", mensagem)
            salvar_mensagem(sb, transcricao_id, "assistant", resposta)
        except Exception:
            pass

    return jsonify({"resposta": resposta})


# ---------------------------------------------------------------------------
# GET /api/chat-ia/<transcricao_id>/historico
# ---------------------------------------------------------------------------

@ia_bp.route("/chat-ia/<transcricao_id>/historico", methods=["GET"])
@login_required
def historico(transcricao_id):
    sb = _sb()
    professor_id = session["user_id"]

    transcricao = buscar_transcricao(sb, professor_id, transcricao_id)
    if not transcricao:
        return jsonify({"erro": "Transcrição não encontrada"}), 404

    mensagens = buscar_historico(sb, transcricao_id)
    return jsonify({"mensagens": mensagens})
