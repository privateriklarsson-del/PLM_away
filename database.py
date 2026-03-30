"""
JM Byggdelar Masterdata — Database
====================================
Core masterdata: building parts, properties, context rules,
junction details, and governance logging.
"""

import sqlite3
import json
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).parent / "masterdata.db"


def get_connection():
    conn = sqlite3.connect(str(DB_PATH), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ============================================================
# Schema
# ============================================================

def init_db():
    conn = get_connection()
    c = conn.cursor()

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
            hierarchy_order TEXT
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
            layer_description TEXT,
            -- Governance log (Typ 2)
            change_type TEXT NOT NULL CHECK(change_type IN ('new', 'major_change', 'phase_out')),
            change_description TEXT NOT NULL,
            change_reason TEXT NOT NULL,
            trigger_category TEXT CHECK(trigger_category IN (
                'regulatory', 'cost', 'quality_issue', 'simplification',
                'supplier_change', 'custom', 'other'
            )),
            custom_trigger_text TEXT,
            decided_by TEXT NOT NULL,
            decided_date DATE NOT NULL,
            UNIQUE(building_part_id, version)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS version_property (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL REFERENCES building_part_version(id),
            property_id TEXT NOT NULL REFERENCES property_definition(id),
            value TEXT NOT NULL,
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
            country TEXT,
            room_type TEXT,
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
        CREATE TABLE IF NOT EXISTS junction_detail (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            system_family_id TEXT NOT NULL REFERENCES system_family(id),
            part_a_id TEXT NOT NULL REFERENCES building_part(id),
            part_b_id TEXT NOT NULL REFERENCES building_part(id),
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'phased_out')),
            description TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS junction_detail_version (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            junction_id TEXT NOT NULL REFERENCES junction_detail(id),
            version TEXT NOT NULL,
            valid_from DATE NOT NULL,
            valid_to DATE,
            category TEXT NOT NULL CHECK(category IN (
                'brand', 'ljud', 'fukt', 'luft', 'generell'
            )),
            context TEXT,
            detail_description TEXT NOT NULL,
            detail_document_ref TEXT,
            change_type TEXT NOT NULL CHECK(change_type IN ('new', 'major_change', 'phase_out')),
            change_description TEXT NOT NULL,
            change_reason TEXT NOT NULL,
            trigger_category TEXT CHECK(trigger_category IN (
                'regulatory', 'cost', 'quality_issue', 'simplification',
                'supplier_change', 'custom', 'other'
            )),
            custom_trigger_text TEXT,
            decided_by TEXT NOT NULL,
            decided_date DATE NOT NULL,
            UNIQUE(junction_id, version)
        )
    """)

    conn.commit()
    conn.close()


# ============================================================
# Seed Data
# ============================================================

def seed_data():
    conn = get_connection()
    c = conn.cursor()

    if c.execute("SELECT COUNT(*) FROM system_family").fetchone()[0] > 0:
        conn.close()
        return

    today = date.today().isoformat()

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
    c.executemany("INSERT INTO property_definition VALUES (?,?,?,?,?,?)", properties)

    # --- System Families ---
    c.execute("INSERT INTO system_family VALUES (?,?,?,?,?)",
        ("IWS", "Icke bärande innerväggar (stålregel)", "Erik",
         "R-10001", "Mellanväggar med stålregelstomme enligt D-0004649"))
    c.execute("INSERT INTO system_family VALUES (?,?,?,?,?)",
        ("EWS", "Ytterväggar (stålregel)", "Erik", "R-10002", "Ytterväggar"))
    c.execute("INSERT INTO system_family VALUES (?,?,?,?,?)",
        ("FLR", "Bjälklag", "Erik", "R-10003", "Bjälklag"))

    # --- Building Parts (IWS) ---
    walls = [
        ("IWS-10", "Vägg limmas mot betong", "Enkel gipsskiva limmad mot betongvägg",
         "12.5mm gipsskiva lätt, limmas mot betong med sättlim",
         {"sound_reduction":"30","thickness":"12.5","max_height_min":"3550","max_height_max":"4400",
          "insulated":"false","load_bearing":"false","stud_width":"0","gypsum_layers_per_side":"1"}),
        ("IWS-03", "Standard mellanvägg 70mm", "Standard mellanvägg med 70mm stålregel",
         "12.5mm gipsskiva lätt | 70mm stålregel | 12.5mm gipsskiva lätt",
         {"sound_reduction":"35","thickness":"95","max_height_min":"3550","max_height_max":"4400",
          "insulated":"false","load_bearing":"false","stud_width":"70","gypsum_layers_per_side":"1"}),
        ("IWS-03i", "Mellanvägg 70mm isolerad", "Extra ljudisolerad vägg vid WC/sovrum. Min 30mm mineralull.",
         "12.5mm gipsskiva lätt | 70mm stålregel (min 30mm min.ull) | 12.5mm gipsskiva lätt",
         {"sound_reduction":"35","thickness":"95","max_height_min":"3550","max_height_max":"4400",
          "insulated":"true","load_bearing":"false","stud_width":"70","gypsum_layers_per_side":"1"}),
        ("IWS-06", "El-/IT-central vägg", "Vägg vid el-/IT-central, 95mm stålregel",
         "12.5mm gipsskiva lätt | 95mm stålregel | 12.5mm gipsskiva lätt",
         {"sound_reduction":"30","thickness":"120","max_height_min":"5500","max_height_max":"5500",
          "insulated":"false","load_bearing":"false","stud_width":"95","gypsum_layers_per_side":"1"}),
        ("IWS-13", "Mellanvägg dubbel gips 70mm", "Dubbel gipsskiva per sida, 70mm stålregel",
         "2x 12.5mm gipsskiva lätt | 70mm stålregel | 2x 12.5mm gipsskiva lätt",
         {"sound_reduction":"35","thickness":"120","max_height_min":"3750","max_height_max":"4600",
          "insulated":"false","load_bearing":"false","stud_width":"70","gypsum_layers_per_side":"2"}),
        ("IWS-13i", "Mellanvägg dubbel gips 70mm isolerad", "Dubbel gips, 70mm regel, min 30mm mineralull",
         "2x 12.5mm gipsskiva lätt | 70mm stålregel (min 30mm min.ull) | 2x 12.5mm gipsskiva lätt",
         {"sound_reduction":"40","thickness":"120","max_height_min":"3750","max_height_max":"4600",
          "insulated":"true","load_bearing":"false","stud_width":"70","gypsum_layers_per_side":"2"}),
        ("IWS-16", "Skjutdörrsvägg 95mm", "Dubbel gips per sida, 95mm stålregel, vid skjutdörr",
         "2x 12.5mm gipsskiva lätt | 95mm stålregel | 2x 12.5mm gipsskiva lätt",
         {"sound_reduction":"40","thickness":"145","max_height_min":"5650","max_height_max":"6000",
          "insulated":"false","load_bearing":"false","stud_width":"95","gypsum_layers_per_side":"2"}),
        ("IWS-16i", "Skjutdörrsvägg 95mm isolerad", "Skjutdörrsvägg, extra ljudisolerad. Min 30mm mineralull.",
         "2x 12.5mm gipsskiva lätt | 95mm stålregel (min 30mm min.ull) | 2x 12.5mm gipsskiva lätt",
         {"sound_reduction":"44","thickness":"145","max_height_min":"5650","max_height_max":"6000",
          "insulated":"true","load_bearing":"false","stud_width":"95","gypsum_layers_per_side":"2"}),
    ]

    for w_id, w_name, w_desc, w_layers, w_props in walls:
        c.execute("INSERT INTO building_part VALUES (?,?,?,?,?)",
            (w_id, w_name, "IWS", "active", w_desc))
        c.execute(
            """INSERT INTO building_part_version
               (building_part_id, version, valid_from, change_type,
                change_description, change_reason, trigger_category,
                custom_trigger_text, decided_by, decided_date, layer_description)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (w_id, "1.0", today, "new", "Initial import från D-0004649",
             "Uppbyggnad av masterdata MVP", "other", None, "Erik", today, w_layers))
        vid = c.lastrowid
        for prop_id, val in w_props.items():
            c.execute("INSERT INTO version_property (version_id, property_id, value) VALUES (?,?,?)",
                (vid, prop_id, val))

    # --- Placeholder parts for junctions ---
    for pid, pname, fam, pdesc in [
        ("EW-01", "Yttervägg puts", "EWS", "Standard yttervägg med puts"),
        ("EW-02", "Yttervägg tegel", "EWS", "Standard yttervägg med tegelfasad"),
        ("FL-01", "Bjälklag standard", "FLR", "Standard bjälklag betong"),
    ]:
        c.execute("INSERT INTO building_part VALUES (?,?,?,?,?)", (pid, pname, fam, "active", pdesc))
        c.execute(
            """INSERT INTO building_part_version
               (building_part_id, version, valid_from, change_type,
                change_description, change_reason, trigger_category,
                custom_trigger_text, decided_by, decided_date, layer_description)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, "1.0", today, "new", "Platshållare", "MVP seed", "other", None, "Erik", today, "Se dokumentation"))

    # --- Context Requirements ---
    for ctx_name, country, room, desc, reqs in [
        ("Våtrum SE", "SE", "våtrum", "Krav på innerväggar i våtrum, Sverige",
         {"sound_reduction": "35", "insulated": "true"}),
        ("Sovrum SE", "SE", "sovrum", "Krav på innerväggar mellan sovrum, Sverige",
         {"sound_reduction": "35"}),
        ("Korridor SE", "SE", "korridor", "Krav på innerväggar i korridor, Sverige",
         {"sound_reduction": "30"}),
        ("Schakt SE (EI60)", "SE", "schakt", "Krav på innerväggar mot schakt med EI60, Sverige",
         {"sound_reduction": "30", "fire_class": "EI60"}),
    ]:
        c.execute("INSERT INTO context_requirement (name, system_family_id, country, room_type, description) VALUES (?,?,?,?,?)",
            (ctx_name, "IWS", country, room, desc))
        ctx_id = c.lastrowid
        for prop_id, val in reqs.items():
            c.execute("INSERT INTO context_requirement_property (context_id, property_id, required_value) VALUES (?,?,?)",
                (ctx_id, prop_id, val))

    # --- Junction Details ---
    for j_id, j_name, pa, pb, cat, ctx, detail, doc_ref in [
        ("JD-IWS03-EW01-001", "Innervägg IWS-03 mot yttervägg EW-01 (generell)",
         "IWS-03", "EW-01", "generell", None,
         "Anslutning innervägg mot yttervägg. Stålregel infäst i ytterväggskonstruktion. "
         "Gipsskiva dras förbi anslutningspunkt min 50mm. Mineralull fylls till tätning.",
         "D-0005001_IWS03-EW01_generell.pdf"),
        ("JD-IWS03-EW01-002", "Innervägg IWS-03 mot yttervägg EW-01 (våtrum)",
         "IWS-03", "EW-01", "fukt", "våtrum",
         "Anslutning i våtrum. Tätskikt ska föras obrutet över anslutningen. "
         "Avstånd gipsskiva till golv min 10mm. Fogmassa i överkant.",
         "D-0005002_IWS03-EW01_vatrum.pdf"),
        ("JD-IWS03-FL01-001", "Innervägg IWS-03 mot bjälklag FL-01",
         "IWS-03", "FL-01", "ljud", None,
         "Underskena monteras med akustisk remsa (min 3mm). "
         "Gipsskiva ska inte ha kontakt med bjälklag — min 5mm luft.",
         "D-0005003_IWS03-FL01_ljud.pdf"),
        ("JD-IWS13-EW01-001", "Innervägg IWS-13 mot yttervägg EW-01 (brand EI30)",
         "IWS-13", "EW-01", "brand", None,
         "Båda gipsskikten ska dras förbi anslutning utan fog i brandcellsgräns. "
         "Mineralull tätning i regel.",
         "D-0005004_IWS13-EW01_brand.pdf"),
        ("JD-IWS16-FL01-001", "Skjutdörrsvägg IWS-16 mot bjälklag FL-01",
         "IWS-16", "FL-01", "generell", None,
         "Förstärkt överskena krävs pga dubbel gips + skjutdörrsbeslag. "
         "Max spännvidd enligt tillverkarens anvisning.",
         "D-0005005_IWS16-FL01_generell.pdf"),
    ]:
        c.execute("INSERT INTO junction_detail VALUES (?,?,?,?,?,?,?)",
            (j_id, j_name, "IWS", pa, pb, "active", None))
        c.execute(
            """INSERT INTO junction_detail_version
               (junction_id, version, valid_from, category, context,
                detail_description, detail_document_ref,
                change_type, change_description, change_reason,
                trigger_category, custom_trigger_text, decided_by, decided_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (j_id, "1.0", today, cat, ctx, detail, doc_ref,
             "new", "Initial import", "MVP seed", "other", None, "Erik", today))

    conn.commit()
    conn.close()


# ============================================================
# Queries — Building Parts
# ============================================================

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
            (system_family_id,)).fetchall()
    else:
        rows = conn.execute(
            """SELECT bp.*, bpv.version, bpv.id as version_id,
                      bpv.valid_from, bpv.layer_description,
                      bpv.change_type, bpv.change_description,
                      bpv.change_reason, bpv.decided_by, bpv.decided_date
               FROM building_part bp
               JOIN building_part_version bpv ON bp.id = bpv.building_part_id
               ORDER BY bp.id, bpv.valid_from DESC""").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_version_properties(version_id):
    conn = get_connection()
    rows = conn.execute(
        """SELECT pd.id, pd.name, pd.unit, pd.data_type,
                  pd.comparison_operator, pd.hierarchy_order, vp.value
           FROM version_property vp
           JOIN property_definition pd ON vp.property_id = pd.id
           WHERE vp.version_id = ?""",
        (version_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_property_definitions():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM property_definition").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_building_part_version(building_part_id, version, change_type,
                               change_description, change_reason,
                               trigger_category, decided_by, layer_description,
                               properties, custom_trigger_text=None):
    """Add a new version to an existing building part."""
    conn = get_connection()
    c = conn.cursor()
    today = date.today().isoformat()

    c.execute("UPDATE building_part_version SET valid_to = ? WHERE building_part_id = ? AND valid_to IS NULL",
        (today, building_part_id))

    c.execute(
        """INSERT INTO building_part_version
           (building_part_id, version, valid_from, change_type,
            change_description, change_reason, trigger_category,
            custom_trigger_text, decided_by, decided_date, layer_description)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (building_part_id, version, today, change_type,
         change_description, change_reason, trigger_category,
         custom_trigger_text, decided_by, today, layer_description))
    version_id = c.lastrowid

    for prop_id, val in properties.items():
        c.execute("INSERT INTO version_property (version_id, property_id, value) VALUES (?,?,?)",
            (version_id, prop_id, val))

    conn.commit()
    conn.close()
    return version_id


# ============================================================
# Queries — Context Filtering
# ============================================================

def get_all_contexts(system_family_id=None):
    conn = get_connection()
    if system_family_id:
        rows = conn.execute("SELECT * FROM context_requirement WHERE system_family_id = ?",
            (system_family_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM context_requirement").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def filter_by_context(context_id):
    """Given a context requirement, return all building part versions that satisfy it."""
    conn = get_connection()

    reqs = conn.execute(
        """SELECT crp.property_id, crp.required_value,
                  pd.data_type, pd.comparison_operator, pd.hierarchy_order
           FROM context_requirement_property crp
           JOIN property_definition pd ON crp.property_id = pd.id
           WHERE crp.context_id = ?""", (context_id,)).fetchall()

    ctx = dict(conn.execute("SELECT * FROM context_requirement WHERE id = ?", (context_id,)).fetchone())

    versions = conn.execute(
        """SELECT bpv.id as version_id, bp.id as part_id, bp.name,
                  bpv.version, bpv.layer_description, bp.status
           FROM building_part_version bpv
           JOIN building_part bp ON bpv.building_part_id = bp.id
           WHERE bp.system_family_id = ? AND bp.status = 'active' AND bpv.valid_to IS NULL""",
        (ctx["system_family_id"],)).fetchall()

    matching = []
    for v in versions:
        v_dict = dict(v)
        props = conn.execute("SELECT property_id, value FROM version_property WHERE version_id = ?",
            (v_dict["version_id"],)).fetchall()
        prop_map = {p["property_id"]: p["value"] for p in props}

        passes = True
        for req in reqs:
            req = dict(req)
            prop_val = prop_map.get(req["property_id"])
            if prop_val is None:
                passes = False; break
            if req["comparison_operator"] == ">=":
                if float(prop_val) < float(req["required_value"]): passes = False; break
            elif req["comparison_operator"] == "<=":
                if float(prop_val) > float(req["required_value"]): passes = False; break
            elif req["comparison_operator"] == "exact":
                if prop_val.lower() != req["required_value"].lower(): passes = False; break
            elif req["comparison_operator"] == "hierarchy":
                hierarchy = json.loads(req["hierarchy_order"]) if req["hierarchy_order"] else []
                if hierarchy:
                    req_idx = hierarchy.index(req["required_value"]) if req["required_value"] in hierarchy else -1
                    val_idx = hierarchy.index(prop_val) if prop_val in hierarchy else -1
                    if val_idx < req_idx: passes = False; break
        if passes:
            matching.append(v_dict)

    conn.close()
    return matching, ctx, [dict(r) for r in reqs]


# ============================================================
# Queries — Junction Details
# ============================================================

CATEGORY_LABELS = {
    "brand": "Brand", "ljud": "Ljud", "fukt": "Fukt",
    "luft": "Luft", "generell": "Generell",
}


def get_all_junctions(system_family_id=None, part_filter=None):
    conn = get_connection()
    query = """
        SELECT jd.*, jdv.version, jdv.id as version_id,
               jdv.valid_from, jdv.valid_to, jdv.category, jdv.context,
               jdv.detail_description, jdv.detail_document_ref,
               jdv.change_type, jdv.change_description, jdv.change_reason,
               jdv.decided_by, jdv.decided_date,
               bp_a.name as part_a_name, bp_b.name as part_b_name
        FROM junction_detail jd
        JOIN junction_detail_version jdv ON jd.id = jdv.junction_id
        JOIN building_part bp_a ON jd.part_a_id = bp_a.id
        JOIN building_part bp_b ON jd.part_b_id = bp_b.id
        WHERE jdv.valid_to IS NULL
    """
    params = []
    if system_family_id:
        query += " AND jd.system_family_id = ?"; params.append(system_family_id)
    if part_filter:
        query += " AND (jd.part_a_id = ? OR jd.part_b_id = ?)"; params.extend([part_filter, part_filter])
    query += " ORDER BY jd.part_a_id, jd.part_b_id, jdv.category"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_junction_version_history(junction_id):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM junction_detail_version WHERE junction_id = ? ORDER BY valid_from DESC",
        (junction_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_junctions_for_part(building_part_id):
    return get_all_junctions(part_filter=building_part_id)


def get_junction_pairs():
    conn = get_connection()
    rows = conn.execute(
        """SELECT DISTINCT jd.part_a_id, bp_a.name as part_a_name,
                  jd.part_b_id, bp_b.name as part_b_name,
                  COUNT(jd.id) as detail_count
           FROM junction_detail jd
           JOIN building_part bp_a ON jd.part_a_id = bp_a.id
           JOIN building_part bp_b ON jd.part_b_id = bp_b.id
           WHERE jd.status = 'active'
           GROUP BY jd.part_a_id, jd.part_b_id
           ORDER BY jd.part_a_id, jd.part_b_id""").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_junction_detail(junction_id, name, system_family_id, part_a_id, part_b_id,
                        version, category, context, detail_description,
                        detail_document_ref, change_description, change_reason,
                        trigger_category, decided_by, custom_trigger_text=None):
    conn = get_connection()
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute("INSERT INTO junction_detail VALUES (?,?,?,?,?,?,?)",
        (junction_id, name, system_family_id, part_a_id, part_b_id, "active", None))
    c.execute(
        """INSERT INTO junction_detail_version
           (junction_id, version, valid_from, category, context,
            detail_description, detail_document_ref,
            change_type, change_description, change_reason,
            trigger_category, custom_trigger_text, decided_by, decided_date)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (junction_id, version, today, category, context, detail_description, detail_document_ref,
         "new", change_description, change_reason, trigger_category, custom_trigger_text, decided_by, today))
    conn.commit()
    conn.close()
