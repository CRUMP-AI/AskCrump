"""Generate human-reviewable release samples through Ask Crump's export engines."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.artifact_service import ArtifactService
from backend.manuscript_service import ManuscriptService, kdp_profile


OUTPUT = ROOT / 'output' / 'artifact-quality-audit'

ACADEMIC = """# Governance Before Scale: A Human-Centered Standard for Generative AI in Higher Education

Generative artificial intelligence has entered higher education faster than most institutions have developed policies for its responsible use. That timing mismatch creates a false choice: either prohibit a technology students already encounter or accept it before its educational value and risks are understood. A stronger position is available. Colleges should permit carefully bounded uses of generative AI only when those uses preserve human judgment, disclose material assistance, protect student data, and undergo continuous evaluation. Governance is not a brake on innovation; it is the structure that makes meaningful innovation possible.

## The Central Governance Problem

The central question is not whether generative AI is universally “good” or “bad.” It is whether a particular use advances a legitimate educational purpose without displacing the learning the assignment is designed to measure. A brainstorming assistant may help a student surface counterarguments. The same system, asked to produce the submitted analysis, can obscure whether the student understands the material. Because the tool can occupy both roles, policy must focus on use, evidence, and accountability rather than on the mere presence of AI.

The National Institute of Standards and Technology frames AI risk management as a continuing set of functions: **Govern, Map, Measure, and Manage** (Tabassi, 2023). Applied to higher education, that sequence is more useful than a one-time approval. An institution first establishes responsibility and acceptable-use rules; maps the people, data, and academic objectives affected by a proposed use; measures performance and harm; and manages the system as conditions change. This lifecycle approach recognizes that model behavior, vendor practices, and classroom norms do not remain static.

## Human Agency as the Design Constraint

UNESCO’s guidance for generative AI in education argues for a human-centered approach and emphasizes protection of human agency, privacy, inclusion, and pedagogical appropriateness (Miao & Holmes, 2023). Human agency should therefore be treated as a design constraint, not as an aspirational slogan. Students must be able to question outputs, decline inappropriate collection of personal information, and understand when an automated system is shaping a consequential decision. Faculty must remain responsible for learning objectives, assessment design, and final academic judgments.

This constraint changes implementation. AI-assisted feedback should identify patterns and invite revision rather than issue an unappealable judgment. Administrative tools should minimize data and avoid repurposing student work without informed authorization. Assignments should specify whether AI may support ideation, editing, translation, coding, or source discovery—and which portions must demonstrate unaided competence. Disclosure should be proportional: a material contribution to reasoning deserves explanation, while routine spelling assistance may not.

## Evidence, Not Enthusiasm

Institutional adoption often begins with a compelling demonstration. Demonstrations, however, are not evaluations. A fluent output can still contain unsupported claims, fabricated citations, hidden bias, or reasoning that collapses outside a narrow prompt. Before a tool is used at scale, the institution should define what success means, test performance on representative tasks, document failure modes, and establish a process for reporting harm. Evaluation must include the populations most affected rather than relying on a generic benchmark.

The same standard applies to educational benefit. A tool should not be credited with improving learning merely because students complete work faster or report that it feels convenient. Institutions should examine whether students retain knowledge, transfer skills, detect errors, and develop independent judgment. Where evidence is weak, use should remain reversible and limited. This posture is neither technophobic nor passive; it is an evidence-based commitment to learning.

## A Practical Institutional Standard

A defensible institutional policy can be organized around five requirements:

1. **Purpose:** Every approved use identifies the educational or operational problem it is meant to solve.
2. **Disclosure:** Students and employees know when generative AI materially contributes to content, feedback, or decisions.
3. **Data protection:** Collection is minimized, sensitive data is prohibited unless specifically authorized, and vendor retention practices are reviewed.
4. **Evaluation:** Accuracy, bias, accessibility, security, and educational outcomes are tested before scale and monitored afterward.
5. **Human accountability:** A named person or office remains responsible for the decision, the remedy, and the decision to stop using the system.

These requirements make experimentation possible without making experimentation invisible. They also reduce policy fragmentation. Individual instructors can adapt course-level rules, but students should not face fundamentally different privacy and disclosure standards in every classroom.

## Counterargument and Response

One objection is that strong governance will slow adoption and leave institutions behind. The concern is understandable: review processes can become ceremonial, duplicative, or detached from classroom reality. Yet speed without a clear purpose is not progress. Poorly governed deployments create remediation costs, undermine trust, and make it difficult to distinguish educational value from novelty. The answer is not to abandon review but to make it proportionate. Low-risk experiments can use a short, time-bounded review; systems handling sensitive data or consequential decisions require deeper scrutiny.

Another objection is that students must learn to use the tools they will encounter at work. That is true, but workplace preparation includes learning when not to trust automation, how to verify an output, how to protect confidential information, and how to take responsibility for a final decision. A human-centered policy does not remove AI literacy from the curriculum. It defines AI literacy more seriously.

## Conclusion

Higher education should neither freeze in place nor treat technical capability as sufficient justification for adoption. The better standard is governed experimentation: purposeful, disclosed, privacy-preserving, evaluated, and accountable to human judgment. NIST offers a practical risk-management lifecycle, while UNESCO places human agency and educational purpose at the center. Together, those principles support a policy that can adapt as the technology changes without surrendering the institution’s obligations to students. The decisive question is not whether a campus uses generative AI. It is whether the campus can explain, evaluate, and take responsibility for how it is used.

## References

Miao, F., & Holmes, W. (2023). *Guidance for generative AI in education and research*. UNESCO. https://www.unesco.org/en/articles/guidance-generative-ai-education-and-research

Tabassi, E. (2023). *Artificial Intelligence Risk Management Framework (AI RMF 1.0)* (NIST AI 100-1). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.AI.100-1
"""

RESUME = """# Jordan Ellis

Savannah, Georgia · jordan.ellis@example.com · (555) 010-0142 · linkedin.com/in/jordan-ellis

## Professional Summary

Product operations leader with eight years of experience turning customer insight into repeatable launch, adoption, and measurement systems for B2B software teams. Known for clarifying ownership, building durable operating rhythms, and translating strategy into work that teams can execute.

## Core Skills

- Product operations · Go-to-market planning · Customer research · KPI design
- Cross-functional facilitation · Process design · Executive communication · SQL

## Experience

### Senior Product Operations Manager · Harbor Systems · 2022–Present

- Established a quarterly product-planning system used by four product groups, reducing late roadmap changes by 31% over two planning cycles.
- Built launch-readiness reviews across product, sales, support, and marketing, improving on-time enablement from 68% to 92%.
- Created a customer-insight repository that connected 1,400 interview notes and support themes to product decisions.
- Partnered with analytics to define activation and retention dashboards for a multi-product SaaS portfolio.

### Product Operations Manager · Meridian Cloud · 2019–2022

- Standardized beta recruitment, feedback collection, and decision logs across six launches.
- Designed weekly executive reporting that replaced five disconnected status documents with one accountable operating view.
- Facilitated post-launch reviews and converted findings into owners, deadlines, and reusable launch criteria.

### Business Analyst · Southline Logistics · 2017–2019

- Automated recurring performance reports and returned approximately 12 analyst hours per week to customer-facing work.
- Mapped order-exception workflows and helped reduce average resolution time by 18%.

## Education

Bachelor of Business Administration, Operations Management · Coastal State University · 2017

## Selected Tools

SQL · Tableau · Jira · Linear · Notion · Salesforce · Excel
"""

DECK = """# From AI Output to Trusted Work

A release standard for documents people can edit, present, submit, and keep.

## The standard is the finished experience

- A file opening successfully is the minimum, not the quality bar.
- Content, structure, visual hierarchy, truthfulness, and editability must work together.
- Every export should survive the moment it leaves the chat.

## Different outcomes require different rules

| Outcome | Non-negotiable | Failure to prevent |
| --- | --- | --- |
| Academic paper | Grounded sources and coherent argument | Invented citations |
| Résumé | ATS clarity and supplied facts | Fabricated credentials |
| Presentation | One takeaway per slide | Dense document-on-a-slide |
| Spreadsheet | Typed inputs and transparent formulas | Unsafe or opaque calculations |
| Manuscript | Persistent chapters and print-aware export | Truncated “complete” books |

## Quality is enforced before packaging

- The creation contract tells the model what finished means for the selected outcome.
- Source-heavy requests trigger current research when search is available.
- A final reviewer checks completeness, internal consistency, and unsupported claims.
- The deterministic exporter applies a tested visual and structural system.

## The export layer stays editable

- Word files use native paragraphs, headings, lists, tables, and page fields.
- PowerPoint uses native text boxes and tables on a 16:9 canvas.
- Excel uses native values, formulas, filters, tables, and number formats.
- PDF preserves a stable presentation while retaining extractable text.

## Release gates make the claim defensible

- Structural tests validate containers, metadata, dimensions, formulas, and safety guards.
- Render tests expose clipping, overflow, weak hierarchy, and broken pagination.
- Human review checks whether the artifact looks ready for its actual audience.

## The promise

- Ask Crump helps turn a conversation into professional, editable work.
- It does not invent evidence, guarantee a grade, or replace human accountability.
- Premium means clarity, continuity, and craft—front to back.
"""

WORKBOOK = """# Launch Operating Model

All figures below are illustrative assumptions for quality verification, not forecasts.

## Assumptions

| Input | Value | Unit | Owner |
| --- | --- | --- | --- |
| Starting active users | 2,500 | users | Growth |
| Monthly organic growth | 12% | percent | Growth |
| Trial-to-paid conversion | 4.5% | percent | Revenue |
| Paid monthly price | $20.00 | USD | Finance |
| Monthly churn | 3.0% | percent | Success |

## Twelve-Month Model

| Month | Active Users | New Paid Users | Ending Paid Users | MRR |
| --- | --- | --- | --- | --- |
| 1 | 2500 | =B2*Assumptions!B4 | =C2 | =D2*Assumptions!B5 |
| 2 | =B2*(1+Assumptions!B3) | =B3*Assumptions!B4 | =D2*(1-Assumptions!B6)+C3 | =D3*Assumptions!B5 |
| 3 | =B3*(1+Assumptions!B3) | =B4*Assumptions!B4 | =D3*(1-Assumptions!B6)+C4 | =D4*Assumptions!B5 |
| 4 | =B4*(1+Assumptions!B3) | =B5*Assumptions!B4 | =D4*(1-Assumptions!B6)+C5 | =D5*Assumptions!B5 |

## Launch Owners

| Workstream | Outcome | Date | Status |
| --- | --- | --- | --- |
| Product | Activation path verified | 2026-09-05 | In progress |
| Growth | First-use campaign live | 2026-09-08 | Planned |
| Success | Retention check-in active | 2026-09-12 | Planned |
| Finance | Revenue dashboard reconciled | 2026-09-15 | Planned |
"""


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifacts = ArtifactService(files=None)
    (OUTPUT / 'academic-essay.docx').write_bytes(artifacts.docx(ACADEMIC, profile='academic'))
    (OUTPUT / 'academic-essay.pdf').write_bytes(artifacts.pdf(ACADEMIC, profile='academic'))
    (OUTPUT / 'executive-resume.docx').write_bytes(artifacts.docx(RESUME, profile='resume'))
    (OUTPUT / 'quality-standard-deck.pptx').write_bytes(artifacts.pptx(DECK))
    (OUTPUT / 'launch-operating-model.xlsx').write_bytes(artifacts.xlsx(WORKBOOK))

    manuscript = ManuscriptService(db=None, ai=None, projects=None)
    book = {'id': 'quality-audit', 'title': 'The Last Signal', 'subtitle': 'A Sample Manuscript', 'author_name': 'Ask Crump Sample'}
    sections = [
        {'title': 'Chapter One: The Quiet Frequency', 'content': (
            'Mara heard the signal at 2:17 in the morning, buried beneath the weather band and the soft electrical breath of the observatory. '
            'It was not loud. It was precise.\n\nShe leaned toward the console and watched the pattern return: seven pulses, a pause, then three. '
            'No satellite in the registry used that cadence. No instrument on the mountain should have been awake.\n\n⸻\n\nBy sunrise, the signal had crossed every frequency she could monitor. It was not calling the observatory. It was learning how to speak.'
        )},
        {'title': 'Chapter Two: A Map Without Distance', 'content': (
            'The team assembled before the coffee finished brewing. Mara projected the overnight trace across the wall and let the silence do the first round of explaining.\n\n'
            '“It moved,” Elias said.\n\n“Frequencies do not move,” Mara replied. “Transmitters do.”\n\nOutside, dawn found the dish already turning toward an empty region of sky.'
        )},
    ]
    profile = kdp_profile(trim_code='6x9', page_count=180, bleed=False)
    (OUTPUT / 'manuscript-sample.docx').write_bytes(manuscript._docx(book, sections, profile))
    (OUTPUT / 'manuscript-sample.pdf').write_bytes(manuscript._pdf(book, sections, profile))
    (OUTPUT / 'manuscript-sample.epub').write_bytes(manuscript._epub(book, sections))
    print(OUTPUT)


if __name__ == '__main__':
    main()
