"""
ASTRA-Interface Platform — app.py
Full Flask application: auth, dashboard, 3 feature pages, API endpoints.
"""
from __future__ import annotations

import os
import sys
import math
import traceback
from functools import wraps
from pathlib import Path
from datetime import datetime, timezone

# ── ASTRA-Core path injection ─────────────────────────────────────────────────
_ASTRA_ROOT = Path(__file__).parent.parent / "ASTRA"
if _ASTRA_ROOT.exists() and str(_ASTRA_ROOT) not in sys.path:
    sys.path.insert(0, str(_ASTRA_ROOT))

import numpy as np
from werkzeug.security import generate_password_hash, check_password_hash
from flask import (
    Flask, render_template, redirect, url_for, flash,
    session, request, jsonify, g
)
from flask_cors import CORS

import astra
from astra import errors as astra_errors
from astra.spacetrack import _get_credentials, _create_session, _ST_QUERY_URL
from astra.omm import parse_omm_json

import crypto
import database as db
import storage

# ── App Setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("ASTRA_SECRET_KEY", "astra-mission-ctrl-2026-dev")
CORS(app)

# Wrap WSGI app with WhiteNoise to serve static files in production efficiently
from whitenoise import WhiteNoise
app.wsgi_app = WhiteNoise(app.wsgi_app, root='static/', prefix='static/')

# Initialise Fernet key from the app secret (must happen before any DB read/write)
crypto.init_crypto(app.secret_key)

db.init_db()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _jd_to_iso(jd: float) -> str:
    unix_sec = (jd - 2440587.5) * 86400.0
    return datetime.fromtimestamp(unix_sec, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _orbit_regime(alt_km: float) -> str:
    if alt_km < 2000:    return "LEO"
    if alt_km < 35786:   return "MEO"
    if alt_km < 35887:   return "GEO"
    return "HEO"


# ── Auth Decorator ────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def _inject_st_creds() -> bool:
    """Inject the current user's Space-Track creds into env vars for ASTRA.

    Also opportunistically re-encrypts any legacy plaintext rows left over
    from before the Fernet upgrade was deployed.
    """
    user_id = session.get("user_id")
    if not user_id:
        return False
    creds = db.get_spacetrack_creds(user_id)
    if not creds:
        return False

    os.environ["SPACETRACK_USER"] = creds["st_username"]
    os.environ["SPACETRACK_PASS"] = creds["st_password"]

    # Opportunistic re-encryption: if the stored row was plaintext (legacy),
    # re-save it now so it gets Fernet-encrypted going forward.
    raw_row = db._get_raw_st_password(user_id)
    if raw_row and not crypto.is_encrypted(raw_row):
        db.save_spacetrack_creds(user_id, creds["st_username"], creds["st_password"])

    return True


def _has_st_creds() -> bool:
    user_id = session.get("user_id")
    if not user_id:
        return False
    return db.get_spacetrack_creds(user_id) is not None


# ── Context Processor ─────────────────────────────────────────────────────────

@app.context_processor
def inject_globals():
    user = None
    has_creds = False
    if "user_id" in session:
        row = db.get_user_by_id(session["user_id"])
        if row:
            user = row
        has_creds = _has_st_creds()
    return dict(
        current_user=user,
        has_st_creds=has_creds,
        astra_version=astra.__version__,
        s3_static_prefix=storage.get_static_prefix(),
    )


# ════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ════════════════════════════════════════════════════════════════════

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        action = request.form.get("action", "login")

        if action == "register":
            username = request.form.get("username", "").strip()
            email    = request.form.get("email", "").strip()
            password = request.form.get("password", "")
            confirm  = request.form.get("confirm", "")

            if not username or not email or not password:
                flash("All fields are required.", "error")
            elif password != confirm:
                flash("Passwords do not match.", "error")
            elif len(password) < 6:
                flash("Password must be at least 6 characters.", "error")
            elif db.get_user_by_username(username):
                flash("Username already taken.", "error")
            else:
                hashed = generate_password_hash(password)
                uid = db.create_user(username, email, hashed)
                session["user_id"]  = uid
                session["username"] = username
                db.log_activity(uid, "REGISTER", f"New account created")
                flash("Account created! Welcome aboard.", "success")
                return redirect(url_for("dashboard"))
        else:
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            row = db.get_user_by_username(username)
            if not row or not check_password_hash(row["password"], password):
                flash("Invalid username or password.", "error")
            else:
                session["user_id"]  = row["id"]
                session["username"] = row["username"]
                db.log_activity(row["id"], "LOGIN", "Successful login")
                return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    user_id = session.get("user_id")
    if user_id:
        db.log_activity(user_id, "LOGOUT", "Session ended")
    session.clear()
    return redirect(url_for("login"))


# ════════════════════════════════════════════════════════════════════
# PAGE ROUTES
# ════════════════════════════════════════════════════════════════════

@app.route("/")
@login_required
def dashboard():
    user_id  = session["user_id"]
    activity = db.get_recent_activity(user_id, limit=8)
    has_creds = _has_st_creds()
    return render_template("dashboard.html", activity=activity, show_creds_modal=not has_creds)


@app.route("/catalog")
@login_required
def catalog():
    return render_template("catalog.html")


@app.route("/conjunctions")
@login_required
def conjunctions():
    return render_template("conjunctions.html")


@app.route("/passes")
@login_required
def passes():
    return render_template("passes.html")


# ════════════════════════════════════════════════════════════════════
# CREDENTIALS API
# ════════════════════════════════════════════════════════════════════

@app.route("/api/spacetrack-creds", methods=["POST"])
@login_required
def save_st_creds():
    body = request.get_json(force=True, silent=True) or {}
    st_user = body.get("st_username", "").strip()
    st_pass = body.get("st_password", "").strip()
    if not st_user or not st_pass:
        return jsonify({"error": "Both username and password are required."}), 400

    # Verify credentials work before saving
    os.environ["SPACETRACK_USER"] = st_user
    os.environ["SPACETRACK_PASS"] = st_pass
    try:
        _get_credentials()
        sess = _create_session(st_user, st_pass)
        # Quick test query
        url = f"{_ST_QUERY_URL}/NORAD_CAT_ID/25544/FORMAT/json"
        r = sess.get(url, timeout=15.0)
        r.raise_for_status()
        if not r.text.strip():
            return jsonify({"error": "Authentication succeeded but query returned empty."}), 400
    except astra_errors.AstraError as exc:
        return jsonify({"error": str(exc)}), 401
    except Exception as exc:
        return jsonify({"error": f"Connection test failed: {exc}"}), 400

    db.save_spacetrack_creds(session["user_id"], st_user, st_pass)
    db.log_activity(session["user_id"], "ST_CREDS_SAVED", f"Space-Track credentials updated")
    return jsonify({"ok": True, "message": "Credentials saved and verified successfully."})


@app.route("/api/status")
@login_required
def api_status():
    has_creds = _inject_st_creds()
    st_user   = os.environ.get("SPACETRACK_USER", "") if has_creds else ""
    return jsonify({
        "status": "ok",
        "astra_version": astra.__version__,
        "spacetrack_credentials": has_creds,
        "user": st_user,
        "username": session.get("username"),
    })


_STATS_CACHE = {"data": None, "timestamp": 0}

@app.route("/api/dashboard-stats")
@login_required
def dashboard_stats():
    """Return quick stats for the dashboard cards."""
    if not _inject_st_creds():
        return jsonify({"error": "no_credentials"}), 400

    import time
    now = time.time()
    
    # Use cached data if less than 2 hours old to prevent hitting Space-Track rate limits on every reload
    if _STATS_CACHE["data"] and (now - _STATS_CACHE["timestamp"]) < 7200:
        return jsonify(_STATS_CACHE["data"])

    try:
        from astra.spacetrack import fetch_spacetrack_active
        satellites = fetch_spacetrack_active(format="json")
        
        regime_counts = {"LEO": 0, "MEO": 0, "GEO": 0, "HEO": 0}
        
        for sat in satellites:
            alt_km = 0
            if hasattr(sat, "mean_motion_rad_min") and sat.mean_motion_rad_min > 0:
                n_rads = sat.mean_motion_rad_min / 60.0
                a_km = (398600.4418 / (n_rads**2)) ** (1/3)
                alt_km = a_km - 6371.0
            
            regime = _orbit_regime(max(0, alt_km))
            regime_counts[regime] = regime_counts.get(regime, 0) + 1

        latest_epoch = _jd_to_iso(satellites[0].epoch_jd) if satellites else "—"

        data = {
            "tracked_objects": len(satellites),
            "leo_objects": regime_counts["LEO"],
            "meo_objects": regime_counts["MEO"],
            "geo_objects": regime_counts["GEO"],
            "heo_objects": regime_counts["HEO"],
            "data_fresh": True,
            "latest_epoch": latest_epoch,
        }
        
        _STATS_CACHE["data"] = data
        _STATS_CACHE["timestamp"] = now
        return jsonify(data)
    except Exception as exc:
        traceback.print_exc()
        # If cache exists but fetch fails, return cached data as fallback
        if _STATS_CACHE["data"]:
            return jsonify(_STATS_CACHE["data"])
        return jsonify({"error": str(exc)}), 500


# ════════════════════════════════════════════════════════════════════
# DATA API ENDPOINTS (require auth + ST creds)
# ════════════════════════════════════════════════════════════════════

@app.route("/api/fetch", methods=["POST"])
@login_required
def fetch_catalog():
    if not _inject_st_creds():
        return jsonify({"error": "no_credentials"}), 400

    body   = request.get_json(force=True, silent=True) or {}
    group  = body.get("group", "starlink").strip()
    fmt    = body.get("format", "json")
    limit  = int(body.get("limit", 200))

    try:
        satellites = astra.fetch_spacetrack_group(group, format=fmt)
    except astra_errors.AstraError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": f"Unexpected error: {exc}"}), 500

    db.log_activity(session["user_id"], "CATALOG_FETCH", f"group={group} fmt={fmt} n={len(satellites)}")

    records = []
    regime_counts = {"LEO": 0, "MEO": 0, "GEO": 0, "HEO": 0}

    for sat in satellites[:limit]:
        if hasattr(sat, "inclination_rad"):
            inc_deg = math.degrees(sat.inclination_rad)
            mm      = sat.mean_motion_rad_min * 1440 / (2 * math.pi)
            # Approximate altitude from mean motion: a = (μ/n²)^(1/3) - Re
            MU_KM3  = 398600.4418
            n_rads  = sat.mean_motion_rad_min / 60.0
            a_km    = (MU_KM3 / (n_rads**2)) ** (1/3)
            alt_km  = a_km - 6371.0
            regime  = _orbit_regime(max(0, alt_km))
            regime_counts[regime] = regime_counts.get(regime, 0) + 1
            records.append({
                "norad_id": sat.norad_id,
                "name": sat.name.strip(),
                "object_type": sat.object_type,
                "epoch": _jd_to_iso(sat.epoch_jd),
                "inclination_deg": round(inc_deg, 4),
                "eccentricity": round(sat.eccentricity, 6),
                "mean_motion_rev_day": round(mm, 4),
                "altitude_km": round(alt_km, 1),
                "regime": regime,
                "rcs_m2": _safe_float(sat.rcs_m2),
                "mass_kg": _safe_float(sat.mass_kg),
                "format": "OMM",
            })
        else:
            try:
                inc = float(sat.line2[8:16])
            except Exception:
                inc = None
            records.append({
                "norad_id": sat.norad_id,
                "name": sat.name.strip(),
                "object_type": sat.object_type,
                "epoch": _jd_to_iso(sat.epoch_jd),
                "inclination_deg": inc,
                "eccentricity": None,
                "mean_motion_rev_day": None,
                "altitude_km": None,
                "regime": "—",
                "rcs_m2": _safe_float(getattr(sat, "rcs_m2", None)),
                "mass_kg": None,
                "format": "TLE",
            })

    return jsonify({
        "group": group,
        "total_fetched": len(satellites),
        "returned": len(records),
        "regime_counts": regime_counts,
        "records": records,
    })


@app.route("/api/conjunctions", methods=["POST"])
@login_required
def api_conjunctions():
    if not _inject_st_creds():
        return jsonify({"error": "no_credentials"}), 400

    body           = request.get_json(force=True, silent=True) or {}
    group          = body.get("group", "starlink").strip()
    limit          = min(int(body.get("limit", 80)), 250)
    threshold_km   = float(body.get("threshold_km", 10.0))
    duration_min   = float(body.get("duration_min", 120.0))
    step_min       = float(body.get("step_min", 5.0))

    try:
        raw = astra.fetch_spacetrack_group(group, format="json")
    except astra_errors.AstraError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": f"Unexpected error: {exc}"}), 500

    raw     = raw[:limit]
    objects = [astra.make_debris_object(s) for s in raw]
    sources = [obj.source for obj in objects]
    if not sources:
        return jsonify({"error": "No valid satellites."}), 400

    epoch_jd = sources[0].epoch_jd
    n_steps  = max(3, int(duration_min / step_min))
    times_jd = epoch_jd + np.arange(n_steps) * (step_min / 1440.0)

    try:
        traj_map, vel_map = astra.propagate_many(sources, times_jd)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": f"Propagation failed: {exc}"}), 500

    elements_map = {obj.source.norad_id: obj for obj in objects}

    try:
        events = astra.find_conjunctions(
            traj_map, times_jd=times_jd,
            elements_map=elements_map, threshold_km=threshold_km,
            vel_map=vel_map,
        )
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": f"Conjunction screening failed: {exc}"}), 500

    db.log_activity(session["user_id"], "CONJUNCTION_SCREEN",
                    f"group={group} n={len(sources)} events={len(events)}")

    result_events = []
    risk_summary  = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
    for ev in events[:100]:
        risk_summary[ev.risk_level] = risk_summary.get(ev.risk_level, 0) + 1
        result_events.append({
            "object_a": ev.object_a_id,
            "object_b": ev.object_b_id,
            "tca": _jd_to_iso(ev.tca_jd),
            "miss_distance_km": round(ev.miss_distance_km, 3),
            "relative_velocity_km_s": round(ev.relative_velocity_km_s, 3),
            "collision_probability": _safe_float(ev.collision_probability),
            "risk_level": ev.risk_level,
            "covariance_source": ev.covariance_source,
        })

    return jsonify({
        "group": group,
        "satellites_screened": len(sources),
        "duration_min": duration_min,
        "threshold_km": threshold_km,
        "events_found": len(events),
        "risk_summary": risk_summary,
        "events": result_events,
    })


@app.route("/api/passes", methods=["POST"])
@login_required
def api_passes():
    if not _inject_st_creds():
        return jsonify({"error": "no_credentials"}), 400

    body            = request.get_json(force=True, silent=True) or {}
    norad_id        = str(body.get("norad_id", "25544")).strip()
    lat             = float(body.get("lat", 12.9716))
    lon             = float(body.get("lon", 77.5946))
    elev_m          = float(body.get("elevation_m", 920.0))
    hours_ahead     = float(body.get("hours_ahead", 24.0))
    min_elev        = float(body.get("min_elevation_deg", 10.0))
    observer_name   = body.get("observer_name", "Ground Station")

    try:
        username, password = _get_credentials()
        sess = _create_session(username, password)
        url  = f"{_ST_QUERY_URL}/NORAD_CAT_ID/{norad_id}/FORMAT/json"
        resp = sess.get(url, timeout=20.0)
        resp.raise_for_status()
        raw = parse_omm_json(resp.text)
        if not raw:
            return jsonify({"error": f"No satellite found for NORAD ID {norad_id}."}), 404
        satellite = raw[0]
    except astra_errors.AstraError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": f"Fetch failed: {exc}"}), 500

    observer = astra.Observer(
        name=observer_name, latitude_deg=lat,
        longitude_deg=lon, elevation_m=elev_m,
        min_elevation_deg=min_elev,
    )
    t_start = satellite.epoch_jd
    t_end   = t_start + hours_ahead / 24.0

    try:
        pass_events = astra.passes_over_location(satellite, observer, t_start, t_end)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": f"Pass prediction failed: {exc}"}), 500

    db.log_activity(session["user_id"], "PASS_PREDICT",
                    f"NORAD={norad_id} obs={observer_name} passes={len(pass_events)}")

    result_passes = []
    for p in pass_events:
        result_passes.append({
            "norad_id": p.norad_id,
            "aos": _jd_to_iso(p.aos_jd),
            "tca": _jd_to_iso(p.tca_jd),
            "los": _jd_to_iso(p.los_jd),
            "max_elevation_deg": round(p.max_elevation_deg, 1),
            "azimuth_at_aos_deg": round(p.azimuth_at_aos_deg, 1),
            "azimuth_at_los_deg": round(p.azimuth_at_los_deg, 1),
            "duration_seconds": round(p.duration_seconds, 0),
        })

    return jsonify({
        "norad_id": norad_id,
        "satellite_name": satellite.name.strip(),
        "observer": observer_name,
        "observer_lat": lat,
        "observer_lon": lon,
        "hours_ahead": hours_ahead,
        "passes_found": len(pass_events),
        "passes": result_passes,
    })


@app.route("/api/health")
def health_check():
    """Load balancer health check endpoint for AWS EC2/ALB."""
    try:
        # Check DB connection
        db.get_user_by_id(0) # dummy query
        return jsonify({"status": "healthy", "s3_configured": bool(storage.AWS_S3_BUCKET)}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 503

# ════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("  ASTRA-Interface  —  Mission Control Platform")
    print("=" * 60)
    print(f"  ASTRA-Core v{astra.__version__}")
    db_print = db.DATABASE_URL.split("@")[-1] if "@" in db.DATABASE_URL else db.DATABASE_URL
    print(f"  DB: {db_print}")
    print(f"  → Open http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=True, port=5000)
