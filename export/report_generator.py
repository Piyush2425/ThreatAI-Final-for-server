"""Generate reports in PDF and CSV formats."""

import csv
import html
import io
import re
from datetime import datetime
from typing import Dict, Any, List
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
import logging

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generate reports in different formats."""

    REPORT_WRAPPER_PATTERNS = [
        r"^\s*Understood\.\s+I\s+prepared\s+this\s+report\s+context\s+for\s+.+?\n\n",
        r"^\s*Understood\.\s+I\s+used\s+your\s+previous\s+request\s+to\s+prepare\s+this\s+report\s+context\.\n\n",
    ]

    FOLLOWUP_BLOCK_PATTERNS = [
        r"\n\s*(Suggested\s+follow[- ]?up\s+questions?|Follow[- ]?up\s+questions?)\s*:?[\s\S]*$",
    ]

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        """Parse ISO timestamps, including Z suffix."""
        if not value:
            return datetime.now()
        try:
            if isinstance(value, str) and value.endswith('Z'):
                value = value[:-1] + '+00:00'
            return datetime.fromisoformat(value)
        except Exception:
            return datetime.now()

    @staticmethod
    def _normalize_result(result: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize payload shape from different API responses for export."""
        result = result or {}
        metadata = result.get('metadata') if isinstance(result.get('metadata'), dict) else {}

        normalized = {
            'query': result.get('query') or result.get('user_message') or metadata.get('effective_query') or '',
            'answer': result.get('answer') or result.get('assistant_message') or '',
            'confidence': result.get('confidence', metadata.get('confidence', 0.0)),
            'source_count': result.get('source_count', metadata.get('source_count', 0)),
            'trace_id': result.get('trace_id') or metadata.get('trace_id') or '',
            'intent': result.get('intent') or result.get('query_type') or metadata.get('query_type') or 'general',
            'timestamp': result.get('timestamp') or metadata.get('timestamp') or datetime.now().isoformat(),
            'evidence': result.get('evidence') or metadata.get('evidence') or [],
        }

        # Recompute source_count if missing but evidence is present.
        if (not normalized['source_count']) and normalized['evidence']:
            normalized['source_count'] = len(normalized['evidence'])

        return normalized

    @staticmethod
    def _build_summary(answer: str) -> str:
        """Create a short, human-readable summary from the answer text."""
        if not answer:
            return "No summary available."
        answer = ReportGenerator._sanitize_answer_for_report(answer)
        # Remove markdown formatting for summary
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', answer)  # Remove bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)  # Remove italic
        text = " ".join(text.strip().split())
        sentences = re.split(r"(?<=[.!?])\s+", text)
        summary = " ".join(sentences[:2]).strip()
        return summary if summary else text[:200]

    @staticmethod
    def _sanitize_answer_for_report(answer: str) -> str:
        """Remove chat wrappers and follow-up blocks from answer before exporting."""
        if not answer:
            return ""

        cleaned = answer.strip()

        for pattern in ReportGenerator.REPORT_WRAPPER_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        for pattern in ReportGenerator.FOLLOWUP_BLOCK_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        cleaned = re.sub(r"^\s*DETAILED\s+ANALYSIS\s*\n", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    @staticmethod
    def _source_field_counts(evidence: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count evidence rows by source field."""
        counts: Dict[str, int] = {}
        for item in evidence or []:
            field = item.get('source', 'unknown')
            counts[field] = counts.get(field, 0) + 1
        return counts

    @staticmethod
    def _extract_section_from_answer(answer: str, heading: str) -> str:
        """Extract section body for markdown heading style **Heading**."""
        if not answer:
            return ""
        pattern = rf"\*\*{re.escape(heading)}\*\*:?\s*(.*?)(?=\n\s*\*\*[^*]+\*\*:?|\Z)"
        match = re.search(pattern, answer, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        return (match.group(1) or "").strip()

    @staticmethod
    def _link_paragraph(url: str, styles) -> Paragraph:
        """Create a robust clickable link paragraph for ReportLab."""
        safe_url = html.escape(url or "", quote=True)
        label = url if len(url or "") <= 72 else (url[:69] + "...")
        safe_label = html.escape(label or "", quote=False)
        link_html = f'<link href="{safe_url}" color="blue"><u>{safe_label}</u></link>'
        link_style = ParagraphStyle(
            'LinkCell',
            parent=styles['BodyText'],
            fontSize=7.5,
            leading=9,
            wordWrap='CJK',
        )
        return Paragraph(link_html, link_style)

    @staticmethod
    def _collect_references(evidence: List[Dict[str, Any]]) -> Dict[str, str]:
        """Build deterministic reference ids (R1, R2...) for unique URLs."""
        refs: Dict[str, str] = {}
        ref_idx = 1
        for item in evidence or []:
            for url in item.get('links', []) or []:
                if isinstance(url, str) and url.startswith('http') and url not in refs:
                    refs[url] = f"R{ref_idx}"
                    ref_idx += 1
        return refs

    @staticmethod
    def _build_data_coverage_table(evidence: List[Dict[str, Any]]) -> List:
        """Build table showing available structured fields from evidence."""
        if not evidence:
            return []

        counts = ReportGenerator._source_field_counts(evidence)
        ordered_fields = [
            'entity_profile', 'last_updated', 'observed_countries', 'observed_sectors',
            'tools', 'campaigns', 'sponsor', 'counter_operations', 'alias_givers'
        ]

        data = [['Structured Field', 'Records Found']]
        for field in ordered_fields:
            if counts.get(field, 0) > 0:
                data.append([field, str(counts[field])])

        if len(data) == 1:
            return []

        table = Table(data, colWidths=[4.5*inch, 2.0*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#111827')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 1), (1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        return [table]
    
    @staticmethod
    def _format_section_content(text: str, styles) -> List:
        """Format a section body into PDF elements."""
        elements = []
        if not text:
            return elements

        # Check if it's a bullet or numbered list
        if re.match(r'^(\d+\.\s+|[\-\*]\s+)', text):
            lines = text.split('\n')
            list_items = []
            for line in lines:
                line = line.strip()
                if re.match(r'^(\d+\.|[\-\*])\s+', line):
                    item_text = re.sub(r'^(\d+\.|[\-\*])\s+', '', line)
                    item_text = ReportGenerator._format_inline_markdown(item_text)
                    list_items.append(item_text)

            if list_items:
                for item in list_items:
                    bullet_style = ParagraphStyle(
                        'BulletItem',
                        parent=styles['BodyText'],
                        fontSize=10,
                        leftIndent=20,
                        bulletIndent=10,
                        spaceAfter=6
                    )
                    elements.append(Paragraph(f"• {item}", bullet_style))
            return elements

        formatted_text = ReportGenerator._format_inline_markdown(text.replace('\n', '<br/>'))
        elements.append(Paragraph(formatted_text, styles['BodyText']))
        elements.append(Spacer(1, 0.1*inch))
        return elements

    @staticmethod
    def _format_answer_for_pdf(answer: str, styles) -> List:
        """Convert markdown-formatted answer to PDF elements."""
        if not answer:
            return [Paragraph("No answer available.", styles['BodyText'])]
        
        elements = []
        
        # Split by double newlines for paragraphs
        sections = answer.split('\n\n')
        
        for section in sections:
            section = section.strip()
            if not section:
                continue

            section_lower = section.lower()
            if any(token in section_lower for token in [
                'information not available',
                'not available in the current data',
                'no specific',
                'not found in the available data',
            ]):
                continue
            
            # Check if it's a heading (starts with **)
            if section.startswith('**') and section.count('**') >= 2:
                # Extract heading text
                heading_match = re.match(r'^\*\*([^*]+)\*\*:?[\s]*(.*)', section, re.DOTALL)
                if heading_match:
                    heading_text = heading_match.group(1)
                    rest_text = heading_match.group(2).strip()
                    if not rest_text:
                        lines = section.split('\n')
                        rest_text = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

                    rest_text_lower = rest_text.lower()
                    if any(token in rest_text_lower for token in [
                        'information not available',
                        'not available in the current data',
                        'no specific',
                        'not found in the available data',
                    ]):
                        continue
                    
                    # Add as subheading
                    subheading_style = ParagraphStyle(
                        'SubHeading',
                        parent=styles['Heading3'],
                        fontSize=12,
                        textColor=colors.HexColor('#1f2937'),
                        spaceAfter=8,
                        spaceBefore=12,
                        fontName='Helvetica-Bold'
                    )
                    elements.append(Paragraph(heading_text, subheading_style))
                    
                    if rest_text:
                        elements.extend(ReportGenerator._format_section_content(rest_text, styles))
                    continue
            
            elements.extend(ReportGenerator._format_section_content(section, styles))
        
        return elements
    
    @staticmethod
    def _format_inline_markdown(text: str) -> str:
        """Format inline markdown (bold, italic) for ReportLab."""
        if not text:
            return text
        br_token = "__BR__TOKEN__"
        text = text.replace('<br/>', br_token)
        # Escape special characters first
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        # Convert **bold** to <b>bold</b>
        text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
        # Convert *italic* to <i>italic</i>
        text = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', text)
        text = text.replace(br_token, '<br/>')
        return text

    @staticmethod
    def _extract_headings(answer: str) -> List[str]:
        """Extract section headings from markdown answer."""
        if not answer:
            return []
        headings = []
        for match in re.finditer(r'^\*\*([^*]+)\*\*', answer, re.MULTILINE):
            heading = match.group(1).strip()
            if heading and heading not in headings:
                headings.append(heading)
        return headings

    @staticmethod
    def _build_evidence_table(evidence: List[Dict[str, Any]], styles) -> List:
        """Build a structured evidence table for PDF."""
        if not evidence:
            return []

        refs = ReportGenerator._collect_references(evidence)
        compact_style = ParagraphStyle(
            'EvidenceCompact',
            parent=styles['BodyText'],
            fontSize=7.5,
            leading=9,
            wordWrap='CJK',
        )

        data = [['#', 'Actor', 'Field', 'Score', 'Evidence (Excerpt)', 'Refs']]
        for idx, item in enumerate(evidence, 1):
            evidence_text = (item.get('text', '') or '').strip().replace('\n', ' ')
            if len(evidence_text) > 180:
                evidence_text = evidence_text[:177].rstrip() + '...'

            item_refs = []
            for url in item.get('links', []) or []:
                if isinstance(url, str) and url in refs:
                    item_refs.append(refs[url])

            data.append([
                str(idx),
                Paragraph(html.escape(item.get('actor', 'Unknown')), compact_style),
                Paragraph(html.escape(item.get('source', 'Unknown')), compact_style),
                f"{item.get('score', 0):.3f}",
                Paragraph(ReportGenerator._format_inline_markdown(evidence_text), compact_style),
                Paragraph(html.escape(", ".join(item_refs) if item_refs else "N/A"), compact_style),
            ])

        table = Table(data, colWidths=[0.35*inch, 1.2*inch, 1.0*inch, 0.55*inch, 3.2*inch, 0.8*inch], repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#111827')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 7.5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (3, 0), (3, -1), 'CENTER'),
            ('ALIGN', (5, 0), (5, -1), 'CENTER'),
        ]))
        return [table]

    @staticmethod
    def _build_references_table(evidence: List[Dict[str, Any]], styles) -> List:
        """Build structured references table with clickable links."""
        refs = ReportGenerator._collect_references(evidence)
        if not refs:
            return []

        data = [['Ref', 'URL']]
        for url, ref_id in refs.items():
            data.append([
                ref_id,
                ReportGenerator._link_paragraph(url, styles)
            ])

        table = Table(data, colWidths=[0.8*inch, 5.9*inch], repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#111827')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 7.5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return [table]

    @staticmethod
    def _extract_campaign_table(answer: str) -> List[Dict[str, str]]:
        """Extract campaign rows from a markdown table in the answer."""
        if not answer:
            return []
        lines = [line.strip() for line in answer.split('\n')]
        rows = []
        table_started = False
        for idx, line in enumerate(lines):
            if line.startswith('| Date ') and '| Activity ' in line:
                table_started = True
                continue
            if table_started:
                if not line.startswith('|'):
                    break
                if set(line.replace('|', '').strip()) <= set('- '):
                    continue
                parts = [part.strip() for part in line.strip('|').split('|')]
                if len(parts) < 2:
                    continue
                rows.append({
                    'date': parts[0],
                    'activity': parts[1],
                })
        return rows

    @staticmethod
    def _extract_counter_operations_table(answer: str) -> List[Dict[str, str]]:
        """Extract counter operations rows from a markdown table in the answer."""
        if not answer:
            return []
        lines = [line.strip() for line in answer.split('\n')]
        rows = []
        table_started = False
        for line in lines:
            line_lower = line.lower()
            if line_lower.startswith('| sr ') and '| date ' in line_lower and '| activity ' in line_lower:
                table_started = True
                continue
            if table_started:
                if not line.startswith('|'):
                    break
                if set(line.replace('|', '').strip()) <= set('- '):
                    continue
                parts = [part.strip() for part in line.strip('|').split('|')]
                if len(parts) < 3:
                    continue
                rows.append({
                    'sr': parts[0],
                    'date': parts[1],
                    'activity': parts[2],
                })
        return rows

    @staticmethod
    def _build_campaign_table(rows: List[Dict[str, str]]) -> List:
        """Build a structured campaign table for PDF."""
        if not rows:
            return []
        data = [['#', 'Date', 'Activity']]
        for idx, row in enumerate(rows, 1):
            data.append([
                str(idx),
                row.get('date', 'Unknown'),
                row.get('activity', ''),
            ])
        table = Table(data, colWidths=[0.4*inch, 1.1*inch, 4.6*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#111827')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ]))
        return [table]

    @staticmethod
    def _build_counter_operations_table(rows: List[Dict[str, str]]) -> List:
        """Build a structured counter operations table for PDF."""
        if not rows:
            return []
        data = [['Sr', 'Date', 'Activity']]
        for idx, row in enumerate(rows, 1):
            data.append([
                row.get('sr', str(idx)),
                row.get('date', 'Unknown'),
                row.get('activity', ''),
            ])
        table = Table(data, colWidths=[0.6*inch, 1.1*inch, 4.4*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#111827')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ]))
        return [table]
    
    @staticmethod
    def generate_pdf(result: Dict[str, Any]) -> bytes:
        """
        Generate PDF report from query result.
        
        Args:
            result: Query result dictionary with query, answer, evidence, confidence
            
        Returns:
            PDF bytes
        """
        try:
            normalized = ReportGenerator._normalize_result(result)

            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=0.5*inch,
                leftMargin=0.5*inch,
                topMargin=0.75*inch,
                bottomMargin=0.5*inch
            )
            
            story = []
            styles = getSampleStyleSheet()
            answer_text = ReportGenerator._sanitize_answer_for_report(normalized.get('answer', ''))
            evidence = normalized.get('evidence', [])
            field_counts = ReportGenerator._source_field_counts(evidence)
            
            # Custom styles
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                textColor=colors.HexColor('#0f172a'),
                spaceAfter=30,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )

            company_style = ParagraphStyle(
                'CompanyTitle',
                parent=styles['Heading2'],
                fontSize=14,
                textColor=colors.HexColor('#0f172a'),
                spaceAfter=6,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            
            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=14,
                textColor=colors.HexColor('#1f2937'),
                spaceAfter=12,
                spaceBefore=12,
                fontName='Helvetica-Bold'
            )
            
            body_style = ParagraphStyle(
                'CustomBody',
                parent=styles['BodyText'],
                fontSize=10,
                textColor=colors.HexColor('#111827'),
                alignment=TA_JUSTIFY,
                spaceAfter=10
            )
            
            # Title Section with better spacing
            story.append(Paragraph("THREAT INTELLIGENCE REPORT", title_style))
            story.append(Paragraph("ThreatAI Platform", company_style))
            story.append(Spacer(1, 0.3*inch))
            
            # Add a horizontal line
            from reportlab.platypus import HRFlowable
            story.append(HRFlowable(
                width="100%",
                thickness=2,
                color=colors.HexColor('#3b82f6'),
                spaceBefore=0,
                spaceAfter=20
            ))
            
            # Metadata Section with improved layout
            timestamp = ReportGenerator._parse_timestamp(normalized.get('timestamp'))
            metadata = [
                ['Report Generated:', timestamp.strftime('%B %d, %Y at %H:%M:%S')],
                ['Query Trace ID:', (normalized.get('trace_id', 'N/A')[:20] + '...') if normalized.get('trace_id') else 'N/A'],
                ['Confidence Level:', f"{(normalized.get('confidence', 0) * 100):.1f}%"],
                ['Evidence Sources:', str(normalized.get('source_count', 0))],
                ['Query Intent:', normalized.get('intent', 'general').upper()]
            ]
            
            meta_table = Table(metadata, colWidths=[1.8*inch, 4.5*inch])
            meta_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#eff6ff')),
                ('BACKGROUND', (1, 0), (1, -1), colors.white),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#111827')),
                ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
                ('LINEBELOW', (0, -1), (-1, -1), 2, colors.HexColor('#3b82f6')),
            ]))
            story.append(meta_table)
            story.append(Spacer(1, 0.4*inch))

            # Executive Summary
            story.append(Paragraph("EXECUTIVE SUMMARY", heading_style))
            summary_text = ReportGenerator._build_summary(answer_text)
            story.append(Paragraph(summary_text, body_style))
            story.append(Spacer(1, 0.2*inch))

            # Structured Data Coverage (only available fields)
            coverage_table = ReportGenerator._build_data_coverage_table(evidence)
            if coverage_table:
                story.append(Paragraph("DATA COVERAGE", heading_style))
                story.extend(coverage_table)
                story.append(Spacer(1, 0.2*inch))

            # Table of Contents
            toc_entries = ReportGenerator._extract_headings(answer_text)
            if toc_entries:
                story.append(Paragraph("TABLE OF CONTENTS", heading_style))
                for entry in toc_entries:
                    story.append(Paragraph(f"• {entry}", styles['BodyText']))
                story.append(Spacer(1, 0.2*inch))
            
            # Answer Section
            story.append(Paragraph("DETAILED ANALYSIS", heading_style))
            
            # Use the new markdown-aware formatter
            answer_elements = ReportGenerator._format_answer_for_pdf(
                answer_text or 'N/A',
                styles
            )
            story.extend(answer_elements)
            
            story.append(Spacer(1, 0.3*inch))

            campaign_rows = ReportGenerator._extract_campaign_table(answer_text)
            if campaign_rows:
                story.append(Paragraph("CAMPAIGNS & OPERATIONS", heading_style))
                story.extend(ReportGenerator._build_campaign_table(campaign_rows))
                story.append(Spacer(1, 0.3*inch))

            counter_rows = ReportGenerator._extract_counter_operations_table(answer_text)
            if counter_rows:
                story.append(Paragraph("COUNTER OPERATIONS", heading_style))
                story.extend(ReportGenerator._build_counter_operations_table(counter_rows))
                story.append(Spacer(1, 0.3*inch))

            # Render optional sections only when supporting evidence exists
            if field_counts.get('sponsor', 0) > 0:
                sponsor_text = ReportGenerator._extract_section_from_answer(answer_text, 'Sponsorship')
                if sponsor_text:
                    story.append(Paragraph("SPONSORSHIP", heading_style))
                    story.extend(ReportGenerator._format_section_content(sponsor_text, styles))
                    story.append(Spacer(1, 0.2*inch))

            if field_counts.get('entity_profile', 0) > 0:
                profile_text = ReportGenerator._extract_section_from_answer(answer_text, 'Profile')
                if profile_text:
                    story.append(Paragraph("PROFILE", heading_style))
                    story.extend(ReportGenerator._format_section_content(profile_text, styles))
                    story.append(Spacer(1, 0.2*inch))
            
            # Evidence Section
            if evidence:
                story.append(Paragraph(f"EVIDENCE MATRIX ({len(evidence)} records)", heading_style))
                story.extend(ReportGenerator._build_evidence_table(evidence, styles))
                story.append(Spacer(1, 0.2*inch))

                refs_table = ReportGenerator._build_references_table(evidence, styles)
                if refs_table:
                    story.append(Paragraph("REFERENCES", heading_style))
                    story.extend(refs_table)
            
            story.append(Spacer(1, 0.2*inch))
            story.append(Paragraph("_" * 80, body_style))
            
            # Footer
            footer_text = "This report was generated by Threat-AI Intelligence Platform"
            story.append(Paragraph(footer_text, ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontSize=8,
                textColor=colors.HexColor('#6b7280'),
                alignment=TA_CENTER
            )))
            
            doc.build(story)
            buffer.seek(0)
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Error generating PDF: {e}")
            raise
    
    @staticmethod
    def generate_csv(result: Dict[str, Any]) -> str:
        """
        Generate CSV report from query result.
        
        Args:
            result: Query result dictionary
            
        Returns:
            CSV string
        """
        try:
            normalized = ReportGenerator._normalize_result(result)

            output = io.StringIO()
            writer = csv.writer(output)
            
            # Header
            writer.writerow(['ThreatAI Intelligence Report'])
            writer.writerow([])
            
            # Metadata
            timestamp = ReportGenerator._parse_timestamp(normalized.get('timestamp'))
            writer.writerow(['Report Metadata'])
            writer.writerow(['Generated', timestamp.strftime('%Y-%m-%d %H:%M:%S')])
            writer.writerow(['Trace ID', normalized.get('trace_id', 'N/A')])
            writer.writerow(['Confidence', f"{(normalized.get('confidence', 0) * 100):.1f}%"])
            writer.writerow(['Sources Used', normalized.get('source_count', 0)])
            writer.writerow([])
            
            # Query
            writer.writerow(['QUERY'])
            writer.writerow([normalized.get('query', 'N/A')])
            writer.writerow([])
            
            answer_text = ReportGenerator._sanitize_answer_for_report(normalized.get('answer', ''))

            # Executive Summary
            writer.writerow(['EXECUTIVE SUMMARY'])
            summary_text = ReportGenerator._build_summary(answer_text)
            writer.writerow([summary_text])
            writer.writerow([])

            # Answer
            writer.writerow(['ANALYSIS & ANSWER'])
            writer.writerow([answer_text or 'N/A'])
            writer.writerow([])
            
            # Evidence
            evidence = normalized.get('evidence', [])
            if evidence:
                writer.writerow(['EVIDENCE SOURCES'])
                writer.writerow(['#', 'Actor', 'Source', 'Score', 'Text', 'Links'])
                for i, e in enumerate(evidence, 1):
                    links = e.get('links', [])
                    link_str = " | ".join([l for l in links if isinstance(l, str)])
                    writer.writerow([
                        i,
                        e.get('actor', 'Unknown'),
                        e.get('source', 'Unknown'),
                        f"{e.get('score', 0):.3f}",
                        e.get('text', 'N/A'),
                        link_str
                    ])
                writer.writerow([])

                # References section
                all_links = []
                for e in evidence:
                    links = e.get('links', [])
                    if links:
                        all_links.extend([l for l in links if isinstance(l, str)])
                unique_links = list(dict.fromkeys(all_links))
                if unique_links:
                    writer.writerow(['REFERENCES'])
                    for link in unique_links:
                        writer.writerow([link])
                    writer.writerow([])
            
            writer.writerow(['---'])
            writer.writerow(['Generated by Threat-AI Intelligence Platform'])
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Error generating CSV: {e}")
            raise
