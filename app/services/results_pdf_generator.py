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

def create_head_to_head_bar_chart(cand1_name, cand2_name, cand1_votes, cand2_votes, is_tie=False, margin=0, width=5.5*inch, height=1.1*inch):
    """
    Create a clean, professional head-to-head comparison chart.
    Vote boxes and bars use EXACT same widths for perfect alignment.
    """
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib import colors
    
    drawing = Drawing(width, height)
    
    # Calculate percentages - ONLY from voters with opinion
    total_with_opinion = cand1_votes + cand2_votes
    if total_with_opinion == 0:
        return drawing
    
    cand1_pct = (cand1_votes / total_with_opinion) * 100
    cand2_pct = (cand2_votes / total_with_opinion) * 100
    
    # Professional muted colors
    if is_tie:
        winner_color = colors.HexColor('#9e9e9e')
        loser_color = colors.HexColor('#9e9e9e')
        winner_bg = colors.HexColor('#f5f5f5')
        loser_bg = colors.HexColor('#f5f5f5')
        winner_text = colors.HexColor('#666666')
        loser_text = colors.HexColor('#666666')
    else:
        winner_color = colors.HexColor('#66bb6a')  # Muted green
        loser_color = colors.HexColor('#ef5350')   # Muted red  
        winner_bg = colors.HexColor('#e8f5e9')     # Light green
        loser_bg = colors.HexColor('#ffebee')      # Light red
        winner_text = colors.HexColor('#2e7d32')   # Dark green
        loser_text = colors.HexColor('#c62828')    # Dark red
    
    # CRITICAL: Calculate widths ONCE and use for both boxes and bars
    cand1_width = (cand1_pct / 100) * width
    cand2_width = (cand2_pct / 100) * width
    
    # Layout dimensions
    vote_box_height = 26
    vote_box_y = height * 0.58
    bar_height = 26
    bar_y = height * 0.28
    
    # === VOTE COUNT BOXES - EXACT SAME WIDTHS AS BARS ===
    if cand1_width > 0:
        drawing.add(Rect(0, vote_box_y, cand1_width, vote_box_height,
                        fillColor=winner_bg, strokeColor=None))
    
    if cand2_width > 0:
        drawing.add(Rect(cand1_width, vote_box_y, cand2_width, vote_box_height,
                        fillColor=loser_bg, strokeColor=None))
    
    # Vote count text - centered in their respective sections
    drawing.add(String(cand1_width / 2, vote_box_y + vote_box_height / 2 - 3,
                      f"{int(cand1_votes):,}",
                      fontSize=10, fontName=get_font_name('normal', use_bold=True),
                      fillColor=winner_text,
                      textAnchor='middle'))

    drawing.add(String(cand1_width + cand2_width / 2, vote_box_y + vote_box_height / 2 - 3,
                      f"{int(cand2_votes):,}",
                      fontSize=10, fontName=get_font_name('normal', use_bold=True),
                      fillColor=loser_text,
                      textAnchor='middle'))
    
    # === MAIN BAR - EXACT SAME WIDTHS AS BOXES ===
    if cand1_width > 0:
        drawing.add(Rect(0, bar_y, cand1_width, bar_height,
                        fillColor=winner_color, strokeColor=None))
        # Percentage inside bar - SMALLER FONT
        if cand1_pct >= 15:
            drawing.add(String(cand1_width / 2, bar_y + bar_height / 2 - 3,
                              f"{round(cand1_pct)}%",
                              fontSize=10, fontName=get_font_name('normal', use_bold=True),
                              fillColor=colors.white, textAnchor='middle'))
    
    if cand2_width > 0:
        drawing.add(Rect(cand1_width, bar_y, cand2_width, bar_height,
                        fillColor=loser_color, strokeColor=None))
        # Percentage inside bar - SMALLER FONT
        if cand2_pct >= 15:
            drawing.add(String(cand1_width + cand2_width / 2, bar_y + bar_height / 2 - 3,
                              f"{round(cand2_pct)}%",
                              fontSize=10, fontName=get_font_name('normal', use_bold=True),
                              fillColor=colors.white, textAnchor='middle'))
    
    # === MARGIN TEXT (Below bar) ===
    if not is_tie and margin > 0:
        margin_y = bar_y - 12
        margin_text = f"{cand1_name} wins by a margin of {int(margin):,}"
        drawing.add(String(width / 2, margin_y,
                          margin_text,
                          fontSize=8, fontName=get_font_name('normal', use_bold=True),
                          fillColor=colors.HexColor('#2e7d32'),
                          textAnchor='middle'))
    elif is_tie:
        margin_y = bar_y - 12
        drawing.add(String(width / 2, margin_y,
                          "Tied",
                          fontSize=8, fontName=get_font_name('normal', use_bold=True),
                          fillColor=colors.HexColor('#666'),
                          textAnchor='middle'))
    
    return drawing

def create_ballot_statistics_visual(stats):
    """Create visual representation of ballot statistics."""
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib import colors
    
    width = 6*inch
    height = 2.5*inch  # Reduced height
    drawing = Drawing(width, height)
    
    # Statistics to display - pairwise comparison stats
    stat_items = [
        ("Completed all matchups", stats.get('completed_all_matchups', 0), colors.HexColor('#4CAF50')),
        ("Partial ballot", stats.get('partial_ballot', 0), colors.HexColor('#2196F3')),
        ("Selected both (no preference)", stats.get('has_ties', 0), colors.HexColor('#FF9800')),
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

def generate_results_pdf(poll: Dict, results: Dict, base_url: str = None) -> bytes:
    """
    Generate a professional PDF of poll results including winner, head-to-head comparisons, and details.
    
    Args:
        poll: Poll data dictionary
        results: Results data dictionary from the API
        base_url: Base URL for generating results link (e.g., 'https://betterchoicesohio.org')
    
    Returns:
        PDF content as bytes
    """
    
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("PDF generation requires reportlab library")
    
    # Register custom fonts
    register_custom_fonts()
    
    # Create a BytesIO buffer
    buffer = BytesIO()
    
    # Create the PDF with clean margins
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=60,
        leftMargin=60,
        topMargin=50,
        bottomMargin=70
    )

    # Page width for content
    page_content_width = A4[0] - 120  # 60 left + 60 right

    # Get styles
    styles = getSampleStyleSheet()

    # Custom styles — all left-aligned
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=22,
        textColor=colors.black,
        spaceAfter=20,
        alignment=TA_LEFT,
        fontName=get_font_name('heading')
    )

    heading_style = ParagraphStyle(
        'Heading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#2C3E50'),
        spaceAfter=10,
        spaceBefore=16,
        alignment=TA_LEFT,
        fontName=get_font_name('heading')
    )

    normal_style = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_LEFT,
        fontName=get_font_name('normal')
    )

    bold_style = ParagraphStyle(
        'Bold',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_LEFT,
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
        story.append(Paragraph("Better Choices for Ohio",
                              ParagraphStyle('LogoText', parent=heading_style, fontSize=14)))
    
    story.append(Spacer(1, 20))
    
    # Main title
    story.append(Paragraph("Poll Results Report", title_style))
    
    # Poll Information with QR Code
    story.append(Paragraph("Poll Information", heading_style))
    
    # Generate QR code for results URL
    if base_url is None:
        base_url = os.getenv('BASE_URL', 'https://betterchoicesohio.org')
    results_url = f"{base_url}/results/{poll.get('short_id', '')}"
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
            qr_image = Image(qr_buffer, width=1*inch, height=1*inch)
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
    poll_info_table = Table(poll_info_basic, colWidths=[1.5*inch, 4*inch])
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
        container_table = Table(container_data, colWidths=[page_content_width - 2*inch, 2*inch])
        container_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(container_table)
    else:
        story.append(poll_info_table)
    
    # Description — flush left
    if poll.get('description'):
        story.append(Spacer(1, 10))
        story.append(Paragraph("<b>Description</b>", bold_style))
        story.append(Spacer(1, 4))
        desc_html = convert_markdown_to_reportlab_html(poll['description'])
        story.append(Paragraph(desc_html, normal_style))
    
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
    
    winner_name = results.get('winner', '')
    winner_explanation = {
        'condorcet': 'Wins all of their head-to-head matchups',
        'most_wins': 'Has no head-to-head losses',
        'smallest_loss': f'Every candidate loses to one candidate. {winner_name} has the smallest loss.',
        'tie': 'There is a tie in the head-to-head comparisons'
    }.get(winner_type, '')
    
    winner_para = Paragraph(
        f"{winner_text}<br/><br/><i>{winner_explanation}</i>",
        ParagraphStyle('Winner', parent=normal_style,
                      textColor=winner_color,
                      fontSize=13,
                      alignment=TA_LEFT,
                      spaceAfter=16)
    )

    winner_table = Table([[winner_para]], colWidths=[page_content_width])
    winner_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1.5, winner_color),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FAFAFA')),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
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
    
    # Page break before head-to-head comparisons
    story.append(PageBreak())

    # HEAD-TO-HEAD COMPARISONS
    story.append(Paragraph("Head-to-Head Comparisons", heading_style))
    story.append(Spacer(1, 10))
    
    if detailed_results and pairwise_matrix:
        # Get list of all candidates
        candidates = list(pairwise_matrix.keys())
        
        # Collect all matchups exactly like HeadToHeadTable.jsx
        all_matchups = []
        processed_pairs = set()
        
        for candidateA in candidates:
            for candidateB in candidates:
                if candidateA != candidateB:
                    pair_key = '|'.join(sorted([candidateA, candidateB]))
                    if pair_key not in processed_pairs:
                        processed_pairs.add(pair_key)
                        
                        marginA = pairwise_matrix.get(candidateA, {}).get(candidateB, 0)
                        marginB = pairwise_matrix.get(candidateB, {}).get(candidateA, 0)
                        
                        # Get detailed results for vote counts
                        detail_key = f"{candidateA}_vs_{candidateB}"
                        reverse_detail_key = f"{candidateB}_vs_{candidateA}"
                        
                        # Extract vote counts
                        aOverB = 0
                        bOverA = 0
                        
                        if detail_key in detailed_results:
                            aOverB = detailed_results[detail_key].get(candidateA, 0)
                            bOverA = detailed_results[detail_key].get(candidateB, 0)
                        elif reverse_detail_key in detailed_results:
                            aOverB = detailed_results[reverse_detail_key].get(candidateA, 0)
                            bOverA = detailed_results[reverse_detail_key].get(candidateB, 0)
                        
                        # Determine winner/loser/tie
                        matchup = {
                            'candidateA': candidateA,
                            'candidateB': candidateB,
                            'aOverB': aOverB,
                            'bOverA': bOverA,
                            'winner': None,
                            'loser': None,
                            'margin': 0,
                            'isTie': False
                        }
                        
                        if marginA > 0:
                            matchup['winner'] = candidateA
                            matchup['loser'] = candidateB
                            matchup['margin'] = marginA
                        elif marginB > 0:
                            matchup['winner'] = candidateB
                            matchup['loser'] = candidateA
                            matchup['margin'] = marginB
                        else:
                            # It's a tie
                            matchup['winner'] = candidateA
                            matchup['loser'] = candidateB
                            matchup['isTie'] = True
                        
                        all_matchups.append(matchup)
        
        # Calculate wins, losses, ties for each candidate BEFORE sorting
        candidate_stats = {c: {'wins': 0, 'losses': 0, 'ties': 0} for c in candidates}
        
        for matchup in all_matchups:
            if matchup['isTie']:
                candidate_stats[matchup['winner']]['ties'] += 1
                candidate_stats[matchup['loser']]['ties'] += 1
            else:
                candidate_stats[matchup['winner']]['wins'] += 1
                candidate_stats[matchup['loser']]['losses'] += 1
        
        # Sort matchups exactly like HeadToHeadTable.jsx
        def sort_matchups(a, b):
            # Put ties at the end
            if a['isTie'] and not b['isTie']:
                return 1
            if not a['isTie'] and b['isTie']:
                return -1
            
            # For non-ties, sort by winner's total wins
            if not a['isTie'] and not b['isTie']:
                aWinnerStats = candidate_stats[a['winner']]
                bWinnerStats = candidate_stats[b['winner']]
                
                # Sort by number of wins (descending)
                if aWinnerStats['wins'] != bWinnerStats['wins']:
                    return bWinnerStats['wins'] - aWinnerStats['wins']
                
                # If same number of wins, sort by winner name alphabetically
                if a['winner'] != b['winner']:
                    return -1 if a['winner'] < b['winner'] else 1
                
                # Same winner, sort by loser name alphabetically
                return -1 if a['loser'] < b['loser'] else 1
            
            # For ties, sort alphabetically by first candidate then second
            if a['isTie'] and b['isTie']:
                if a['winner'] != b['winner']:
                    return -1 if a['winner'] < b['winner'] else 1
                return -1 if a['loser'] < b['loser'] else 1
            
            return 0
        
        from functools import cmp_to_key
        all_matchups.sort(key=cmp_to_key(sort_matchups))
        
        # Create comparison visuals with professional design
        comparison_elements = []
        
        for matchup in all_matchups:
            # Create title - show matchup
            if matchup['isTie']:
                # For ties, show in alphabetical order
                first_cand = matchup['candidateA'] if matchup['candidateA'] < matchup['candidateB'] else matchup['candidateB']
                second_cand = matchup['candidateB'] if matchup['candidateA'] < matchup['candidateB'] else matchup['candidateA']
                first_votes = matchup['aOverB'] if matchup['candidateA'] < matchup['candidateB'] else matchup['bOverA']
                second_votes = matchup['bOverA'] if matchup['candidateA'] < matchup['candidateB'] else matchup['aOverB']
                margin = 0
            else:
                # Winner on top
                first_cand = matchup['winner']
                second_cand = matchup['loser']
                first_votes = matchup['aOverB'] if matchup['winner'] == matchup['candidateA'] else matchup['bOverA']
                second_votes = matchup['bOverA'] if matchup['winner'] == matchup['candidateA'] else matchup['aOverB']
                margin = matchup['margin']
            
            # Simple bold title - flush left, no background
            title_text = f"<b>{first_cand} vs {second_cand}</b>"
            title_para = Paragraph(
                title_text,
                ParagraphStyle('ComparisonTitle', parent=bold_style,
                             fontSize=11,
                             alignment=TA_LEFT,
                             spaceAfter=8)
            )
            
            # Create the clean, aligned bar chart
            bar_chart = create_head_to_head_bar_chart(
                first_cand, second_cand,
                first_votes, second_votes,
                is_tie=matchup['isTie'],
                margin=margin,
                width=page_content_width - 10, height=1*inch
            )
            
            comparison_elements.append([title_para])
            comparison_elements.append([Spacer(1, 4)])
            comparison_elements.append([bar_chart])
            comparison_elements.append([Spacer(1, 18)])
        
        if comparison_elements:
            # Remove the last spacer
            if len(comparison_elements) > 0 and isinstance(comparison_elements[-1][0], Spacer):
                comparison_elements.pop()
            
            comparison_table = Table(comparison_elements, colWidths=[page_content_width])
            comparison_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ]))
            story.append(comparison_table)
    
    story.append(Spacer(1, 20))
    
    # Build the PDF with custom footer
    def add_footer(canvas, doc):
        """Add footer to each page with clickable links."""
        canvas.saveState()
        
        # Footer position
        footer_y = 50
        page_width = doc.pagesize[0]
        
        # Footer text styles
        footer_font = 'Helvetica'
        footer_size = 8
        
        # Line 1
        canvas.setFont(footer_font, footer_size)
        canvas.setFillColorRGB(0.4, 0.4, 0.4)
        canvas.drawCentredString(page_width / 2, footer_y + 12, "This results report is generated from Better Choices for Ohio.")

        # Line 2: clickable link
        link_text = "betterchoicesohio.org"
        link_width = canvas.stringWidth(link_text, footer_font, footer_size)
        link_x = (page_width - link_width) / 2
        canvas.setFillColorRGB(0, 0.4, 0.8)
        canvas.drawString(link_x, footer_y, link_text)
        canvas.linkURL("https://betterchoicesohio.org",
                      (link_x, footer_y - 2, link_x + link_width, footer_y + footer_size + 2),
                      relative=0)
        
        canvas.restoreState()
    
    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    
    # Get the PDF content
    pdf_content = buffer.getvalue()
    buffer.close()
    
    return pdf_content