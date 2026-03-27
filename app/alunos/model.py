"""
Camada de acesso a dados para alunos e geração de aulas recorrentes.
Todas as funções recebem o cliente Supabase autenticado (sb) e professor_id.
"""
from datetime import date, datetime, time, timedelta
import uuid


# ---------------------------------------------------------------------------
# CRUD ALUNOS
# ---------------------------------------------------------------------------

def listar_alunos(sb, professor_id, apenas_ativos=True):
    query = (
        sb.table("alunos")
        .select("*")
        .eq("professor_id", professor_id)
    )
    if apenas_ativos:
        query = query.eq("ativo", True)
    res = query.order("nome").execute()
    return res.data


def buscar_aluno(sb, professor_id, aluno_id):
    try:
        res = (
            sb.table("alunos")
            .select("*")
            .eq("professor_id", professor_id)
            .eq("id", aluno_id)
            .maybe_single()
            .execute()
        )
        return res.data
    except Exception:
        return None


def criar_aluno(sb, professor_id, dados: dict):
    """
    Cria o aluno. Se vier dia_semana_fixo + horario_fixo,
    gera as aulas recorrentes do mês atual automaticamente.
    Retorna o aluno criado.
    """
    payload = {
        "professor_id": professor_id,
        "nome": dados["nome"],
        "data_nascimento": dados.get("data_nascimento") or None,
        "responsavel": dados.get("responsavel") or None,
        "telefone": dados.get("telefone") or None,
        "email": dados.get("email") or None,
        "observacoes": dados.get("observacoes") or None,
        "ativo": True,
        "foto_url": dados.get("foto_url") or None,
        "fase_atual": dados.get("fase_atual") or "anamnese",
    }

    # Lógica de Vínculo Familiar
    familia_id = None
    aluno_vinculo_id = dados.get("aluno_vinculo_id")
    if aluno_vinculo_id:
        irmao = buscar_aluno(sb, professor_id, aluno_vinculo_id)
        if irmao:
            if irmao.get("familia_id"):
                familia_id = irmao["familia_id"]
            else:
                familia_id = str(uuid.uuid4())
                sb.table("alunos").update({"familia_id": familia_id}).eq("professor_id", professor_id).eq("id", irmao["id"]).execute()
    payload["familia_id"] = familia_id

    dia_semana = _parse_int(dados.get("dia_semana_fixo"))
    horario_str = dados.get("horario_fixo") or None
    duracao = _parse_int(dados.get("duracao_padrao_min")) or 60
    valor = _parse_float(dados.get("valor_aula"))

    payload["dia_semana_fixo"] = dia_semana
    payload["horario_fixo"] = horario_str
    payload["duracao_padrao_min"] = duracao
    payload["valor_aula"] = valor

    res = sb.table("alunos").insert(payload).execute()
    aluno = res.data[0]

    # Gera aulas recorrentes se dia + horário estiverem definidos
    if dia_semana is not None and horario_str:
        horario = _parse_time(horario_str)
        if horario:
            gerar_aulas_mes(sb, professor_id, aluno["id"], dia_semana, horario, duracao)

    return aluno


def atualizar_aluno(sb, professor_id, aluno_id, dados: dict):
    payload = {
        "nome": dados["nome"],
        "data_nascimento": dados.get("data_nascimento") or None,
        "responsavel": dados.get("responsavel") or None,
        "telefone": dados.get("telefone") or None,
        "email": dados.get("email") or None,
        "observacoes": dados.get("observacoes") or None,
        "dia_semana_fixo": _parse_int(dados.get("dia_semana_fixo")),
        "horario_fixo": dados.get("horario_fixo") or None,
        "duracao_padrao_min": _parse_int(dados.get("duracao_padrao_min")) or 60,
        "valor_aula": _parse_float(dados.get("valor_aula")),
        "foto_url": dados.get("foto_url") or None,
        "fase_atual": dados.get("fase_atual") or "anamnese",
    }
    # Lógica de Vínculo Familiar
    familia_id = None
    aluno_vinculo_id = dados.get("aluno_vinculo_id")
    if aluno_vinculo_id:
        irmao = buscar_aluno(sb, professor_id, aluno_vinculo_id)
        if irmao:
            if irmao.get("familia_id"):
                familia_id = irmao["familia_id"]
            else:
                familia_id = str(uuid.uuid4())
                sb.table("alunos").update({"familia_id": familia_id}).eq("professor_id", professor_id).eq("id", irmao["id"]).execute()
    payload["familia_id"] = familia_id

    res = (
        sb.table("alunos")
        .update(payload)
        .eq("professor_id", professor_id)
        .eq("id", aluno_id)
        .execute()
    )
    return res.data[0] if res.data else None


def desativar_aluno(sb, professor_id, aluno_id):
    res = (
        sb.table("alunos")
        .update({"ativo": False})
        .eq("professor_id", professor_id)
        .eq("id", aluno_id)
        .execute()
    )
    return res.data[0] if res.data else None


def reativar_aluno(sb, professor_id, aluno_id):
    res = (
        sb.table("alunos")
        .update({"ativo": True})
        .eq("professor_id", professor_id)
        .eq("id", aluno_id)
        .execute()
    )
    return res.data[0] if res.data else None


def listar_irmaos(sb, professor_id, familia_id):
    """Retorna todos os alunos com o mesmo familia_id."""
    if not familia_id:
        return []
    res = (
        sb.table("alunos")
        .select("id, nome, ativo")
        .eq("professor_id", professor_id)
        .eq("familia_id", familia_id)
        .execute()
    )
    return res.data


# ---------------------------------------------------------------------------
# AULAS RECORRENTES
# ---------------------------------------------------------------------------

def gerar_aulas_mes(sb, professor_id, aluno_id, dia_semana: int, horario: time,
                    duracao_min: int = 60, mes: date = None):
    """
    Gera todas as aulas do mês para o dia_semana informado.
    dia_semana: 0=Segunda … 6=Domingo (convenção Python weekday).
    mes: qualquer data dentro do mês desejado (default = mês atual).
    Não duplica aulas já existentes na mesma data/hora.
    """
    ref = mes or date.today()
    primeiro = ref.replace(day=1)
    if ref.month == 12:
        ultimo = date(ref.year + 1, 1, 1) - timedelta(days=1)
    else:
        ultimo = date(ref.year, ref.month + 1, 1) - timedelta(days=1)

    # Datas do mês que caem no dia_semana desejado
    datas = []
    dia = primeiro
    while dia <= ultimo:
        if dia.weekday() == dia_semana:
            datas.append(dia)
        dia += timedelta(days=1)

    if not datas:
        return []

    # Verifica quais já existem para não duplicar
    inicio_str = primeiro.isoformat()
    fim_str = ultimo.isoformat()
    existentes = (
        sb.table("aulas")
        .select("data_hora")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .gte("data_hora", inicio_str)
        .lte("data_hora", fim_str + "T23:59:59")
        .execute()
    )
    horas_existentes = {e["data_hora"][:10] for e in (existentes.data or [])}

    novas = []
    for d in datas:
        if d.isoformat() in horas_existentes:
            continue
        dt = datetime.combine(d, horario)
        novas.append({
            "professor_id": professor_id,
            "aluno_id": aluno_id,
            "data_hora": dt.isoformat(),
            "duracao_min": duracao_min,
            "status": "agendada",
        })

    if novas:
        sb.table("aulas").insert(novas).execute()

    return novas


# ---------------------------------------------------------------------------
# FICHA: aulas recentes + próximas
# ---------------------------------------------------------------------------

def ficha_aluno(sb, professor_id, aluno_id):
    """Retorna dados consolidados para a ficha do aluno."""
    aluno = buscar_aluno(sb, professor_id, aluno_id)
    if not aluno:
        return None

    hoje = date.today().isoformat()

    proximas = (
        sb.table("aulas")
        .select("id, data_hora, status, duracao_min")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .eq("status", "agendada")
        .gte("data_hora", hoje)
        .order("data_hora")
        .limit(5)
        .execute()
    ).data or []

    # Histórico: aulas realizadas/canceladas/remarcadas OU agendadas no passado
    historico = (
        sb.table("aulas")
        .select("id, data_hora, status, duracao_min, registros_sessao(id, descricao, enviado_familia, fotos_sessao(id, storage_path, legenda))")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .or_(f"status.neq.agendada,data_hora.lt.{hoje}T00:00:00")
        .order("data_hora", desc=True)
        .limit(20)
        .execute()
    ).data or []

    irmaos = listar_irmaos(sb, professor_id, aluno.get("familia_id"))
    irmaos = [i for i in irmaos if i["id"] != aluno_id]

    try:
        foto_count = (
            sb.table("fotos_sessao")
            .select("id", count="exact")
            .eq("professor_id", professor_id)
            .eq("aluno_id", aluno_id)
            .execute()
        ).count or 0
    except Exception:
        foto_count = 0

    # Resumo clínico (caixinhas da ficha)
    clinico = {}
    try:
        from ..clinico.model import resumo_clinico
        clinico = resumo_clinico(sb, professor_id, aluno_id)
    except Exception:
        pass

    return {
        "aluno": aluno,
        "proximas_aulas": proximas,
        "historico_aulas": historico,
        "irmaos": irmaos,
        "foto_count": foto_count,
        "clinico": clinico,
    }


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _parse_int(val):
    try:
        return int(val) if val not in (None, "", "None") else None
    except (ValueError, TypeError):
        return None


def _parse_float(val):
    try:
        return float(val) if val not in (None, "", "None") else None
    except (ValueError, TypeError):
        return None


def _parse_time(val: str):
    """Converte string 'HH:MM' ou 'HH:MM:SS' para objeto time."""
    if not val:
        return None
    try:
        parts = val.split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return None
