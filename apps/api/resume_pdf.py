"""Generate a tailored resume PDF from the pool + plan, in a 1-page or 2-page
variant. Pure Python (reportlab) — no Word, runs on any host, and gives precise
control over how much content fits, which is what makes the page toggle real.

Content is SELECTION-only: every line comes from the verified pool. Descriptions
render hyphen-free (project rule); dates/headers keep theirs.
"""
import io

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                HRFlowable)

ACCENT = "#1f3a5f"
INK = "#16203a"
DIM = "#4e5a74"


def _dehyph(s: str) -> str:
    t = s.replace("-", " ")
    while "  " in t:
        t = t.replace("  ", " ")
    return t


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bulletize(text: str, metric: str) -> str:
    """Escaped bullet text with the metric substring bolded (hyphen-free)."""
    text = _dehyph(" ".join(text.split()))
    body = _esc(text)
    metric = _dehyph((metric or "").strip())
    if metric:
        em = _esc(metric)
        body = body.replace(em, f"<b>{em}</b>", 1)
    return body


# variant knobs: starting density. build_resume_pdf() then auto-trims until the
# output fits the variant's page target, so the page count is always honored.
VARIANTS = {
    "twopage": dict(role_bullets=6, projects=3, proj_bullets=2, base=9.6,
                    lead=12.2, gap=5, margin=0.55, accomplishments=True,
                    education_coursework=True, max_roles=99, target=2),
    "onepage": dict(role_bullets=2, projects=2, proj_bullets=1, base=8.7,
                    lead=10.6, gap=3, margin=0.45, accomplishments=False,
                    education_coursework=False, max_roles=4, target=1),
}

# ordered reductions applied (in place) when the draft overflows its target
_TRIMS = [
    lambda k: k.update(role_bullets=max(2, k["role_bullets"] - 1)),
    lambda k: k.update(role_bullets=max(2, k["role_bullets"] - 1)),
    lambda k: k.update(proj_bullets=1),
    lambda k: k.update(accomplishments=False),
    lambda k: k.update(role_bullets=max(1, k["role_bullets"] - 1)),
    lambda k: k.update(projects=max(1, k["projects"] - 1)),
    lambda k: k.update(education_coursework=False),
    lambda k: k.update(max_roles=max(3, k.get("max_roles", 99) if k.get("max_roles", 99) < 90 else 4)),
    lambda k: k.update(projects=max(1, k["projects"] - 1)),
    lambda k: k.update(base=k["base"] - 0.4, lead=k["lead"] - 0.5),
]


def _styles(v: dict) -> dict:
    base, lead = v["base"], v["lead"]
    return {
        "name": ParagraphStyle("name", fontName="Helvetica-Bold", fontSize=base + 6,
                               leading=base + 8, alignment=TA_CENTER, textColor=ACCENT),
        "contact": ParagraphStyle("contact", fontName="Helvetica", fontSize=base - 1.2,
                                  leading=base, alignment=TA_CENTER, textColor=DIM,
                                  spaceAfter=4),
        "summary": ParagraphStyle("summary", fontName="Helvetica", fontSize=base,
                                  leading=lead, textColor=INK),
        "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=base,
                                  leading=lead, textColor=ACCENT, spaceBefore=v["gap"] + 2,
                                  spaceAfter=1),
        "role": ParagraphStyle("role", fontName="Helvetica-Bold", fontSize=base,
                               leading=lead, textColor=INK),
        "rolemeta": ParagraphStyle("rolemeta", fontName="Helvetica-Oblique",
                                   fontSize=base - 1, leading=lead - 1, textColor=DIM),
        "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=base,
                                 leading=lead, leftIndent=10, bulletIndent=0,
                                 textColor=INK),
        "skill": ParagraphStyle("skill", fontName="Helvetica", fontSize=base,
                                leading=lead, textColor=INK),
    }


def _rule(color=ACCENT):
    return HRFlowable(width="100%", thickness=0.6, color=color,
                      spaceBefore=1, spaceAfter=3)


def build_resume_pdf(pool: dict, plan: dict, variant: str = "twopage") -> bytes:
    """Render, then auto-trim until the output fits the variant's page target."""
    knobs = dict(VARIANTS.get(variant, VARIANTS["twopage"]))
    target = knobs["target"]
    pdf = _render(pool, plan, knobs)
    for trim in _TRIMS:
        if page_count(pdf) <= target:
            break
        trim(knobs)
        pdf = _render(pool, plan, knobs)
    return pdf


def _render(pool: dict, plan: dict, v: dict) -> bytes:
    s = _styles(v)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=v["margin"] * inch, bottomMargin=v["margin"] * inch,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        title=f"{pool['contact']['name']} — Resume",
    )
    flow = []
    c = pool["contact"]

    flow.append(Paragraph(_esc(c["name"]), s["name"]))
    contact_bits = [c.get("location"), c.get("phone"), c.get("email"),
                    c.get("linkedin"), c.get("work_authorization")]
    flow.append(Paragraph("  |  ".join(_esc(b) for b in contact_bits if b), s["contact"]))
    flow.append(Paragraph(_dehyph(" ".join(plan["summary_text"].split())), s["summary"]))

    def section(title):
        flow.append(Paragraph(title.upper(), s["section"]))
        flow.append(_rule())

    # ---- skills ----
    section("Technical Skills")
    for g in plan["skills"]:
        flow.append(Paragraph(f"<b>{_esc(g['label'])}:</b> " +
                              _esc(", ".join(g["items"])), s["skill"]))

    # ---- education ----
    edu = pool.get("education", [])
    if edu:
        section("Education")
        for e in edu:
            flow.append(Paragraph(f"<b>{_esc(e['school'])}</b>  |  {_esc(e.get('dates',''))}",
                                  s["role"]))
            flow.append(Paragraph(_esc(e.get("degree", "")), s["rolemeta"]))
            if e.get("notes"):
                flow.append(Paragraph(_esc(e["notes"]), s["rolemeta"]))
            if v["education_coursework"] and e.get("coursework"):
                flow.append(Paragraph("<b>Relevant Coursework:</b> " +
                                      _esc(e["coursework"]), s["skill"]))

    # ---- experience ----
    roles_by_id = {r["id"]: r for r in pool["experience"]}
    section("Experience")
    for entry in plan["experience"][: v["max_roles"]]:
        role = roles_by_id[entry["id"]]
        by_id = {b["id"]: b for b in role["bullets"]}
        flow.append(Paragraph(f"<b>{_esc(role['org'])}</b>", s["role"]))
        flow.append(Paragraph(f"{_esc(role['title'])}  |  {_esc(role.get('dates',''))}",
                              s["rolemeta"]))
        for bid in entry["bullets"][: v["role_bullets"]]:
            b = by_id[bid]
            flow.append(Paragraph(_bulletize(b["text"], b.get("metric", "")),
                                  s["bullet"], bulletText="•"))
        flow.append(Spacer(1, v["gap"]))

    # ---- projects ----
    pj_by_id = {pj["id"]: pj for pj in pool["projects"]}
    chosen = plan["projects"][: v["projects"]]
    if chosen:
        section("Projects")
        for entry in chosen:
            pj = pj_by_id[entry["id"]]
            by_id = {b["id"]: b for b in pj["bullets"]}
            flow.append(Paragraph(f"<b>{_esc(pj['name'])}</b>  |  {_esc(pj.get('stack',''))}",
                                  s["role"]))
            for bid in entry["bullets"][: v["proj_bullets"]]:
                b = by_id[bid]
                flow.append(Paragraph(_bulletize(b["text"], b.get("metric", "")),
                                      s["bullet"], bulletText="•"))
            flow.append(Spacer(1, v["gap"]))

    # ---- accomplishments ----
    if v["accomplishments"] and pool.get("accomplishments"):
        section("Accomplishments")
        for a in pool["accomplishments"]:
            flow.append(Paragraph(_bulletize(a["text"], a.get("metric", "")),
                                  s["bullet"], bulletText="•"))

    doc.build(flow)
    return buf.getvalue()


def page_count(pdf_bytes: bytes) -> int:
    import pypdfium2 as pdfium
    d = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
    try:
        return len(d)
    finally:
        d.close()
