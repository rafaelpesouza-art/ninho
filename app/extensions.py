from supabase import create_client, Client

supabase: Client = None


def init_supabase(app):
    global supabase
    url = app.config["SUPABASE_URL"]
    key = app.config["SUPABASE_KEY"]
    supabase = create_client(url, key)
    app.extensions["supabase"] = supabase


def get_supabase() -> Client:
    return supabase
