"""Generate reports in PDF and CSV formats."""

import csv
import io
import re
from datetime import datetime
from typing import Dict, Any, List
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, HRFlowable
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
import logging

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generate reports in different formats."""

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
    def _build_summary(answer: str) -> str:
        """Create a short, human-readable summary from the answer text."""
        if not answer:
            return "No summary available."
        # Remove markdown formatting for summary
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', answer)  # Remove bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)  # Remove italic
        text = " ".join(text.strip().split())
        sentences = re.split(r"(?<=[.!?])\s+", text)
        summary = " ".join(sentences[:2]).strip()
        return summary if summary else text[:200]
    
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
        """Build an appendix evidence table for PDF."""
        if not evidence:
            return []
        data = [['#', 'Actor', 'Source', 'Score', 'Link']]
        for idx, item in enumerate(evidence, 1):
            link = ''
            links = item.get('links', [])
            if links:
                for l in links:
                    if isinstance(l, str) and l.startswith('http'):
                        link = l
                        break
            data.append([
                str(idx),
                item.get('actor', 'Unknown'),
                item.get('source', 'Unknown'),
                f"{item.get('score', 0):.3f}",
                link or 'N/A'
            ])

        table = Table(data, colWidths=[0.4*inch, 1.4*inch, 1.2*inch, 0.7*inch, 2.6*inch])
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
            timestamp = ReportGenerator._parse_timestamp(result.get('timestamp'))
            metadata = [
                ['Report Generated:', timestamp.strftime('%B %d, %Y at %H:%M:%S')],
                ['Query Trace ID:', result.get('trace_id', 'N/A')[:20] + '...'],
                ['Confidence Level:', f"{(result.get('confidence', 0) * 100):.1f}%"],
                ['Evidence Sources:', str(result.get('source_count', 0))],
                ['Query Intent:', result.get('intent', 'general').upper()]
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
            
            # Query Section with box
            query_box_style = ParagraphStyle(
                'QueryBox',
                parent=styles['BodyText'],
                fontSize=11,
                textColor=colors.HexColor('#1e40af'),
                fontName='Helvetica-Bold',
                leftIndent=10,
                rightIndent=10,
                spaceAfter=10
            )
            story.append(Paragraph("USER QUERY", heading_style))
            
            # Create a box around the query
            query_table = Table([[Paragraph(result.get('query', 'N/A'), query_box_style)]], 
                              colWidths=[6.5*inch])
            query_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f9ff')),
                ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#3b82f6')),
                ('TOPPADDING', (0, 0), (-1, -1), 12),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ]))
            story.append(query_table)
            story.append(Spacer(1, 0.3*inch))

            # Executive Summary
            story.append(Paragraph("EXECUTIVE SUMMARY", heading_style))
            summary_text = ReportGenerator._build_summary(result.get('answer', ''))
            story.append(Paragraph(summary_text, body_style))
            story.append(Spacer(1, 0.2*inch))

            # Table of Contents
            toc_entries = ReportGenerator._extract_headings(result.get('answer', ''))
            if toc_entries:
                story.append(Paragraph("TABLE OF CONTENTS", heading_style))
                for entry in toc_entries:
                    story.append(Paragraph(f"• {entry}", styles['BodyText']))
                story.append(Spacer(1, 0.2*inch))
            
            # Answer Section
            story.append(Paragraph("DETAILED ANALYSIS", heading_style))
            
            # Use the new markdown-aware formatter
            answer_elements = ReportGenerator._format_answer_for_pdf(
                result.get('answer', 'N/A'), 
                styles
            )
            story.extend(answer_elements)
            
            story.append(Spacer(1, 0.3*inch))

            campaign_rows = ReportGenerator._extract_campaign_table(result.get('answer', ''))
            if campaign_rows:
                story.append(Paragraph("CAMPAIGNS & OPERATIONS", heading_style))
                story.extend(ReportGenerator._build_campaign_table(campaign_rows))
                story.append(Spacer(1, 0.3*inch))

            counter_rows = ReportGenerator._extract_counter_operations_table(result.get('answer', ''))
            if counter_rows:
                story.append(Paragraph("COUNTER OPERATIONS", heading_style))
                story.extend(ReportGenerator._build_counter_operations_table(counter_rows))
                story.append(Spacer(1, 0.3*inch))
            
            # Evidence Section
            evidence = result.get('evidence', [])
            if evidence:
                story.append(Paragraph(f"EVIDENCE SOURCES ({len(evidence)} found)", heading_style))
                
                for i, e in enumerate(evidence, 1):
                    evidence_header = f"[{i}] {e.get('actor', 'Unknown')} - {e.get('source', 'Unknown')} (Score: {e.get('score', 0):.3f})"
                    story.append(Paragraph(evidence_header, ParagraphStyle(
                        'EvidenceHeader',
                        parent=styles['BodyText'],
                        fontSize=9,
                        textColor=colors.HexColor('#111827'),
                        fontName='Helvetica-Bold'
                    )))
                    links = e.get('links', [])
                    if links:
                        safe_links = [l for l in links if isinstance(l, str) and l.startswith('http')]
                        if safe_links:
                            links_html = "<br/>".join([f"<link href='{l}'>{l}</link>" for l in safe_links])
                            story.append(Paragraph(f"Sources:<br/>{links_html}", body_style))
                    story.append(Paragraph(e.get('text', 'N/A'), body_style))
                    story.append(Spacer(1, 0.1*inch))

                # References section
                all_links = []
                for e in evidence:
                    links = e.get('links', [])
                    if links:
                        all_links.extend([l for l in links if isinstance(l, str) and l.startswith('http')])
                unique_links = list(dict.fromkeys(all_links))
                if unique_links:
                    story.append(Spacer(1, 0.2*inch))
                    story.append(Paragraph("REFERENCES", heading_style))
                    refs_html = "<br/>".join([f"<link href='{l}'>{l}</link>" for l in unique_links])
                    story.append(Paragraph(refs_html, body_style))

                story.append(Spacer(1, 0.2*inch))
                story.append(Paragraph("APPENDIX: SOURCES TABLE", heading_style))
                story.extend(ReportGenerator._build_evidence_table(evidence, styles))
            
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
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Header
            writer.writerow(['ThreatAI Intelligence Report'])
            writer.writerow([])
            
            # Metadata
            timestamp = ReportGenerator._parse_timestamp(result.get('timestamp'))
            writer.writerow(['Report Metadata'])
            writer.writerow(['Generated', timestamp.strftime('%Y-%m-%d %H:%M:%S')])
            writer.writerow(['Trace ID', result.get('trace_id', 'N/A')])
            writer.writerow(['Confidence', f"{(result.get('confidence', 0) * 100):.1f}%"])
            writer.writerow(['Sources Used', result.get('source_count', 0)])
            writer.writerow([])
            
            # Query
            writer.writerow(['QUERY'])
            writer.writerow([result.get('query', 'N/A')])
            writer.writerow([])
            
            # Executive Summary
            writer.writerow(['EXECUTIVE SUMMARY'])
            summary_text = ReportGenerator._build_summary(result.get('answer', ''))
            writer.writerow([summary_text])
            writer.writerow([])

            # Answer
            writer.writerow(['ANALYSIS & ANSWER'])
            writer.writerow([result.get('answer', 'N/A')])
            writer.writerow([])
            
            # Evidence
            evidence = result.get('evidence', [])
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
