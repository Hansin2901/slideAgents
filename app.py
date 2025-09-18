import os
from textwrap import dedent
from uuid import uuid4
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
        get_presentation,
        set_template_explanation,
        get_template_explanation,
    )
except Exception as e:
    upsert_user = None
    get_user = None
    create_or_replace_presentation = None
    list_presentations_for_user = None
    delete_presentation = None
    get_presentation = None
    set_template_explanation = None
    get_template_explanation = None
    print("[warn] users_dal not available:", e)

try:
    from src.slide_generation.planner_service import resolve_plan_for_presentation, MissingPlanError
    from src.slide_generation.adapter import build_slide_requests
    from src.slide_generation.slides_api import send_batch_requests
except Exception as e:
    resolve_plan_for_presentation = None
    MissingPlanError = None
    build_slide_requests = None
    send_batch_requests = None
    print("[warn] slide_generation modules not available:", e)


# ---- Flask app setup ----
load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")


# ---- OAuth configuration ----
DEFAULT_CLIENT_SECRETS = (
    "client_secret_1080418670704-k0uh9qj9sstfp0lnbm7huscs63f6l2rm.apps.googleusercontent.com.json"
)
CLIENT_SECRETS_FILE = os.environ.get(
    "GOOGLE_CLIENT_SECRETS_FILE",
    DEFAULT_CLIENT_SECRETS if os.path.exists(DEFAULT_CLIENT_SECRETS) else "client_secret.json",
)

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/presentations",
]

DEFAULT_PORT = int(os.environ.get("FLASK_PORT", "5000"))
DEFAULT_HOST = os.environ.get("FLASK_HOST", "127.0.0.1")
REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/callback")


def credentials_to_dict(creds: Credentials) -> dict:
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "id_token": getattr(creds, "id_token", None),
    }


def build_flow(redirect_uri: str | None = None):
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
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
    """Ensure the logged-in Google user exists in Mongo. Returns user_id or None."""
    global upsert_user
    if upsert_user is None:
        return None

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
        user_id = user_id or email

    if not user_id or not email:
        return None

    previous_uid = session.get("user_id")
    doc = upsert_user({
        "id": user_id,
        "email": email,
        "name": name,
        "photo_url": photo_url,
        "provider": "google",
    })
    session["user_id"] = (doc.get("_id") if isinstance(doc, dict) else user_id)
    try:
        if previous_uid and previous_uid != session["user_id"]:
            from src.db.template_dal import migrate_owner_presentations
            moved = migrate_owner_presentations(previous_uid, session["user_id"])
            if moved:
                print(f"[auth] Migrated {moved} templates from {previous_uid} to {session['user_id']}")
        if email and email != session["user_id"]:
            from src.db.template_dal import migrate_owner_presentations
            moved_email = migrate_owner_presentations(email, session["user_id"])
            if moved_email:
                print(f"[auth] Migrated {moved_email} templates from email {email} to {session['user_id']}")
    except Exception as e:
        print("[auth] Owner migration skipped:", e)
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
    if "credentials" in session:
        html = """
        <h2>Welcome back</h2>
        <p>You are logged in.</p>
        <p>
            <a href="{{ url_for('dashboard') }}">Go to dashboard</a> |
            <a href="{{ url_for('logout') }}">Logout</a>
        </p>
        """
    else:
        html = """
        <h2>Welcome</h2>
        <p>You are not logged in.</p>
        <a href="{{ url_for('login') }}">Login with Google</a>
        """
    return render_template_string(html)


@app.route("/login")
def login():
    flow = build_flow(REDIRECT_URI)
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    session["state"] = state
    return redirect(authorization_url)


@app.route("/callback")
def oauth_callback():
    state_from_google = request.args.get("state")
    state_in_session = session.get("state")
    if not state_in_session or state_from_google != state_in_session:
        print(f"[callback] State mismatch. got={state_from_google} expected={state_in_session}")
        return "State mismatch. Please try logging in again.", 400

    flow = build_flow(REDIRECT_URI)
    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials
    session["credentials"] = credentials_to_dict(credentials)
    
    try:
        user_id = _ensure_user_in_db(credentials)
        print("[callback] Upserted/verified user:", user_id)
    except Exception as e:
        print("[callback] Failed to upsert user:", e)

    session.pop("state", None)
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    if "credentials" not in session:
        return redirect(url_for("index"))

    creds = _rebuild_creds()
    if creds is None:
        return redirect(url_for("logout"))

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

    def get_first(values, key):
        try:
            return values[0].get(key)
        except Exception:
            return None

    full_name = name_from_db or (get_first(profile.get("names", []), "displayName") or "Unknown")
    email = email_from_db or (get_first(profile.get("emailAddresses", []), "value") or "Unknown")
    photo_url = photo_from_db or (get_first(profile.get("photos", []), "url") or "")

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
          <a href="{{ url_for('templates_dashboard') }}" style="margin-left:8px;">View Template Explanations</a>
          <a href="{{ url_for('slides_batch_page') }}" style="margin-left:8px;">Slides Batch Update</a>
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


# -------- Template Dashboard (Admin-style) --------
@app.route("/templates/dashboard")
def templates_dashboard():
    if "credentials" not in session:
        return redirect(url_for("index"))
    if not session.get("user_id"):
        return redirect(url_for("dashboard"))

    html = dedent(
        """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8"/>
            <title>Template Dashboard</title>
            <style>
                body { font-family: system-ui, Arial, sans-serif; margin: 24px; }
                table { width: 100%; border-collapse: collapse; }
                th, td { padding: 8px 12px; border-bottom: 1px solid #ddd; vertical-align: top; }
                th { text-align: left; background:#fafafa; }
                tr.expandable { cursor: pointer; }
                .details-row td { background: #f5f7fa; }
                .label-col { font-weight: 600; width: 180px; }
                .actions button { margin-right: 4px; }
                .caret { transition: transform .2s ease; display:inline-block; }
                .caret.open { transform: rotate(90deg); }
                .hidden { display: none !important; }
                .modal-backdrop { position: fixed; inset:0; background: rgba(0,0,0,.35); display:flex; align-items:center; justify-content:center; }
                .modal { background:#fff; padding:20px; border-radius:8px; width:640px; max-width:95%; box-shadow:0 4px 12px rgba(0,0,0,.15); }
                .modal h3 { margin-top:0; }
                .modal textarea { width:100%; min-height:100px; resize:vertical; font-family:inherit; font-size:14px; }
                .modal-actions { margin-top:12px; text-align:right; }
                .toast { position:fixed; bottom:16px; right:16px; background:#222; color:#fff; padding:10px 14px; border-radius:4px; opacity:0; transform:translateY(8px); transition: all .25s; }
                .toast.show { opacity:1; transform:translateY(0); }
            </style>
        </head>
        <body>
            <h2>Template Dashboard</h2>
            <p><a href="{{ url_for('dashboard') }}">&larr; Back to user dashboard</a></p>
            <table id="templateTable">
                <thead>
                    <tr><th></th><th>Template Name</th><th>Last Modified</th><th>Actions</th></tr>
                </thead>
                <tbody id="templateBody"></tbody>
            </table>

            <div id="editModalWrap" class="modal-backdrop hidden" role="dialog" aria-modal="true">
                <div class="modal">
                    <h3 id="modalTitle">Edit Template</h3>
                    <form id="editForm">
                        <label>General Description</label>
                        <textarea id="genDesc" name="generalDescription"></textarea>
                        <label>Structural Description</label>
                        <textarea id="structDesc" name="structuralDescription"></textarea>
                        <label>Usage Instructions</label>
                        <textarea id="usageInstr" name="usageInstructions"></textarea>
                        <div class="modal-actions">
                            <button type="button" id="cancelBtn">Cancel</button>
                            <button type="submit" id="saveBtn">Save Changes</button>
                        </div>
                    </form>
                </div>
            </div>
            <div id="toast" class="toast" role="status" aria-live="polite"></div>

        <script>
        async function fetchTemplates(){
            const r = await fetch('/templates/json');
            if(!r.ok) throw new Error('Failed to load templates');
            return await r.json();
        }

        function rowTemplate(t){
            const modified = t.updated_at || t.created_at || '';
            const name = t.title || t.presentationId;
                return `
                <tr class="expandable" data-id="${t.presentationId}">
                    <td><span class="caret">▶</span></td>
                    <td>${name}</td>
                    <td>${modified}</td>
                    <td class="actions">
                        <button data-action="delete" data-id="${t.presentationId}">Delete</button>
                    </td>
                </tr>
                <tr class="details-row hidden" data-details-for="${t.presentationId}">
                    <td></td>
                    <td colspan="3">
                        <div class="detail-wrapper" id="detail-${t.presentationId}">Loading...</div>
                    </td>
                </tr>`;
        }

        async function fetchLayouts(id){
            const r = await fetch(`/templates/${id}/layouts`);
            if(!r.ok) return [];
            return await r.json();
        }

        function layoutsHtml(list){
            if(!list.length) return '<em>No layouts found.</em>';
            const header = `<tr><th>Layout Object ID</th><th>Layout Display Name</th><th>General Description</th><th>Structural Description</th><th>Usage Instructions</th></tr>`;
            const rows = list.map(l => {
                return `<tr>
                    <td>${escapeHtml(l.objectId || '')}</td>
                    <td>${escapeHtml(l.displayName || '')}</td>
                    <td>${escapeHtml(l.generalDescription || '')}</td>
                    <td>${escapeHtml(l.structuralDescription || '')}</td>
                    <td>${escapeHtml(l.usageInstructions || '')}</td>
                </tr>`;
            }).join('');
            return `<table style="width:100%; border-collapse:collapse;" class="inner-layout-table">${header}${rows}</table>`;
        }

        function escapeHtml(str){
            return str.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
        }

        function showToast(msg){
            const t = document.getElementById('toast');
            t.textContent = msg; t.classList.add('show');
            setTimeout(()=> t.classList.remove('show'), 3000);
        }
        async function init(){
            const data = await fetchTemplates();
            const body = document.getElementById('templateBody');
            body.innerHTML = data.map(rowTemplate).join('');

            body.addEventListener('click', async (e)=>{
                const tr = e.target.closest('tr.expandable');
                if(tr && !e.target.dataset.action){
                    const id = tr.dataset.id;
                    const caret = tr.querySelector('.caret');
                    const detailsRow = body.querySelector(`tr.details-row[data-details-for="${id}"]`);
                    const panel = detailsRow.querySelector('.detail-wrapper');
                    const open = !detailsRow.classList.contains('hidden');
                    if(open){
                        detailsRow.classList.add('hidden'); caret.classList.remove('open');
                    } else {
                        detailsRow.classList.remove('hidden'); caret.classList.add('open');
                        panel.innerHTML = 'Loading layouts...';
                        const layouts = await fetchLayouts(id);
                        panel.innerHTML = layoutsHtml(layouts);
                    }
                }

                if(e.target.dataset.action === 'delete'){
                    if(confirm('Delete this template?')){
                        const form = document.createElement('form');
                        form.method='POST'; form.action='/templates/remove';
                        const inp = document.createElement('input'); inp.type='hidden'; inp.name='presentation_id'; inp.value=e.target.dataset.id; form.appendChild(inp);
                        document.body.appendChild(form); form.submit();
                    }
                }

            });
        }

        init();
        </script>
        </body></html>
        """
    )
    return render_template_string(html)


@app.route("/templates/json")
def templates_json():
    if "credentials" not in session:
        return jsonify([])
    uid = session.get("user_id")
    if not uid or not list_presentations_for_user:
        return jsonify([])
    rows = list_presentations_for_user(uid, limit=200)
    out = []
    for r in rows:
        out.append({
            "presentationId": r.get("presentationId"),
            "title": r.get("title"),
            "updated_at": r.get("updated_at"),
            "created_at": r.get("created_at"),
        })
    return jsonify(out)


def _derive_explanation_from_layouts(doc: dict) -> dict | None:
    pres = doc.get("presentationData") or {}
    layouts = pres.get("layouts") or []
    for l in layouts:
        ex = l.get("explanation")
        if ex and all(k in ex for k in ("generalDescription","structuralDescription","usageInstructions")):
            return ex
    return None


@app.route("/templates/<presentation_id>/explanation", methods=["GET"])
def get_template_explanation_route(presentation_id: str):
    if "credentials" not in session:
        return jsonify({}), 403
    uid = session.get("user_id")
    if not uid or not get_presentation:
        return jsonify({}), 404
    doc = get_presentation(presentation_id)
    if not doc or doc.get("ownerId") != uid:
        return jsonify({}), 404
    stored = None
    if get_template_explanation:
        stored = get_template_explanation(presentation_id, uid)
    if stored:
        return jsonify(stored)
    derived = _derive_explanation_from_layouts(doc) or {}
    return jsonify(derived)


@app.route("/templates/<presentation_id>/explanation", methods=["POST"])
def set_template_explanation_route(presentation_id: str):
    if "credentials" not in session:
        return jsonify({"error": "auth"}), 403
    uid = session.get("user_id")
    if not uid or not get_presentation:
        return jsonify({"error": "not-found"}), 404
    doc = get_presentation(presentation_id)
    if not doc or doc.get("ownerId") != uid:
        return jsonify({"error": "not-found"}), 404
    data = request.get_json(silent=True) or {}
    allowed = {k: (data.get(k) or "").strip() for k in ["generalDescription","structuralDescription","usageInstructions"]}
    if not any(allowed.values()):
        return jsonify({"error": "empty"}), 400
    if set_template_explanation:
        ok = set_template_explanation(presentation_id, uid, allowed)
        if not ok:
            return jsonify({"error": "save"}), 500
    return jsonify({"status": "ok"})


@app.route("/templates/<presentation_id>/layouts", methods=["GET"])
def list_template_layouts(presentation_id: str):
    if "credentials" not in session:
        return jsonify([]), 403
    uid = session.get("user_id")
    if not uid or not get_presentation:
        return jsonify([]), 404
    doc = get_presentation(presentation_id)
    if not doc or doc.get("ownerId") != uid:
        return jsonify([]), 404
    pres = doc.get("presentationData") or {}
    layouts = pres.get("layouts") or []
    out = []
    for l in layouts:
        ex = l.get("explanation") or {}
        out.append({
            "objectId": l.get("objectId"),
            "displayName": (l.get("layoutProperties") or {}).get("displayName"),
            "generalDescription": ex.get("generalDescription"),
            "structuralDescription": ex.get("structuralDescription"),
            "usageInstructions": ex.get("usageInstructions"),
        })
    return jsonify(out)


# -------- Slides Batch Update Page (clean) --------
@app.route("/slides/batch")
def slides_batch_page():
    if "credentials" not in session:
        return redirect(url_for("index"))
    if not session.get("user_id"):
        return redirect(url_for("dashboard"))
    
    user_templates = []
    if list_presentations_for_user and session.get("user_id"):
        try:
            user_templates = list_presentations_for_user(session["user_id"], limit=100)
        except Exception as e:
            print("[slides_batch_page] list_presentations_for_user error:", e)

    html = dedent(
        """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="utf-8" />
            <title>Slides Batch Update</title>
            <style>
                body { font-family: system-ui, Arial, sans-serif; margin: 24px; }
                textarea { width: 100%; min-height: 200px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
                label { font-weight: 600; display:block; margin-top: 12px; }
                .row { margin: 8px 0; }
                .btn { padding: 8px 12px; }
                .log { background: #f7f7f9; border: 1px solid #ddd; padding: 8px; margin-top: 12px; white-space: pre-wrap; }
            </style>
            <script>
            async function runBatch(e){
                e.preventDefault();
                const presId = document.getElementById('presId').value.trim();
                let planText = document.getElementById('plan').value.trim();
                if(!presId){ alert('Select a presentation'); return; }
                if(!planText){ alert('Enter plan JSON'); return; }
                let plan;
                try{
                    plan = JSON.parse(planText);
                } catch(err){
                    alert('Plan must be valid JSON.'); return;
                }
                const res = await fetch('/slides/batch/run', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ presentationId: presId, plan })
                });
                const txt = await res.text();
                document.getElementById('log').textContent = txt;
            }
            </script>
        </head>
        <body>
            <h2>Slides Batch Update</h2>
            <p><a href="{{ url_for('dashboard') }}">&larr; Back to dashboard</a></p>
            <form onsubmit="runBatch(event)">
                <label for="presId">Presentation</label>
                <select id="presId" required>
                    {% for t in templates %}
                        <option value="{{ t.presentationId }}">{{ t.title or t.presentationId }}</option>
                    {% endfor %}
                </select>
                <label for="plan">Plan JSON</label>
                <textarea id="plan" placeholder="{
          \\\"presentation_plan\\\": [ ... ]
        }"></textarea>
                <div class="row"><button class="btn" type="submit">Generate & Run</button></div>
            </form>
            <div id="log" class="log"></div>
        </body>
        </html>
        """
    )
    return render_template_string(html, templates=user_templates)


@app.route("/slides/batch/run", methods=["POST"])
def slides_batch_run():
    if "credentials" not in session:
        return ("Not logged in", 401)
    creds = _rebuild_creds()
    if not creds:
        return ("Missing credentials", 401)
    if resolve_plan_for_presentation is None or build_slide_requests is None or send_batch_requests is None:
        return ("Slide generation modules unavailable", 500)

    data = request.get_json(force=True, silent=True) or {}
    pres_id = (data.get("presentationId") or "").strip()
    plan = data.get("plan") or {}
    owner_id = session.get("user_id")
    if not pres_id:
        return ("presentationId is required", 400)
    if not plan:
        return ("plan payload is required", 400)
    if not isinstance(plan, dict):
        return ("plan must be a JSON object", 400)
    if "presentation_plan" not in plan:
        return ("plan must include 'presentation_plan'", 400)

    try:
        resolved = resolve_plan_for_presentation(pres_id, owner_id, plan)
    except MissingPlanError as e:
        return (str(e), 400)

    combined_requests = []
    run_prefix = uuid4().hex[:8]
    for idx, slide in enumerate(resolved, start=1):
        if slide.errors:
            return (
                f"Validation errors for layout '{slide.layout_id}': {', '.join(slide.errors)}",
                400,
            )
        payload = build_slide_requests(idx, slide, run_prefix=run_prefix)
        combined_requests.extend(payload.get("requests", []))

    try:
        response = send_batch_requests(
            pres_id,
            combined_requests,
            credentials_obj=creds,
        )
        return jsonify(response)
    except Exception as e:
        return (f"batchUpdate failed: {e}", 500)


def _extract_presentation_id_from_url(url: str) -> str | None:
    """Extract the presentation ID from a Google Slides URL."""
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

    slides = build("slides", "v1", credentials=creds)
    try:
        pres = slides.presentations().get(presentationId=pres_id).execute()
        title = pres.get("title")
        create_or_replace_presentation(pres_id, user_id, pres, title)
        flash("Template added.")
    except Exception as e:
        print("[add_template] Error:", e)
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
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    app.run(host=host, port=port, debug=True)