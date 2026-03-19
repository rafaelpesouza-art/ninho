"""Perfil do professor — leitura e gravação."""
import httpx
import uuid
from ..registros.model import BUCKET, _ALLOWED_EXTS, _MIME_TO_EXT, _MAX_BYTES, _st_base, _st_headers, buscar_foto_bytes


def buscar_perfil(sb, professor_id: str) -> dict:
    try:
        res = (
            sb.table("perfis_professor")
            .select("*")
            .eq("professor_id", professor_id)
            .maybe_single()
            .execute()
        )
        return res.data or {}
    except Exception:
        return {}


def salvar_perfil(sb, professor_id: str, dados: dict, novo_logo_path: str | None = None) -> None:
    payload = {
        "professor_id":    professor_id,
        "nome_completo":   (dados.get("nome_completo") or "").strip(),
        "apelido":         (dados.get("apelido") or "").strip() or None,
        "data_nascimento": dados.get("data_nascimento") or None,
        "cpf":             (dados.get("cpf") or "").strip() or None,
        "telefone":        (dados.get("telefone") or "").strip() or None,
        "email_contato":   (dados.get("email_contato") or "").strip() or None,
    }
    
    cor = (dados.get("cor_primaria") or "").strip()
    if cor:
        payload["cor_primaria"] = cor
        
    if novo_logo_path is not None:
        payload["logo_url"] = novo_logo_path

    existing = buscar_perfil(sb, professor_id)
    if existing:
        sb.table("perfis_professor").update(payload).eq("professor_id", professor_id).execute()
    else:
        sb.table("perfis_professor").insert(payload).execute()


def nome_exibicao(perfil: dict) -> str:
    """Apelido ou primeiro nome ou 'Professor'."""
    apelido = (perfil.get("apelido") or "").strip()
    if apelido:
        return apelido
    nome = (perfil.get("nome_completo") or "").strip()
    if nome:
        return nome.split()[0]
    return "Professor"


def inicial(perfil: dict) -> str:
    """Primeira letra para o avatar."""
    apelido = (perfil.get("apelido") or "").strip()
    if apelido:
        return apelido[0].upper()
    nome = (perfil.get("nome_completo") or "").strip()
    if nome:
        return nome[0].upper()
    return "P"


def fazer_upload_logo(professor_id: str, file) -> str:
    """Faz upload da logo para o Storage e retorna o path no bucket."""
    nome = getattr(file, "filename", "") or ""
    ext  = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    mime = getattr(file, "mimetype", "") or getattr(file, "content_type", "") or ""
    if not ext:
        ext = _MIME_TO_EXT.get(mime, "")
    if ext not in _ALLOWED_EXTS:
        raise ValueError("Formato não suportado. Use JPG, PNG ou WebP.")
    
    content = file.read()
    if len(content) > _MAX_BYTES:
        raise ValueError("Imagem muito grande (máximo 5 MB).")

    token_uuid = str(uuid.uuid4()).split("-")[0]
    path = f"{professor_id}/logo_{token_uuid}.{ext}"
    ct   = mime or f"image/{ext}"

    resp = httpx.post(
        f"{_st_base()}/object/{BUCKET}/{path}",
        content=content,
        headers=_st_headers(content_type=ct),
        timeout=30,
    )
    if resp.status_code >= 400:
        raise ValueError(resp.json().get("message", resp.text))

    return path
