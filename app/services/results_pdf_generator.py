# app/services/results_pdf_generator.py
from io import BytesIO
from datetime import datetime
from typing import Any, Dict, List
import os
import math
import pytz
import re

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    from reportlab.platypus.flowables import Flowable
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.graphics.charts.barcharts import HorizontalBarChart
    from reportlab.graphics import renderPDF
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    import qrcode
    from qrcode.image.styledpil import StyledPilImage
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

def convert_markdown_to_reportlab_html(markdown_text: str) -> str:
    """
    Convert markdown to ReportLab-compatible HTML.
    ReportLab Paragraph supports: b, i, u, a href, br, font
    """
    if not markdown_text:
        return ""
    
    html = markdown_text
    
    # Convert **bold** to <b>bold</b>
    html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
    html = re.sub(r'__(.+?)__', r'<b>\1</b>', html)
    
    # Convert *italic* to <i>italic</i>
    html = re.sub(r'\*(.+?)\*', r'<i>\1</i>', html)
    html = re.sub(r'_(.+?)_', r'<i>\1</i>', html)
    
    # Convert [text](url) to <a href="url">text</a>
    html = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2" color="blue">\1</a>', html)
    
    # Convert line breaks
    html = html.replace('\n', '<br/>')
    
    # Escape any remaining special characters that might break ReportLab
    # But preserve our HTML tags
    return html

def register_custom_fonts():
    """Register Montserrat and Gloock fonts for the PDF."""
    fonts_registered = False
    
    try:
        fonts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "fonts")
        
        # Register Montserrat
        try:
            pdfmetrics.registerFont(TTFont('Montserrat', os.path.join(fonts_dir, 'Montserrat-Regular.ttf')))
            pdfmetrics.registerFont(TTFont('Montserrat-Medium', os.path.join(fonts_dir, 'Montserrat-Medium.ttf')))
            pdfmetrics.registerFont(TTFont('Montserrat-SemiBold', os.path.join(fonts_dir, 'Montserrat-SemiBold.ttf')))
            print("✓ Montserrat fonts registered successfully")
        except:
            print("✗ Montserrat fonts not found, using fallback")
        
        # Register Gloock
        try:
            pdfmetrics.registerFont(TTFont('Gloock', os.path.join(fonts_dir, 'Gloock-Regular.ttf')))
            print("✓ Gloock font registered successfully")
        except:
            print("✗ Gloock font not found, using fallback")
        
        # Register font families
        try:
            registerFontFamily('Montserrat', normal='Montserrat', bold='Montserrat-SemiBold')
            registerFontFamily('Gloock', normal='Gloock')
            fonts_registered = True
        except:
            pass
        
    except Exception as e:
        print(f"Failed to register custom fonts: {e}")
    
    return fonts_registered

def get_font_name(font_type='normal', use_bold=False):
    """Get the appropriate font name with fallback support."""
    try:
        if font_type == 'heading':
            try:
                pdfmetrics.getFont('Gloock')
                return 'Gloock'
            except:
                return 'Helvetica-Bold'
        elif use_bold:
            try:
                pdfmetrics.getFont('Montserrat-SemiBold')
                return 'Montserrat-SemiBold'
            except:
                return 'Helvetica-Bold'
        else:
            try:
                pdfmetrics.getFont('Montserrat')
                return 'Montserrat'
            except:
                return 'Helvetica'
    except:
        return 'Helvetica'

def get_winner_color(winner_type):
    """Get color based on winner type."""
    colors_map = {
        'condorcet': colors.HexColor('#4CAF50'),  # Green
        'most_wins': colors.HexColor('#2196F3'),   # Blue
        'smallest_loss': colors.HexColor('#FF9800'), # Orange
        'tie': colors.HexColor('#757575'),         # Grey
    }
    return colors_map.get(winner_type, colors.HexColor('#757575'))

def create_head_to_head_bar_chart(cand1_name, cand2_name, cand1_votes, cand2_votes, width=4*inch, height=0.8*inch):
    """Create a horizontal bar chart for head-to-head comparison."""
    from reportlab.graphics.shapes import Drawing, Rect, String
    
    drawing = Drawing(width, height)
    
    # Calculate total and percentages
    total_votes = cand1_votes + cand2_votes
    if total_votes == 0:
        return drawing
    
    cand1_pct = (cand1_votes / total_votes) * 100
    cand2_pct = (cand2_votes / total_votes) * 100
    
    # Determine winner for coloring
    if cand1_votes > cand2_votes:
        cand1_color = colors.HexColor('#4CAF50')  # Green for winner
        cand2_color = colors.HexColor('#F44336')  # Red for loser
    elif cand2_votes > cand1_votes:
        cand1_color = colors.HexColor('#F44336')  # Red for loser
        cand2_color = colors.HexColor('#4CAF50')  # Green for winner
    else:
        cand1_color = colors.HexColor('#FFC107')  # Amber for tie
        cand2_color = colors.HexColor('#FFC107')  # Amber for tie
    
    # Bar dimensions
    bar_height = height * 0.25
    bar_y_top = height * 0.65
    bar_y_bottom = height * 0.25
    
    # Calculate bar widths
    cand1_width = (cand1_pct / 100) * width
    cand2_width = (cand2_pct / 100) * width
    
    # Draw bars
    # Candidate 1 bar (top)
    drawing.add(Rect(0, bar_y_top, cand1_width, bar_height, 
                    fillColor=cand1_color, strokeColor=None))
    
    # Candidate 2 bar (bottom)
    drawing.add(Rect(0, bar_y_bottom, cand2_width, bar_height, 
                    fillColor=cand2_color, strokeColor=None))
    
    # Add labels
    # Candidate names and votes
    drawing.add(String(5, bar_y_top + bar_height + 5, 
                      f"{cand1_name}: {cand1_votes:,} votes ({cand1_pct:.1f}%)",
                      fontSize=9, fontName=get_font_name('normal')))
    
    drawing.add(String(5, bar_y_bottom - 12, 
                      f"{cand2_name}: {cand2_votes:,} votes ({cand2_pct:.1f}%)",
                      fontSize=9, fontName=get_font_name('normal')))
    
    return drawing

def create_ballot_statistics_visual(stats):
    """Create visual representation of ballot statistics."""
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib import colors
    
    width = 6*inch
    height = 2.5*inch  # Reduced height
    drawing = Drawing(width, height)
    
    # Statistics to display - MUST match field names from backend!
    stat_items = [
        ("Ranked (almost) all candidates", stats.get('ranked_almost_all', 0), colors.HexColor('#4CAF50')),
        ("Submitted a partial ranking", stats.get('partial_ranking', 0), colors.HexColor('#2196F3')),
        ("Ballots had gaps", stats.get('had_gaps', 0), colors.HexColor('#FF9800')),
        ("Bullet vote", stats.get('single_choice_only', 0), colors.HexColor('#9E9E9E'))
    ]
    
    # Layout parameters - FIXED positioning
    bar_width = width * 0.45  # Narrower bars
    bar_height = 15  # Thinner bars
    y_spacing = 35  # Less spacing
    left_margin = width * 0.42  # Move bars right to give text more room
    
    for i, (label, value, color) in enumerate(stat_items):
        y_pos = height - ((i + 1) * y_spacing) + 10  # Adjust vertical position
        
        # Label (left side - more room)
        drawing.add(String(5, y_pos + 3, label, 
                         fontSize=9, fontName=get_font_name('normal')))
        
        # Background bar
        drawing.add(Rect(left_margin, y_pos, bar_width, bar_height,
                        fillColor=colors.HexColor('#E0E0E0'), strokeColor=None))
        
        # Value bar
        if value > 0:
            value_width = (value / 100) * bar_width
            drawing.add(Rect(left_margin, y_pos, value_width, bar_height,
                           fillColor=color, strokeColor=None))
        
        # Percentage label (right of bar)
        drawing.add(String(left_margin + bar_width + 10, y_pos + 3, f"{value}%",
                         fontSize=9, fontName=get_font_name('normal', use_bold=True)))
    
    return drawing

def generate_results_pdf(poll: Dict, results: Dict) -> bytes:
    """
    Generate a professional PDF of poll results including winner, head-to-head comparisons, and details.
    
    Args:
        poll: Poll data dictionary
        results: Results data dictionary from the API
    
    Returns:
        PDF content as bytes
    """
    
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("PDF generation requires reportlab library")
    
    # Register custom fonts
    register_custom_fonts()
    
    # Create a BytesIO buffer
    buffer = BytesIO()
    
    # Create the PDF
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=50,
        bottomMargin=72
    )
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.black,
        spaceAfter=25,
        alignment=TA_CENTER,
        fontName=get_font_name('heading')
    )
    
    heading_style = ParagraphStyle(
        'Heading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2C3E50'),
        spaceAfter=12,
        spaceBefore=20,
        fontName=get_font_name('heading')
    )
    
    normal_style = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=10,
        fontName=get_font_name('normal')
    )
    
    bold_style = ParagraphStyle(
        'Bold',
        parent=styles['Normal'],
        fontSize=10,
        fontName=get_font_name('normal', use_bold=True)
    )
    
    # Build the document content
    story = []
    
    # Header with logo
    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images", "betterchoices-full-logo.png")
    
    if not os.path.exists(logo_path):
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "betterchoices-full-logo.png")
    
    logo_added = False
    if os.path.exists(logo_path):
        try:
            logo_width = 2.5 * inch
            logo_height = 0.95 * inch  # Maintains aspect ratio
            logo = Image(logo_path, width=logo_width, height=logo_height)
            logo.hAlign = 'LEFT'
            story.append(logo)
            logo_added = True
        except Exception as e:
            print(f"Failed to load logo: {e}")
    
    if not logo_added:
        story.append(Paragraph("BetterChoices - Better Democracy Through Better Voting", 
                              ParagraphStyle('LogoText', parent=heading_style, fontSize=14)))
    
    story.append(Spacer(1, 20))
    
    # Main title
    story.append(Paragraph("Poll Results Report", title_style))
    
    # Poll Information with QR Code
    story.append(Paragraph("Poll Information", heading_style))
    
    # Generate QR code for results URL
    results_url = f"{os.getenv('BASE_URL', 'https://betterchoices.vote')}/results/{poll.get('short_id', '')}"
    qr_image = None
    
    if QRCODE_AVAILABLE:
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=5,
                border=2,
            )
            qr.add_data(results_url)
            qr.make(fit=True)
            
            qr_img = qr.make_image(fill_color="black", back_color="white")
            
            qr_buffer = BytesIO()
            qr_img.save(qr_buffer, format='PNG')
            qr_buffer.seek(0)
            qr_image = Image(qr_buffer, width=1.5*inch, height=1.5*inch)
        except Exception as e:
            print(f"QR code generation failed: {e}")
    
    # Create poll info data - Include total voters
    # Wrap title and URL in Paragraph to allow wrapping
    title_para = Paragraph(poll.get('title', 'Untitled Poll'), normal_style)
    url_para = Paragraph(results_url, normal_style)
    
    poll_info_basic = [
        ["Poll Title:", title_para],
        ["Poll ID:", poll.get('short_id', 'N/A')],
        ["Total Voters:", f"{results.get('statistics', {}).get('total_votes', 0):,}"],  # Keep total voters
        ["Generated:", datetime.now().strftime('%B %d, %Y at %I:%M %p')],
        ["Results URL:", url_para]
    ]
    
    # Create the basic info table
    poll_info_table = Table(poll_info_basic, colWidths=[1.5*inch, 3.8*inch])
    poll_info_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 0), (0, -1), get_font_name('normal', use_bold=True)),
        ('FONTNAME', (1, 0), (1, -1), get_font_name('normal')),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    
    # If QR code exists, create layout with QR on right
    if qr_image:
        # Create a table with info on left and QR on right
        container_data = [[poll_info_table, qr_image]]
        container_table = Table(container_data, colWidths=[5.5*inch, 1.5*inch])
        container_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(container_table)
    else:
        story.append(poll_info_table)
    
    # Add description separately below the QR code section
    if poll.get('description'):
        story.append(Spacer(1, 10))
        # Convert markdown to HTML for ReportLab
        desc_html = convert_markdown_to_reportlab_html(poll['description'])
        desc_para = Paragraph(f"<b>Description:</b> {desc_html}", normal_style)
        story.append(desc_para)
    
    story.append(Spacer(1, 25))
    
    # Winner Section
    winner_type = results.get('winner_type', 'unknown')
    winner = results.get('winner')
    winners = results.get('winners', [])
    winner_color = get_winner_color(winner_type)
    
    story.append(Paragraph("Consensus Choice Winner", heading_style))
    
    # Winner box
    if winner_type == 'tie' and winners:
        winner_text = f"<b>Tied Winners:</b> {', '.join(winners)}"
    elif winner:
        winner_text = f"<b>Winner:</b> {winner}"
    else:
        winner_text = "<b>No Clear Winner</b>"
    
    winner_explanation = {
        'condorcet': 'Beats every other candidate head-to-head',
        'most_wins': 'Has the best win-loss record',
        'smallest_loss': 'Has the smallest loss among all candidates with the most wins',
        'tie': 'There is a tie in the head-to-head comparisons'
    }.get(winner_type, '')
    
    winner_para = Paragraph(
        f"{winner_text}<br/><br/><i>{winner_explanation}</i>",
        ParagraphStyle('Winner', parent=normal_style, 
                      textColor=winner_color, 
                      fontSize=14,
                      alignment=TA_CENTER,
                      spaceAfter=20)
    )
    
    winner_table = Table([[winner_para]], colWidths=[6*inch])
    winner_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 2, winner_color),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F5F5F5')),
        ('TOPPADDING', (0, 0), (-1, -1), 15),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
    ]))
    
    story.append(winner_table)
    story.append(Spacer(1, 20))
    
    # Get pairwise matrix and detailed results for later use
    pairwise_matrix = results.get('pairwise_matrix', {})
    detailed_results = results.get('detailed_pairwise_results', {})
    
    # STANDINGS TABLE (no heading, right after winner)
    if pairwise_matrix:
        candidates = list(pairwise_matrix.keys())
        
        # Calculate wins, losses, ties for each candidate
        candidate_stats = {}
        for candidate in candidates:
            wins = 0
            losses = 0
            ties = 0
            for opponent in candidates:
                if opponent != candidate:
                    margin = pairwise_matrix.get(candidate, {}).get(opponent, 0)
                    if margin > 0:
                        wins += 1
                    elif margin < 0:
                        losses += 1
                    else:
                        ties += 1
            candidate_stats[candidate] = {'wins': wins, 'losses': losses, 'ties': ties}
        
        # Create standings table
        standings_data = [['Candidate', 'Wins', 'Losses', 'Ties']]
        
        sorted_candidates = sorted(candidates, 
                                  key=lambda c: (candidate_stats[c]['wins'], -candidate_stats[c]['losses']), 
                                  reverse=True)
        
        for candidate in sorted_candidates:
            stats = candidate_stats[candidate]
            is_winner = (winner and candidate == winner) or (candidate in winners)
            row = [
                candidate if not is_winner else f"{candidate} ★",
                str(stats['wins']),
                str(stats['losses']),
                str(stats['ties'])
            ]
            standings_data.append(row)
        
        standings_table = Table(standings_data, colWidths=[3*inch, 1*inch, 1*inch, 1*inch])
        standings_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), get_font_name('normal', use_bold=True)),
            ('FONTNAME', (0, 1), (0, -1), get_font_name('normal')),
            ('FONTNAME', (1, 1), (-1, -1), get_font_name('normal')),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        story.append(standings_table)
    
    story.append(Spacer(1, 25))
    
    # HEAD-TO-HEAD COMPARISONS with Visual Bar Charts
    story.append(Paragraph("Head-to-Head Comparisons", heading_style))
    
    if detailed_results:
        # Sort comparisons for consistent ordering
        comparisons = sorted(detailed_results.keys())
        
        # Create a table with bar charts for each comparison
        comparison_data = []
        
        for comparison_key in comparisons:
            comp_data = detailed_results[comparison_key]
            
            # Extract candidate names from the comparison key
            parts = comparison_key.replace('_vs_', ' vs ').split(' vs ')
            if len(parts) == 2:
                cand1_name = parts[0]
                cand2_name = parts[1]
                
                # Get vote counts
                cand1_votes = comp_data.get(cand1_name, 0)
                cand2_votes = comp_data.get(cand2_name, 0)
                
                # Create title for this comparison
                title_text = f"<b>{cand1_name} vs {cand2_name}</b>"
                title_para = Paragraph(title_text, bold_style)
                
                # Create the bar chart
                bar_chart = create_head_to_head_bar_chart(
                    cand1_name, cand2_name, 
                    cand1_votes, cand2_votes,
                    width=4.5*inch, height=0.8*inch
                )
                
                # Add to comparison data
                comparison_data.append([title_para])
                comparison_data.append([bar_chart])
                comparison_data.append([Spacer(1, 10)])
        
        if comparison_data:
            # Remove the last spacer
            if len(comparison_data) > 0 and isinstance(comparison_data[-1][0], Spacer):
                comparison_data.pop()
            
            comparison_table = Table(comparison_data, colWidths=[6*inch])
            comparison_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ]))
            story.append(comparison_table)
    
    story.append(Spacer(1, 25))
    
    # BALLOT STATISTICS - matching online display exactly
    if results.get('statistics'):
        story.append(Paragraph("Ballot Statistics", heading_style))
        
        stats = results['statistics']
        
        # Add Total Voters prominently
        total_voters_data = [
            ["Total Voters:", f"{stats.get('total_votes', 0):,}"]
        ]
        total_voters_table = Table(total_voters_data, colWidths=[1.5*inch, 2*inch])
        total_voters_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, 0), get_font_name('normal', use_bold=True)),
            ('FONTNAME', (1, 0), (1, 0), get_font_name('normal', use_bold=True)),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(total_voters_table)
        story.append(Spacer(1, 15))
        
        # Voting Patterns heading
        story.append(Paragraph("VOTING PATTERNS", 
                              ParagraphStyle('PatternTitle', parent=normal_style, 
                                           fontSize=9, textColor=colors.HexColor('#666666'))))
        story.append(Spacer(1, 10))
        
        # Statistics table with percentages - matching the exact field names!
        stats_data = []
        
        # Ranked (almost) all candidates
        if 'ranked_almost_all' in stats:
            stats_data.append([
                "Ranked (almost) all candidates",
                f"{stats['ranked_almost_all']}%",
                "All except possibly 1 candidate"
            ])
        
        # Submitted a partial ranking
        if 'partial_ranking' in stats:
            stats_data.append([
                "Submitted a partial ranking",
                f"{stats['partial_ranking']}%",
                "Left at least 2 candidates unranked"
            ])
        
        # Ballots had gaps
        if 'had_gaps' in stats:
            stats_data.append([
                "Ballots had gaps",
                f"{stats['had_gaps']}%",
                "Skipped ranks in sequence"
            ])
        
        # Bullet vote
        if 'single_choice_only' in stats:
            stats_data.append([
                "Bullet vote",
                f"{stats['single_choice_only']}%",
                "Ranked only first choice"
            ])
        
        if stats_data:
            stats_table = Table(stats_data, colWidths=[2.6*inch, 0.8*inch, 3*inch])
            stats_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), get_font_name('normal', use_bold=True)),
                ('FONTNAME', (1, 0), (1, -1), get_font_name('normal', use_bold=True)),
                ('FONTNAME', (2, 0), (2, -1), get_font_name('normal')),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#2196F3')),
                ('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor('#666666')),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F9F9F9')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E0E0E0')),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ]))
            story.append(stats_table)
        
        story.append(Spacer(1, 10))
        
        # Note about overlapping
        story.append(Paragraph(
            "<i>Note: Categories can overlap (e.g., a ballot can be both partial and have gaps)</i>",
            ParagraphStyle('Note', parent=normal_style, fontSize=8, 
                         textColor=colors.HexColor('#666666'), alignment=TA_CENTER)
        ))
    
    # Footer
    story.append(Spacer(1, 40))
    
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    story.append(Paragraph(
        "This results report is generated from BetterChoices voting platform.",
        footer_style
    ))
    story.append(Paragraph(
        "Powered by BetterChoices - Better Democracy Through Better Voting",
        ParagraphStyle('FooterBold', parent=footer_style, fontName='Helvetica-Bold')
    ))
    story.append(Paragraph("betterchoices.vote", 
                          ParagraphStyle('Website', parent=footer_style, 
                                       textColor=colors.HexColor('#0066CC'))))
    
    # Build the PDF
    doc.build(story)
    
    # Get the PDF content
    pdf_content = buffer.getvalue()
    buffer.close()
    
    return pdf_content