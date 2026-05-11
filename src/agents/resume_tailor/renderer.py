"""Render YAML-canonical resume content into deterministic LaTeX output.

Purpose:
    Convert validated resume YAML models into a stable `.tex` artifact while
    enforcing locked section order and heading text.
"""

from __future__ import annotations

from pathlib import Path

from .schemas import LOCKED_SECTION_HEADINGS
from .schemas import LOCKED_SECTION_ORDER
from .schemas import ResumeContent
from .schemas import validate_locked_structure
from .yaml_io import load_resume_yaml


def _format_decimal(value: float) -> str:
    """Format a float for compact LaTeX numeric emission.

    Purpose:
        Keep rendered layout knobs deterministic while avoiding unnecessary
        trailing zeros in generated TeX files.
    Args:
        value: Floating-point numeric value to format.
    Output:
        Returns a compact decimal string safe to embed in LaTeX commands.
    """

    formatted_value = f"{value:.3f}".rstrip("0").rstrip(".")
    if formatted_value == "-0":
        return "0"
    return formatted_value


def _render_personal_block(resume_content: ResumeContent) -> list[str]:
    """Render the personal heading/contact block.

    Purpose:
        Generate the top-of-document personal information block that remains
        immutable during tailoring.
    Args:
        resume_content: Canonical resume model being rendered.
    Output:
        Returns LaTeX lines representing the personal heading block.
    """

    personal = resume_content.personal
    contact_segments: list[str] = [personal.phone]
    contact_segments.append(f"\\href{{mailto:{personal.email}}}{{{personal.email}}}")
    for link in personal.links:
        contact_segments.append(f"\\href{{{link.url}}}{{{link.label}}}")

    contact_text = " \\textbar\\ ".join(contact_segments)
    return [
        "%----------HEADING----------",
        "\\begin{center}",
        f"  {{\\fontsize{{15pt}}{{16pt}}\\selectfont\\bfseries {personal.name}}}\\\\",
        "  \\vspace{2pt}",
        f"  {{\\normalsize {contact_text}}}",
        "\\end{center}",
        "",
    ]


def _render_education_section(resume_content: ResumeContent) -> list[str]:
    """Render the Education section in locked location/order.

    Purpose:
        Generate immutable education entries exactly from canonical YAML while
        keeping section heading and ordering fixed.
    Args:
        resume_content: Canonical resume model being rendered.
    Output:
        Returns LaTeX lines for the Education section.
    """

    lines: list[str] = [
        "%-----------EDUCATION-----------",
        f"\\section{{\\textbf{{{LOCKED_SECTION_HEADINGS['education']}}}}}",
        "\\resumeSubHeadingListStart",
    ]

    for entry in resume_content.education.entries:
        lines.append(
            "  "
            f"\\resumeSubheading{{{entry.institution}}}{{{entry.date_range}}}"
            f"{{{entry.degree}}}{{{entry.detail}}}"
        )
        for bullet in entry.bullets:
            lines.append(f"  \\item {bullet.text}")

    lines.extend(["\\resumeSubHeadingListEnd", ""])
    return lines


def _render_experience_section(resume_content: ResumeContent) -> list[str]:
    """Render enabled Experience listings and bullets.

    Purpose:
        Convert canonical experience listings into LaTeX while honoring
        active/inactive pool toggles via each listing's `enabled` flag.
    Args:
        resume_content: Canonical resume model being rendered.
    Output:
        Returns LaTeX lines for the Experience section.
    """

    lines: list[str] = [
        "%-----------EXPERIENCE-----------",
        f"\\section{{\\textbf{{{LOCKED_SECTION_HEADINGS['experience']}}}}}",
        "\\resumeSubHeadingListStart",
    ]

    for listing in resume_content.experience.listings:
        if not listing.enabled:
            continue

        lines.append(
            "  "
            f"\\item {{\\textbf{{{listing.title}}}}} \\hfill "
            f"{{\\textbf{{{listing.date_range}}}}}\\\\"
        )
        lines.append(f"    \\textbf{{{listing.organization}}}")
        lines.append("  \\resumeItemListStart")
        for bullet in listing.bullets:
            lines.append(f"    \\resumeItem{{{bullet.text}}}")
        lines.append("  \\resumeItemListEnd")

    lines.extend(["\\resumeSubHeadingListEnd", ""])
    return lines


def _render_projects_section(resume_content: ResumeContent) -> list[str]:
    """Render enabled Project listings and bullets.

    Purpose:
        Convert canonical project listings into LaTeX while honoring
        active/inactive pool toggles via each listing's `enabled` flag.
    Args:
        resume_content: Canonical resume model being rendered.
    Output:
        Returns LaTeX lines for the Projects section.
    """

    lines: list[str] = [
        "%-----------PROJECTS-----------",
        f"\\section{{\\textbf{{{LOCKED_SECTION_HEADINGS['projects']}}}}}",
        "\\resumeSubHeadingListStart",
    ]

    for listing in resume_content.projects.listings:
        if not listing.enabled:
            continue

        title_with_stack = listing.title
        if listing.tech_stack.strip():
            title_with_stack = f"{listing.title} $|$ {listing.tech_stack}"

        lines.append(
            "  "
            f"\\item{{\\textbf{{{title_with_stack}}}}}"
            f"\\hfill\\textbf{{{listing.date_range}}}"
        )
        lines.append("  \\resumeItemListStart")
        for bullet in listing.bullets:
            lines.append(f"  \\resumeItem{{{bullet.text}}}")
        lines.append("  \\resumeItemListEnd")

    lines.extend(["\\resumeSubHeadingListEnd", ""])
    return lines


def _render_skills_section(resume_content: ResumeContent) -> list[str]:
    """Render enabled Skills and Achievements listings.

    Purpose:
        Convert canonical skill rows into LaTeX while honoring active/inactive
        pool toggles via each listing's `enabled` flag.
    Args:
        resume_content: Canonical resume model being rendered.
    Output:
        Returns LaTeX lines for the Skills and Achievements section.
    """

    lines: list[str] = [
        "%-----------SKILLS AND ACHIEVEMENTS-----------",
        f"\\section{{\\textbf{{{LOCKED_SECTION_HEADINGS['skills_achievements']}}}}}",
        "\\resumeSubHeadingListStart",
    ]

    for listing in resume_content.skills_achievements.listings:
        if not listing.enabled:
            continue
        lines.append(f"  \\item{{\\textbf{{{listing.category}}}: {listing.text}}}")

    lines.extend(["\\resumeSubHeadingListEnd", ""])
    return lines


def render_resume_tex(resume_content: ResumeContent) -> str:
    """Render canonical resume content into deterministic LaTeX text.

    Purpose:
        Produce a compile-ready `.tex` artifact from YAML while enforcing lock
        boundaries and section ordering rules.
    Args:
        resume_content: Validated canonical resume model.
    Output:
        Returns complete LaTeX document text.
    """

    validate_locked_structure(resume_content)

    section_renderers = {
        "education": _render_education_section,
        "experience": _render_experience_section,
        "projects": _render_projects_section,
        "skills_achievements": _render_skills_section,
    }

    rendered_sections: list[str] = []
    for section_id in LOCKED_SECTION_ORDER:
        section_lines = section_renderers[section_id](resume_content)
        rendered_sections.extend(section_lines)

    layout = resume_content.layout
    latex_lines: list[str] = [
        "\\documentclass[letterpaper,10pt]{article}",
        f"\\usepackage[margin={_format_decimal(layout.margin_in)}in]{{geometry}}",
        "\\usepackage{titlesec}",
        "\\usepackage[usenames,dvipsnames]{color}",
        "\\usepackage{enumitem}",
        "\\usepackage{fancyhdr}",
        "\\usepackage[english]{babel}",
        "\\input{glyphtounicode}",
        "% Use Times New Roman font",
        "\\usepackage{newtxtext,newtxmath}",
        "\\usepackage[hidelinks]{hyperref}",
        "",
        "% Page style and spacing",
        "\\pagestyle{fancy}",
        "\\fancyhf{}",
        "\\renewcommand{\\headrulewidth}{0pt}",
        "\\renewcommand{\\footrulewidth}{0pt}",
        "\\setlist{nosep,leftmargin=*}",
        "",
        "% Section formatting",
        (
            "\\titleformat{\\section}{"
            f"\\fontsize{{{_format_decimal(layout.section_heading_font_size_pt)}pt}}"
            f"{{{_format_decimal(layout.section_heading_line_height_pt)}pt}}"
            "\\selectfont\\scshape}{}{0em}{}[\\color{black}\\titlerule]"
        ),
        (
            "\\titlespacing*{\\section}{0pt}"
            f"{{{_format_decimal(layout.section_spacing_before_pt)}pt}}"
            f"{{{_format_decimal(layout.section_spacing_after_pt)}pt}}"
        ),
        "",
        "% Ensure machine-readable PDF",
        "\\pdfgentounicode=1",
        "",
        "% List commands",
        (
            "\\newcommand{\\resumeSubHeadingListStart}"
            "{\\begin{itemize}[leftmargin=0pt,label={},"
            f"itemsep={_format_decimal(layout.subheading_itemsep_pt)}pt]}}"
        ),
        "\\newcommand{\\resumeSubHeadingListEnd}{\\end{itemize}}",
        (
            "\\newcommand{\\resumeItemListStart}"
            "{\\begin{itemize}[label=\\textbullet,leftmargin=0.2in,"
            f"itemsep={_format_decimal(layout.bullet_itemsep_pt)}pt]}}"
        ),
        "\\newcommand{\\resumeItemListEnd}{\\end{itemize}}",
        (
            "\\newcommand{\\resumeSubheading}[4]{\\item {\\textbf{#1}}"
            "\\hfill{\\textbf{#2}}\\\\"
        ),
        "  {#3}\\hfill{\\textbf{#4}}}",
        "\\newcommand{\\resumeItem}[1]{\\item #1}",
        "",
        "% Document start",
        "\\begin{document}",
        f"\\vspace*{{{_format_decimal(layout.top_vspace_in)}in}}",
        "",
    ]

    latex_lines.extend(_render_personal_block(resume_content))
    latex_lines.extend(rendered_sections)
    latex_lines.extend(["\\end{document}", ""])

    return "\n".join(latex_lines)


def render_resume_yaml_to_tex(
    *, yaml_path: str | Path, tex_output_path: str | Path
) -> Path:
    """Render a canonical YAML file directly to a `.tex` artifact path.

    Purpose:
        Provide one deterministic renderer entry point used by scripts and tool
        adapters without duplicating read/validate/write logic.
    Args:
        yaml_path: Path to canonical resume YAML input.
        tex_output_path: Destination path for generated LaTeX output.
    Output:
        Returns the absolute path of the written `.tex` file.
    """

    resume_content = load_resume_yaml(yaml_path)
    rendered_tex = render_resume_tex(resume_content)

    output_path = Path(tex_output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as tex_file:
        tex_file.write(rendered_tex)

    return output_path.resolve()
