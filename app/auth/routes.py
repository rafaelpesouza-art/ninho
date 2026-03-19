from flask import request, jsonify, session, render_template, redirect, url_for, flash, Response
from . import auth_bp
from ..extensions import get_supabase
from .model import buscar_perfil, salvar_perfil, nome_exibicao, inicial, fazer_upload_logo, buscar_foto_bytes
from ..auth.decorators import login_required


def _carregar_perfil_na_sessao(sb, professor_id: str) -> None:
    """Após login ou edição, grava nome e inicial na sessão."""
    perfil = buscar_perfil(sb, professor_id)
    session["user_nome"]    = nome_exibicao(perfil)
    session["user_inicial"] = inicial(perfil)
    session["perfil_completo"] = bool((perfil.get("nome_completo") or "").strip())
    session["user_cor_primaria"] = perfil.get("cor_primaria") or "#7F77DD"
    if perfil.get("logo_url"):
        session["user_logo_url"] = url_for("auth.servir_logo") + f"?v={perfil.get('atualizado_em', '')}"
    else:
        session["user_logo_url"] = ""


# ---------------------------------------------------------------------------
# LOGIN
# ---------------------------------------------------------------------------

@auth_bp.route("/login", methods=["GET"])
def login_page():
    if session.get("user_id"):
        return redirect(url_for("main.index"))
    return render_template("auth/login.html")


@auth_bp.route("/login", methods=["POST"])
def login():
    if request.content_type and "application/json" in request.content_type:
        data = request.get_json()
    else:
        data = request.form

    email    = data.get("email")
    password = data.get("password")

    if not email or not password:
        flash("Email e senha são obrigatórios.", "danger")
        return redirect(url_for("auth.login_page"))

    try:
        sb = get_supabase()
        response = sb.auth.sign_in_with_password({"email": email, "password": password})
        user = response.user

        session["access_token"] = response.session.access_token
        session["user_id"]      = user.id
        session["user_email"]   = user.email

        sb.postgrest.auth(response.session.access_token)
        _carregar_perfil_na_sessao(sb, user.id)

        if not session.get("perfil_completo"):
            return redirect(url_for("auth.completar_perfil"))

        next_url = request.args.get("next") or url_for("main.dashboard")
        return redirect(next_url)

    except Exception as e:
        flash(f"Credenciais inválidas: {e}", "danger")
        return redirect(url_for("auth.login_page"))


# ---------------------------------------------------------------------------
# LOGOUT
# ---------------------------------------------------------------------------

@auth_bp.route("/logout", methods=["POST"])
def logout():
    try:
        sb = get_supabase()
        sb.auth.sign_out()
    except Exception:
        pass
    session.clear()
    return redirect(url_for("auth.login_page"))


# ---------------------------------------------------------------------------
# CADASTRO
# ---------------------------------------------------------------------------

@auth_bp.route("/cadastro", methods=["GET"])
def cadastro_page():
    if session.get("user_id"):
        return redirect(url_for("main.index"))
    return render_template("auth/cadastro.html")


@auth_bp.route("/cadastro", methods=["POST"])
def cadastro():
    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm  = request.form.get("confirm_password", "")

    if not email or not password:
        flash("Email e senha são obrigatórios.", "danger")
        return redirect(url_for("auth.cadastro_page"))

    if password != confirm:
        flash("As senhas não coincidem.", "danger")
        return redirect(url_for("auth.cadastro_page"))

    if len(password) < 6:
        flash("A senha deve ter pelo menos 6 caracteres.", "danger")
        return redirect(url_for("auth.cadastro_page"))

    try:
        sb = get_supabase()
        response = sb.auth.sign_up({"email": email, "password": password})
        user = response.user

        if user and response.session:
            session["access_token"] = response.session.access_token
            session["user_id"]      = user.id
            session["user_email"]   = user.email
            session["user_nome"]    = "Professor"
            session["user_inicial"] = "P"
            session["perfil_completo"] = False
            flash("Conta criada! Complete seu perfil para continuar.", "success")
            return redirect(url_for("auth.completar_perfil"))
        else:
            flash("Conta criada! Verifique seu email para confirmar.", "success")
            return redirect(url_for("auth.login_page"))

    except Exception as e:
        flash(f"Erro ao criar conta: {e}", "danger")
        return redirect(url_for("auth.cadastro_page"))


# ---------------------------------------------------------------------------
# COMPLETAR PERFIL (pós-cadastro)
# ---------------------------------------------------------------------------

@auth_bp.route("/completar-perfil", methods=["GET"])
@login_required
def completar_perfil():
    return render_template("auth/perfil.html",
                           perfil={},
                           modo="completar")


@auth_bp.route("/completar-perfil", methods=["POST"])
@login_required
def completar_perfil_post():
    professor_id = session["user_id"]
    sb = get_supabase()
    token = session.get("access_token")
    if token:
        try:
            sb.postgrest.auth(token)
        except Exception:
            pass

    nome = request.form.get("nome_completo", "").strip()
    if not nome:
        flash("Nome completo é obrigatório.", "danger")
        return redirect(url_for("auth.completar_perfil"))

    # Upload da logo (se existir)
    file = request.files.get("logo_file")
    novo_logo_path = None
    if file and file.filename:
        try:
            novo_logo_path = fazer_upload_logo(professor_id, file)
        except Exception as e:
            flash(f"Erro no upload da logo: {e}", "warning")

    salvar_perfil(sb, professor_id, request.form, novo_logo_path)
    _carregar_perfil_na_sessao(sb, professor_id)
    flash("Perfil salvo com sucesso!", "success")
    return redirect(url_for("main.dashboard"))


# ---------------------------------------------------------------------------
# EDITAR PERFIL (usuários existentes)
# ---------------------------------------------------------------------------

@auth_bp.route("/perfil", methods=["GET"])
@login_required
def perfil():
    professor_id = session["user_id"]
    sb = get_supabase()
    token = session.get("access_token")
    if token:
        try:
            sb.postgrest.auth(token)
        except Exception:
            pass
    perfil_data = buscar_perfil(sb, professor_id)
    return render_template("auth/perfil.html",
                           perfil=perfil_data,
                           modo="editar")


@auth_bp.route("/perfil", methods=["POST"])
@login_required
def perfil_post():
    professor_id = session["user_id"]
    sb = get_supabase()
    token = session.get("access_token")
    if token:
        try:
            sb.postgrest.auth(token)
        except Exception:
            pass

    nome = request.form.get("nome_completo", "").strip()
    if not nome:
        flash("Nome completo é obrigatório.", "danger")
        return redirect(url_for("auth.perfil"))

    # Upload da logo (se existir)
    file = request.files.get("logo_file")
    novo_logo_path = None
    if file and file.filename:
        try:
            novo_logo_path = fazer_upload_logo(professor_id, file)
        except Exception as e:
            flash(f"Erro no upload da logo: {e}", "warning")

    salvar_perfil(sb, professor_id, request.form, novo_logo_path)
    _carregar_perfil_na_sessao(sb, professor_id)
    flash("Perfil atualizado com sucesso!", "success")
    return redirect(url_for("auth.perfil"))


# ---------------------------------------------------------------------------
# ESQUECI MINHA SENHA
# ---------------------------------------------------------------------------

@auth_bp.route("/esqueci-senha", methods=["GET"])
def esqueci_senha():
    if session.get("user_id"):
        return redirect(url_for("main.dashboard"))
    return render_template("auth/esqueci_senha.html")


@auth_bp.route("/esqueci-senha", methods=["POST"])
def esqueci_senha_post():
    email = request.form.get("email", "").strip()
    if not email:
        flash("Informe seu email.", "danger")
        return redirect(url_for("auth.esqueci_senha"))

    try:
        sb = get_supabase()
        redirect_to = url_for("auth.nova_senha", _external=True)
        sb.auth.reset_password_email(email, {"redirect_to": redirect_to})
    except Exception:
        pass  # não revelar se email existe ou não

    flash("Se esse email estiver cadastrado, você receberá um link de redefinição.", "success")
    return redirect(url_for("auth.esqueci_senha"))


@auth_bp.route("/nova-senha", methods=["GET"])
def nova_senha():
    return render_template("auth/nova_senha.html")


@auth_bp.route("/nova-senha", methods=["POST"])
def nova_senha_post():
    access_token  = request.form.get("access_token", "").strip()
    refresh_token = request.form.get("refresh_token", "").strip()
    nova          = request.form.get("password", "")
    confirma      = request.form.get("confirm_password", "")

    if not access_token or not refresh_token:
        flash("Link inválido ou expirado. Solicite um novo.", "danger")
        return redirect(url_for("auth.esqueci_senha"))

    if len(nova) < 6:
        flash("A nova senha deve ter pelo menos 6 caracteres.", "danger")
        return render_template("auth/nova_senha.html",
                               access_token=access_token,
                               refresh_token=refresh_token)

    if nova != confirma:
        flash("As senhas não coincidem.", "danger")
        return render_template("auth/nova_senha.html",
                               access_token=access_token,
                               refresh_token=refresh_token)

    try:
        sb = get_supabase()
        sb.auth.set_session(access_token, refresh_token)
        sb.auth.update_user({"password": nova})
        flash("Senha alterada com sucesso! Faça login.", "success")
        return redirect(url_for("auth.login_page"))
    except Exception as e:
        flash(f"Não foi possível redefinir a senha: {e}", "danger")
        return render_template("auth/nova_senha.html",
                               access_token=access_token,
                               refresh_token=refresh_token)


# ---------------------------------------------------------------------------
# ME (API)
# ---------------------------------------------------------------------------

@auth_bp.route("/me", methods=["GET"])
def me():
    user_id    = session.get("user_id")
    user_email = session.get("user_email")
    if not user_id:
        return jsonify({"error": "Não autenticado."}), 401
    return jsonify({"user": {"id": user_id, "email": user_email}}), 200


@auth_bp.route("/logo", methods=["GET"])
@login_required
def servir_logo():
    user_id = session["user_id"]
    sb = get_supabase()
    perfil = buscar_perfil(sb, user_id)
    storage_path = perfil.get("logo_url") if perfil else None
    
    if not storage_path:
        return "", 404
        
    try:
        content, content_type = buscar_foto_bytes(storage_path)
    except Exception:
        return "", 404

    return Response(
        content,
        status=200,
        content_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
