"""Generate reports in PDF and CSV formats."""

import csv
import io
from datetime import datetime
from typing import Dict, Any, List
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
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
                textColor=colors.HexColor('#00d9ff'),
                spaceAfter=30,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            
            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=14,
                textColor=colors.HexColor('#7c3aed'),
                spaceAfter=12,
                spaceBefore=12,
                fontName='Helvetica-Bold'
            )
            
            body_style = ParagraphStyle(
                'CustomBody',
                parent=styles['BodyText'],
                fontSize=10,
                alignment=TA_JUSTIFY,
                spaceAfter=10
            )
            
            # Title
            story.append(Paragraph("THREAT-AI Intelligence Report", title_style))
            story.append(Spacer(1, 0.2*inch))
            
            # Metadata
            timestamp = ReportGenerator._parse_timestamp(result.get('timestamp'))
            metadata = [
                ['Generated:', timestamp.strftime('%Y-%m-%d %H:%M:%S')],
                ['Trace ID:', result.get('trace_id', 'N/A')[:16] + '...'],
                ['Model:', result.get('model', 'N/A')],
                ['Confidence:', f"{(result.get('confidence', 0) * 100):.1f}%"],
                ['Sources Used:', str(result.get('source_count', 0))]
            ]
            
            meta_table = Table(metadata, colWidths=[1.5*inch, 4*inch])
            meta_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#1a1f3a')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#e2e8f0')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#2d3748')),
            ]))
            story.append(meta_table)
            story.append(Spacer(1, 0.3*inch))
            
            # Query Section
            story.append(Paragraph("QUERY", heading_style))
            story.append(Paragraph(result.get('query', 'N/A'), body_style))
            story.append(Spacer(1, 0.2*inch))
            
            # Answer Section
            story.append(Paragraph("ANALYSIS & ANSWER", heading_style))
            story.append(Paragraph(result.get('answer', 'N/A'), body_style))
            story.append(Spacer(1, 0.2*inch))
            
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
                        textColor=colors.HexColor('#00d9ff'),
                        fontName='Helvetica-Bold'
                    )))
                    story.append(Paragraph(e.get('text', 'N/A'), body_style))
                    story.append(Spacer(1, 0.1*inch))
            
            story.append(Spacer(1, 0.2*inch))
            story.append(Paragraph("_" * 80, body_style))
            
            # Footer
            footer_text = "This report was generated by Threat-AI Intelligence Platform"
            story.append(Paragraph(footer_text, ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontSize=8,
                textColor=colors.HexColor('#64748b'),
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
            writer.writerow(['Threat-AI Intelligence Report'])
            writer.writerow([])
            
            # Metadata
            timestamp = ReportGenerator._parse_timestamp(result.get('timestamp'))
            writer.writerow(['Report Metadata'])
            writer.writerow(['Generated', timestamp.strftime('%Y-%m-%d %H:%M:%S')])
            writer.writerow(['Trace ID', result.get('trace_id', 'N/A')])
            writer.writerow(['Model', result.get('model', 'N/A')])
            writer.writerow(['Confidence', f"{(result.get('confidence', 0) * 100):.1f}%"])
            writer.writerow(['Sources Used', result.get('source_count', 0)])
            writer.writerow([])
            
            # Query
            writer.writerow(['QUERY'])
            writer.writerow([result.get('query', 'N/A')])
            writer.writerow([])
            
            # Answer
            writer.writerow(['ANALYSIS & ANSWER'])
            writer.writerow([result.get('answer', 'N/A')])
            writer.writerow([])
            
            # Evidence
            evidence = result.get('evidence', [])
            if evidence:
                writer.writerow(['EVIDENCE SOURCES'])
                writer.writerow(['#', 'Actor', 'Source', 'Score', 'Text'])
                for i, e in enumerate(evidence, 1):
                    writer.writerow([
                        i,
                        e.get('actor', 'Unknown'),
                        e.get('source', 'Unknown'),
                        f"{e.get('score', 0):.3f}",
                        e.get('text', 'N/A')
                    ])
                writer.writerow([])
            
            writer.writerow(['---'])
            writer.writerow(['Generated by Threat-AI Intelligence Platform'])
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Error generating CSV: {e}")
            raise
