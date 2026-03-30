"""
JM Byggdelar Masterdata MVP
============================
Byggdelsdatabas med versionshantering, kontextregler,
mötesdetaljer och governance-logg.
"""

import streamlit as st
import pandas as pd
from database import (
    init_db, seed_data,
    get_all_building_parts, get_version_properties,
    get_all_property_definitions, add_building_part_version,
    filter_by_context, get_all_contexts,
    get_all_junctions, get_junction_version_history, add_junction_detail,
    get_junctions_for_part, get_junction_pairs,
    CATEGORY_LABELS
)

st.set_page_config(page_title="JM Byggdelar Masterdata", page_icon="🏗️", layout="wide")

init_db()
seed_data()

# ============================================================
# Navigation
# ============================================================
st.sidebar.title("🏗️ JM Masterdata")
st.sidebar.markdown("*Governance & Masterdata*")

page = st.sidebar.radio("Navigering", [
    "Byggdelar",
    "Detaljer (möten)",
    "Kontextregler",
    "Egenskapsdefinitioner",
    "Governance-logg",
], label_visibility="collapsed")

# ============================================================
# Dark theme
# ============================================================
st.markdown("""
<style>
    .stMainBlockContainer { background-color: #1a1a2e; color: #e0e0e0; }
    .stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown h1,
    .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 { color: #e0e0e0 !important; }
    .stMarkdown h1 { color: #ffffff !important; }
    .stMarkdown h2, .stMarkdown h3 { color: #b8c5d6 !important; }
    .stCaption, .stCaption p { color: #8899aa !important; }
    div[data-testid="stInfo"] { background-color: #16213e; border-color: #0f3460; }
    div[data-testid="stInfo"] p { color: #a8c0d8 !important; }
    div[data-testid="stExpander"] { background-color: #16213e; border-color: #2a2a4a; }
    div[data-testid="stExpander"] summary span,
    div[data-testid="stExpander"] p { color: #c0c8d8 !important; }
    div[data-testid="element-container"] > div[style*="border"] {
        background-color: #16213e !important; border-color: #2a2a4a !important; }
    .stDataFrame { background-color: #16213e; }
    .stTabs [data-baseweb="tab"] { color: #8899aa; }
    .stTabs [aria-selected="true"] { color: #ffffff !important; }
    div[data-testid="stSuccess"] { background-color: #0a2e1a; border-color: #1a5c34; }
    div[data-testid="stWarning"] { background-color: #2e2a0a; border-color: #5c4a1a; }
    div[data-testid="stError"] { background-color: #2e0a0a; border-color: #5c1a1a; }
    hr { border-color: #2a2a4a !important; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# PAGE: Byggdelar
# ============================================================
if page == "Byggdelar":
    st.title("Byggdelar — Icke bärande innerväggar")
    st.caption("SystemFamily: IWS · Källa: D-0004649")

    st.info(
        "**Byggdelsregistret** innehåller alla registrerade byggdelar inom en systemfamilj. "
        "Varje byggdel har en aktiv version med definierade egenskaper och uppbyggnad. "
        "En ny version kräver alltid motivering — det är governance-loggen som gör "
        "att vi kan spåra varför en förändring gjordes."
    )

    parts = get_all_building_parts("IWS")

    if not parts:
        st.warning("Inga byggdelar hittade.")
    else:
        summary = []
        for p in parts:
            props = get_version_properties(p["version_id"])
            pm = {pr["id"]: pr["value"] for pr in props}
            summary.append({
                "ID": p["id"], "Namn": p["name"], "Version": p["version"],
                "Tjocklek (mm)": pm.get("thickness", ""),
                "R'w (dB)": pm.get("sound_reduction", ""),
                "Max höjd min": pm.get("max_height_min", ""),
                "Max höjd max": pm.get("max_height_max", ""),
                "Isolerad": "✅" if pm.get("insulated") == "true" else "❌",
                "Regel (mm)": pm.get("stud_width", ""),
                "Gips/sida": pm.get("gypsum_layers_per_side", ""),
                "Status": p["status"],
            })
        st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)

        # Detail view
        st.markdown("---")
        st.subheader("Detaljer & versionshantering")
        selected_id = st.selectbox("Välj byggdel", [p["id"] for p in parts],
            format_func=lambda x: f"{x} — {next(p['name'] for p in parts if p['id'] == x)}")

        sel = next(p for p in parts if p["id"] == selected_id)
        props = get_version_properties(sel["version_id"])

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**{sel['id']}** — {sel['name']}")
            st.markdown(f"*{sel['description']}*")
            st.markdown(f"**Version:** {sel['version']} (giltig från {sel['valid_from']})")
            st.markdown(f"**Uppbyggnad:** `{sel['layer_description']}`")
        with col2:
            st.markdown("**Egenskaper:**")
            for pr in props:
                unit = f" {pr['unit']}" if pr['unit'] else ""
                val = "Ja" if pr['data_type'] == 'boolean' and pr['value'] == "true" else \
                      "Nej" if pr['data_type'] == 'boolean' else pr['value']
                st.markdown(f"- {pr['name']}: **{val}{unit}**")

        # Related junctions
        related = get_junctions_for_part(selected_id)
        if related:
            st.markdown("---")
            st.markdown(f"**Mötesdetaljer som involverar {selected_id}** ({len(related)} st)")
            for rj in related:
                other = rj["part_b_id"] if rj["part_a_id"] == selected_id else rj["part_a_id"]
                cat_icon = {"brand":"🔥","ljud":"🔊","fukt":"💧","luft":"💨","generell":"🔧"}.get(rj["category"],"📋")
                ctx = f" ({rj['context']})" if rj.get("context") else ""
                st.markdown(f"- {cat_icon} {selected_id} ↔ **{other}** — {CATEGORY_LABELS.get(rj['category'], rj['category'])}{ctx}")

        # New version form
        st.markdown("---")
        with st.expander("➕ Skapa ny version"):
            st.caption(
                "En ny version stänger den föregående och loggar beslutet permanent. "
                "Fyll i vad som ändrats och varför."
            )
            with st.form(f"new_version_{selected_id}"):
                st.markdown(f"Ny version av **{selected_id}**")
                new_version = st.text_input("Versionsnummer", value="1.1")
                change_type = st.selectbox("Ändringstyp", ["major_change", "new", "phase_out"],
                    format_func=lambda x: {"major_change":"Väsentlig ändring","new":"Ny byggdel","phase_out":"Avveckling"}.get(x,x))
                change_desc = st.text_area("Beskrivning av ändring", help="Vad ändrades tekniskt?")
                change_reason = st.text_area("Beslutsmotivering", help="Varför — loggas permanent.")
                trigger = st.selectbox("Utlösande faktor", [
                    "regulatory","cost","quality_issue","simplification","supplier_change","custom","other"
                ], format_func=lambda x: {
                    "regulatory":"🔴 Myndighetskrav","cost":"🟡 Kostnad",
                    "quality_issue":"🟠 Kvalitetsavvikelse","simplification":"🟡 Förenkling",
                    "supplier_change":"🟡 Leverantörsbyte","custom":"🟡 Fri orsak","other":"🟡 Övrigt",
                }.get(x,x))
                custom_trigger = st.text_input("Fri orsak (valfritt)", placeholder="T.ex. 'Inte köpt detta än'")
                decided_by = st.text_input("Beslutare", value="Erik")
                layer_desc = st.text_input("Uppbyggnad", value=sel["layer_description"])

                st.markdown("**Egenskaper:**")
                new_props = {}
                prop_defs = get_all_property_definitions()
                current = {pr["id"]: pr["value"] for pr in props}
                for pd_item in prop_defs:
                    unit_label = f" ({pd_item['unit']})" if pd_item["unit"] else ""
                    new_props[pd_item["id"]] = st.text_input(
                        f"{pd_item['name']}{unit_label}", value=current.get(pd_item["id"], ""),
                        key=f"prop_{selected_id}_{pd_item['id']}")

                submitted = st.form_submit_button("Skapa version")
                if submitted and change_desc and change_reason:
                    add_building_part_version(selected_id, new_version, change_type,
                        change_desc, change_reason, trigger, decided_by, layer_desc, new_props,
                        custom_trigger_text=custom_trigger if custom_trigger else None)
                    st.success(f"Version {new_version} skapad för {selected_id}")
                    st.rerun()
                elif submitted:
                    st.error("Fyll i beskrivning och motivering (governance-krav).")


# ============================================================
# PAGE: Detaljer (möten)
# ============================================================
elif page == "Detaljer (möten)":
    st.title("Detaljer — möten mellan byggdelar")

    st.info(
        "**Mötesdetaljer** beskriver vad som händer när två byggdelar möts. "
        "Till skillnad från byggdelar (självständiga objekt) är detaljer *relationer* — "
        "de är meningslösa utan de två delarna de kopplar.\n\n"
        "Varje detalj har en kategori (brand, ljud, fukt, luft, generell) och kan vara "
        "kontextberoende (t.ex. bara i våtrum). Samma governance-logg som byggdelar."
    )

    tab_browse, tab_matrix, tab_new = st.tabs(["Bläddra", "Mötesmatris", "Skapa ny detalj"])

    with tab_browse:
        fcol1, fcol2 = st.columns(2)
        with fcol1:
            all_parts = get_all_building_parts()
            part_ids = sorted(set(p["id"] for p in all_parts))
            filter_part = st.selectbox("Filtrera på byggdel", ["Alla"] + part_ids)
        with fcol2:
            filter_cat = st.selectbox("Filtrera på kategori", ["Alla"] + list(CATEGORY_LABELS.keys()),
                format_func=lambda x: "Alla" if x == "Alla" else CATEGORY_LABELS.get(x, x))

        junctions = get_all_junctions(part_filter=filter_part if filter_part != "Alla" else None)
        if filter_cat != "Alla":
            junctions = [j for j in junctions if j["category"] == filter_cat]

        if not junctions:
            st.info("Inga detaljer matchar filtret.")
        else:
            st.markdown(f"**{len(junctions)} detaljer**")
            for j in junctions:
                cat_icon = {"brand":"🔥","ljud":"🔊","fukt":"💧","luft":"💨","generell":"🔧"}.get(j["category"],"📋")
                ctx_label = f" · *{j['context']}*" if j.get("context") else ""
                with st.container(border=True):
                    jcol1, jcol2 = st.columns([3, 1])
                    with jcol1:
                        st.markdown(f"{cat_icon} **{j['part_a_id']}** ↔ **{j['part_b_id']}** — "
                            f"{CATEGORY_LABELS.get(j['category'], j['category'])}{ctx_label}")
                        st.markdown(f"*{j['name']}*")
                        st.markdown(j["detail_description"])
                    with jcol2:
                        st.caption(f"v{j['version']} · {j['valid_from']}")
                        if j.get("detail_document_ref"):
                            st.caption(f"📄 {j['detail_document_ref']}")
                    with st.expander("Versionshistorik"):
                        for h in get_junction_version_history(j["id"]):
                            active = "✅ Aktiv" if h.get("valid_to") is None else f"Ersatt {h['valid_to']}"
                            st.markdown(f"**v{h['version']}** ({active}) — {h['change_description']} · "
                                f"*{h['change_reason']}* · {h['decided_by']} {h['decided_date']}")

    with tab_matrix:
        st.caption("Vilka byggdelspar har definierade detaljer. Siffran anger antal detaljtyper per par.")
        pairs = get_junction_pairs()
        if not pairs:
            st.info("Inga detaljer registrerade.")
        else:
            st.dataframe(pd.DataFrame([{
                "Del A": f"{p['part_a_id']} ({p['part_a_name']})",
                "Del B": f"{p['part_b_id']} ({p['part_b_name']})",
                "Antal detaljer": p["detail_count"],
            } for p in pairs]), use_container_width=True, hide_index=True)

            parts_with = set()
            for p in pairs:
                parts_with.add(p["part_a_id"]); parts_with.add(p["part_b_id"])
            active = sorted(set(p["id"] for p in get_all_building_parts() if p["status"] == "active"))
            missing = [pid for pid in active if pid not in parts_with]
            if missing:
                st.warning(f"Byggdelar utan mötesdetaljer: {', '.join(missing)}")

    with tab_new:
        st.caption("Skapa en ny mötesdetalj mellan två byggdelar.")
        with st.form("new_junction"):
            parts_list = sorted(set(p["id"] for p in get_all_building_parts()))
            jcol1, jcol2 = st.columns(2)
            with jcol1: part_a = st.selectbox("Byggdel A", parts_list, key="jd_a")
            with jcol2: part_b = st.selectbox("Byggdel B", parts_list, key="jd_b", index=min(1, len(parts_list)-1))
            jd_name = st.text_input("Namn", placeholder="Innervägg IWS-03 mot yttervägg EW-01 (brand)")
            jd_id = st.text_input("Detalj-ID", placeholder="JD-IWS03-EW01-003")
            jd_cat = st.selectbox("Kategori", list(CATEGORY_LABELS.keys()),
                format_func=lambda x: CATEGORY_LABELS.get(x, x))
            jd_ctx = st.text_input("Kontext (valfritt)", placeholder="våtrum, schakt...")
            jd_desc = st.text_area("Utförandebeskrivning")
            jd_doc = st.text_input("Dokumentreferens (valfritt)", placeholder="D-0005006.pdf")
            jd_reason = st.text_area("Beslutsmotivering")
            jd_by = st.text_input("Beslutare", value="Erik")
            if st.form_submit_button("Skapa detalj"):
                if jd_id and jd_name and jd_desc and jd_reason:
                    try:
                        add_junction_detail(jd_id, jd_name, "IWS", part_a, part_b, "1.0",
                            jd_cat, jd_ctx or None, jd_desc, jd_doc or None,
                            "Ny detalj skapad", jd_reason, "other", jd_by)
                        st.success(f"Detalj **{jd_id}** skapad!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Fel: {e}")
                else:
                    st.error("Fyll i ID, namn, beskrivning och motivering.")


# ============================================================
# PAGE: Kontextregler
# ============================================================
elif page == "Kontextregler":
    st.title("Kontextregler")

    st.info(
        "**Kontextregler** definierar vilka krav som ställs i en given situation. "
        "Matchningen är automatisk — systemet jämför byggdelens egenskaper mot kontextens krav "
        "och visar vilka delar som uppfyller alla villkor. Ingen manuell koppling behövs."
    )

    contexts = get_all_contexts("IWS")
    if not contexts:
        st.warning("Inga kontextkrav definierade.")
    else:
        ctx_choice = st.selectbox("Välj kontext", [c["id"] for c in contexts],
            format_func=lambda x: next(c["name"] for c in contexts if c["id"] == x))

        matching, ctx_info, reqs = filter_by_context(ctx_choice)

        st.markdown(f"### {ctx_info['name']}")
        st.markdown(f"*{ctx_info.get('description', '')}*")
        st.markdown(f"**Land:** {ctx_info.get('country', 'Alla')} · **Rumstyp:** {ctx_info.get('room_type', 'Alla')}")

        st.markdown("**Krav som ställs:**")
        prop_defs = {p["id"]: p for p in get_all_property_definitions()}
        for r in reqs:
            pd_info = prop_defs.get(r["property_id"], {})
            unit = f" {pd_info.get('unit', '')}" if pd_info.get('unit') else ""
            op = {">=":"≥","<=":"≤","exact":"=","hierarchy":"≥"}.get(pd_info.get("comparison_operator",""), "")
            val = r["required_value"]
            if pd_info.get("data_type") == "boolean":
                val = "Ja" if val == "true" else "Nej"
            st.markdown(f"- {pd_info.get('name', r['property_id'])} {op} **{val}{unit}**")

        st.markdown("---")
        if matching:
            st.success(f"**{len(matching)} byggdelar uppfyller kraven:**")
            for m in matching:
                st.markdown(f"- **{m['part_id']}** ({m['name']}) — v{m['version']} — `{m['layer_description']}`")
        else:
            st.error("Inga byggdelar uppfyller kontextens krav.")


# ============================================================
# PAGE: Egenskapsdefinitioner
# ============================================================
elif page == "Egenskapsdefinitioner":
    st.title("Egenskapsdefinitioner (Ontologi)")

    st.info(
        "**Ontologin** är den gemensamma vokabulären för alla systemfamiljer. "
        "Varje egenskap har en datatyp, enhet och jämförelseoperator. "
        "Det säkerställer att kontextfiltrering fungerar konsekvent.\n\n"
        "**Hierarki-egenskaper** (t.ex. brandklass): en byggdel med EI60 uppfyller "
        "automatiskt krav på EI30."
    )

    st.dataframe(pd.DataFrame([{
        "ID": p["id"], "Namn": p["name"],
        "Datatyp": {"number":"Tal","text":"Text","boolean":"Ja/Nej"}.get(p["data_type"], p["data_type"]),
        "Enhet": p["unit"] or "—",
        "Jämförelse": {">=":"≥ (minst)","<=":"≤ (högst)","exact":"= (exakt)","hierarchy":"≥ (hierarki)"}.get(p["comparison_operator"], p["comparison_operator"]),
        "Hierarki": p["hierarchy_order"] or "—",
    } for p in get_all_property_definitions()]), use_container_width=True, hide_index=True)


# ============================================================
# PAGE: Governance-logg
# ============================================================
elif page == "Governance-logg":
    st.title("Governance-logg")

    st.info(
        "**Varje versionsändring loggas permanent.** Loggen visar vem som beslutade, "
        "varför, och vad som ändrades. Tänk på det som en commit-historik för tekniska krav."
    )

    parts = get_all_building_parts("IWS")
    st.dataframe(pd.DataFrame([{
        "Byggdel": p["id"], "Version": p["version"],
        "Typ": {"major_change":"Väsentlig ändring","new":"Ny","phase_out":"Avveckling"}.get(p["change_type"], p["change_type"]),
        "Beskrivning": p["change_description"],
        "Motivering": p["change_reason"],
        "Beslutare": p["decided_by"],
        "Datum": p["decided_date"],
    } for p in parts]), use_container_width=True, hide_index=True)


# ============================================================
# Footer
# ============================================================
st.sidebar.markdown("---")
st.sidebar.code("""
SystemFamily
 └─ BuildingPart
 │   └─ BuildingPartVersion
 │       └─ Properties
 └─ JunctionDetail
     └─ JunctionDetailVersion

ContextRequirement
 └─ ContextRequirementProperty

PropertyDefinition
""", language=None)
st.sidebar.caption("JM Masterdata MVP v0.4")
