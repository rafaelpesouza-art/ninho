"""
Camada de dados para o módulo de Agenda.
Gerencia aulas (CRUD, cancelamento, reagendamento, geração em lote) e feriados.
"""
from datetime import date, datetime, timedelta
import calendar as _cal


MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

STATUS_LABELS = {
    "agendada":              ("Agendada",            "blue"),
    "realizada":             ("Realizada",           "green"),
    "cancelada":             ("Cancelada",           "red"),
    "cancelada_aluno":       ("Cancelada (aluno)",   "orange"),
    "cancelada_professor":   ("Cancelada (prof.)",   "red"),
    "remarcada":             ("Remarcada",           "yellow"),
}


# ---------------------------------------------------------------------------
# QUERIES
# ---------------------------------------------------------------------------

def listar_aulas_mes(sb, professor_id: str, ano: int, mes: int) -> list:
    primeiro = date(ano, mes, 1)
    _, ultimo_dia = _cal.monthrange(ano, mes)
    ultimo = date(ano, mes, ultimo_dia)
    res = (
        sb.table("aulas")
        .select("id, data_hora, duracao_min, status, motivo_cancelamento, aula_origem_id, alunos(id, nome)")
        .eq("professor_id", professor_id)
        .gte("data_hora", primeiro.isoformat() + "T00:00:00")
        .lte("data_hora", ultimo.isoformat() + "T23:59:59")
        .order("data_hora")
        .execute()
    )
    return res.data or []


def listar_aulas_dia(sb, professor_id: str, data: date) -> list:
    res = (
        sb.table("aulas")
        .select("id, data_hora, duracao_min, status, motivo_cancelamento, observacoes, lembrete_enviado, alunos(id, nome, telefone)")
        .eq("professor_id", professor_id)
        .gte("data_hora", data.isoformat() + "T00:00:00")
        .lte("data_hora", data.isoformat() + "T23:59:59")
        .order("data_hora")
        .execute()
    )
    return res.data or []


def listar_aulas_semana(sb, professor_id: str, inicio: date) -> list:
    fim = inicio + timedelta(days=6)
    res = (
        sb.table("aulas")
        .select("id, data_hora, duracao_min, status, alunos(id, nome)")
        .eq("professor_id", professor_id)
        .gte("data_hora", inicio.isoformat() + "T00:00:00")
        .lte("data_hora", fim.isoformat() + "T23:59:59")
        .order("data_hora")
        .execute()
    )
    return res.data or []


def listar_aulas_por_aluno(sb, professor_id: str, aluno_id: str,
                           inicio: date, fim: date) -> list:
    res = (
        sb.table("aulas")
        .select("id, data_hora, duracao_min, status, motivo_cancelamento")
        .eq("professor_id", professor_id)
        .eq("aluno_id", aluno_id)
        .gte("data_hora", inicio.isoformat() + "T00:00:00")
        .lte("data_hora", fim.isoformat() + "T23:59:59")
        .order("data_hora")
        .execute()
    )
    return res.data or []


def buscar_aula(sb, professor_id: str, aula_id: str) -> dict | None:
    try:
        res = (
            sb.table("aulas")
            .select("*, alunos(id, nome, telefone, dia_semana_fixo, horario_fixo, duracao_padrao_min)")
            .eq("professor_id", professor_id)
            .eq("id", aula_id)
            .maybe_single()
            .execute()
        )
        return res.data
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CRUD AULAS
# ---------------------------------------------------------------------------

def criar_aula_avulsa(sb, professor_id: str, dados: dict) -> dict:
    aluno_id = dados.get("aluno_id", "").strip()
    data_hora_str = (dados.get("data_hora") or "").strip()

    if not aluno_id:
        raise ValueError("Selecione um aluno.")
    if not data_hora_str:
        raise ValueError("Informe a data e horário.")

    # Normaliza para ISO 8601 (HTML datetime-local envia 'YYYY-MM-DDTHH:MM')
    if "T" not in data_hora_str:
        data_hora_str = data_hora_str.replace(" ", "T")

    payload = {
        "professor_id": professor_id,
        "aluno_id":     aluno_id,
        "data_hora":    data_hora_str,
        "duracao_min":  int(dados.get("duracao_min") or 60),
        "status":       "agendada",
        "observacoes":  dados.get("observacoes") or None,
    }
    res = sb.table("aulas").insert(payload).execute()
    return res.data[0]


def cancelar_aula(sb, professor_id: str, aula_id: str,
                  motivo: str = None, tipo: str = "cancelada_professor") -> dict | None:
    payload = {
        "status":               tipo,
        "motivo_cancelamento":  motivo or None,
    }
    res = (
        sb.table("aulas")
        .update(payload)
        .eq("professor_id", professor_id)
        .eq("id", aula_id)
        .execute()
    )
    return res.data[0] if res.data else None


def reagendar_aula(sb, professor_id: str, aula_id: str,
                   nova_data_hora: str, motivo: str = None) -> dict:
    original = buscar_aula(sb, professor_id, aula_id)
    if not original:
        raise ValueError("Aula não encontrada.")

    cancelar_aula(sb, professor_id, aula_id,
                  motivo=motivo or "Remarcada",
                  tipo="cancelada")

    if "T" not in nova_data_hora:
        nova_data_hora = nova_data_hora.replace(" ", "T")

    payload = {
        "professor_id":  professor_id,
        "aluno_id":      original["aluno_id"],
        "data_hora":     nova_data_hora,
        "duracao_min":   original["duracao_min"],
        "status":        "agendada",
        "aula_origem_id": aula_id,
        "observacoes":   f"Remarcada de {original['data_hora'][:10]}",
        "plano_id":      original.get("plano_id"),
    }
    res = sb.table("aulas").insert(payload).execute()
    return res.data[0]


def marcar_realizada(sb, professor_id: str, aula_id: str) -> dict | None:
    res = (
        sb.table("aulas")
        .update({"status": "realizada"})
        .eq("professor_id", professor_id)
        .eq("id", aula_id)
        .execute()
    )
    return res.data[0] if res.data else None


def deletar_aula(sb, professor_id: str, aula_id: str) -> list:
    res = (
        sb.table("aulas")
        .delete()
        .eq("professor_id", professor_id)
        .eq("id", aula_id)
        .execute()
    )
    return res.data or []


# ---------------------------------------------------------------------------
# FERIADOS
# ---------------------------------------------------------------------------

def listar_feriados(sb, professor_id: str, ano: int = None) -> list:
    q = (
        sb.table("feriados")
        .select("*")
        .eq("professor_id", professor_id)
        .order("data")
    )
    if ano:
        q = q.gte("data", f"{ano}-01-01").lte("data", f"{ano}-12-31")
    return (q.execute()).data or []


def criar_feriado(sb, professor_id: str, dados: dict) -> dict:
    if not dados.get("data") or not dados.get("nome"):
        raise ValueError("Data e nome são obrigatórios.")
    payload = {
        "professor_id": professor_id,
        "data":         dados["data"],
        "nome":         dados["nome"].strip(),
        "recorrente":   dados.get("recorrente") == "on",
    }
    res = sb.table("feriados").insert(payload).execute()
    return res.data[0]


def deletar_feriado(sb, professor_id: str, feriado_id: str) -> list:
    res = (
        sb.table("feriados")
        .delete()
        .eq("professor_id", professor_id)
        .eq("id", feriado_id)
        .execute()
    )
    return res.data or []


def cancelar_aulas_em_feriado(sb, professor_id: str, data_str: str) -> list:
    """Cancela todas as aulas 'agendada' na data informada."""
    res = (
        sb.table("aulas")
        .update({"status": "cancelada", "motivo_cancelamento": "Feriado"})
        .eq("professor_id", professor_id)
        .eq("status", "agendada")
        .gte("data_hora", data_str + "T00:00:00")
        .lte("data_hora", data_str + "T23:59:59")
        .execute()
    )
    return res.data or []


# ---------------------------------------------------------------------------
# GERAÇÃO EM LOTE
# ---------------------------------------------------------------------------

def gerar_aulas_mes_todos_alunos(sb, professor_id: str, ano: int, mes: int) -> dict:
    """Gera aulas recorrentes para todos os alunos ativos com dia/horário fixo."""
    from ..alunos.model import gerar_aulas_mes, _parse_time

    todos = (
        sb.table("alunos")
        .select("id, nome, dia_semana_fixo, horario_fixo, duracao_padrao_min")
        .eq("professor_id", professor_id)
        .eq("ativo", True)
        .execute()
    ).data or []

    alunos_fixos = [
        a for a in todos
        if a.get("dia_semana_fixo") is not None and a.get("horario_fixo")
    ]

    mes_ref = date(ano, mes, 1)
    total, erros = 0, []

    for aluno in alunos_fixos:
        try:
            horario = _parse_time(aluno["horario_fixo"])
            if horario is None:
                continue
            novas = gerar_aulas_mes(
                sb, professor_id, aluno["id"],
                aluno["dia_semana_fixo"], horario,
                aluno.get("duracao_padrao_min") or 60,
                mes=mes_ref,
            )
            total += len(novas)
        except Exception as ex:
            erros.append({"aluno": aluno.get("nome"), "erro": str(ex)})

    return {"geradas": total, "erros": erros}


# ---------------------------------------------------------------------------
# HELPER: monta estrutura do calendário
# ---------------------------------------------------------------------------

def montar_calendario(aulas: list, ano: int, mes: int) -> dict:
    """
    Agrupa aulas por dia e retorna as semanas do mês.
    Retorna:
        por_dia  : {date_str: [aulas]}
        semanas  : lista de listas [[int, ...], ...] — 0 = sem dia
    """
    por_dia: dict = {}
    for a in aulas:
        dia_str = a["data_hora"][:10]
        por_dia.setdefault(dia_str, []).append(a)

    _cal.setfirstweekday(0)          # semana começa na segunda
    semanas = _cal.monthcalendar(ano, mes)

    return {"por_dia": por_dia, "semanas": semanas}


def _navegar_mes(ano: int, mes: int):
    """Retorna (ano_ant, mes_ant) e (ano_prox, mes_prox)."""
    if mes == 1:
        anterior = (ano - 1, 12)
    else:
        anterior = (ano, mes - 1)

    if mes == 12:
        proximo = (ano + 1, 1)
    else:
        proximo = (ano, mes + 1)

    return anterior, proximo
