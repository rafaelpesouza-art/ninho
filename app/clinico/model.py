"""
Modelo clínico: Anamnese, Avaliação, Devolutiva,
Plano de Intervenção, Documentos e upload de arquivos.
"""
from __future__ import annotations
import json
import uuid as _uuid_mod
from datetime import date, datetime as _dt
import httpx as _httpx

BUCKET_DOCS  = "documentos-alunos"
BUCKET_FOTOS = "avatares-alunos"   # para foto_url do aluno

_ALLOWED_DOC_EXTS = {"pdf", "png", "jpg", "jpeg", "webp", "doc", "docx"}
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


# ─── Helpers de Storage ───────────────────────────────────────────────────────

def _st_base() -> str:
    from flask import current_app
    return current_app.config["SUPABASE_URL"].rstrip("/") + "/storage/v1"


def _st_headers(content_type: str | None = None) -> dict:
    from flask import session, current_app
    token = session.get("access_token") or current_app.config["SUPABASE_KEY"]
    key   = current_app.config["SUPABASE_KEY"]
    h = {"apiKey": key, "Authorization": f"Bearer {token}"}
    if content_type:
        h["Content-Type"] = content_type
    return h


def _upload_arquivo(bucket: str, path: str, content: bytes, content_type: str) -> None:
    """Faz upload de bytes para o Supabase Storage via REST."""
    resp = _httpx.post(
        f"{_st_base()}/object/{bucket}/{path}",
        content=content,
        headers=_st_headers(content_type=content_type),
        timeout=30,
    )
    if resp.status_code >= 400:
        raise ValueError(resp.json().get("message", resp.text[:200]))


def gerar_url_signed(bucket: str, storage_path: str, expires_in: int = 3600) -> str:
    """Gera URL assinada para arquivo privado (válida por expires_in segundos)."""
    try:
        resp = _httpx.post(
            f"{_st_base()}/object/sign/{bucket}/{storage_path}",
            json={"expiresIn": expires_in},
            headers=_st_headers(),
            timeout=10,
        )
        if resp.status_code >= 400:
            return ""
        data = resp.json()
        url = data.get("signedURL") or data.get("signedUrl") or ""
        if url and url.startswith("/"):
            from flask import current_app
            url = current_app.config["SUPABASE_URL"].rstrip("/") + url
        return url
    except Exception:
        return ""


def fazer_upload_documento(professor_id: str, aluno_id: str, file) -> str:
    """Faz upload de documento e retorna o storage_path."""
    nome = getattr(file, "filename", "") or ""
    ext  = nome.rsplit(".", 1)[-1].lower() if "." in nome else "bin"
    if ext not in _ALLOWED_DOC_EXTS:
        raise ValueError(f"Formato '.{ext}' não suportado.")
    content = file.read()
    if len(content) > _MAX_BYTES:
        raise ValueError("Arquivo muito grande (máx 10 MB).")
    content_type = getattr(file, "content_type", "") or "application/octet-stream"
    mes  = _dt.now().strftime("%Y-%m")
    path = f"{professor_id}/{aluno_id}/{mes}/{_uuid_mod.uuid4()}.{ext}"
    _upload_arquivo(BUCKET_DOCS, path, content, content_type)
    return path


def fazer_upload_avatar(professor_id: str, aluno_id: str, file) -> str:
    """Faz upload de foto de perfil do aluno e retorna URL pública."""
    nome = getattr(file, "filename", "") or ""
    ext  = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if ext not in {"jpg", "jpeg", "png", "webp"}:
        raise ValueError("Use JPG, PNG ou WebP para a foto.")
    content = file.read()
    if len(content) > 5 * 1024 * 1024:
        raise ValueError("Foto muito grande (máx 5 MB).")
    content_type = getattr(file, "content_type", "") or f"image/{ext}"
    path = f"{professor_id}/{aluno_id}/{_uuid_mod.uuid4()}.{ext}"
    _upload_arquivo(BUCKET_FOTOS, path, content, content_type)
    # Bucket público — URL direta
    from flask import current_app
    base = current_app.config["SUPABASE_URL"].rstrip("/")
    return f"{base}/storage/v1/object/public/{BUCKET_FOTOS}/{path}"


# ─── ANAMNESE ────────────────────────────────────────────────────────────────

def buscar_anamnese(sb, professor_id: str, aluno_id: str) -> dict | None:
    res = (
        sb.table("anamneses")
        .select("*")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .order("data_realizacao", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def salvar_anamnese(sb, professor_id: str, aluno_id: str, dados: dict,
                    anamnese_id: str | None = None) -> dict:
    secoes = _parse_json_list(dados.get("secoes_json", ""))
    payload = {
        "professor_id":   professor_id,
        "aluno_id":       aluno_id,
        "data_realizacao": dados.get("data_realizacao") or date.today().isoformat(),
        "conteudo":       dados.get("conteudo") or None,
        "secoes":         secoes,
        "observacoes":    dados.get("observacoes") or None,
    }
    if anamnese_id:
        res = (
            sb.table("anamneses")
            .update(payload)
            .eq("id", anamnese_id)
            .eq("professor_id", professor_id)
            .execute()
        )
    else:
        res = sb.table("anamneses").insert(payload).execute()
    return res.data[0]


# ─── AVALIAÇÃO ───────────────────────────────────────────────────────────────

def buscar_avaliacao_atual(sb, professor_id: str, aluno_id: str) -> dict | None:
    """Retorna avaliação em andamento ou a mais recente."""
    res = (
        sb.table("avaliacoes")
        .select("*")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .eq("status", "em_andamento")
        .order("data_inicio", desc=True)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]
    res = (
        sb.table("avaliacoes")
        .select("*")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .order("data_inicio", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def listar_avaliacoes(sb, professor_id: str, aluno_id: str) -> list:
    res = (
        sb.table("avaliacoes")
        .select("*")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .order("data_inicio", desc=True)
        .execute()
    )
    return res.data or []


def salvar_avaliacao(sb, professor_id: str, aluno_id: str, dados: dict,
                     avaliacao_id: str | None = None) -> dict:
    areas = _parse_json_list(dados.get("areas_json", ""))
    payload = {
        "professor_id":            professor_id,
        "aluno_id":                aluno_id,
        "data_inicio":             dados.get("data_inicio") or date.today().isoformat(),
        "data_fim":                dados.get("data_fim") or None,
        "status":                  dados.get("status", "em_andamento"),
        "conteudo":                dados.get("conteudo") or None,
        "areas":                   areas,
        "instrumentos_utilizados": dados.get("instrumentos_utilizados") or None,
        "pontos_fortes":           dados.get("pontos_fortes") or None,
        "pontos_atencao":          dados.get("pontos_atencao") or None,
        "observacoes":             dados.get("observacoes") or None,
    }
    if avaliacao_id:
        res = (
            sb.table("avaliacoes")
            .update(payload)
            .eq("id", avaliacao_id)
            .eq("professor_id", professor_id)
            .execute()
        )
    else:
        res = sb.table("avaliacoes").insert(payload).execute()
    return res.data[0]


def concluir_avaliacao(sb, professor_id: str, avaliacao_id: str) -> dict | None:
    res = (
        sb.table("avaliacoes")
        .update({"status": "concluida", "data_fim": date.today().isoformat()})
        .eq("id", avaliacao_id)
        .eq("professor_id", professor_id)
        .execute()
    )
    return res.data[0] if res.data else None


# ─── DEVOLUTIVA ───────────────────────────────────────────────────────────────

def buscar_devolutiva(sb, professor_id: str, aluno_id: str) -> dict | None:
    res = (
        sb.table("devolutivas")
        .select("*")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .order("criado_em", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def salvar_devolutiva(sb, professor_id: str, aluno_id: str, dados: dict,
                      devolutiva_id: str | None = None) -> dict:
    payload = {
        "professor_id":          professor_id,
        "aluno_id":              aluno_id,
        "avaliacao_id":          dados.get("avaliacao_id") or None,
        "data_entrega":          dados.get("data_entrega") or None,
        "conteudo":              dados.get("conteudo") or None,
        "encaminhamentos":       dados.get("encaminhamentos") or None,
        "recomendacoes_familia": dados.get("recomendacoes_familia") or None,
        "recomendacoes_escola":  dados.get("recomendacoes_escola") or None,
    }
    if devolutiva_id:
        res = (
            sb.table("devolutivas")
            .update(payload)
            .eq("id", devolutiva_id)
            .eq("professor_id", professor_id)
            .execute()
        )
    else:
        res = sb.table("devolutivas").insert(payload).execute()
    return res.data[0]


def marcar_enviada(sb, professor_id: str, devolutiva_id: str, campo: str) -> dict | None:
    if campo not in ("enviado_familia", "enviado_escola"):
        raise ValueError("Campo inválido.")
    res = (
        sb.table("devolutivas")
        .update({campo: True})
        .eq("id", devolutiva_id)
        .eq("professor_id", professor_id)
        .execute()
    )
    return res.data[0] if res.data else None


# ─── PLANO DE INTERVENÇÃO ────────────────────────────────────────────────────

def buscar_plano_ativo(sb, professor_id: str, aluno_id: str) -> dict | None:
    res = (
        sb.table("planos_intervencao")
        .select("*")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .eq("status", "ativo")
        .order("criado_em", desc=True)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]
    res = (
        sb.table("planos_intervencao")
        .select("*")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .order("criado_em", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def salvar_plano(sb, professor_id: str, aluno_id: str, dados: dict,
                 plano_id: str | None = None) -> dict:
    raw = dados.get("areas_foco", "")
    areas_foco = [a.strip() for a in raw.split(",") if a.strip()] if raw else []
    payload = {
        "professor_id":    professor_id,
        "aluno_id":        aluno_id,
        "titulo":          dados.get("titulo", "").strip() or "Plano sem título",
        "objetivo_geral":  dados.get("objetivo_geral") or None,
        "areas_foco":      areas_foco,
        "estrategias":     dados.get("estrategias") or None,
        "duracao_estimada": dados.get("duracao_estimada") or None,
        "status":          dados.get("status", "ativo"),
        "observacoes":     dados.get("observacoes") or None,
    }
    if plano_id:
        res = (
            sb.table("planos_intervencao")
            .update(payload)
            .eq("id", plano_id)
            .eq("professor_id", professor_id)
            .execute()
        )
    else:
        res = sb.table("planos_intervencao").insert(payload).execute()
    return res.data[0]


# ─── DOCUMENTOS ──────────────────────────────────────────────────────────────

def listar_documentos(sb, professor_id: str, aluno_id: str) -> list:
    res = (
        sb.table("documentos_aluno")
        .select("*")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .order("criado_em", desc=True)
        .execute()
    )
    return res.data or []


def salvar_documento(sb, professor_id: str, aluno_id: str, dados: dict) -> dict:
    payload = {
        "professor_id": professor_id,
        "aluno_id":     aluno_id,
        "titulo":       dados.get("titulo", "").strip(),
        "tipo":         dados.get("tipo", "outro"),
        "arquivo_url":  dados.get("arquivo_url") or None,
        "observacoes":  dados.get("observacoes") or None,
    }
    res = sb.table("documentos_aluno").insert(payload).execute()
    return res.data[0]


def excluir_documento(sb, professor_id: str, doc_id: str) -> None:
    sb.table("documentos_aluno").delete().eq("id", doc_id).eq("professor_id", professor_id).execute()


# ─── TEMPLATES PROFISSIONAL ──────────────────────────────────────────────────

def listar_templates(sb, professor_id: str) -> list:
    res = (
        sb.table("templates_profissional")
        .select("*")
        .eq("professor_id", professor_id)
        .order("tipo")
        .order("nome")
        .execute()
    )
    return res.data or []


def buscar_template_padrao(sb, professor_id: str, tipo: str) -> dict | None:
    res = (
        sb.table("templates_profissional")
        .select("*")
        .eq("professor_id", professor_id)
        .eq("tipo", tipo)
        .eq("padrao", True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def salvar_template(sb, professor_id: str, dados: dict, template_id: str | None = None) -> dict:
    secoes = _parse_json_list(dados.get("secoes_json", ""))
    tipo   = dados.get("tipo", "anamnese")
    is_padrao = dados.get("padrao") in ("on", "1", True)
    if is_padrao:
        # Remove padrão dos outros templates do mesmo tipo
        sb.table("templates_profissional").update({"padrao": False}).eq("professor_id", professor_id).eq("tipo", tipo).execute()
    payload = {
        "professor_id": professor_id,
        "tipo":         tipo,
        "nome":         dados.get("nome", "").strip(),
        "secoes":       secoes,
        "padrao":       is_padrao,
    }
    if template_id:
        res = (
            sb.table("templates_profissional")
            .update(payload)
            .eq("id", template_id)
            .eq("professor_id", professor_id)
            .execute()
        )
    else:
        res = sb.table("templates_profissional").insert(payload).execute()
    return res.data[0]


def excluir_template(sb, professor_id: str, template_id: str) -> None:
    sb.table("templates_profissional").delete().eq("id", template_id).eq("professor_id", professor_id).execute()


# ─── RESUMO CLÍNICO (para a ficha) ───────────────────────────────────────────

def resumo_clinico(sb, professor_id: str, aluno_id: str) -> dict:
    """Resumo rápido de cada módulo clínico (para as caixinhas da ficha)."""
    anamnese  = buscar_anamnese(sb, professor_id, aluno_id)
    avaliacao = buscar_avaliacao_atual(sb, professor_id, aluno_id)
    devolutiva = buscar_devolutiva(sb, professor_id, aluno_id)
    plano     = buscar_plano_ativo(sb, professor_id, aluno_id)
    try:
        n_docs = (
            sb.table("documentos_aluno")
            .select("id", count="exact")
            .eq("professor_id", professor_id)
            .eq("aluno_id", aluno_id)
            .execute()
        ).count or 0
    except Exception:
        n_docs = 0
    return {
        "anamnese":    anamnese,
        "avaliacao":   avaliacao,
        "devolutiva":  devolutiva,
        "plano":       plano,
        "n_documentos": n_docs,
    }


def atualizar_fase_aluno(sb, professor_id: str, aluno_id: str, fase: str) -> None:
    fases_validas = ("anamnese", "avaliacao", "intervencao", "alta")
    if fase not in fases_validas:
        raise ValueError("Fase inválida.")
    sb.table("alunos").update({"fase_atual": fase}).eq("id", aluno_id).eq("professor_id", professor_id).execute()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _parse_json_list(raw: str) -> list | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else None
    except Exception:
        return None
