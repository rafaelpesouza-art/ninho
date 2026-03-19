from functools import wraps
from flask import session, redirect, url_for, request


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login_page", next=request.url))
        return f(*args, **kwargs)
    return decorated
