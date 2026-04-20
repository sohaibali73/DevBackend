"""Dump the XML of each slide in the Acrobat-converted reference PPTX so we
can see exactly where each element sits (EMU offsets/sizes + fonts)."""

import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

PPTX = Path(r"C:/Users/SohaibAli/Documents/Potomac_University_Template-1.pptx")
NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
EMU_PER_INCH = 914400


def inspect() -> None:
    with zipfile.ZipFile(PPTX) as z:
        slide_files = sorted([n for n in z.namelist()
                              if n.startswith("ppt/slides/slide") and n.endswith(".xml")],
                             key=lambda s: int(s.rsplit("slide", 1)[-1].split(".")[0]))
        presentation_xml = z.read("ppt/presentation.xml").decode()
        m_w = re.search(r'cx="(\d+)"', presentation_xml)
        m_h = re.search(r'cy="(\d+)"', presentation_xml)
        if m_w and m_h:
            W_in = int(m_w.group(1)) / EMU_PER_INCH
            H_in = int(m_h.group(1)) / EMU_PER_INCH
            print(f"Canvas: {W_in:.3f}\" × {H_in:.3f}\"")

        for sf in slide_files:
            print(f"\n═══ {sf} ═══")
            xml = z.read(sf).decode()
            root = ET.fromstring(xml)
            # Iterate shape tree
            tree_shapes = root.findall(".//p:sp", NS) + root.findall(".//p:pic", NS)
            for idx, shape in enumerate(tree_shapes):
                xfrm = shape.find(".//a:xfrm", NS)
                off = xfrm.find("a:off", NS) if xfrm is not None else None
                ext = xfrm.find("a:ext", NS) if xfrm is not None else None
                x_in = y_in = w_in = h_in = None
                if off is not None:
                    x_in = int(off.get("x")) / EMU_PER_INCH
                    y_in = int(off.get("y")) / EMU_PER_INCH
                if ext is not None:
                    w_in = int(ext.get("cx")) / EMU_PER_INCH
                    h_in = int(ext.get("cy")) / EMU_PER_INCH
                kind = shape.tag.rsplit("}", 1)[-1]
                # Get any text
                t_runs = shape.findall(".//a:t", NS)
                text = " | ".join(tr.text or "" for tr in t_runs)[:80]
                # Font size (first a:rPr sz)
                rpr = shape.find(".//a:rPr", NS)
                sz = rpr.get("sz") if rpr is not None else None
                sz_pt = int(sz) / 100 if sz else None
                # Shape type
                prst = shape.find(".//a:prstGeom", NS)
                prst_type = prst.get("prst") if prst is not None else None
                # Fill
                fill = shape.find(".//a:solidFill/a:srgbClr", NS)
                fill_color = fill.get("val") if fill is not None else None
                print(
                    f"  [{idx:02d}] {kind:3s} prst={prst_type or '-':16s} "
                    f"x={x_in:6.3f} y={y_in:6.3f} w={w_in:6.3f} h={h_in:6.3f} "
                    f"{'fill='+fill_color+' ' if fill_color else '':17s}"
                    f"pt={sz_pt if sz_pt else '-':<4}  {text!r}"
                    if x_in is not None else f"  [{idx:02d}] {kind} (no xfrm)  {text!r}"
                )


if __name__ == "__main__":
    import re
    inspect()
