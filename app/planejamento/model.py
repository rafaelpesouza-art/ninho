"""Camada de dados para o módulo de planejamento."""
from datetime import datetime, timezone

MATERIAS = [
    "Matemática", "Português", "Ciências", "História", "Geografia",
    "Inglês", "Arte", "Música", "Ed. Física", "Outro",
]

SERIES = [
    "1º ano EF", "2º ano EF", "3º ano EF", "4º ano EF", "5º ano EF",
    "6º ano EF", "7º ano EF", "8º ano EF", "9º ano EF",
    "1º EM", "2º EM", "3º EM",
]

DIFICULDADES = {"facil": "Fácil", "medio": "Médio", "dificil": "Difícil"}


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# ATIVIDADES
# ---------------------------------------------------------------------------

def listar_atividades(sb, professor_id, materia=None, serie=None, tag=None, q=None):
    query = (
        sb.table("atividades")
        .select("*")
        .eq("professor_id", professor_id)
        .order("criado_em", desc=True)
    )
    if materia:
        query = query.eq("materia", materia)
    if serie:
        query = query.eq("serie", serie)
    if tag:
        query = query.cs("tags", f'["{tag}"]')
    if q:
        query = query.ilike("titulo", f"%{q}%")
    return query.execute().data or []


def buscar_atividade(sb, professor_id, atividade_id):
    try:
        res = (
            sb.table("atividades")
            .select("*")
            .eq("professor_id", professor_id)
            .eq("id", atividade_id)
            .maybe_single()
            .execute()
        )
        return res.data
    except Exception:
        return None


def salvar_atividade(sb, professor_id, dados):
    tags = [t.strip() for t in dados.get("tags", "").split(",") if t.strip()]
    payload = {
        "professor_id": professor_id,
        "titulo":       dados["titulo"].strip(),
        "descricao":    dados.get("descricao", "").strip(),
        "materia":      dados.get("materia", ""),
        "serie":        dados.get("serie", ""),
        "dificuldade":  dados.get("dificuldade", ""),
        "tags":         tags,
    }
    res = sb.table("atividades").insert(payload).execute()
    return (res.data or [{}])[0]


def atualizar_atividade(sb, professor_id, atividade_id, dados):
    tags = [t.strip() for t in dados.get("tags", "").split(",") if t.strip()]
    payload = {
        "titulo":       dados["titulo"].strip(),
        "descricao":    dados.get("descricao", "").strip(),
        "materia":      dados.get("materia", ""),
        "serie":        dados.get("serie", ""),
        "dificuldade":  dados.get("dificuldade", ""),
        "tags":         tags,
        "atualizado_em": _now(),
    }
    sb.table("atividades").update(payload) \
        .eq("professor_id", professor_id).eq("id", atividade_id).execute()


def excluir_atividade(sb, professor_id, atividade_id):
    sb.table("atividades").delete() \
        .eq("professor_id", professor_id).eq("id", atividade_id).execute()


# ---------------------------------------------------------------------------
# PLANOS DE AULA
# ---------------------------------------------------------------------------

def listar_planos(sb, professor_id, aluno_id=None):
    q = (
        sb.table("planos_aula")
        .select("*, alunos(id, nome)")
        .eq("professor_id", professor_id)
        .order("criado_em", desc=True)
    )
    if aluno_id:
        q = q.eq("aluno_id", aluno_id)
    return q.execute().data or []


def buscar_plano(sb, professor_id, plano_id):
    try:
        res = (
            sb.table("planos_aula")
            .select("*, alunos(id, nome)")
            .eq("professor_id", professor_id)
            .eq("id", plano_id)
            .maybe_single()
            .execute()
        )
        plano = res.data
        if not plano:
            return None
        pa = (
            sb.table("planos_atividades")
            .select("ordem, atividades(*)")
            .eq("plano_id", plano_id)
            .order("ordem")
            .execute()
        )
        plano["atividades"] = [row["atividades"] for row in (pa.data or [])]
        return plano
    except Exception:
        return None


def salvar_plano(sb, professor_id, dados):
    payload = {
        "professor_id": professor_id,
        "aluno_id":     dados.get("aluno_id") or None,
        "titulo":       dados["titulo"].strip(),
        "descricao":    dados.get("descricao", "").strip(),
        "materia":      dados.get("materia", ""),
        "serie":        dados.get("serie", ""),
    }
    res = sb.table("planos_aula").insert(payload).execute()
    plano = (res.data or [{}])[0]
    _set_atividades_plano(sb, plano["id"], dados.get("atividade_ids", []))
    return plano


def atualizar_plano(sb, professor_id, plano_id, dados):
    payload = {
        "aluno_id":     dados.get("aluno_id") or None,
        "titulo":       dados["titulo"].strip(),
        "descricao":    dados.get("descricao", "").strip(),
        "materia":      dados.get("materia", ""),
        "serie":        dados.get("serie", ""),
        "atualizado_em": _now(),
    }
    sb.table("planos_aula").update(payload) \
        .eq("professor_id", professor_id).eq("id", plano_id).execute()
    _set_atividades_plano(sb, plano_id, dados.get("atividade_ids", []))


def excluir_plano(sb, professor_id, plano_id):
    sb.table("planos_atividades").delete().eq("plano_id", plano_id).execute()
    sb.table("planos_aula").delete() \
        .eq("professor_id", professor_id).eq("id", plano_id).execute()


def _set_atividades_plano(sb, plano_id, atividade_ids):
    sb.table("planos_atividades").delete().eq("plano_id", plano_id).execute()
    rows = [
        {"plano_id": plano_id, "atividade_id": aid, "ordem": i}
        for i, aid in enumerate(atividade_ids) if aid
    ]
    if rows:
        sb.table("planos_atividades").insert(rows).execute()
