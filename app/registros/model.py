"""
Camada de dados para registros de aula (sessões realizadas) e fotos de sessão.
"""
import uuid as _uuid_mod
from datetime import datetime as _dt
import httpx as _httpx

BUCKET = "fotos-sessoes"
_ALLOWED_EXTS = {"jpg", "jpeg", "png", "webp"}
_MIME_TO_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def _st_base() -> str:
    """URL base da Storage API, ex: https://xxx.supabase.co/storage/v1"""
    from flask import current_app
    return current_app.config["SUPABASE_URL"].rstrip("/") + "/storage/v1"


def _st_headers(content_type: str | None = None) -> dict:
    """Headers autenticados para chamadas diretas à Storage API."""
    from flask import session, current_app
    token = session.get("access_token") or current_app.config["SUPABASE_KEY"]
    key   = current_app.config["SUPABASE_KEY"]
    h = {"apiKey": key, "Authorization": f"Bearer {token}"}
    if content_type:
        h["Content-Type"] = content_type
    return h


def buscar_registro(sb, professor_id: str, registro_id: str) -> dict | None:
    try:
        res = (
            sb.table("registros_sessao")
            .select("*, aulas(id, data_hora, duracao_min, aluno_id), alunos(id, nome, telefone)")
            .eq("professor_id", professor_id)
            .eq("id", registro_id)
            .maybe_single()
            .execute()
        )
        return res.data
    except Exception:
        return None


def listar_registros_aluno(sb, professor_id: str, aluno_id: str, limit: int = 20) -> list:
    res = (
        sb.table("registros_sessao")
        .select("id, criado_em, descricao, proximos_passos, observacoes_familia, enviado_familia, aulas(data_hora)")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .order("criado_em", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def criar_registro(sb, professor_id: str, dados: dict) -> dict:
    aula_id  = dados.get("aula_id", "").strip()
    aluno_id = dados.get("aluno_id", "").strip()

    if not aula_id or not aluno_id:
        raise ValueError("aula_id e aluno_id são obrigatórios.")

    payload = {
        "professor_id":        professor_id,
        "aula_id":             aula_id,
        "aluno_id":            aluno_id,
        "descricao":           dados.get("descricao") or None,
        "proximos_passos":     dados.get("proximos_passos") or None,
        "enviado_familia":     False,
    }
    res = sb.table("registros_sessao").insert(payload).execute()
    return res.data[0]


def atualizar_registro(sb, professor_id: str, registro_id: str, dados: dict) -> dict | None:
    payload = {
        "descricao":           dados.get("descricao") or None,
        "proximos_passos":     dados.get("proximos_passos") or None,
    }
    res = (
        sb.table("registros_sessao")
        .update(payload)
        .eq("professor_id", professor_id)
        .eq("id", registro_id)
        .execute()
    )
    return res.data[0] if res.data else None


def marcar_enviada_familia(sb, professor_id: str, registro_id: str) -> None:
    sb.table("registros_sessao").update({"enviado_familia": True}).eq("id", registro_id).eq("professor_id", professor_id).execute()


def salvar_mensagem_familia(sb, professor_id: str, registro_id: str, aluno_id: str,
                            texto: str, foto_ids: list) -> dict:
    """Salva mensagem para família e retorna o registro criado."""
    from datetime import datetime as _datetime
    payload = {
        "professor_id":       professor_id,
        "registro_id":        registro_id,
        "aluno_id":           aluno_id,
        "texto":              texto or None,
        "fotos_selecionadas": foto_ids or [],
        "enviado":            True,
        "data_envio":         _datetime.utcnow().isoformat(),
    }
    res = sb.table("mensagens_familia").insert(payload).execute()
    return res.data[0] if res.data else {}


# ---------------------------------------------------------------------------
# FOTOS DE SESSÃO
# ---------------------------------------------------------------------------

def fazer_upload_foto(sb, professor_id: str, registro_id: str, aluno_id: str,
                      file, legenda: str = "") -> dict:
    """Faz upload de uma foto para o Storage e salva metadados em fotos_sessao."""
    nome = getattr(file, "filename", "") or ""
    ext  = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    mime = getattr(file, "mimetype", "") or getattr(file, "content_type", "") or ""
    if not ext:
        ext = _MIME_TO_EXT.get(mime, "")
    if ext not in _ALLOWED_EXTS:
        raise ValueError("Formato não suportado. Use JPG, PNG ou WebP.")
    content = file.read()
    if len(content) > _MAX_BYTES:
        raise ValueError("Arquivo muito grande (máx 5 MB).")

    mes  = _dt.now().strftime("%Y-%m")
    path = f"{professor_id}/{aluno_id}/{mes}/{_uuid_mod.uuid4()}.{ext}"
    ct   = mime or f"image/{ext}"

    # Upload direto via REST — evita o problema de auth no cliente SDK compartilhado
    resp = _httpx.post(
        f"{_st_base()}/object/{BUCKET}/{path}",
        content=content,
        headers=_st_headers(content_type=ct),
        timeout=30,
    )
    if resp.status_code >= 400:
        raise ValueError(resp.json().get("message", resp.text))

    res = (
        sb.table("fotos_sessao")
        .insert({
            "professor_id": professor_id,
            "registro_id":  registro_id,
            "aluno_id":     aluno_id,
            "storage_path": path,
            "legenda":      legenda.strip() or None,
        })
        .execute()
    )
    return res.data[0]


def gerar_url_temporaria(sb, storage_path: str, expires_in: int = 3600) -> str:
    """Gera URL assinada para arquivo privado no Storage (válida por expires_in s)."""
    try:
        resp = _httpx.post(
            f"{_st_base()}/object/sign/{BUCKET}/{storage_path}",
            json={"expiresIn": expires_in},
            headers=_st_headers(),
            timeout=10,
        )
        if resp.status_code >= 400:
            return ""
        data = resp.json()
        url  = data.get("signedURL") or data.get("signedUrl") or ""
        # Supabase pode retornar path relativo; completa se necessário
        if url and url.startswith("/"):
            from flask import current_app
            url = current_app.config["SUPABASE_URL"].rstrip("/") + url
        return url
    except Exception:
        return ""


def buscar_foto_bytes(storage_path: str) -> tuple:
    """Busca bytes da foto no Storage via JWT autenticado. Retorna (bytes, content_type)."""
    resp = _httpx.get(
        f"{_st_base()}/object/authenticated/{BUCKET}/{storage_path}",
        headers=_st_headers(),
        timeout=30,
        follow_redirects=True,
    )
    if resp.status_code >= 400:
        raise ValueError(f"Storage error {resp.status_code}: {resp.text[:200]}")
    return resp.content, resp.headers.get("content-type", "image/jpeg")


def listar_fotos_registro(sb, professor_id: str, registro_id: str) -> list:
    res = (
        sb.table("fotos_sessao")
        .select("id, storage_path, legenda, criado_em")
        .eq("professor_id", professor_id)
        .eq("registro_id", registro_id)
        .order("criado_em")
        .execute()
    )
    return res.data or []


def listar_fotos_aluno(sb, professor_id: str, aluno_id: str, limit: int = 60) -> list:
    res = (
        sb.table("fotos_sessao")
        .select("id, storage_path, legenda, criado_em, registro_id, registros_sessao(descricao)")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .order("criado_em", desc=True)
        .limit(limit)
        .execute()
    )
    fotos = res.data or []
    for f in fotos:
        regs = f.get("registros_sessao")
        f["descricao_aula"] = regs.get("descricao") if isinstance(regs, dict) else None
    return fotos


def contar_fotos_aluno(sb, professor_id: str, aluno_id: str) -> int:
    try:
        res = (
            sb.table("fotos_sessao")
            .select("id", count="exact")
            .eq("professor_id", professor_id)
            .eq("aluno_id", aluno_id)
            .execute()
        )
        return res.count or 0
    except Exception:
        return 0


def deletar_foto(sb, professor_id: str, foto_id: str) -> dict:
    """Remove foto do Storage e da tabela. Retorna registro_id e aluno_id."""
    res = (
        sb.table("fotos_sessao")
        .select("storage_path, registro_id, aluno_id")
        .eq("professor_id", professor_id)
        .eq("id", foto_id)
        .maybe_single()
        .execute()
    )
    if not res.data:
        raise ValueError("Foto não encontrada ou sem permissão.")
    path = res.data["storage_path"]
    try:
        # DELETE direto via REST com JWT do usuário
        _httpx.delete(
            f"{_st_base()}/object/{BUCKET}",
            json={"prefixes": [path]},
            headers=_st_headers(),
            timeout=10,
        )
    except Exception:
        pass
    sb.table("fotos_sessao").delete().eq("professor_id", professor_id).eq("id", foto_id).execute()
    return {
        "registro_id": res.data.get("registro_id"),
        "aluno_id":    res.data.get("aluno_id"),
    }


def registro_ja_existe(sb, professor_id: str, aula_id: str) -> dict | None:
    """Retorna o registro existente para a aula, se houver."""
    try:
        res = (
            sb.table("registros_sessao")
            .select("id")
            .eq("professor_id", professor_id)
            .eq("aula_id", aula_id)
            .maybe_single()
            .execute()
        )
        return res.data
    except Exception:
        return None
