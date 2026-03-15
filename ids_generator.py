"""
IDS Generator — creates IDS 1.0 XML files from masterdata.
One IDS file per BuildingPart, validating that IFC elements
claiming to be that type actually match the defined properties.

IDS = Information Delivery Specification (buildingSMART standard).
Used with ifctester / Solibri for automated BIM validation.
"""

from database import get_all_building_parts, get_version_properties
from xml.sax.saxutils import escape

# --- IFC Property Mapping ---
# Maps masterdata property IDs to IFC PropertySet + PropertyName + dataType.
# Adjust these mappings to match your Revit shared parameters / export config.

PROPERTY_MAP = {
    "sound_reduction": {
        "propertySet": "Pset_WallCommon",
        "baseName": "AcousticRating",
        "dataType": "IfcLabel",
        "format_value": lambda v: f"{int(float(v))} dB",
    },
    "load_bearing": {
        "propertySet": "Pset_WallCommon",
        "baseName": "LoadBearing",
        "dataType": "IfcBoolean",
        "format_value": lambda v: "TRUE" if v == "true" else "FALSE",
    },
    "fire_class": {
        "propertySet": "Pset_WallCommon",
        "baseName": "FireRating",
        "dataType": "IfcLabel",
        "format_value": lambda v: v,
    },
    "insulated": {
        "propertySet": "JM_TechnicalProperties",
        "baseName": "IsInsulated",
        "dataType": "IfcBoolean",
        "format_value": lambda v: "TRUE" if v == "true" else "FALSE",
    },
    "stud_width": {
        "propertySet": "JM_TechnicalProperties",
        "baseName": "StudWidth",
        "dataType": "IfcLengthMeasure",
        "format_value": lambda v: v,
    },
    "gypsum_layers_per_side": {
        "propertySet": "JM_TechnicalProperties",
        "baseName": "GypsumLayersPerSide",
        "dataType": "IfcInteger",
        "format_value": lambda v: str(int(float(v))),
    },
    "max_height_min": {
        "propertySet": "JM_TechnicalProperties",
        "baseName": "MaxHeightMin",
        "dataType": "IfcLengthMeasure",
        "format_value": lambda v: v,
    },
    "max_height_max": {
        "propertySet": "JM_TechnicalProperties",
        "baseName": "MaxHeightMax",
        "dataType": "IfcLengthMeasure",
        "format_value": lambda v: v,
    },
}

# Properties checked via geometry, not IDS property rules
SKIP_PROPERTIES = {"thickness"}


def _property_requirement(pset, base_name, data_type, value, instructions=""):
    """Generate XML for one IDS property requirement."""
    instr = f' instructions="{escape(instructions)}"' if instructions else ""
    return f"""        <property dataType="{escape(data_type)}"{instr}>
          <propertySet>
            <simpleValue>{escape(pset)}</simpleValue>
          </propertySet>
          <baseName>
            <simpleValue>{escape(base_name)}</simpleValue>
          </baseName>
          <value>
            <simpleValue>{escape(str(value))}</simpleValue>
          </value>
        </property>"""


def _applicability_wall(part_id):
    """Generate applicability block: IfcWall where Name matches part_id."""
    e = escape(part_id)
    return f"""      <applicability minOccurs="0" maxOccurs="unbounded">
        <entity>
          <name>
            <simpleValue>IFCWALL</simpleValue>
          </name>
        </entity>
        <attribute>
          <name>
            <simpleValue>Name</simpleValue>
          </name>
          <value>
            <simpleValue>{e}</simpleValue>
          </value>
        </attribute>
      </applicability>"""


def generate_ids_for_part(part_id, system_family_id="IWS"):
    """Generate IDS 1.0 XML for a single building part.

    Spec 1 — Property validation:
      Applicability: IfcWall where Name = part_id
      Requirements: mapped properties must match masterdata values

    Spec 2 — Reference check:
      Applicability: IfcWall where Name = part_id
      Requirements: Pset_WallCommon.Reference = part_id
    """
    parts = get_all_building_parts(system_family_id)
    part = next((p for p in parts if p["id"] == part_id), None)
    if not part:
        raise ValueError(f"Building part {part_id} not found")

    props = get_version_properties(part["version_id"])
    prop_map = {p["id"]: p["value"] for p in props}

    # Build property requirements
    req_blocks = []
    for prop_id, prop_value in sorted(prop_map.items()):
        if prop_id in SKIP_PROPERTIES:
            continue
        mapping = PROPERTY_MAP.get(prop_id)
        if not mapping:
            continue
        req_blocks.append(_property_requirement(
            pset=mapping["propertySet"],
            base_name=mapping["baseName"],
            data_type=mapping["dataType"],
            value=mapping["format_value"](prop_value),
            instructions=f"{prop_id} — JM Masterdata v{part['version']}"
        ))

    prop_count = len(req_blocks)
    requirements_xml = "\n".join(req_blocks)
    applicability = _applicability_wall(part_id)
    e_id = escape(part_id)
    e_title = escape(f"{part_id} — {part['name']}")
    e_desc = escape(
        f"IDS validation for {part_id} v{part['version']}. "
        f"Generated from JM Masterdata. "
        f"Layer: {part.get('layer_description', 'N/A')}"
    )

    ref_requirement = _property_requirement(
        pset="Pset_WallCommon",
        base_name="Reference",
        data_type="IfcLabel",
        value=part_id,
        instructions="Wall type reference must match masterdata ID"
    )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<ids xmlns="http://standards.buildingsmart.org/IDS"
     xmlns:xs="http://www.w3.org/2001/XMLSchema"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="http://standards.buildingsmart.org/IDS http://standards.buildingsmart.org/IDS/1.0/ids.xsd">
  <info>
    <title>{e_title}</title>
    <description>{e_desc}</description>
    <version>{escape(part['version'])}</version>
    <author>JM Masterdata MVP</author>
  </info>
  <specifications>
    <specification name="{e_id} property validation" ifcVersion="IFC4">
{applicability}
      <requirements>
{requirements_xml}
      </requirements>
    </specification>
    <specification name="{e_id} reference check" ifcVersion="IFC4">
{applicability}
      <requirements>
{ref_requirement}
      </requirements>
    </specification>
  </specifications>
</ids>"""

    return xml, prop_count


def generate_all_ids(system_family_id="IWS"):
    """Generate IDS files for all active building parts.
    Returns dict of part_id -> {xml, name, version, property_count}.
    """
    parts = get_all_building_parts(system_family_id)
    seen = set()
    result = {}
    for p in parts:
        if p["id"] not in seen:
            seen.add(p["id"])
            xml_str, count = generate_ids_for_part(p["id"], system_family_id)
            result[p["id"]] = {
                "xml": xml_str,
                "name": p["name"],
                "version": p["version"],
                "property_count": count,
            }
    return result
