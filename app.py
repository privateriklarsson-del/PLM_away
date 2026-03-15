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
    check_project_upgrades, upgrade_project_part,
    update_project_phase, get_project_directives, respond_to_directive,
    get_all_directives, get_directive_phase_rules, get_directive_project_responses,
    PHASE_ORDER, PHASE_LABELS
)
from ids_generator import generate_ids_for_part, generate_all_ids, PROPERTY_MAP, SKIP_PROPERTIES

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
    ["Byggdelar", "Kontextfiltrering", "Projektkonfiguration", "Ändringsdirektiv", "Governance-logg", "Egenskapsdefinitioner", "Export (IDS/JSON)"]
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
                    "simplification", "supplier_change", "custom", "other"
                ], format_func=lambda x: {
                    "regulatory": "Myndighetskrav",
                    "cost": "Kostnad",
                    "quality_issue": "Kvalitetsavvikelse",
                    "simplification": "Förenkling",
                    "supplier_change": "Leverantörsbyte",
                    "custom": "Fri orsak (ange nedan)",
                    "other": "Övrigt",
                }.get(x, x))
                custom_trigger = st.text_input("Fri orsak (valfritt, t.ex. 'Inte köpt detta än')")
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
                        decided_by, layer_desc, new_props,
                        custom_trigger_text=custom_trigger if custom_trigger else None
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
    st.markdown("*Skapa projektspecifik byggdelslista med versionslåsning och fasstyrning*")

    tab1, tab2 = st.tabs(["Skapa nytt projekt", "Hantera projekt"])

    with tab1:
        with st.form("new_project"):
            st.subheader("Nytt projekt")
            proj_id = st.text_input("Projekt-ID", placeholder="PRJ-2026-001")
            proj_name = st.text_input("Projektnamn", placeholder="Brf Solbacken")
            proj_country = st.selectbox("Land", ["SE", "NO", "FI", "DK"])
            proj_phase = st.selectbox(
                "Projektfas",
                PHASE_ORDER,
                format_func=lambda x: PHASE_LABELS.get(x, x)
            )
            proj_desc = st.text_input("Beskrivning", placeholder="48 lgh, 6 vån")

            available_room_types = ["sovrum", "vardagsrum", "korridor", "våtrum",
                                     "schakt", "förråd", "trapphus", "kök"]
            proj_rooms = st.multiselect("Rumstyper i projektet", available_room_types,
                                         default=["sovrum", "korridor", "våtrum"])

            submitted = st.form_submit_button("Skapa projekt")
            if submitted and proj_id and proj_name:
                try:
                    create_project(proj_id, proj_name, proj_country, proj_rooms, proj_phase, proj_desc)
                    st.success(f"Projekt **{proj_name}** skapat i fas *{PHASE_LABELS[proj_phase]}*!")
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
            is_locked = bool(proj["locked"])

            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"**{proj['name']}**")
                st.markdown(f"*{proj.get('description', '')}*")
            with col2:
                st.markdown(f"**Land:** {proj['country']}")
                st.markdown(f"**Skapad:** {proj['created_date']}")
                st.markdown(f"**Rumstyper:** {', '.join(room_types)}")
            with col3:
                st.markdown(f"**Status:** {'🔒 Låst' if is_locked else '🔓 Öppen'}")
                current_phase = proj.get("phase", "design")
                st.markdown(f"**Fas:** {PHASE_LABELS.get(current_phase, current_phase)}")

                # Phase selector
                if not is_locked:
                    new_phase = st.selectbox(
                        "Ändra fas",
                        PHASE_ORDER,
                        index=PHASE_ORDER.index(current_phase),
                        format_func=lambda x: PHASE_LABELS.get(x, x),
                        key="phase_select"
                    )
                    if new_phase != current_phase:
                        if st.button("Uppdatera fas"):
                            update_project_phase(proj_choice, new_phase)
                            st.success(f"Fas ändrad till {PHASE_LABELS[new_phase]}")
                            st.rerun()

            # Directive summary
            directives = get_project_directives(proj_choice)
            pending = [d for d in directives if d["response"] == "pending"]
            mandatory_pending = [d for d in pending if d["classification"] == "mandatory"]

            if mandatory_pending:
                st.error(f"🚨 {len(mandatory_pending)} obligatoriska ändringsdirektiv väntar på svar")
            elif pending:
                st.warning(f"📋 {len(pending)} valfria ändringsdirektiv väntar på svar")

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

                # Export
                st.markdown("---")
                included_parts = [p for p in parts if p["included"]]
                st.markdown(f"**{len(included_parts)} byggdelar inkluderade** av {len(parts)} matchade")

                revit_list = [f"{p['building_part_id']}_v{p['version']}" for p in included_parts]
                st.markdown("**Revit-typer att inkludera:**")
                st.code("\n".join(revit_list))

                proj_export = {
                    "project_id": proj["id"],
                    "project_name": proj["name"],
                    "country": proj["country"],
                    "phase": proj.get("phase", "design"),
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
# PAGE: Ändringsdirektiv
# ============================================================
elif page == "Ändringsdirektiv":
    st.title("Ändringsdirektiv")
    st.markdown("*Spåra hur kravändringar sprids till projekt baserat på projektfas*")

    tab1, tab2 = st.tabs(["Per projekt", "Översikt alla direktiv"])

    with tab1:
        projects = get_all_projects()
        if not projects:
            st.info("Inga projekt skapade.")
        else:
            proj_choice = st.selectbox(
                "Välj projekt",
                [p["id"] for p in projects],
                format_func=lambda x: f"{x} — {next(p['name'] for p in projects if p['id'] == x)} ({PHASE_LABELS.get(next(p['phase'] for p in projects if p['id'] == x), '')})",
                key="directive_proj"
            )

            proj = next(p for p in projects if p["id"] == proj_choice)
            directives = get_project_directives(proj_choice)

            if not directives:
                st.success("Inga ändringsdirektiv för detta projekt.")
            else:
                # Group by status
                pending = [d for d in directives if d["response"] == "pending"]
                handled = [d for d in directives if d["response"] != "pending"]

                if pending:
                    st.subheader(f"Väntar på svar ({len(pending)})")
                    for d in pending:
                        class_icon = "🔴" if d["classification"] == "mandatory" else "🟡"
                        class_label = "OBLIGATORISK" if d["classification"] == "mandatory" else "VALFRI"

                        with st.container(border=True):
                            dcol1, dcol2 = st.columns([3, 1])
                            with dcol1:
                                st.markdown(
                                    f"{class_icon} **{class_label}** — {d['building_part_id']}: "
                                    f"v{d.get('from_version', '?')} → v{d['to_version']}"
                                )
                                st.markdown(f"*{d['directive_description']}*")
                                trigger_labels = {
                                    "regulatory": "Myndighetskrav",
                                    "cost": "Kostnad",
                                    "quality_issue": "Kvalitetsavvikelse",
                                    "simplification": "Förenkling",
                                    "supplier_change": "Leverantörsbyte",
                                    "custom": d.get("custom_trigger_text") or "Fri orsak",
                                    "other": "Övrigt",
                                }
                                st.caption(f"Utfärdat: {d['issued_date']} | Orsak: {trigger_labels.get(d['trigger_category'], d['trigger_category'])}")
                            with dcol2:
                                note = st.text_input("Kommentar", key=f"note_{d['directive_id']}", placeholder="Valfri motivering")
                                bcol1, bcol2, bcol3 = st.columns(3)
                                with bcol1:
                                    if st.button("✅ Acceptera", key=f"accept_{d['directive_id']}"):
                                        respond_to_directive(proj_choice, d["directive_id"], "accepted", "Erik", note)
                                        st.rerun()
                                with bcol2:
                                    if d["classification"] != "mandatory":
                                        if st.button("❌ Avvisa", key=f"reject_{d['directive_id']}"):
                                            respond_to_directive(proj_choice, d["directive_id"], "rejected", "Erik", note)
                                            st.rerun()
                                with bcol3:
                                    if st.button("⏸️ Skjut upp", key=f"defer_{d['directive_id']}"):
                                        respond_to_directive(proj_choice, d["directive_id"], "deferred", "Erik", note)
                                        st.rerun()

                if handled:
                    st.markdown("---")
                    st.subheader(f"Hanterade ({len(handled)})")
                    handled_data = []
                    for d in handled:
                        response_labels = {
                            "accepted": "✅ Accepterad",
                            "rejected": "❌ Avvisad",
                            "deferred": "⏸️ Uppskjuten",
                        }
                        handled_data.append({
                            "Byggdel": d["building_part_id"],
                            "Ändring": f"v{d.get('from_version', '?')} → v{d['to_version']}",
                            "Klass": d["classification"],
                            "Svar": response_labels.get(d["response"], d["response"]),
                            "Datum": d.get("response_date", ""),
                            "Av": d.get("responded_by", ""),
                            "Kommentar": d.get("note", ""),
                        })
                    st.dataframe(pd.DataFrame(handled_data), use_container_width=True, hide_index=True)

    with tab2:
        all_directives = get_all_directives()
        if not all_directives:
            st.info("Inga ändringsdirektiv utfärdade.")
        else:
            for d in all_directives:
                with st.container(border=True):
                    dcol1, dcol2 = st.columns([3, 1])
                    with dcol1:
                        st.markdown(
                            f"**{d['building_part_id']}**: v{d.get('from_version', '?')} → v{d['to_version']} "
                            f"({d['default_classification']})"
                        )
                        st.markdown(f"*{d['description']}* — {d['issued_date']}")

                        # Trigger label
                        overview_trigger_labels = {
                            "regulatory": "Myndighetskrav",
                            "cost": "Kostnad",
                            "quality_issue": "Kvalitetsavvikelse",
                            "simplification": "Förenkling",
                            "supplier_change": "Leverantörsbyte",
                            "custom": d.get("custom_trigger_text") or "Fri orsak",
                            "other": "Övrigt",
                        }
                        trigger_label = overview_trigger_labels.get(d.get("trigger_category", ""), d.get("trigger_category", ""))

                        # Phase rules
                        phase_rules = get_directive_phase_rules(d["id"])
                        phase_chips = []
                        for phase in PHASE_ORDER:
                            cls = phase_rules.get(phase, "?")
                            icon = {"mandatory": "🔴", "optional": "🟡", "not_applicable": "⚪"}.get(cls, "❓")
                            phase_chips.append(f"{icon} {PHASE_LABELS.get(phase, phase)}")
                        st.caption(f"Orsak: {trigger_label} | " + " | ".join(phase_chips))

                    with dcol2:
                        total = d.get("total_projects", 0)
                        accepted = d.get("accepted", 0)
                        pending_count = d.get("pending", 0)
                        rejected = d.get("rejected", 0)
                        deferred = d.get("deferred", 0)
                        if total > 0:
                            st.metric("Projekt", total)
                            st.caption(f"✅ {accepted}  ⏳ {pending_count}  ❌ {rejected}  ⏸️ {deferred}")

                    # Expandable detail
                    with st.expander("Visa projektresponser"):
                        responses = get_directive_project_responses(d["id"])
                        if responses:
                            resp_data = []
                            for r in responses:
                                response_labels = {
                                    "pending": "⏳ Väntar",
                                    "accepted": "✅ Accepterad",
                                    "rejected": "❌ Avvisad",
                                    "deferred": "⏸️ Uppskjuten",
                                }
                                resp_data.append({
                                    "Projekt": f"{r['project_id']} ({r['project_name']})",
                                    "Fas": PHASE_LABELS.get(r.get("project_phase", ""), ""),
                                    "Klass": r["classification"],
                                    "Svar": response_labels.get(r["response"], r["response"]),
                                    "Datum": r.get("response_date", ""),
                                    "Kommentar": r.get("note", ""),
                                })
                            st.dataframe(pd.DataFrame(resp_data), use_container_width=True, hide_index=True)


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
    st.title("Export")

    tab_ids, tab_json, tab_ctx = st.tabs(["IDS-filer", "JSON (masterdata)", "Kontextkrav"])

    # --- IDS Tab ---
    with tab_ids:
        st.markdown("*En IDS-fil per byggdel — ladda ner och kör i ifctester / Solibri*")

        all_ids = generate_all_ids("IWS")

        if not all_ids:
            st.warning("Inga aktiva byggdelar att generera IDS för.")
        else:
            # Summary
            st.markdown(f"**{len(all_ids)} IDS-filer** genererade")

            # Property mapping info
            with st.expander("Egenskapsmappning (masterdata → IFC)"):
                st.markdown("Dessa masterdata-egenskaper mappas till IFC-properties i IDS:")
                map_data = []
                for prop_id, mapping in sorted(PROPERTY_MAP.items()):
                    map_data.append({
                        "Masterdata-egenskap": prop_id,
                        "IFC PropertySet": mapping["propertySet"],
                        "IFC Property": mapping["baseName"],
                        "Datatyp": mapping["dataType"],
                    })
                st.dataframe(pd.DataFrame(map_data), use_container_width=True, hide_index=True)
                st.caption(f"Egenskaper som hoppas över (geometri-check): {', '.join(SKIP_PROPERTIES)}")
                st.markdown("*Redigera `PROPERTY_MAP` i `ids_generator.py` för att anpassa till er Revit-export.*")

            st.markdown("---")

            # Download all as zip
            import io
            import zipfile
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for part_id, data in all_ids.items():
                    filename = f"{part_id}_v{data['version']}.ids"
                    zf.writestr(filename, data["xml"])
            zip_buffer.seek(0)

            st.download_button(
                label=f"📦 Ladda ner alla IDS-filer ({len(all_ids)} st) som ZIP",
                data=zip_buffer.getvalue(),
                file_name="JM_IWS_IDS_all.zip",
                mime="application/zip",
                type="primary"
            )

            st.markdown("---")

            # Per-file view and download
            st.subheader("Per byggdel")
            for part_id, data in sorted(all_ids.items()):
                with st.container(border=True):
                    icol1, icol2, icol3 = st.columns([2, 2, 1])
                    with icol1:
                        st.markdown(f"**{part_id}** — {data['name']}")
                    with icol2:
                        st.caption(f"v{data['version']} | {data['property_count']} egenskapskontroller + referenscheck")
                    with icol3:
                        st.download_button(
                            label="📥 .ids",
                            data=data["xml"],
                            file_name=f"{part_id}_v{data['version']}.ids",
                            mime="application/xml",
                            key=f"ids_dl_{part_id}"
                        )

                    with st.expander("Visa XML"):
                        st.code(data["xml"], language="xml")

    # --- JSON Tab ---
    with tab_json:
        st.markdown("*JSON-export av alla aktiva byggdelar med egenskaper*")

        data = export_for_ids("IWS")

        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        st.download_button(
            label="📥 Ladda ner JSON",
            data=json_str,
            file_name="IWS_active_export.json",
            mime="application/json"
        )

        st.json(data)

    # --- Context Tab ---
    with tab_ctx:
        st.markdown("*Kontextkrav (export)*")
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
