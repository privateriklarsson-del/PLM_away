"""
JM Byggdelar Masterdata MVP
============================
Streamlit app for managing building part masterdata.
Replaces PLM for technical system requirements.
"""

import streamlit as st
import json
import pandas as pd
from database import (
    init_db, seed_data,
    get_all_building_parts, get_version_properties,
    filter_by_context, get_all_contexts,
    get_all_property_definitions, export_for_ids,
    add_building_part_version,
    create_project, get_all_projects, get_project_parts,
    get_project_room_types, lock_project, toggle_project_part,
    check_project_upgrades, upgrade_project_part
)

st.set_page_config(
    page_title="JM Byggdelar Masterdata",
    page_icon="🏗️",
    layout="wide"
)

# Initialize DB
init_db()
seed_data()

# --- Sidebar Navigation ---
st.sidebar.title("🏗️ JM Masterdata")
st.sidebar.markdown("*MVP — Byggdelar & Regler*")
page = st.sidebar.radio(
    "Navigering",
    ["Byggdelar", "Kontextfiltrering", "Projektkonfiguration", "Governance-logg", "Egenskapsdefinitioner", "Export (IDS/JSON)"]
)


# ============================================================
# PAGE: Byggdelar
# ============================================================
if page == "Byggdelar":
    st.title("Byggdelar — Icke bärande innerväggar")
    st.caption("SystemFamily: IWS | Källa: D-0004649")

    parts = get_all_building_parts("IWS")

    if not parts:
        st.warning("Inga byggdelar hittade.")
    else:
        # Summary table
        summary_data = []
        for p in parts:
            props = get_version_properties(p["version_id"])
            prop_map = {pr["id"]: pr["value"] for pr in props}
            summary_data.append({
                "ID": p["id"],
                "Namn": p["name"],
                "Version": p["version"],
                "Tjocklek (mm)": prop_map.get("thickness", ""),
                "R'w (dB)": prop_map.get("sound_reduction", ""),
                "Max höjd min (mm)": prop_map.get("max_height_min", ""),
                "Max höjd max (mm)": prop_map.get("max_height_max", ""),
                "Isolerad": "✅" if prop_map.get("insulated") == "true" else "❌",
                "Regel (mm)": prop_map.get("stud_width", ""),
                "Gips/sida": prop_map.get("gypsum_layers_per_side", ""),
                "Status": p["status"],
            })

        df = pd.DataFrame(summary_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Detail view
        st.markdown("---")
        st.subheader("Detaljer")
        selected_id = st.selectbox(
            "Välj byggdel",
            [p["id"] for p in parts],
            format_func=lambda x: f"{x} — {next(p['name'] for p in parts if p['id'] == x)}"
        )

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
                val = pr['value']
                if pr['data_type'] == 'boolean':
                    val = "Ja" if val == "true" else "Nej"
                st.markdown(f"- {pr['name']}: **{val}{unit}**")

        # --- New version form ---
        st.markdown("---")
        with st.expander("➕ Skapa ny version"):
            with st.form(f"new_version_{selected_id}"):
                st.markdown(f"Ny version av **{selected_id}**")

                new_version = st.text_input("Versionsnummer", value="1.1")
                change_type = st.selectbox("Ändringstyp", ["major_change", "new", "phase_out"])
                change_desc = st.text_area("Beskrivning av ändring")
                change_reason = st.text_area("Beslutsmotivering")
                trigger = st.selectbox("Utlösande faktor", [
                    "regulatory", "cost", "quality_issue",
                    "simplification", "supplier_change", "other"
                ])
                decided_by = st.text_input("Beslutare", value="Erik")
                layer_desc = st.text_input("Uppbyggnad", value=sel["layer_description"])

                st.markdown("**Egenskaper:**")
                new_props = {}
                prop_defs = get_all_property_definitions()
                current_props = {pr["id"]: pr["value"] for pr in props}
                for pd_item in prop_defs:
                    default = current_props.get(pd_item["id"], "")
                    unit_label = f" ({pd_item['unit']})" if pd_item["unit"] else ""
                    new_props[pd_item["id"]] = st.text_input(
                        f"{pd_item['name']}{unit_label}",
                        value=default,
                        key=f"prop_{selected_id}_{pd_item['id']}"
                    )

                submitted = st.form_submit_button("Skapa version")
                if submitted and change_desc and change_reason:
                    add_building_part_version(
                        selected_id, new_version, change_type,
                        change_desc, change_reason, trigger,
                        decided_by, layer_desc, new_props
                    )
                    st.success(f"Version {new_version} skapad för {selected_id}")
                    st.rerun()
                elif submitted:
                    st.error("Fyll i beskrivning och motivering (governance-krav).")


# ============================================================
# PAGE: Kontextfiltrering
# ============================================================
elif page == "Kontextfiltrering":
    st.title("Kontextfiltrering")
    st.markdown("*Givet en kontext — vilka byggdelar uppfyller kraven?*")

    contexts = get_all_contexts("IWS")

    if not contexts:
        st.warning("Inga kontextkrav definierade.")
    else:
        ctx_choice = st.selectbox(
            "Välj kontext",
            [c["id"] for c in contexts],
            format_func=lambda x: next(c["name"] for c in contexts if c["id"] == x)
        )

        matching, ctx_info, reqs = filter_by_context(ctx_choice)

        st.markdown(f"### {ctx_info['name']}")
        st.markdown(f"*{ctx_info.get('description', '')}*")
        st.markdown(f"**Land:** {ctx_info.get('country', 'Alla')} | **Rumstyp:** {ctx_info.get('room_type', 'Alla')}")

        st.markdown("**Krav som ställs:**")
        prop_defs = {p["id"]: p for p in get_all_property_definitions()}
        for r in reqs:
            pd_info = prop_defs.get(r["property_id"], {})
            unit = f" {pd_info.get('unit', '')}" if pd_info.get('unit') else ""
            op = pd_info.get("comparison_operator", "")
            op_symbol = {">=": "≥", "<=": "≤", "exact": "=", "hierarchy": "≥"}.get(op, op)
            val = r["required_value"]
            if pd_info.get("data_type") == "boolean":
                val = "Ja" if val == "true" else "Nej"
            st.markdown(f"- {pd_info.get('name', r['property_id'])} {op_symbol} **{val}{unit}**")

        st.markdown("---")
        if matching:
            st.success(f"**{len(matching)} byggdelar uppfyller kraven:**")
            for m in matching:
                st.markdown(f"- **{m['part_id']}** ({m['name']}) — v{m['version']} — `{m['layer_description']}`")
        else:
            st.error("Inga byggdelar uppfyller kontextens krav.")


# ============================================================
# PAGE: Projektkonfiguration
# ============================================================
elif page == "Projektkonfiguration":
    st.title("Projektkonfiguration")
    st.markdown("*Skapa projektspecifik byggdelslista med versionslåsning*")

    tab1, tab2 = st.tabs(["Skapa nytt projekt", "Hantera projekt"])

    with tab1:
        with st.form("new_project"):
            st.subheader("Nytt projekt")
            proj_id = st.text_input("Projekt-ID", placeholder="PRJ-2026-001")
            proj_name = st.text_input("Projektnamn", placeholder="Brf Solbacken")
            proj_country = st.selectbox("Land", ["SE", "NO", "FI", "DK"])
            proj_desc = st.text_input("Beskrivning", placeholder="48 lgh, 6 vån")

            available_room_types = ["sovrum", "vardagsrum", "korridor", "våtrum",
                                     "schakt", "förråd", "trapphus", "kök"]
            proj_rooms = st.multiselect("Rumstyper i projektet", available_room_types,
                                         default=["sovrum", "korridor", "våtrum"])

            submitted = st.form_submit_button("Skapa projekt")
            if submitted and proj_id and proj_name:
                try:
                    create_project(proj_id, proj_name, proj_country, proj_rooms, proj_desc)
                    st.success(f"Projekt **{proj_name}** skapat! Byggdelar matchade och låsta till aktuella versioner.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Fel: {e}")
            elif submitted:
                st.error("Fyll i projekt-ID och namn.")

    with tab2:
        projects = get_all_projects()
        if not projects:
            st.info("Inga projekt skapade ännu.")
        else:
            proj_choice = st.selectbox(
                "Välj projekt",
                [p["id"] for p in projects],
                format_func=lambda x: f"{x} — {next(p['name'] for p in projects if p['id'] == x)}"
            )

            proj = next(p for p in projects if p["id"] == proj_choice)
            room_types = get_project_room_types(proj_choice)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"**{proj['name']}**")
                st.markdown(f"*{proj.get('description', '')}*")
            with col2:
                st.markdown(f"**Land:** {proj['country']}")
                st.markdown(f"**Skapad:** {proj['created_date']}")
            with col3:
                is_locked = bool(proj["locked"])
                st.markdown(f"**Status:** {'🔒 Låst' if is_locked else '🔓 Öppen'}")
                st.markdown(f"**Rumstyper:** {', '.join(room_types)}")

            st.markdown("---")

            # Check for available upgrades
            upgrades = check_project_upgrades(proj_choice)
            if upgrades:
                st.warning(f"⚠️ {len(upgrades)} byggdelar har nyare versioner tillgängliga")
                for u in upgrades:
                    ucol1, ucol2 = st.columns([3, 1])
                    with ucol1:
                        st.markdown(
                            f"**{u['building_part_id']}**: v{u['locked_version']} → v{u['latest_version']} "
                            f"*({u.get('change_description', '')})*"
                        )
                    with ucol2:
                        if not is_locked:
                            if st.button(f"Uppgradera", key=f"upgrade_{u['building_part_id']}"):
                                upgrade_project_part(proj_choice, u["building_part_id"])
                                st.rerun()
                        else:
                            st.caption("Lås upp för att uppgradera")

                st.markdown("---")

            # Building parts list
            st.subheader("Byggdelar i projektet")
            parts = get_project_parts(proj_choice)

            if parts:
                for p in parts:
                    pcol1, pcol2, pcol3 = st.columns([3, 2, 1])
                    with pcol1:
                        status_icon = "✅" if p["included"] else "⬜"
                        version_warning = ""
                        if p.get("valid_to"):
                            version_warning = " ⚠️ *gammal version*"
                        st.markdown(f"{status_icon} **{p['building_part_id']}** — {p['part_name']}{version_warning}")
                    with pcol2:
                        st.markdown(f"v{p['version']} | `{p['layer_description']}`")
                    with pcol3:
                        if not is_locked:
                            new_state = 0 if p["included"] else 1
                            label = "Exkludera" if p["included"] else "Inkludera"
                            if st.button(label, key=f"toggle_{p['building_part_id']}"):
                                toggle_project_part(proj_choice, p["building_part_id"], new_state)
                                st.rerun()

                # Export project-specific list
                st.markdown("---")
                included_parts = [p for p in parts if p["included"]]
                st.markdown(f"**{len(included_parts)} byggdelar inkluderade** av {len(parts)} matchade")

                # Revit type list export
                revit_list = [
                    f"{p['building_part_id']}_v{p['version']}"
                    for p in included_parts
                ]
                st.markdown("**Revit-typer att inkludera:**")
                st.code("\n".join(revit_list))

                # JSON export for project
                proj_export = {
                    "project_id": proj["id"],
                    "project_name": proj["name"],
                    "country": proj["country"],
                    "room_types": room_types,
                    "locked": is_locked,
                    "building_parts": [
                        {
                            "id": p["building_part_id"],
                            "name": p["part_name"],
                            "version": p["version"],
                            "layer_description": p["layer_description"],
                        }
                        for p in included_parts
                    ]
                }
                st.download_button(
                    "📥 Ladda ner projektkonfiguration (JSON)",
                    json.dumps(proj_export, indent=2, ensure_ascii=False),
                    file_name=f"{proj['id']}_config.json",
                    mime="application/json"
                )

            # Lock button
            if not is_locked:
                st.markdown("---")
                if st.button("🔒 Lås projektkonfiguration", type="primary"):
                    lock_project(proj_choice)
                    st.success("Projektet är nu låst. Versioner kan inte ändras.")
                    st.rerun()


# ============================================================
# PAGE: Governance-logg
# ============================================================
elif page == "Governance-logg":
    st.title("Governance-logg")
    st.markdown("*Alla versionsändringar med beslutsmotivering (Typ 2)*")

    parts = get_all_building_parts("IWS")

    log_data = []
    for p in parts:
        log_data.append({
            "Byggdel": p["id"],
            "Version": p["version"],
            "Typ": p["change_type"],
            "Beskrivning": p["change_description"],
            "Motivering": p["change_reason"],
            "Beslutare": p["decided_by"],
            "Datum": p["decided_date"],
        })

    df = pd.DataFrame(log_data)
    st.dataframe(df, use_container_width=True, hide_index=True)


# ============================================================
# PAGE: Egenskapsdefinitioner
# ============================================================
elif page == "Egenskapsdefinitioner":
    st.title("Egenskapsdefinitioner (Ontologi)")
    st.markdown("*Gemensam vokabulär för alla systemfamiljer*")

    prop_defs = get_all_property_definitions()
    prop_data = []
    for p in prop_defs:
        prop_data.append({
            "ID": p["id"],
            "Namn": p["name"],
            "Datatyp": p["data_type"],
            "Enhet": p["unit"] or "—",
            "Jämförelse": p["comparison_operator"],
            "Hierarki": p["hierarchy_order"] or "—",
        })

    df = pd.DataFrame(prop_data)
    st.dataframe(df, use_container_width=True, hide_index=True)


# ============================================================
# PAGE: Export
# ============================================================
elif page == "Export (IDS/JSON)":
    st.title("Export för IDS-pipeline")
    st.markdown("*JSON-export av alla aktiva byggdelar med egenskaper — redo att konsumeras av IDS-generator*")

    data = export_for_ids("IWS")

    st.json(data)

    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    st.download_button(
        label="📥 Ladda ner JSON",
        data=json_str,
        file_name="IWS_active_export.json",
        mime="application/json"
    )

    st.markdown("---")
    st.markdown("### Kontextkrav (export)")
    contexts = get_all_contexts("IWS")
    ctx_export = []
    for ctx in contexts:
        _, ctx_info, reqs = filter_by_context(ctx["id"])
        ctx_export.append({
            "context": ctx_info,
            "requirements": reqs
        })
    st.json(ctx_export)


# --- Footer ---
st.sidebar.markdown("---")
st.sidebar.markdown("**Datamodell:**")
st.sidebar.code("""
SystemFamily
 └─ BuildingPart
     └─ BuildingPartVersion
         ├─ Properties
         ├─ CountryVariant
         └─ ArticleMapping

ContextRequirement
 └─ ContextRequirementProperty

PropertyDefinition (ontologi)
""", language=None)
st.sidebar.markdown(f"*MVP v0.1 — {pd.__version__ if hasattr(pd, '__version__') else 'dev'}*")
