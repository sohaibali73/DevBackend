"""Inspect the `tEMPLATE.pptx` to enumerate every slide's shapes + image
references so we can replicate each layout as a named template and
figure out which brand-asset each image slot corresponds to."""

import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

PPTX = Path(r"C:/Users/SohaibAli/Desktop/tEMPLATE.pptx")
NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
EMU = 914400


def parse_rels(z, slide_name: str) -> dict:
    rels_name = slide_name.replace("ppt/slides/", "ppt/slides/_rels/") + ".rels"
    if rels_name not in z.namelist():
        return {}
    tree = ET.fromstring(z.read(rels_name))
    out = {}
    for r in tree:
        rid = r.get("Id")
        target = r.get("Target")
        if target:
            out[rid] = target
    return out


def inspect() -> None:
    with zipfile.ZipFile(PPTX) as z:
        pres_xml = z.read("ppt/presentation.xml").decode()
        m_w = re.search(r'cx="(\d+)"', pres_xml)
        m_h = re.search(r'cy="(\d+)"', pres_xml)
        print(f"Canvas: {int(m_w.group(1))/EMU:.3f}\" × {int(m_h.group(1))/EMU:.3f}\"")

        slide_files = sorted([n for n in z.namelist()
                              if n.startswith("ppt/slides/slide") and n.endswith(".xml")],
                             key=lambda s: int(s.rsplit("slide", 1)[-1].split(".")[0]))

        for sf in slide_files:
            print(f"\n══════ {sf} ══════")
            rels = parse_rels(z, sf)
            xml = z.read(sf).decode()
            root = ET.fromstring(xml)
            shapes = root.findall(".//p:sp", NS) + root.findall(".//p:pic", NS)
            for idx, shape in enumerate(shapes):
                xfrm = shape.find(".//a:xfrm", NS)
                off = xfrm.find("a:off", NS) if xfrm is not None else None
                ext = xfrm.find("a:ext", NS) if xfrm is not None else None
                x_in = int(off.get("x"))/EMU if off is not None else None
                y_in = int(off.get("y"))/EMU if off is not None else None
                w_in = int(ext.get("cx"))/EMU if ext is not None else None
                h_in = int(ext.get("cy"))/EMU if ext is not None else None
                kind = shape.tag.rsplit("}", 1)[-1]
                prst = shape.find(".//a:prstGeom", NS)
                prst_v = prst.get("prst") if prst is not None else "-"
                fill_el = shape.find(".//a:solidFill/a:srgbClr", NS)
                fill = fill_el.get("val") if fill_el is not None else None
                # All text runs
                runs = shape.findall(".//a:t", NS)
                text = " / ".join((r.text or "").strip() for r in runs if (r.text or "").strip())[:120]
                # Image reference (pic)
                img_target = None
                if kind == "pic":
                    blip = shape.find(".//a:blip", NS)
                    if blip is not None:
                        rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
                        img_target = rels.get(rid)
                rpr = shape.find(".//a:rPr", NS)
                sz_pt = int(rpr.get("sz"))/100 if (rpr is not None and rpr.get("sz")) else None

                line_parts = [
                    f"[{idx:02d}] {kind:3s}",
                    f"prst={prst_v:14s}",
                ]
                if x_in is not None:
                    line_parts.append(f"x={x_in:6.3f} y={y_in:6.3f} w={w_in:6.3f} h={h_in:6.3f}")
                else:
                    line_parts.append("(no xfrm)".ljust(40))
                if fill:
                    line_parts.append(f"fill=#{fill}")
                if sz_pt:
                    line_parts.append(f"{sz_pt:.1f}pt")
                if img_target:
                    line_parts.append(f"img={img_target}")
                if text:
                    line_parts.append(f"'{text}'")
                print("  ".join(line_parts))


if __name__ == "__main__":
    inspect()
