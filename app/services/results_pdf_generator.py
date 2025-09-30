# app/services/results_pdf_generator.py
from io import BytesIO
from datetime import datetime
from typing import Any, Dict, List
import os
import math
import pytz

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
    
    # Create poll info data
    poll_info_basic = [
        ["Poll Title:", poll.get('title', 'Untitled Poll')],
        ["Poll ID:", poll.get('short_id', 'N/A')],
        ["Total Votes:", f"{results.get('statistics', {}).get('total_votes', 0):,}"],
        ["Generated:", datetime.now().strftime('%B %d, %Y at %I:%M %p')],
        ["Results URL:", results_url]
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
        container_table = Table(container_data, colWidths=[5.5*inch, 1.5*inch])
        container_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(container_table)
    else:
        story.append(poll_info_table)
    
    # Add description separately below the QR code section (so it won't be cut off)
    if poll.get('description'):
        story.append(Spacer(1, 10))
        # Use a wrapping paragraph that spans the full width
        desc_para = Paragraph(f"<b>Description:</b> {poll['description']}", normal_style)
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
    story.append(Spacer(1, 25))
    
    # Get pairwise matrix and detailed results for later use
    pairwise_matrix = results.get('pairwise_matrix', {})
    detailed_results = results.get('detailed_pairwise_results', {})
    
    # Additional Details Section (matching PollResults.jsx exactly)
    if winner_type in ['condorcet', 'most_wins', 'smallest_loss']:
        story.append(Paragraph("Additional Details", heading_style))
        
        # CONDORCET WINNER
        if winner_type == 'condorcet' and winner:
            # Statement
            statement = f"{winner} is the only candidate that wins all of their head-to-head matchups."
            story.append(Paragraph(statement, normal_style))
            story.append(Spacer(1, 10))
            
            # Wins box
            wins_title = Paragraph(f"<b>{winner.upper()}'S WINS</b>", 
                                 ParagraphStyle('WinsTitle', parent=bold_style, 
                                              textColor=colors.HexColor('#4CAF50')))
            
            # Get wins from pairwise matrix
            wins_data = []
            if pairwise_matrix and winner in pairwise_matrix:
                for opponent, margin in pairwise_matrix[winner].items():
                    if margin > 0:
                        wins_data.append([f"• Beats {opponent} by {margin:,} votes"])
            
            wins_table_data = [[wins_title]] + [[Paragraph(w[0], normal_style)] for w in wins_data]
            
            wins_table = Table(wins_table_data, colWidths=[6*inch])
            wins_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F5F5F5')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#E0E0E0')),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ]))
            story.append(wins_table)
        
        # MOST WINS
        elif winner_type == 'most_wins' and winner:
            # Statement
            statement = f"No candidate beats all others head-to-head. {winner} has the highest score based on head-to-head matchups."
            story.append(Paragraph(statement, normal_style))
            story.append(Spacer(1, 10))
            
            # Scoring explanation box
            scoring_title = Paragraph("<b>HOW THE SCORING WORKS</b>", 
                                    ParagraphStyle('ScoringTitle', parent=bold_style, fontSize=9))
            scoring_text = Paragraph(
                "Each candidate gets points based on their head-to-head matchups:<br/>"
                "• Each win earns 1 point<br/>"
                "• Each tie earns 0.5 points<br/>"
                "• Each loss earns 0 points",
                ParagraphStyle('ScoringText', parent=normal_style, fontSize=9)
            )
            
            scoring_table = Table([[scoring_title], [scoring_text]], colWidths=[6*inch])
            scoring_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F5F5F5')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#E0E0E0')),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ]))
            story.append(scoring_table)
            story.append(Spacer(1, 15))
            
            # Final Scores
            story.append(Paragraph("<b>FINAL SCORES</b>", 
                                 ParagraphStyle('ScoresTitle', parent=bold_style, fontSize=9)))
            story.append(Spacer(1, 10))
            
            # Calculate and display scores
            if results.get('explanation') and results['explanation'].get('copeland_scores'):
                scores = results['explanation']['copeland_scores']
                sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                
                # Calculate wins/ties for each candidate
                for candidate_name, score in sorted_scores:
                    is_winner = candidate_name == winner
                    wins = losses = ties = 0
                    
                    if candidate_name in pairwise_matrix:
                        for opponent, margin in pairwise_matrix[candidate_name].items():
                            if margin > 0: wins += 1
                            elif margin < 0: losses += 1
                            else: ties += 1
                    
                    # Format calculation string
                    calc_parts = []
                    if wins > 0:
                        calc_parts.append(f"{wins} {'win' if wins == 1 else 'wins'}")
                    if ties > 0:
                        calc_parts.append(f"{ties} {'tie' if ties == 1 else 'ties'} × 0.5")
                    if not calc_parts:
                        calc_parts.append("0 wins")
                    calculation = f"<i>{' + '.join(calc_parts)} = {score} {'point' if score == 1 else 'points'}</i>"
                    
                    # Create the score display
                    if is_winner:
                        name_para = Paragraph(f"<b>{candidate_name}</b>", 
                                            ParagraphStyle('WinnerName', parent=bold_style, 
                                                         textColor=colors.HexColor('#2196F3')))
                        score_para = Paragraph(f"<b>{score} {'point' if score == 1 else 'points'}</b>", 
                                             ParagraphStyle('WinnerScore', parent=bold_style, 
                                                          textColor=colors.HexColor('#2196F3')))
                    else:
                        name_para = Paragraph(candidate_name, normal_style)
                        score_para = Paragraph(f"{score} {'point' if score == 1 else 'points'}", normal_style)
                    
                    calc_para = Paragraph(calculation, 
                                        ParagraphStyle('Calc', parent=normal_style, fontSize=8, 
                                                     textColor=colors.HexColor('#666666')))
                    
                    score_table = Table([[name_para], [score_para], [calc_para]], colWidths=[6*inch])
                    
                    if is_winner:
                        score_table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#E3F2FD')),
                            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#90CAF9')),
                            ('TOPPADDING', (0, 0), (-1, -1), 6),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                            ('LEFTPADDING', (0, 0), (-1, -1), 12),
                        ]))
                    else:
                        score_table.setStyle(TableStyle([
                            ('TOPPADDING', (0, 0), (-1, -1), 4),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                            ('LEFTPADDING', (0, 0), (-1, -1), 12),
                        ]))
                    
                    story.append(score_table)
                    story.append(Spacer(1, 8))
        
        # SMALLEST LOSS
        elif winner_type == 'smallest_loss' and winner:
            # Get tied candidates
            tied_candidates = []
            if results.get('explanation') and results['explanation'].get('candidates_with_most_wins'):
                tied_candidates = results['explanation']['candidates_with_most_wins']
            
            # Statement about tie
            if len(tied_candidates) == 2:
                statement = f"{tied_candidates[0]} and {tied_candidates[1]} are tied for the most wins."
            elif len(tied_candidates) > 2:
                statement = f"{', '.join(tied_candidates[:-1])}, and {tied_candidates[-1]} are tied for the most wins."
            else:
                statement = f"{winner} has the most wins."
            
            story.append(Paragraph(statement, normal_style))
            story.append(Spacer(1, 10))
            
            # Scoring explanation (same as most_wins)
            scoring_title = Paragraph("<b>HOW THE SCORING WORKS</b>", 
                                    ParagraphStyle('ScoringTitle', parent=bold_style, fontSize=9))
            scoring_text = Paragraph(
                "Each candidate gets points based on their head-to-head matchups:<br/>"
                "• Each win earns 1 point<br/>"
                "• Each tie earns 0.5 points<br/>"
                "• Each loss earns 0 points",
                ParagraphStyle('ScoringText', parent=normal_style, fontSize=9)
            )
            
            scoring_table = Table([[scoring_title], [scoring_text]], colWidths=[6*inch])
            scoring_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F5F5F5')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#E0E0E0')),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ]))
            story.append(scoring_table)
            story.append(Spacer(1, 15))
            
            # Final Scores (highlighting tied candidates)
            story.append(Paragraph("<b>FINAL SCORES</b>", 
                                 ParagraphStyle('ScoresTitle', parent=bold_style, fontSize=9)))
            story.append(Spacer(1, 10))
            
            if results.get('explanation') and results['explanation'].get('copeland_scores'):
                scores = results['explanation']['copeland_scores']
                sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                
                for candidate_name, score in sorted_scores:
                    is_winner = candidate_name == winner
                    is_tied = candidate_name in tied_candidates
                    wins = losses = ties = 0
                    
                    if candidate_name in pairwise_matrix:
                        for opponent, margin in pairwise_matrix[candidate_name].items():
                            if margin > 0: wins += 1
                            elif margin < 0: losses += 1
                            else: ties += 1
                    
                    # Format calculation
                    calc_parts = []
                    if wins > 0:
                        calc_parts.append(f"{wins} {'win' if wins == 1 else 'wins'}")
                    if ties > 0:
                        calc_parts.append(f"{ties} {'tie' if ties == 1 else 'ties'} × 0.5")
                    if not calc_parts:
                        calc_parts.append("0 wins")
                    calculation = f"<i>{' + '.join(calc_parts)} = {score} {'point' if score == 1 else 'points'}</i>"
                    
                    # Style based on status
                    if is_winner:
                        name_para = Paragraph(f"<b>{candidate_name}</b>", 
                                            ParagraphStyle('WinnerName', parent=bold_style, 
                                                         textColor=colors.HexColor('#FF9800')))
                        score_para = Paragraph(f"<b>{score} {'point' if score == 1 else 'points'}</b>", 
                                             ParagraphStyle('WinnerScore', parent=bold_style, 
                                                          textColor=colors.HexColor('#FF9800')))
                    elif is_tied:
                        name_para = Paragraph(f"<b>{candidate_name}</b>", 
                                            ParagraphStyle('TiedName', parent=bold_style, 
                                                         textColor=colors.HexColor('#FF9800')))
                        score_para = Paragraph(f"<b>{score} {'point' if score == 1 else 'points'}</b>", 
                                             ParagraphStyle('TiedScore', parent=bold_style, 
                                                          textColor=colors.HexColor('#FF9800')))
                    else:
                        name_para = Paragraph(candidate_name, normal_style)
                        score_para = Paragraph(f"{score} {'point' if score == 1 else 'points'}", normal_style)
                    
                    calc_para = Paragraph(calculation, 
                                        ParagraphStyle('Calc', parent=normal_style, fontSize=8, 
                                                     textColor=colors.HexColor('#666666')))
                    
                    score_table = Table([[name_para], [score_para], [calc_para]], colWidths=[6*inch])
                    
                    if is_winner or is_tied:
                        score_table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FFF3E0')),
                            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#FFCC80')),
                            ('TOPPADDING', (0, 0), (-1, -1), 6),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                            ('LEFTPADDING', (0, 0), (-1, -1), 12),
                        ]))
                    else:
                        score_table.setStyle(TableStyle([
                            ('TOPPADDING', (0, 0), (-1, -1), 4),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                            ('LEFTPADDING', (0, 0), (-1, -1), 12),
                        ]))
                    
                    story.append(score_table)
                    story.append(Spacer(1, 8))
            
            # Statement about smallest loss
            story.append(Paragraph(f"Among {', '.join(tied_candidates)}, {winner} has the smallest loss.", normal_style))
            story.append(Spacer(1, 15))
            
            # Loss Comparisons
            story.append(Paragraph("<b>LOSS COMPARISONS</b>", 
                                 ParagraphStyle('LossTitle', parent=bold_style, fontSize=9)))
            story.append(Spacer(1, 10))
            
            # Show losses for each tied candidate
            for candidate_name in tied_candidates:
                is_winner = candidate_name == winner
                
                # Get losses for this candidate
                losses = []
                if candidate_name in pairwise_matrix:
                    for opponent, margin in pairwise_matrix[candidate_name].items():
                        if margin < 0:
                            losses.append((opponent, abs(margin)))
                losses.sort(key=lambda x: x[1])  # Sort by margin (smallest first)
                
                # Create loss display
                if is_winner:
                    loss_title = Paragraph(f"<b>{candidate_name.upper()}'S LOSSES (SMALLEST TO LARGEST)</b>",
                                         ParagraphStyle('LossTitle', parent=bold_style, fontSize=9,
                                                      textColor=colors.HexColor('#FF9800')))
                else:
                    loss_title = Paragraph(f"<b>{candidate_name.upper()}'S LOSSES (SMALLEST TO LARGEST)</b>",
                                         ParagraphStyle('LossTitle', parent=bold_style, fontSize=9,
                                                      textColor=colors.HexColor('#F44336')))
                
                loss_data = [[loss_title]]
                if losses:
                    for opponent, margin in losses:
                        loss_text = f"• Loses to {opponent} by {margin:,} {'vote' if margin == 1 else 'votes'}"
                        loss_data.append([Paragraph(loss_text, normal_style)])
                else:
                    loss_data.append([Paragraph("No losses", normal_style)])
                
                loss_table = Table(loss_data, colWidths=[6*inch])
                
                if is_winner:
                    loss_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FFF3E0')),
                        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#FFCC80')),
                        ('TOPPADDING', (0, 0), (-1, -1), 8),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                        ('LEFTPADDING', (0, 0), (-1, -1), 12),
                    ]))
                else:
                    loss_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F5F5F5')),
                        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#E0E0E0')),
                        ('TOPPADDING', (0, 0), (-1, -1), 8),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                        ('LEFTPADDING', (0, 0), (-1, -1), 12),
                    ]))
                
                story.append(loss_table)
                story.append(Spacer(1, 10))
    
    story.append(Spacer(1, 20))
    
    # Head-to-Head Comparisons with Visual Bar Charts
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
    
    # Also add standings table
    if pairwise_matrix:
        story.append(Spacer(1, 20))
        story.append(Paragraph("Standings", heading_style))
        
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
    
    # Ballot Statistics
    if results.get('statistics'):
        story.append(Paragraph("Ballot Statistics", heading_style))
        
        stats = results['statistics']
        
        stats_data = []
        
        if 'linear_orders' in stats:
            pct = round((stats['linear_orders'] / stats['total_votes']) * 100)
            stats_data.append(['Linear orders:', f"{stats['linear_orders']:,} ({pct}%)"])
        
        if 'all_candidates_ranked' in stats:
            pct = round((stats['all_candidates_ranked'] / stats['total_votes']) * 100)
            stats_data.append(['All candidates ranked:', f"{stats['all_candidates_ranked']:,} ({pct}%)"])
        
        if 'bullet_votes' in stats:
            pct = round((stats['bullet_votes'] / stats['total_votes']) * 100)
            stats_data.append(['Bullet votes:', f"{stats['bullet_votes']:,} ({pct}%)"])
        
        if 'has_skipped_ranks' in stats:
            pct = round((stats['has_skipped_ranks'] / stats['total_votes']) * 100)
            stats_data.append(['Skipped ranks:', f"{stats['has_skipped_ranks']:,} ({pct}%)"])
        
        if stats_data:
            stats_table = Table(stats_data, colWidths=[2.5*inch, 2*inch])
            stats_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (0, -1), get_font_name('normal', use_bold=True)),
                ('FONTNAME', (1, 0), (1, -1), get_font_name('normal')),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(stats_table)
    
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


