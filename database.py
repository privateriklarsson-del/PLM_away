"""
Database module for JM Building Parts Masterdata MVP.
Implements the data model:
  SystemFamily → BuildingPart → BuildingPartVersion → Properties
  PropertyDefinition (shared ontology)
  ContextRequirement (filtering criteria)
"""

import sqlite3
import json
from datetime import datetime, date
from pathlib import Path

DB_PATH = Path(__file__).parent / "masterdata.db"


def get_connection():
    conn = sqlite3.connect(str(DB_PATH), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    # --- Schema ---

    c.execute("""
        CREATE TABLE IF NOT EXISTS system_family (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            owner TEXT NOT NULL,
            plm_reference TEXT,
            description TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS property_definition (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            data_type TEXT NOT NULL CHECK(data_type IN ('number', 'text', 'boolean')),
            unit TEXT,
            comparison_operator TEXT NOT NULL CHECK(comparison_operator IN ('exact', '>=', '<=', 'hierarchy')),
            hierarchy_order TEXT  -- JSON list for hierarchy types, e.g. ["EI15","EI30","EI60","EI90"]
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS building_part (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            system_family_id TEXT NOT NULL REFERENCES system_family(id),
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'phased_out')),
            description TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS building_part_version (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            building_part_id TEXT NOT NULL REFERENCES building_part(id),
            version TEXT NOT NULL,
            valid_from DATE NOT NULL,
            valid_to DATE,
            -- Governance log (Typ 2)
            change_type TEXT NOT NULL CHECK(change_type IN ('new', 'major_change', 'phase_out')),
            change_description TEXT NOT NULL,
            change_reason TEXT NOT NULL,
            trigger_category TEXT CHECK(trigger_category IN (
                'regulatory', 'cost', 'quality_issue', 'simplification',
                'supplier_change', 'other'
            )),
            decided_by TEXT NOT NULL,
            decided_date DATE NOT NULL,
            -- Technical description
            layer_description TEXT,  -- human-readable layer build-up
            UNIQUE(building_part_id, version)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS version_property (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL REFERENCES building_part_version(id),
            property_id TEXT NOT NULL REFERENCES property_definition(id),
            value TEXT NOT NULL,  -- stored as text, interpreted per data_type
            UNIQUE(version_id, property_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS country_variant (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL REFERENCES building_part_version(id),
            country TEXT NOT NULL CHECK(country IN ('SE', 'NO', 'FI', 'DK')),
            property_id TEXT NOT NULL REFERENCES property_definition(id),
            value TEXT NOT NULL,
            note TEXT,
            UNIQUE(version_id, country, property_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS context_requirement (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            system_family_id TEXT NOT NULL REFERENCES system_family(id),
            country TEXT,  -- NULL = all countries
            room_type TEXT,  -- NULL = all room types
            description TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS context_requirement_property (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            context_id INTEGER NOT NULL REFERENCES context_requirement(id),
            property_id TEXT NOT NULL REFERENCES property_definition(id),
            required_value TEXT NOT NULL,
            UNIQUE(context_id, property_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS article_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL REFERENCES building_part_version(id),
            country TEXT NOT NULL CHECK(country IN ('SE', 'NO', 'FI', 'DK')),
            article_id TEXT NOT NULL,
            supplier TEXT,
            description TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS project_configuration (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            country TEXT NOT NULL CHECK(country IN ('SE', 'NO', 'FI', 'DK')),
            created_date DATE NOT NULL,
            locked INTEGER NOT NULL DEFAULT 0,
            description TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS project_building_part (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES project_configuration(id),
            building_part_id TEXT NOT NULL REFERENCES building_part(id),
            locked_version_id INTEGER NOT NULL REFERENCES building_part_version(id),
            included INTEGER NOT NULL DEFAULT 1,
            UNIQUE(project_id, building_part_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS project_room_type (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES project_configuration(id),
            room_type TEXT NOT NULL,
            UNIQUE(project_id, room_type)
        )
    """)

    conn.commit()
    conn.close()


def seed_data():
    """Seed with JM inner wall data from D-0004649."""
    conn = get_connection()
    c = conn.cursor()

    # Check if already seeded
    if c.execute("SELECT COUNT(*) FROM system_family").fetchone()[0] > 0:
        conn.close()
        return

    # --- Property Definitions ---
    properties = [
        ("sound_reduction", "Ljudreduktion R'w", "number", "dB", ">=", None),
        ("thickness", "Tjocklek", "number", "mm", "exact", None),
        ("max_height_min", "Max vägghöjd (min)", "number", "mm", ">=", None),
        ("max_height_max", "Max vägghöjd (max)", "number", "mm", ">=", None),
        ("insulated", "Isolerad", "boolean", None, "exact", None),
        ("fire_class", "Brandklass", "text", None, "hierarchy",
         json.dumps(["EI15", "EI30", "EI60", "EI90"])),
        ("load_bearing", "Bärande", "boolean", None, "exact", None),
        ("stud_width", "Regeldimension", "number", "mm", "exact", None),
        ("gypsum_layers_per_side", "Gipsskivor per sida", "number", "st", ">=", None),
    ]
    c.executemany(
        "INSERT INTO property_definition VALUES (?,?,?,?,?,?)", properties
    )

    # --- System Family ---
    c.execute(
        "INSERT INTO system_family VALUES (?,?,?,?,?)",
        ("IWS", "Icke bärande innerväggar (stålregel)", "Erik",
         "R-10001", "Mellanväggar med stålregelstomme enligt D-0004649")
    )

    # --- Building Parts + Versions + Properties ---
    walls = [
        {
            "id": "IWS-10",
            "name": "Vägg limmas mot betong",
            "desc": "Enkel gipsskiva limmad mot betongvägg med sättlim",
            "layers": "12.5mm gipsskiva lätt, limmas mot betong med sättlim",
            "props": {
                "sound_reduction": "30",
                "thickness": "12.5",
                "max_height_min": "3550",
                "max_height_max": "4400",
                "insulated": "false",
                "load_bearing": "false",
                "stud_width": "0",
                "gypsum_layers_per_side": "1",
            }
        },
        {
            "id": "IWS-03",
            "name": "Standard mellanvägg 70mm",
            "desc": "Standard mellanvägg med 70mm stålregel, enkel gips per sida",
            "layers": "12.5mm gipsskiva lätt | 70mm stålregel | 12.5mm gipsskiva lätt",
            "props": {
                "sound_reduction": "35",
                "thickness": "95",
                "max_height_min": "3550",
                "max_height_max": "4400",
                "insulated": "false",
                "load_bearing": "false",
                "stud_width": "70",
                "gypsum_layers_per_side": "1",
            }
        },
        {
            "id": "IWS-03i",
            "name": "Mellanvägg 70mm isolerad",
            "desc": "Extra ljudisolerad vägg vid WC/sovrum, samt tillval från kund. Min 30mm mineralull.",
            "layers": "12.5mm gipsskiva lätt | 70mm stålregel (min 30mm min.ull) | 12.5mm gipsskiva lätt",
            "props": {
                "sound_reduction": "35",
                "thickness": "95",
                "max_height_min": "3550",
                "max_height_max": "4400",
                "insulated": "true",
                "load_bearing": "false",
                "stud_width": "70",
                "gypsum_layers_per_side": "1",
            }
        },
        {
            "id": "IWS-06",
            "name": "El-/IT-central vägg",
            "desc": "Vägg vid el-/IT-central i innervägg, 95mm stålregel",
            "layers": "12.5mm gipsskiva lätt | 95mm stålregel | 12.5mm gipsskiva lätt",
            "props": {
                "sound_reduction": "30",
                "thickness": "120",
                "max_height_min": "5500",
                "max_height_max": "5500",
                "insulated": "false",
                "load_bearing": "false",
                "stud_width": "95",
                "gypsum_layers_per_side": "1",
            }
        },
        {
            "id": "IWS-13",
            "name": "Mellanvägg dubbel gips 70mm",
            "desc": "Mellanvägg med dubbel gipsskiva per sida, 70mm stålregel",
            "layers": "2x 12.5mm gipsskiva lätt | 70mm stålregel | 2x 12.5mm gipsskiva lätt",
            "props": {
                "sound_reduction": "35",
                "thickness": "120",
                "max_height_min": "3750",
                "max_height_max": "4600",
                "insulated": "false",
                "load_bearing": "false",
                "stud_width": "70",
                "gypsum_layers_per_side": "2",
            }
        },
        {
            "id": "IWS-13i",
            "name": "Mellanvägg dubbel gips 70mm isolerad",
            "desc": "Mellanvägg med dubbel gipsskiva per sida, 70mm stålregel, min 30mm mineralull",
            "layers": "2x 12.5mm gipsskiva lätt | 70mm stålregel (min 30mm min.ull) | 2x 12.5mm gipsskiva lätt",
            "props": {
                "sound_reduction": "40",
                "thickness": "120",
                "max_height_min": "3750",
                "max_height_max": "4600",
                "insulated": "true",
                "load_bearing": "false",
                "stud_width": "70",
                "gypsum_layers_per_side": "2",
            }
        },
        {
            "id": "IWS-16",
            "name": "Skjutdörrsvägg 95mm",
            "desc": "Vägg vid skjutdörr, dubbel gips per sida, 95mm stålregel",
            "layers": "2x 12.5mm gipsskiva lätt | 95mm stålregel | 2x 12.5mm gipsskiva lätt",
            "props": {
                "sound_reduction": "40",
                "thickness": "145",
                "max_height_min": "5650",
                "max_height_max": "6000",
                "insulated": "false",
                "load_bearing": "false",
                "stud_width": "95",
                "gypsum_layers_per_side": "2",
            }
        },
        {
            "id": "IWS-16i",
            "name": "Skjutdörrsvägg 95mm isolerad",
            "desc": "Vägg vid skjutdörr, extra ljudisolerad vid tillval från kund. Min 30mm mineralull.",
            "layers": "2x 12.5mm gipsskiva lätt | 95mm stålregel (min 30mm min.ull) | 2x 12.5mm gipsskiva lätt",
            "props": {
                "sound_reduction": "44",
                "thickness": "145",
                "max_height_min": "5650",
                "max_height_max": "6000",
                "insulated": "true",
                "load_bearing": "false",
                "stud_width": "95",
                "gypsum_layers_per_side": "2",
            }
        },
    ]

    today = date.today().isoformat()

    for w in walls:
        # Building part
        c.execute(
            "INSERT INTO building_part VALUES (?,?,?,?,?)",
            (w["id"], w["name"], "IWS", "active", w["desc"])
        )
        # Version 1.0
        c.execute(
            """INSERT INTO building_part_version
               (building_part_id, version, valid_from, change_type,
                change_description, change_reason, trigger_category,
                decided_by, decided_date, layer_description)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (w["id"], "1.0", today, "new",
             "Initial import från D-0004649",
             "Uppbyggnad av masterdata MVP",
             "other", "Erik", today, w["layers"])
        )
        version_id = c.lastrowid
        # Properties
        for prop_id, val in w["props"].items():
            c.execute(
                "INSERT INTO version_property (version_id, property_id, value) VALUES (?,?,?)",
                (version_id, prop_id, val)
            )

    # --- Example Context Requirements ---
    contexts = [
        {
            "name": "Våtrum SE",
            "country": "SE",
            "room_type": "våtrum",
            "desc": "Krav på innerväggar i våtrum, Sverige",
            "reqs": {"sound_reduction": "35", "insulated": "true"}
        },
        {
            "name": "Sovrum SE",
            "country": "SE",
            "room_type": "sovrum",
            "desc": "Krav på innerväggar mellan sovrum, Sverige",
            "reqs": {"sound_reduction": "35"}
        },
        {
            "name": "Korridor SE",
            "country": "SE",
            "room_type": "korridor",
            "desc": "Krav på innerväggar i korridor, Sverige",
            "reqs": {"sound_reduction": "30"}
        },
        {
            "name": "Schakt SE (EI60)",
            "country": "SE",
            "room_type": "schakt",
            "desc": "Krav på innerväggar mot schakt med EI60, Sverige",
            "reqs": {"sound_reduction": "30", "fire_class": "EI60"}
        },
    ]

    for ctx in contexts:
        c.execute(
            """INSERT INTO context_requirement
               (name, system_family_id, country, room_type, description)
               VALUES (?,?,?,?,?)""",
            (ctx["name"], "IWS", ctx["country"], ctx["room_type"], ctx["desc"])
        )
        ctx_id = c.lastrowid
        for prop_id, val in ctx["reqs"].items():
            c.execute(
                """INSERT INTO context_requirement_property
                   (context_id, property_id, required_value)
                   VALUES (?,?,?)""",
                (ctx_id, prop_id, val)
            )

    conn.commit()
    conn.close()


def get_all_building_parts(system_family_id=None):
    conn = get_connection()
    if system_family_id:
        rows = conn.execute(
            """SELECT bp.*, bpv.version, bpv.id as version_id,
                      bpv.valid_from, bpv.layer_description,
                      bpv.change_type, bpv.change_description,
                      bpv.change_reason, bpv.decided_by, bpv.decided_date
               FROM building_part bp
               JOIN building_part_version bpv ON bp.id = bpv.building_part_id
               WHERE bp.system_family_id = ?
               ORDER BY bp.id, bpv.valid_from DESC""",
            (system_family_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT bp.*, bpv.version, bpv.id as version_id,
                      bpv.valid_from, bpv.layer_description,
                      bpv.change_type, bpv.change_description,
                      bpv.change_reason, bpv.decided_by, bpv.decided_date
               FROM building_part bp
               JOIN building_part_version bpv ON bp.id = bpv.building_part_id
               ORDER BY bp.id, bpv.valid_from DESC"""
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_version_properties(version_id):
    conn = get_connection()
    rows = conn.execute(
        """SELECT pd.id, pd.name, pd.unit, pd.data_type,
                  pd.comparison_operator, pd.hierarchy_order,
                  vp.value
           FROM version_property vp
           JOIN property_definition pd ON vp.property_id = pd.id
           WHERE vp.version_id = ?""",
        (version_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def filter_by_context(context_id):
    """Given a context requirement, return all building part versions that satisfy it."""
    conn = get_connection()

    # Get context requirements
    reqs = conn.execute(
        """SELECT crp.property_id, crp.required_value,
                  pd.data_type, pd.comparison_operator, pd.hierarchy_order
           FROM context_requirement_property crp
           JOIN property_definition pd ON crp.property_id = pd.id
           WHERE crp.context_id = ?""",
        (context_id,)
    ).fetchall()

    # Get context info
    ctx = conn.execute(
        "SELECT * FROM context_requirement WHERE id = ?", (context_id,)
    ).fetchone()

    # Get all active versions with their properties
    versions = conn.execute(
        """SELECT bpv.id as version_id, bp.id as part_id, bp.name,
                  bpv.version, bpv.layer_description, bp.status
           FROM building_part_version bpv
           JOIN building_part bp ON bpv.building_part_id = bp.id
           WHERE bp.system_family_id = ? AND bp.status = 'active'
           AND bpv.valid_to IS NULL""",
        (dict(ctx)["system_family_id"],)
    ).fetchall()

    matching = []
    for v in versions:
        v_dict = dict(v)
        props = conn.execute(
            """SELECT property_id, value FROM version_property
               WHERE version_id = ?""",
            (v_dict["version_id"],)
        ).fetchall()
        prop_map = {p["property_id"]: p["value"] for p in props}

        passes = True
        for req in reqs:
            req = dict(req)
            prop_val = prop_map.get(req["property_id"])
            if prop_val is None:
                passes = False
                break

            if req["comparison_operator"] == ">=":
                if float(prop_val) < float(req["required_value"]):
                    passes = False
                    break
            elif req["comparison_operator"] == "<=":
                if float(prop_val) > float(req["required_value"]):
                    passes = False
                    break
            elif req["comparison_operator"] == "exact":
                if prop_val.lower() != req["required_value"].lower():
                    passes = False
                    break
            elif req["comparison_operator"] == "hierarchy":
                hierarchy = json.loads(req["hierarchy_order"]) if req["hierarchy_order"] else []
                if hierarchy:
                    req_idx = hierarchy.index(req["required_value"]) if req["required_value"] in hierarchy else -1
                    val_idx = hierarchy.index(prop_val) if prop_val in hierarchy else -1
                    if val_idx < req_idx:
                        passes = False
                        break

        if passes:
            matching.append(v_dict)

    conn.close()
    return matching, dict(ctx), [dict(r) for r in reqs]


def get_all_contexts(system_family_id=None):
    conn = get_connection()
    if system_family_id:
        rows = conn.execute(
            "SELECT * FROM context_requirement WHERE system_family_id = ?",
            (system_family_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM context_requirement").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_property_definitions():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM property_definition").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def export_for_ids(system_family_id):
    """Export all active building parts with properties as JSON for IDS pipeline."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row  # ensure Row factory
    parts = conn.execute(
        """SELECT bp.id as part_id, bp.name, bp.status,
                  bpv.id as version_id, bpv.version, bpv.valid_from,
                  bpv.layer_description
           FROM building_part bp
           JOIN building_part_version bpv ON bp.id = bpv.building_part_id
           WHERE bp.system_family_id = ? AND bp.status = 'active'
           AND bpv.valid_to IS NULL""",
        (system_family_id,)
    ).fetchall()

    export = []
    for p in parts:
        p_dict = dict(p)
        # Convert date objects to strings for JSON serialization
        for k, v in p_dict.items():
            if isinstance(v, date):
                p_dict[k] = v.isoformat()
        props = conn.execute(
            """SELECT pd.id, pd.name, pd.unit, vp.value
               FROM version_property vp
               JOIN property_definition pd ON vp.property_id = pd.id
               WHERE vp.version_id = ?""",
            (p_dict["version_id"],)
        ).fetchall()
        p_dict["properties"] = {pr["id"]: {"value": pr["value"], "name": pr["name"], "unit": pr["unit"]} for pr in props}

        # Country variants
        variants = conn.execute(
            """SELECT cv.country, pd.id as property_id, pd.name as property_name,
                      cv.value, cv.note
               FROM country_variant cv
               JOIN property_definition pd ON cv.property_id = pd.id
               WHERE cv.version_id = ?""",
            (p_dict["version_id"],)
        ).fetchall()
        if variants:
            p_dict["country_variants"] = {}
            for cv in variants:
                cv = dict(cv)
                if cv["country"] not in p_dict["country_variants"]:
                    p_dict["country_variants"][cv["country"]] = {}
                p_dict["country_variants"][cv["country"]][cv["property_id"]] = cv["value"]

        export.append(p_dict)

    conn.close()
    return export


def add_building_part_version(building_part_id, version, change_type,
                               change_description, change_reason,
                               trigger_category, decided_by, layer_description,
                               properties):
    """Add a new version to an existing building part."""
    conn = get_connection()
    c = conn.cursor()
    today = date.today().isoformat()

    # Close previous version
    c.execute(
        """UPDATE building_part_version SET valid_to = ?
           WHERE building_part_id = ? AND valid_to IS NULL""",
        (today, building_part_id)
    )

    c.execute(
        """INSERT INTO building_part_version
           (building_part_id, version, valid_from, change_type,
            change_description, change_reason, trigger_category,
            decided_by, decided_date, layer_description)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (building_part_id, version, today, change_type,
         change_description, change_reason, trigger_category,
         decided_by, today, layer_description)
    )
    version_id = c.lastrowid

    for prop_id, val in properties.items():
        c.execute(
            "INSERT INTO version_property (version_id, property_id, value) VALUES (?,?,?)",
            (version_id, prop_id, val)
        )

    conn.commit()
    conn.close()
    return version_id


# ============================================================
# Project Configuration
# ============================================================

def create_project(project_id, name, country, room_types, description=""):
    """Create a new project configuration and auto-populate with matching building parts."""
    conn = get_connection()
    c = conn.cursor()
    today = date.today().isoformat()

    c.execute(
        "INSERT INTO project_configuration VALUES (?,?,?,?,?,?)",
        (project_id, name, country, today, 0, description)
    )

    # Store room types
    for rt in room_types:
        c.execute(
            "INSERT INTO project_room_type (project_id, room_type) VALUES (?,?)",
            (project_id, rt)
        )

    # Find all matching building parts via context requirements
    # Get all contexts matching this country + room types
    matched_version_ids = set()
    for rt in room_types:
        contexts = c.execute(
            """SELECT id FROM context_requirement
               WHERE (country = ? OR country IS NULL)
               AND (room_type = ? OR room_type IS NULL)""",
            (country, rt)
        ).fetchall()

        for ctx in contexts:
            # Use the filter logic to find matching parts
            reqs = c.execute(
                """SELECT crp.property_id, crp.required_value,
                          pd.data_type, pd.comparison_operator, pd.hierarchy_order
                   FROM context_requirement_property crp
                   JOIN property_definition pd ON crp.property_id = pd.id
                   WHERE crp.context_id = ?""",
                (ctx["id"],)
            ).fetchall()

            ctx_info = c.execute(
                "SELECT * FROM context_requirement WHERE id = ?", (ctx["id"],)
            ).fetchone()

            versions = c.execute(
                """SELECT bpv.id as version_id, bp.id as part_id
                   FROM building_part_version bpv
                   JOIN building_part bp ON bpv.building_part_id = bp.id
                   WHERE bp.system_family_id = ?
                   AND bp.status = 'active'
                   AND bpv.valid_to IS NULL""",
                (ctx_info["system_family_id"],)
            ).fetchall()

            for v in versions:
                props = c.execute(
                    "SELECT property_id, value FROM version_property WHERE version_id = ?",
                    (v["version_id"],)
                ).fetchall()
                prop_map = {p["property_id"]: p["value"] for p in props}

                passes = True
                for req in reqs:
                    prop_val = prop_map.get(req["property_id"])
                    if prop_val is None:
                        passes = False
                        break
                    if req["comparison_operator"] == ">=":
                        if float(prop_val) < float(req["required_value"]):
                            passes = False; break
                    elif req["comparison_operator"] == "<=":
                        if float(prop_val) > float(req["required_value"]):
                            passes = False; break
                    elif req["comparison_operator"] == "exact":
                        if prop_val.lower() != req["required_value"].lower():
                            passes = False; break
                    elif req["comparison_operator"] == "hierarchy":
                        hierarchy = json.loads(req["hierarchy_order"]) if req["hierarchy_order"] else []
                        if hierarchy:
                            req_idx = hierarchy.index(req["required_value"]) if req["required_value"] in hierarchy else -1
                            val_idx = hierarchy.index(prop_val) if prop_val in hierarchy else -1
                            if val_idx < req_idx:
                                passes = False; break

                if passes:
                    matched_version_ids.add((v["part_id"], v["version_id"]))

    # If no context requirements matched, include ALL active versions as fallback
    if not matched_version_ids:
        all_active = c.execute(
            """SELECT bp.id as part_id, bpv.id as version_id
               FROM building_part bp
               JOIN building_part_version bpv ON bp.id = bpv.building_part_id
               WHERE bp.status = 'active' AND bpv.valid_to IS NULL"""
        ).fetchall()
        matched_version_ids = {(r["part_id"], r["version_id"]) for r in all_active}

    # Insert matched parts, locked to current versions
    for part_id, version_id in matched_version_ids:
        c.execute(
            """INSERT OR IGNORE INTO project_building_part
               (project_id, building_part_id, locked_version_id, included)
               VALUES (?,?,?,1)""",
            (project_id, part_id, version_id)
        )

    conn.commit()
    conn.close()
    return project_id


def get_all_projects():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM project_configuration ORDER BY created_date DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_project_parts(project_id):
    conn = get_connection()
    rows = conn.execute(
        """SELECT pbp.*, bp.name as part_name, bp.status,
                  bpv.version, bpv.valid_from, bpv.layer_description,
                  bpv.valid_to
           FROM project_building_part pbp
           JOIN building_part bp ON pbp.building_part_id = bp.id
           JOIN building_part_version bpv ON pbp.locked_version_id = bpv.id
           WHERE pbp.project_id = ?
           ORDER BY pbp.building_part_id""",
        (project_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_project_room_types(project_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT room_type FROM project_room_type WHERE project_id = ?",
        (project_id,)
    ).fetchall()
    conn.close()
    return [r["room_type"] for r in rows]


def lock_project(project_id):
    conn = get_connection()
    conn.execute(
        "UPDATE project_configuration SET locked = 1 WHERE id = ?",
        (project_id,)
    )
    conn.commit()
    conn.close()


def toggle_project_part(project_id, building_part_id, included):
    conn = get_connection()
    conn.execute(
        """UPDATE project_building_part SET included = ?
           WHERE project_id = ? AND building_part_id = ?""",
        (included, project_id, building_part_id)
    )
    conn.commit()
    conn.close()


def check_project_upgrades(project_id):
    """Check if any locked versions have been superseded by newer versions."""
    conn = get_connection()
    parts = conn.execute(
        """SELECT pbp.building_part_id, pbp.locked_version_id,
                  bpv_locked.version as locked_version,
                  bpv_latest.id as latest_version_id,
                  bpv_latest.version as latest_version,
                  bpv_latest.change_description
           FROM project_building_part pbp
           JOIN building_part_version bpv_locked ON pbp.locked_version_id = bpv_locked.id
           LEFT JOIN building_part_version bpv_latest
             ON bpv_latest.building_part_id = pbp.building_part_id
             AND bpv_latest.valid_to IS NULL
           WHERE pbp.project_id = ? AND pbp.included = 1
           AND bpv_latest.id != pbp.locked_version_id""",
        (project_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in parts]


def upgrade_project_part(project_id, building_part_id):
    """Upgrade a project's building part to the latest active version."""
    conn = get_connection()
    latest = conn.execute(
        """SELECT bpv.id FROM building_part_version bpv
           WHERE bpv.building_part_id = ? AND bpv.valid_to IS NULL""",
        (building_part_id,)
    ).fetchone()
    if latest:
        conn.execute(
            """UPDATE project_building_part SET locked_version_id = ?
               WHERE project_id = ? AND building_part_id = ?""",
            (latest["id"], project_id, building_part_id)
        )
    conn.commit()
    conn.close()
