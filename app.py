import os
from dotenv import load_dotenv
from flask import Flask, request, session, redirect, url_for, render_template_string, jsonify, flash
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# DB DAL
try:
    from src.db.users_dal import upsert_user, get_user
    from src.db.template_dal import (
        create_or_replace_presentation,
        list_presentations_for_user,
        delete_presentation,
    )
except Exception as e:
    upsert_user = None
    get_user = None
    create_or_replace_presentation = None
    list_presentations_for_user = None
    delete_presentation = None
    print("[warn] users_dal not available:", e)


# ---- Flask app setup ----
load_dotenv()  # load .env into environment for local dev
app = Flask(__name__)
# NOTE: For development only. In production, set a strong secret via FLASK_SECRET_KEY env var.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")


# ---- OAuth configuration ----
# Default to the checked-in example file name if present; allow override via env var.
DEFAULT_CLIENT_SECRETS = (
    "client_secret_1080418670704-k0uh9qj9sstfp0lnbm7huscs63f6l2rm.apps.googleusercontent.com.json"
)
CLIENT_SECRETS_FILE = os.environ.get(
    "GOOGLE_CLIENT_SECRETS_FILE",
    DEFAULT_CLIENT_SECRETS if os.path.exists(DEFAULT_CLIENT_SECRETS) else "client_secret.json",
)

# Minimal scopes for identity + profile data
# Scopes per app requirements (avoid OIDC openid to prevent conflicts)
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    # Required to read Google Slides presentations via Slides API
    "https://www.googleapis.com/auth/presentations.readonly",
]

# Redirect URI policy: default to localhost callback; allow explicit override via env.
REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:5000/callback")


def credentials_to_dict(creds: Credentials) -> dict:
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    # Persist id_token so we can resolve user identity without another API call
    "id_token": getattr(creds, "id_token", None),
    }


def build_flow(redirect_uri: str | None = None):
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
    # Prefer provided redirect_uri, then env override, else compute dynamically at call sites.
    if redirect_uri:
        flow.redirect_uri = redirect_uri
    elif REDIRECT_URI:
        flow.redirect_uri = REDIRECT_URI
    return flow


def _rebuild_creds():
    """Rebuild Google Credentials from session; return None if missing."""
    data = session.get("credentials")
    if not data:
        return None
    try:
        return Credentials(**data)
    except Exception:
        return None


def _ensure_user_in_db(creds: Credentials) -> str | None:
    """Ensure the logged-in Google user exists in Mongo. Returns user_id or None.

    Tries id_token to get sub/email; falls back to People API.
    """
    global upsert_user
    if upsert_user is None:
        return None

    # Try to parse id_token if present for stable subject id
    user_id = email = name = photo_url = None
    try:
        token = creds.id_token
        if token:
            info = id_token.verify_oauth2_token(token, google_requests.Request())
            user_id = info.get("sub")
            email = info.get("email")
            name = info.get("name")
            photo_url = info.get("picture")
    except Exception:
        pass

    if not user_id or not email:
        # Fallback: People API
        people_service = build("people", "v1", credentials=creds)
        profile = (
            people_service
            .people()
            .get(resourceName="people/me", personFields="names,emailAddresses,photos")
            .execute()
        )
        def get_first(values, key):
            try:
                return values[0].get(key)
            except Exception:
                return None
        name = name or (get_first(profile.get("names", []), "displayName") or "")
        email = email or (get_first(profile.get("emailAddresses", []), "value") or "")
        photo_url = photo_url or (get_first(profile.get("photos", []), "url") or "")
        # Use email as id fallback if sub not available (rare for proper OIDC)
        user_id = user_id or email

    if not user_id or not email:
        return None

    doc = upsert_user({
        "id": user_id,
        "email": email,
        "name": name,
        "photo_url": photo_url,
        "provider": "google",
    })
    # Be defensive if DAL returns None
    session["user_id"] = (doc.get("_id") if isinstance(doc, dict) else user_id)
    return session["user_id"]


def _current_user_doc():
    """Return the current user document from DB if available."""
    global get_user
    uid = session.get("user_id")
    if uid and get_user:
        try:
            return get_user(uid)
        except Exception:
            return None
    return None


# ---- Routes ----
@app.route("/")
def index():
    logged_in = "credentials" in session
    if not logged_in:
        html = """
        <h2>Welcome</h2>
        <p>You are not logged in.</p>
        <a href="{{ url_for('login') }}">Login with Google</a>
        """
        return render_template_string(html)
    else:
        html = """
        <h2>Welcome back</h2>
        <p>You are logged in.</p>
        <p>
            <a href="{{ url_for('dashboard') }}">Go to dashboard</a> |
            <a href="{{ url_for('logout') }}">Logout</a>
        </p>
        """
        return render_template_string(html)


@app.route("/login")
def login():
    # Use pinned redirect URI unless explicitly overridden via env var above
    flow = build_flow(REDIRECT_URI)
    authorization_url, state = flow.authorization_url(
        access_type="offline",  # request refresh token
        include_granted_scopes="true",
        prompt="consent",  # ensure refresh_token on repeat logins
    )
    # Save state to protect against CSRF
    session["state"] = state
    return redirect(authorization_url)


@app.route("/callback")
def oauth_callback():
    # CSRF protection: verify state parameter matches
    state_from_google = request.args.get("state")
    state_in_session = session.get("state")
    if not state_in_session or state_from_google != state_in_session:
        print(f"[callback] State mismatch. got={state_from_google} expected={state_in_session}")
        return "State mismatch. Please try logging in again.", 400

    # Must use the same redirect URI used during /login
    flow = build_flow(REDIRECT_URI)
    # Exchange authorization code for tokens
    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials
    session["credentials"] = credentials_to_dict(credentials)
    # Debug: confirm what we stored (do not print tokens)
    safe_creds = session.get("credentials", {})
    print("[callback] Stored credentials keys:", list(safe_creds.keys()))
    print("[callback] Scopes:", safe_creds.get("scopes"))

    # Upsert user in DB and store user_id
    try:
        user_id = _ensure_user_in_db(credentials)
        print("[callback] Upserted/verified user:", user_id)
    except Exception as e:
        print("[callback] Failed to upsert user:", e)

    # No longer need state after successful exchange
    session.pop("state", None)

    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    if "credentials" not in session:
        return redirect(url_for("index"))

    # Debug: confirm we can read credentials from session (do not print tokens)
    safe_creds = session.get("credentials", {})
    print("[dashboard] Loaded credentials keys:", list(safe_creds.keys()))
    print("[dashboard] Scopes:", safe_creds.get("scopes"))
    creds = _rebuild_creds()
    if creds is None:
        return redirect(url_for("logout"))

    # Ensure user exists in DB for this session and prefer DB-stored profile
    _ensure_user_in_db(creds)
    user_doc = _current_user_doc() or {}
    name_from_db = (user_doc.get("userdata", {}) or {}).get("name")
    email_from_db = (user_doc.get("userdata", {}) or {}).get("email")
    photo_from_db = (user_doc.get("userdata", {}) or {}).get("photo_url")

    people_service = build("people", "v1", credentials=creds)

    profile = (
        people_service
        .people()
        .get(resourceName="people/me", personFields="names,emailAddresses,photos")
        .execute()
    )

    # Extract data safely
    def get_first(values, key):
        try:
            return values[0].get(key)
        except Exception:
            return None

    full_name = name_from_db or (get_first(profile.get("names", []), "displayName") or "Unknown")
    email = email_from_db or (get_first(profile.get("emailAddresses", []), "value") or "Unknown")
    photo_url = photo_from_db or (get_first(profile.get("photos", []), "url") or "")

    # Fetch user's templates
    templates = []
    if list_presentations_for_user and session.get("user_id"):
        try:
            templates = list_presentations_for_user(session["user_id"], limit=50)
        except Exception as e:
            print("[dashboard] list_presentations_for_user error:", e)

        html = """
    <h2>Dashboard</h2>
        {% with msgs = get_flashed_messages() %}
            {% if msgs %}
                <ul class="flashes">
                    {% for m in msgs %}<li>{{ m }}</li>{% endfor %}
                </ul>
            {% endif %}
        {% endwith %}
    <p><strong>Name:</strong> {{ name }}</p>
    <p><strong>Email:</strong> {{ email }}</p>
    {% if photo_url %}
      <p><img src="{{ photo_url }}" alt="Profile photo" style="height:96px;width:96px;border-radius:50%"></p>
    {% endif %}

    <hr/>
    <h3>Your Templates</h3>
    <ul>
      {% for t in templates %}
        <li>
          <strong>{{ t.title or t.presentationId }}</strong>
          <div>
            <small>ID: {{ t.presentationId }}</small>
          </div>
          <form method="post" action="{{ url_for('remove_template') }}" style="display:inline" onsubmit="return confirm('Remove this template?');">
            <input type="hidden" name="presentation_id" value="{{ t.presentationId }}" />
            <button type="submit">Remove</button>
          </form>
          <a href="https://docs.google.com/presentation/d/{{ t.presentationId }}/edit" target="_blank">Open</a>
        </li>
      {% else %}
        <li>No templates yet.</li>
      {% endfor %}
    </ul>

    <h3>Add a Template</h3>
    <form method="post" action="{{ url_for('add_template') }}">
      <label>Template URL:</label>
      <input type="url" name="template_url" placeholder="https://docs.google.com/presentation/d/..../edit" required style="width:480px" />
      <button type="submit">Add</button>
    </form>

    <p><a href="{{ url_for('logout') }}">Logout</a></p>
    """
    return render_template_string(html, name=full_name, email=email, photo_url=photo_url, templates=templates)


def _extract_presentation_id_from_url(url: str) -> str | None:
    """Extract the presentation ID from a Google Slides URL.

    Accepts formats like:
      https://docs.google.com/presentation/d/{ID}/edit
      https://docs.google.com/presentation/d/{ID}
    """
    try:
        if not url:
            return None
        parts = url.split("/d/")
        if len(parts) < 2:
            return None
        tail = parts[1]
        pres_id = tail.split("/")[0]
        return pres_id
    except Exception:
        return None


@app.route("/templates/add", methods=["POST"])
def add_template():
    if "credentials" not in session:
        return redirect(url_for("index"))
    creds = _rebuild_creds()
    if creds is None:
        return redirect(url_for("logout"))
    user_id = session.get("user_id")
    if not user_id or not create_or_replace_presentation:
        flash("Template storage not available.")
        return redirect(url_for("dashboard"))

    template_url = request.form.get("template_url", "").strip()
    pres_id = _extract_presentation_id_from_url(template_url)
    if not pres_id:
        flash("Invalid Slides URL.")
        return redirect(url_for("dashboard"))

    # Use Slides API to fetch metadata and basics
    slides = build("slides", "v1", credentials=creds)
    try:
        pres = slides.presentations().get(presentationId=pres_id).execute()
        title = pres.get("title")
        # Persist full presentation JSON as template
        create_or_replace_presentation(pres_id, user_id, pres, title)
        flash("Template added.")
    except Exception as e:
        print("[add_template] Error:", e)
        # Common case: missing Slides scope
        msg = str(e)
        if "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in msg or "insufficient authentication scopes" in msg.lower():
            flash("Permission required: please log out and log back in to grant Slides access, then try again.")
        else:
            flash("Failed to add template.")
    return redirect(url_for("dashboard"))


@app.route("/templates/remove", methods=["POST"])
def remove_template():
    if "credentials" not in session:
        return redirect(url_for("index"))
    creds = _rebuild_creds()
    if creds is None:
        return redirect(url_for("logout"))
    user_id = session.get("user_id")
    pres_id = request.form.get("presentation_id", "").strip()
    ok = False
    if user_id and delete_presentation and pres_id:
        try:
            ok = delete_presentation(pres_id, user_id)
        except Exception as e:
            print("[remove_template] Error:", e)
    flash("Template removed." if ok else "Failed to remove template.")
    return redirect(url_for("dashboard"))


@app.route("/me")
def me():
    if "credentials" not in session:
        return jsonify({"error": "unauthorized"}), 401
    creds = _rebuild_creds()
    if creds is None:
        return jsonify({"error": "unauthorized"}), 401
    user_id = session.get("user_id")
    if user_id and get_user:
        doc = get_user(user_id)
        if doc:
            return jsonify({
                "id": doc.get("_id"),
                "email": doc.get("userdata", {}).get("email"),
                "name": doc.get("userdata", {}).get("name"),
                "photo_url": doc.get("userdata", {}).get("photo_url"),
                "provider": doc.get("userdata", {}).get("provider"),
            })
    return jsonify({"id": None, "email": None, "name": None, "photo_url": None}), 200


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    # Allow OAuth over HTTP for local development ONLY. Do not enable this in production.
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    # Relax scope check: accept when provider returns a superset (e.g., adds 'openid').
    # This avoids oauthlib raising on scope differences in local dev.
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
    app.run(host="localhost", port=5000, debug=True)
