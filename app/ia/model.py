"""Camada de dados e integração Gemini para o módulo de IA."""
import os
from google import genai

GEMINI_MODEL = "gemini-2.5-flash"

SYSTEM_PROMPTS = {
    "anamnese": (
        "Você é um assistente especializado em atendimento infantil "
        "(psicopedagogia, fonoaudiologia, terapia). Analise esta transcrição de "
        "anamnese do aluno {nome_aluno} e gere um resumo claro e organizado dos "
        "pontos principais abordados. Destaque: queixas, observações relevantes, "
        "informações sobre desenvolvimento, comportamento e aprendizagem."
    ),
    "avaliacao": (
        "Você é um assistente especializado em atendimento infantil "
        "(psicopedagogia, fonoaudiologia, terapia). Analise esta transcrição de "
        "avaliação do aluno {nome_aluno} e gere um resumo claro e organizado dos "
        "pontos principais abordados. Destaque: queixas, observações relevantes, "
        "informações sobre desenvolvimento, comportamento e aprendizagem."
    ),
    "registro": (
        "Você é um assistente especializado em atendimento infantil "
        "(psicopedagogia, fonoaudiologia, terapia). Analise esta transcrição de "
        "registro de sessão do aluno {nome_aluno} e gere um resumo claro e "
        "organizado dos pontos principais abordados. Destaque: queixas, "
        "observações relevantes, informações sobre desenvolvimento, comportamento "
        "e aprendizagem."
    ),
}

CHAT_SYSTEM_PROMPT_COM_TRANSCRICAO = (
    "Você é um assistente de {tipo} para profissionais de atendimento infantil. "
    "Você tem acesso à transcrição completa da sessão. Responda perguntas, gere "
    "resumos por tópico, sugira observações e ajude a preencher relatórios. "
    "Responda sempre em português brasileiro.\n\n"
    "TRANSCRIÇÃO DA SESSÃO:\n{transcricao}"
)

CHAT_SYSTEM_PROMPT_SEM_TRANSCRICAO = (
    "Você é um assistente especializado em atendimento infantil (psicopedagogia, "
    "fonoaudiologia, terapia) para profissionais da área. "
    "Nenhuma transcrição de sessão foi fornecida — responda com base no seu "
    "conhecimento clínico e nas perguntas do profissional. Sugira observações, "
    "ajude a estruturar relatórios, proponha próximos passos e tire dúvidas. "
    "Responda sempre em português brasileiro."
)


def _client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY não configurada.")
    return genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# TRANSCRIÇÕES
# ---------------------------------------------------------------------------

def salvar_transcricao(sb, professor_id: str, dados: dict) -> dict:
    payload = {
        "professor_id":  professor_id,
        "aluno_id":      dados["aluno_id"],
        "tipo":          dados["tipo"],
        "referencia_id": dados.get("referencia_id"),
        "texto":         dados["texto"],
        "data_sessao":   dados.get("data_sessao") or None,
    }
    res = sb.table("transcricoes").insert(payload).execute()
    return (res.data or [{}])[0]


def atualizar_resumo(sb, transcricao_id: str, resumo: str) -> None:
    sb.table("transcricoes").update({"resumo": resumo}).eq("id", transcricao_id).execute()


def buscar_transcricao_por_referencia(sb, professor_id: str, referencia_id: str, tipo: str) -> dict | None:
    try:
        res = (
            sb.table("transcricoes")
            .select("*")
            .eq("professor_id", professor_id)
            .eq("referencia_id", referencia_id)
            .eq("tipo", tipo)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return (res.data or [None])[0]
    except Exception:
        return None


def buscar_transcricoes_aluno(sb, professor_id: str, aluno_id: str) -> list:
    """Retorna todas as transcrições de um aluno em ordem cronológica."""
    try:
        res = (
            sb.table("transcricoes")
            .select("id, tipo, texto, data_sessao, created_at")
            .eq("professor_id", professor_id)
            .eq("aluno_id", aluno_id)
            .order("data_sessao", desc=False)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def buscar_todas_transcricoes(sb, professor_id: str, referencia_id: str, tipo: str) -> list:
    """Retorna todos os textos de transcrição para uma mesma referência, em ordem cronológica."""
    try:
        res = (
            sb.table("transcricoes")
            .select("id, texto, data_sessao, created_at")
            .eq("professor_id", professor_id)
            .eq("referencia_id", referencia_id)
            .eq("tipo", tipo)
            .order("data_sessao", desc=False)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def buscar_transcricao(sb, professor_id: str, transcricao_id: str) -> dict | None:
    try:
        res = (
            sb.table("transcricoes")
            .select("*, alunos(id, nome)")
            .eq("professor_id", professor_id)
            .eq("id", transcricao_id)
            .maybe_single()
            .execute()
        )
        return res.data
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CHAT
# ---------------------------------------------------------------------------

def buscar_historico(sb, transcricao_id: str) -> list:
    try:
        res = (
            sb.table("chat_ia_mensagens")
            .select("id, role, conteudo, created_at")
            .eq("transcricao_id", transcricao_id)
            .order("created_at")
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def salvar_mensagem(sb, transcricao_id: str, role: str, conteudo: str) -> dict:
    res = (
        sb.table("chat_ia_mensagens")
        .insert({"transcricao_id": transcricao_id, "role": role, "conteudo": conteudo})
        .execute()
    )
    return (res.data or [{}])[0]


# ---------------------------------------------------------------------------
# GEMINI
# ---------------------------------------------------------------------------

def gerar_resumo(tipo: str, nome_aluno: str, texto: str) -> str:
    prompt_template = SYSTEM_PROMPTS.get(tipo, SYSTEM_PROMPTS["registro"])
    system_prompt = prompt_template.format(nome_aluno=nome_aluno)

    client = _client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=system_prompt + "\n\nTRANSCRIÇÃO:\n" + texto,
    )
    return response.text


def gerar_resposta_chat(tipo: str, transcricao: str, historico: list, mensagem: str) -> str:
    if transcricao.strip():
        system = CHAT_SYSTEM_PROMPT_COM_TRANSCRICAO.format(tipo=tipo, transcricao=transcricao)
    else:
        system = CHAT_SYSTEM_PROMPT_SEM_TRANSCRICAO

    # Monta conteúdo: system + histórico + nova mensagem
    contents = []
    contents.append({"role": "user", "parts": [{"text": system}]})
    contents.append({"role": "model", "parts": [{"text": "Entendido. Estou pronto para ajudar com base na transcrição fornecida."}]})

    for msg in historico:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": msg["conteudo"]}]})

    contents.append({"role": "user", "parts": [{"text": mensagem}]})

    client = _client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
    )
    return response.text
