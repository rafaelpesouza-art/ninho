"""
Lógica para o sistema de Lembretes de Sessão.
Gera links wa.me com mensagens pré-formatadas. Pronto para integração
futura com WAHA API (basta substituir gerar_link_wa por chamada HTTP).
"""
from datetime import date, datetime, timedelta, timezone
import re
import urllib.parse

BRT = timezone(timedelta(hours=-3))

MSG_LEMBRETE_PADRAO = (
    "Olá, {responsavel}! 👋 Passando para lembrar da sessão de "
    "*{nome_aluno}* amanhã ({data}) às *{horario}*. "
    "Qualquer dúvida é só chamar! 😊"
)
MSG_CONFIRMACAO_PADRAO = (
    "Olá, {responsavel}! ✅ Confirmando a sessão de *{nome_aluno}* "
    "amanhã ({data}) às *{horario}*. Até lá! 🌟"
)
MSG_CANCELAMENTO_PADRAO = (
    "Olá, {responsavel}! ⚠️ Precisamos cancelar a sessão de "
    "*{nome_aluno}* de {data}. Logo entro em contato para reagendarmos. "
    "Obrigada pela compreensão! 💙"
)

_TEMPLATE_KEY = {
    "lembrete":     "msg_lembrete",
    "confirmacao":  "msg_confirmacao",
    "cancelamento": "msg_cancelamento",
}
_TEMPLATE_PADRAO = {
    "msg_lembrete":     MSG_LEMBRETE_PADRAO,
    "msg_confirmacao":  MSG_CONFIRMACAO_PADRAO,
    "msg_cancelamento": MSG_CANCELAMENTO_PADRAO,
}


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

def buscar_config_lembrete(sb, professor_id: str) -> dict:
    try:
        res = (
            sb.table("config_lembretes")
            .select("*")
            .eq("professor_id", professor_id)
            .maybe_single()
            .execute()
        )
        return res.data or {}
    except Exception:
        return {}


def salvar_config_lembrete(sb, professor_id: str, dados: dict) -> None:
    payload = {
        "professor_id":      professor_id,
        "nome_profissional": (dados.get("nome_profissional") or "").strip() or None,
        "msg_lembrete":      dados.get("msg_lembrete") or MSG_LEMBRETE_PADRAO,
        "msg_confirmacao":   dados.get("msg_confirmacao") or MSG_CONFIRMACAO_PADRAO,
        "msg_cancelamento":  dados.get("msg_cancelamento") or MSG_CANCELAMENTO_PADRAO,
    }
    existing = buscar_config_lembrete(sb, professor_id)
    if existing:
        sb.table("config_lembretes").update(payload).eq("professor_id", professor_id).execute()
    else:
        sb.table("config_lembretes").insert(payload).execute()


# ---------------------------------------------------------------------------
# SESSÕES DE AMANHÃ
# ---------------------------------------------------------------------------

def listar_sessoes_amanha(sb, professor_id: str) -> list:
    """Aulas agendadas para amanhã com dados do aluno e responsável."""
    amanha = (date.today() + timedelta(days=1)).isoformat()
    res = (
        sb.table("aulas")
        .select("id, data_hora, duracao_min, lembrete_enviado, "
                "alunos(id, nome, responsavel, telefone)")
        .eq("professor_id", professor_id)
        .eq("status", "agendada")
        .gte("data_hora", amanha + "T00:00:00")
        .lte("data_hora", amanha + "T23:59:59")
        .order("data_hora")
        .execute()
    )
    return res.data or []


def marcar_lembrete_enviado(sb, professor_id: str, aula_id: str) -> None:
    sb.table("aulas").update({"lembrete_enviado": True})\
      .eq("professor_id", professor_id).eq("id", aula_id).execute()


# ---------------------------------------------------------------------------
# FORMATAÇÃO
# ---------------------------------------------------------------------------

def formatar_mensagem(template: str, nome_aluno: str, data: str,
                      horario: str, responsavel: str, profissional: str) -> str:
    """Substitui {nome_aluno}, {data}, {horario}, {responsavel}, {profissional}."""
    return (
        template
        .replace("{nome_aluno}",   nome_aluno or "")
        .replace("{data}",         data or "")
        .replace("{horario}",      horario or "")
        .replace("{responsavel}",  responsavel or "família")
        .replace("{profissional}", profissional or "")
    )


def gerar_link_wa(telefone: str, mensagem: str) -> str:
    """Gera link wa.me/ com mensagem codificada."""
    tel = re.sub(r"\D", "", telefone or "")
    if tel and not tel.startswith("55"):
        tel = "55" + tel
    if not tel:
        return ""
    return f"https://wa.me/{tel}?text={urllib.parse.quote(mensagem)}"


def enriquecer_sessoes(sessoes: list, config: dict, tipo: str = "lembrete") -> list:
    """
    Adiciona link_wa, mensagem_wa e tem_telefone a cada sessão.
    tipo: 'lembrete' | 'confirmacao' | 'cancelamento'
    """
    nome_prof  = config.get("nome_profissional") or ""
    key        = _TEMPLATE_KEY.get(tipo, "msg_lembrete")
    template   = config.get(key) or _TEMPLATE_PADRAO[key]

    result = []
    for s in sessoes:
        aluno  = s.get("alunos") or {}
        dt_str = s.get("data_hora", "")

        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            if dt.tzinfo:
                dt = dt.astimezone(BRT)
            data_fmt    = dt.strftime("%d/%m")
            horario_fmt = dt.strftime("%H:%M")
        except Exception:
            data_fmt    = dt_str[8:10] + "/" + dt_str[5:7] if len(dt_str) >= 10 else ""
            horario_fmt = dt_str[11:16] if len(dt_str) >= 16 else ""

        nome_resp = (aluno.get("responsavel") or "").split()[0] if aluno.get("responsavel") else "família"
        msg = formatar_mensagem(
            template,
            nome_aluno   = aluno.get("nome", ""),
            data         = data_fmt,
            horario      = horario_fmt,
            responsavel  = nome_resp,
            profissional = nome_prof,
        )
        telefone = aluno.get("telefone") or ""

        enriched = dict(s)
        enriched["mensagem_wa"] = msg
        enriched["link_wa"]     = gerar_link_wa(telefone, msg)
        enriched["tem_telefone"] = bool(re.sub(r"\D", "", telefone))
        result.append(enriched)
    return result
