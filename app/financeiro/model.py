"""Camada de dados para o módulo financeiro."""
from datetime import date, datetime, timedelta, timezone
import calendar as _cal

MESES_PT = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
MESES_PT_ABREV = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                  "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
DIAS_PT = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
BRT = timezone(timedelta(hours=-3))


# ---------------------------------------------------------------------------
# CONFIGURAÇÕES
# ---------------------------------------------------------------------------

def buscar_config(sb, professor_id: str) -> dict:
    try:
        res = (
            sb.table("configuracoes_financeiras")
            .select("*")
            .eq("professor_id", professor_id)
            .maybe_single()
            .execute()
        )
        return res.data or {}
    except Exception:
        return {}


def salvar_config(sb, professor_id: str, dados: dict) -> None:
    dia_venc = _parse_int(dados.get("dia_vencimento")) or 10
    dia_venc = max(1, min(28, dia_venc))
    payload = {
        "professor_id":  professor_id,
        "nome_recebedor": dados.get("nome_recebedor") or None,
        "chave_pix":      dados.get("chave_pix") or None,
        "dia_vencimento": dia_venc,
        "observacoes":    dados.get("observacoes") or None,
    }
    existing = buscar_config(sb, professor_id)
    if existing:
        sb.table("configuracoes_financeiras").update(payload).eq("professor_id", professor_id).execute()
    else:
        sb.table("configuracoes_financeiras").insert(payload).execute()


# ---------------------------------------------------------------------------
# FECHAMENTO MENSAL
# ---------------------------------------------------------------------------

def calcular_fechamento(sb, professor_id: str, mes: int, ano: int) -> list:
    """
    Agrupa aulas realizadas no mês por família/aluno.
    Retorna lista de grupos com total e referência a fatura existente.
    """
    inicio = date(ano, mes, 1).isoformat()
    fim = date(ano + 1, 1, 1).isoformat() if mes == 12 else date(ano, mes + 1, 1).isoformat()

    res = (
        sb.table("aulas")
        .select("id, data_hora, duracao_min, aluno_id, alunos(id, nome, valor_aula, familia_id, responsavel)")
        .eq("professor_id", professor_id)
        .eq("status", "realizada")
        .gte("data_hora", inicio)
        .lt("data_hora", fim)
        .order("data_hora")
        .execute()
    )
    aulas = res.data or []

    grupos: dict = {}
    for aula in aulas:
        aluno = aula.get("alunos") or {}
        familia_id = aluno.get("familia_id")
        key = familia_id or aula["aluno_id"]

        if key not in grupos:
            grupos[key] = {
                "key":            key,
                "familia_id":     familia_id,
                "nomes":          [],
                "aluno_ids":      [],
                "responsavel":    aluno.get("responsavel"),
                "aulas":          [],
                "total":          0.0,
                "sem_valor":      False,
                "fatura_existente": None,
            }

        if aula["aluno_id"] not in grupos[key]["aluno_ids"]:
            grupos[key]["aluno_ids"].append(aula["aluno_id"])
        nome = aluno.get("nome")
        if nome and nome not in grupos[key]["nomes"]:
            grupos[key]["nomes"].append(nome)

        valor = float(aluno.get("valor_aula") or 0)
        if not aluno.get("valor_aula"):
            grupos[key]["sem_valor"] = True
        grupos[key]["aulas"].append(aula)
        grupos[key]["total"] = round(grupos[key]["total"] + valor, 2)

    # Busca faturas já geradas para o mês
    mes_ref = date(ano, mes, 1).isoformat()
    try:
        fat_res = (
            sb.table("faturas")
            .select("id, aluno_id, familia_id, status, valor")
            .eq("professor_id", professor_id)
            .eq("mes_referencia", mes_ref)
            .execute()
        )
        fat_data = fat_res.data or []
    except Exception:
        fat_data = []

    fat_por_aluno  = {f["aluno_id"]: f for f in fat_data}
    fat_por_familia = {f["familia_id"]: f for f in fat_data if f.get("familia_id")}

    for key, grupo in grupos.items():
        fatura = None
        if grupo["familia_id"] and grupo["familia_id"] in fat_por_familia:
            fatura = fat_por_familia[grupo["familia_id"]]
        else:
            for aid in grupo["aluno_ids"]:
                if aid in fat_por_aluno:
                    fatura = fat_por_aluno[aid]
                    break
        grupo["fatura_existente"] = fatura

    return sorted(grupos.values(), key=lambda g: g["nomes"][0] if g["nomes"] else "")


def gerar_faturas(sb, professor_id: str, mes: int, ano: int) -> tuple:
    """Gera faturas pendentes para o mês. Retorna (n_criadas, n_ignoradas)."""
    config  = buscar_config(sb, professor_id)
    dia_venc = max(1, min(28, int(config.get("dia_vencimento") or 10)))
    grupos  = calcular_fechamento(sb, professor_id, mes, ano)

    if mes == 12:
        max_day = _cal.monthrange(ano + 1, 1)[1]
        data_venc = date(ano + 1, 1, min(dia_venc, max_day))
    else:
        max_day = _cal.monthrange(ano, mes + 1)[1]
        data_venc = date(ano, mes + 1, min(dia_venc, max_day))

    mes_ref = date(ano, mes, 1).isoformat()
    criadas, ignoradas = 0, 0

    for grupo in grupos:
        if grupo["fatura_existente"] or not grupo["aulas"] or grupo["total"] <= 0:
            ignoradas += 1
            continue

        nomes_str = " & ".join(grupo["nomes"])
        n = len(grupo["aulas"])

        payload = {
            "professor_id":    professor_id,
            "aluno_id":        grupo["aluno_ids"][0],
            "familia_id":      grupo["familia_id"],
            "mes_referencia":  mes_ref,
            "descricao":       f"Aulas de {MESES_PT[mes]}/{ano} — {nomes_str} ({n} {'aula' if n == 1 else 'aulas'})",
            "valor":           grupo["total"],
            "valor_pago":      0,
            "data_emissao":    date.today().isoformat(),
            "data_vencimento": data_venc.isoformat(),
            "status":          "pendente",
        }
        try:
            sb.table("faturas").insert(payload).execute()
            criadas += 1
        except Exception as e:
            raise ValueError(f"Erro ao criar fatura para {nomes_str}: {e}")

    return criadas, ignoradas


def gerar_fatura_grupo(sb, professor_id: str, mes: int, ano: int,
                       aluno_id: str, familia_id: str | None) -> dict:
    """Gera a fatura de um único grupo (família ou aluno individual)."""
    grupos = calcular_fechamento(sb, professor_id, mes, ano)

    # Encontra o grupo correspondente
    grupo = None
    for g in grupos:
        if familia_id and g.get("familia_id") == familia_id:
            grupo = g
            break
        if not familia_id and aluno_id in g.get("aluno_ids", []):
            grupo = g
            break

    if not grupo:
        raise ValueError("Grupo não encontrado no fechamento do mês.")
    if grupo["fatura_existente"]:
        raise ValueError("Já existe uma fatura para este grupo neste mês.")
    if not grupo["aulas"] or grupo["total"] <= 0:
        raise ValueError("Grupo sem aulas ou sem valor definido.")

    config   = buscar_config(sb, professor_id)
    dia_venc = max(1, min(28, int(config.get("dia_vencimento") or 10)))

    if mes == 12:
        data_venc = date(ano + 1, 1, min(dia_venc, _cal.monthrange(ano + 1, 1)[1]))
    else:
        data_venc = date(ano, mes + 1, min(dia_venc, _cal.monthrange(ano, mes + 1)[1]))

    nomes_str = " & ".join(grupo["nomes"])
    n         = len(grupo["aulas"])
    mes_ref   = date(ano, mes, 1).isoformat()

    payload = {
        "professor_id":    professor_id,
        "aluno_id":        grupo["aluno_ids"][0],
        "familia_id":      grupo["familia_id"],
        "mes_referencia":  mes_ref,
        "descricao":       f"Aulas de {MESES_PT[mes]}/{ano} — {nomes_str} ({n} {'aula' if n == 1 else 'aulas'})",
        "valor":           grupo["total"],
        "valor_pago":      0,
        "data_emissao":    date.today().isoformat(),
        "data_vencimento": data_venc.isoformat(),
        "status":          "pendente",
    }
    res = sb.table("faturas").insert(payload).execute()
    return (res.data or [{}])[0]


# ---------------------------------------------------------------------------
# FATURAS
# ---------------------------------------------------------------------------

def listar_faturas(sb, professor_id: str, status: str = None,
                   mes: int = None, ano: int = None, limit: int = 100) -> list:
    query = (
        sb.table("faturas")
        .select("*, alunos(id, nome, telefone, responsavel)")
        .eq("professor_id", professor_id)
    )
    if status and status not in ("todas", ""):
        query = query.eq("status", status)
    if mes and ano:
        query = query.eq("mes_referencia", date(ano, mes, 1).isoformat())

    query = query.order("data_vencimento", desc=True).limit(limit)
    res = query.execute()
    faturas = _enriquecer(res.data or [])
    _enriquecer_nomes_familia(sb, professor_id, faturas)
    return faturas


def buscar_fatura(sb, professor_id: str, fatura_id: str) -> dict | None:
    res = (
        sb.table("faturas")
        .select("*, alunos(id, nome, telefone, responsavel, familia_id)")
        .eq("professor_id", professor_id)
        .eq("id", fatura_id)
        .maybe_single()
        .execute()
    )
    if not res.data:
        return None
    faturas = _enriquecer([res.data])
    _enriquecer_nomes_familia(sb, professor_id, faturas)
    return faturas[0]


def editar_fatura(sb, professor_id: str, fatura_id: str, dados: dict) -> None:
    """Edita campos da fatura livremente: valor, status, vencimento, descrição, obs."""
    status = dados.get("status") or "pendente"
    if status not in ("pendente", "paga", "parcial", "vencida", "cancelada"):
        raise ValueError("Status inválido.")

    try:
        valor = round(float(dados.get("valor") or 0), 2)
    except (TypeError, ValueError):
        raise ValueError("Valor inválido.")
    if valor <= 0:
        raise ValueError("Valor deve ser maior que zero.")

    try:
        valor_pago = round(float(dados.get("valor_pago") or 0), 2)
    except (TypeError, ValueError):
        valor_pago = 0.0

    data_venc = dados.get("data_vencimento") or ""
    if not data_venc:
        raise ValueError("Data de vencimento obrigatória.")

    # Converte dd/mm/aaaa → aaaa-mm-dd se necessário
    if len(data_venc) == 10 and data_venc[2] == "/":
        d, m, a = data_venc.split("/")
        data_venc = f"{a}-{m}-{d}"

    payload = {
        "valor":            valor,
        "valor_pago":       valor_pago,
        "status":           status,
        "data_vencimento":  data_venc,
        "descricao":        dados.get("descricao") or "",
        "observacoes":      dados.get("observacoes") or None,
        "metodo_pagamento": dados.get("metodo_pagamento") or None,
        "data_pagamento":   dados.get("data_pagamento") or None,
    }

    try:
        sb.table("faturas").update(payload)\
          .eq("professor_id", professor_id).eq("id", fatura_id).execute()
    except Exception as e:
        raise ValueError(f"Erro ao salvar: {e}")


def registrar_pagamento(sb, professor_id: str, fatura_id: str, dados: dict) -> None:
    fatura = buscar_fatura(sb, professor_id, fatura_id)
    if not fatura:
        raise ValueError("Fatura não encontrada.")

    novo_pagamento = float(dados.get("valor_pago") or 0)
    valor_total    = float(fatura["valor"])
    ja_pago        = float(fatura.get("valor_pago") or 0)
    metodo = dados.get("metodo_pagamento") or None
    obs    = dados.get("observacoes") or None

    if novo_pagamento <= 0:
        raise ValueError("Informe um valor pago maior que zero.")

    valor_pago_acumulado = round(ja_pago + novo_pagamento, 2)

    if valor_pago_acumulado >= valor_total:
        status   = "paga"
        data_pag = date.today().isoformat()
    else:
        status   = "parcial"
        data_pag = None

    payload = {
        "valor_pago":       valor_pago_acumulado,
        "status":           status,
        "metodo_pagamento": metodo,
        "data_pagamento":   data_pag,
        "observacoes":      obs,
    }
    try:
        sb.table("faturas").update(payload).eq("professor_id", professor_id).eq("id", fatura_id).execute()
    except Exception as e:
        # Fallback if 'parcial' enum value does not exist yet in DB
        if "parcial" in str(e).lower() or "invalid" in str(e).lower():
            payload["status"] = "pendente"
            payload["observacoes"] = f"[Parcial R$ {valor_pago_acumulado:.2f}] " + (obs or "")
            sb.table("faturas").update(payload).eq("professor_id", professor_id).eq("id", fatura_id).execute()
        else:
            raise


def cancelar_fatura(sb, professor_id: str, fatura_id: str) -> None:
    sb.table("faturas").update({"status": "cancelada"}).eq(
        "professor_id", professor_id).eq("id", fatura_id).execute()


def atualizar_vencidas(sb, professor_id: str) -> None:
    """Marca como 'vencida' faturas pendentes/parciais com data de vencimento passada."""
    hoje = date.today().isoformat()
    try:
        sb.table("faturas").update({"status": "vencida"}).eq(
            "professor_id", professor_id
        ).in_("status", ["pendente", "parcial"]).lt("data_vencimento", hoje).execute()
    except Exception:
        pass


def listar_inadimplentes(sb, professor_id: str) -> list:
    """Faturas pendentes/parciais/vencidas com data de vencimento passada."""
    hoje = date.today().isoformat()
    res = (
        sb.table("faturas")
        .select("*, alunos(id, nome, telefone, responsavel)")
        .eq("professor_id", professor_id)
        .in_("status", ["pendente", "parcial", "vencida"])
        .lt("data_vencimento", hoje)
        .order("data_vencimento")
        .execute()
    )
    return _enriquecer(res.data or [])


def resumo_financeiro(sb, professor_id: str, mes: int, ano: int) -> dict:
    """KPIs para o dashboard."""
    mes_ref = date(ano, mes, 1).isoformat()
    hoje    = date.today().isoformat()
    em7dias = (date.today() + timedelta(days=7)).isoformat()
    try:
        r_pago = (sb.table("faturas").select("valor, valor_pago")
                  .eq("professor_id", professor_id).eq("mes_referencia", mes_ref)
                  .in_("status", ["paga", "parcial"]).execute())
        receita = sum(float(f.get("valor_pago") or f.get("valor") or 0) for f in (r_pago.data or []))

        r_pend = (sb.table("faturas").select("valor")
                  .eq("professor_id", professor_id).eq("mes_referencia", mes_ref)
                  .in_("status", ["pendente", "parcial"]).execute())
        pendente = sum(float(f["valor"]) for f in (r_pend.data or []))

        r_inad = (sb.table("faturas").select("id", count="exact")
                  .eq("professor_id", professor_id)
                  .in_("status", ["pendente", "parcial", "vencida"])
                  .lt("data_vencimento", hoje).execute())
        inadimplente = r_inad.count or 0

        r_venc = (sb.table("faturas").select("id", count="exact")
                  .eq("professor_id", professor_id).in_("status", ["pendente"])
                  .gte("data_vencimento", hoje).lte("data_vencimento", em7dias).execute())
        a_vencer = r_venc.count or 0

        return {"receita": receita, "pendente": pendente,
                "inadimplente": inadimplente, "a_vencer": a_vencer}
    except Exception:
        return {"receita": 0, "pendente": 0, "inadimplente": 0, "a_vencer": 0}


def buscar_aulas_fatura(sb, professor_id: str, fatura: dict) -> list:
    """Retorna aulas realizadas no mês da fatura (para exibição no detalhe)."""
    mes_ref = fatura.get("mes_referencia")
    if not mes_ref:
        return []
    mes_dt = date.fromisoformat(mes_ref)
    fim    = date(mes_dt.year + 1, 1, 1).isoformat() if mes_dt.month == 12 \
             else date(mes_dt.year, mes_dt.month + 1, 1).isoformat()

    fam_id = fatura.get("familia_id")  # só usa o familia_id da própria fatura

    if fam_id:
        al_res    = (sb.table("alunos").select("id").eq("professor_id", professor_id)
                     .eq("familia_id", fam_id).execute())
        aluno_ids = [a["id"] for a in (al_res.data or [])]
    else:
        aluno_ids = [fatura["aluno_id"]]

    all_aulas = []
    for aid in aluno_ids:
        res = (
            sb.table("aulas")
            .select("id, data_hora, duracao_min, alunos(id, nome, valor_aula)")
            .eq("professor_id", professor_id)
            .eq("aluno_id", aid)
            .eq("status", "realizada")
            .gte("data_hora", mes_ref)
            .lt("data_hora", fim)
            .order("data_hora")
            .execute()
        )
        all_aulas.extend(res.data or [])

    all_aulas.sort(key=lambda a: a["data_hora"])
    return all_aulas


# ---------------------------------------------------------------------------
# WHATSAPP — Produção do Mês
# ---------------------------------------------------------------------------

def gerar_texto_whatsapp(sb, professor_id: str, fatura: dict) -> str:
    """Gera texto carinhoso da 'Produção do Mês' para WhatsApp."""
    config = buscar_config(sb, professor_id)
    aluno  = fatura.get("alunos") or {}

    mes_ref = fatura.get("mes_referencia") or ""
    if not mes_ref:
        return ""
    mes_dt   = date.fromisoformat(mes_ref)
    mes_nome = MESES_PT[mes_dt.month]
    fim      = date(mes_dt.year + 1, 1, 1).isoformat() if mes_dt.month == 12 \
               else date(mes_dt.year, mes_dt.month + 1, 1).isoformat()

    fam_id = fatura.get("familia_id")  # só usa o familia_id da própria fatura
    if fam_id:
        al_res    = (sb.table("alunos").select("id, nome").eq("professor_id", professor_id)
                     .eq("familia_id", fam_id).order("nome").execute())
        aluno_ids = [(a["id"], a["nome"]) for a in (al_res.data or [])]
    else:
        aluno_ids = [(fatura["aluno_id"], aluno.get("nome", ""))]

    # Busca aulas por aluno
    aulas_por_aluno: dict = {}
    for aid, anome in aluno_ids:
        res = (
            sb.table("aulas").select("data_hora")
            .eq("professor_id", professor_id).eq("aluno_id", aid)
            .eq("status", "realizada")
            .gte("data_hora", mes_ref).lt("data_hora", fim)
            .order("data_hora").execute()
        )
        aulas_por_aluno[anome] = res.data or []

    nome_recebedor = config.get("nome_recebedor") or "Professora"
    chave_pix      = config.get("chave_pix") or ""
    obs_extra      = config.get("observacoes") or ""
    valor_fmt      = fmt_valor(fatura["valor"])

    responsavel = aluno.get("responsavel") or ""
    saudacao    = f"Oi, {responsavel.split()[0]}! 🌸" if responsavel else "Olá! 🌸"

    linhas = [saudacao, "", f"Aqui vai a *Produção de {mes_nome}* 📚✨", ""]

    if len(aluno_ids) == 1:
        _, anome = aluno_ids[0]
        for a in aulas_por_aluno.get(anome, []):
            dt = _parse_dt(a["data_hora"])
            if dt:
                linhas.append(f"• {dt.day:02d}/{dt.month:02d} ({DIAS_PT[dt.weekday()]})")
    else:
        for aid, anome in aluno_ids:
            aulas = aulas_por_aluno.get(anome, [])
            if not aulas:
                continue
            linhas.append(f"*{anome}:*")
            for a in aulas:
                dt = _parse_dt(a["data_hora"])
                if dt:
                    linhas.append(f"  • {dt.day:02d}/{dt.month:02d} ({DIAS_PT[dt.weekday()]})")

    linhas += ["", f"*Total: {valor_fmt}* 💜", ""]

    if chave_pix:
        linhas += [f"Pagamento via Pix 💳", f"`{chave_pix}`", f"Recebedor: {nome_recebedor}"]
    else:
        linhas += [f"Recebedor: {nome_recebedor}"]

    if obs_extra:
        linhas += ["", obs_extra]

    linhas += ["", "Qualquer dúvida é só falar! Um beijo 🥰"]
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# HELPERS INTERNOS
# ---------------------------------------------------------------------------

def _enriquecer(faturas: list) -> list:
    hoje = date.today().isoformat()
    for f in faturas:
        venc       = f.get("data_vencimento") or ""
        valor      = float(f.get("valor") or 0)
        valor_pago = float(f.get("valor_pago") or 0)
        f["valor_aberto"] = round(valor - valor_pago, 2)
        f["atrasada"]     = venc < hoje and f.get("status") in ("pendente", "parcial", "vencida")

        if f["atrasada"] and f.get("status") in ("pendente", "parcial"):
            f["status"] = "vencida"

        mes_ref = f.get("mes_referencia")
        if mes_ref:
            try:
                d = date.fromisoformat(mes_ref)
                f["mes_label"] = f"{MESES_PT[d.month]}/{d.year}"
            except Exception:
                f["mes_label"] = mes_ref or ""
        else:
            f["mes_label"] = ""
    return faturas


def _enriquecer_nomes_familia(sb, professor_id: str, faturas: list) -> None:
    """
    Preenche fatura['nome_display'] com todos os nomes da família para faturas
    com familia_id, ou com o nome individual para faturas de aluno único.
    Faz uma única query em batch para todas as famílias encontradas.
    """
    familia_ids = list({f["familia_id"] for f in faturas if f.get("familia_id")})

    nomes_por_familia: dict = {}
    if familia_ids:
        try:
            res = (
                sb.table("alunos")
                .select("nome, familia_id")
                .eq("professor_id", professor_id)
                .in_("familia_id", familia_ids)
                .order("nome")
                .execute()
            )
            for a in (res.data or []):
                fid = a["familia_id"]
                nomes_por_familia.setdefault(fid, [])
                if a["nome"] not in nomes_por_familia[fid]:
                    nomes_por_familia[fid].append(a["nome"])
        except Exception:
            pass

    for f in faturas:
        fid = f.get("familia_id")
        if fid and fid in nomes_por_familia:
            f["nome_display"] = " & ".join(nomes_por_familia[fid])
        else:
            aluno = f.get("alunos") or {}
            f["nome_display"] = aluno.get("nome") or "Aluno"


def _parse_dt(dt_str: str):
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(BRT)
        return dt
    except Exception:
        return None


def _parse_int(val):
    try:
        return int(val) if val not in (None, "", "None") else None
    except (ValueError, TypeError):
        return None


def fmt_valor(valor) -> str:
    try:
        v = float(valor)
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"
