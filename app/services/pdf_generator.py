# app/services/pdf_generator.py - With Beautiful Ballot Marks
from io import BytesIO
from datetime import datetime
from typing import Any, List, Dict
import os
import re
import math
import pytz  # For timezone conversion

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether, PageTemplate, BaseDocTemplate, Frame
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    # Import for custom drawing
    from reportlab.platypus.flowables import Flowable
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    import qrcode
    from qrcode.image.styledpil import StyledPilImage
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

# ============ TIMEZONE CONFIGURATION ============
def convert_to_timezone(utc_time, timezone_name='US/Eastern'):
    """
    Convert UTC datetime to specified timezone.
    Default is US/Eastern for the user's request.
    
    Args:
        utc_time: datetime object in UTC
        timezone_name: pytz timezone name (e.g., 'US/Eastern', 'US/Pacific', 'Europe/London')
    
    Returns:
        Localized datetime object
    """
    if not utc_time:
        return None
        
    try:
        # Ensure the datetime is timezone-aware (UTC)
        if utc_time.tzinfo is None:
            utc = pytz.UTC
            utc_time = utc.localize(utc_time)
        elif utc_time.tzinfo != pytz.UTC:
            utc_time = utc_time.astimezone(pytz.UTC)
        
        # Convert to target timezone
        target_tz = pytz.timezone(timezone_name)
        local_time = utc_time.astimezone(target_tz)
        return local_time
    except Exception as e:
        print(f"Timezone conversion failed: {e}")
        # Fallback to UTC if conversion fails
        return utc_time

def format_datetime_with_timezone(dt, timezone_name='US/Eastern', show_timezone=True):
    """
    Format a datetime for display with timezone conversion.
    
    Returns formatted string like: "September 21, 2025 at 05:47 PM EDT"
    """
    if not dt:
        return "Unknown"
    
    # Convert to local timezone
    local_dt = convert_to_timezone(dt, timezone_name)
    
    # Format the datetime
    formatted = local_dt.strftime("%B %d, %Y at %I:%M %p")
    
    # Add timezone abbreviation if requested
    if show_timezone:
        tz_abbr = local_dt.strftime("%Z")  # Gets EDT, EST, PST, etc.
        formatted += f" {tz_abbr}"
    
    return formatted

# ============ BEAUTIFUL BALLOT MARK DESIGNS ============

class BallotMark(Flowable):
    """Base class for ballot mark designs"""
    def __init__(self, size=14):
        Flowable.__init__(self)
        self.size = size
        self.width = size
        self.height = size

class FilledCircle(BallotMark):
    """A perfectly filled circle - classic and professional"""
    def draw(self):
        self.canv.setFillColor(colors.black)
        # Draw a perfect filled circle
        self.canv.circle(self.width/2, self.height/2, self.width/2.5, stroke=0, fill=1)

class CircleWithDot(BallotMark):
    """Radio button style - circle with center dot"""
    def draw(self):
        # Outer circle
        self.canv.setStrokeColor(colors.black)
        self.canv.setLineWidth(1.5)
        self.canv.circle(self.width/2, self.height/2, self.width/2.2, stroke=1, fill=0)
        # Inner filled dot
        self.canv.setFillColor(colors.black)
        self.canv.circle(self.width/2, self.height/2, self.width/3.5, stroke=0, fill=1)

class CheckMark(BallotMark):
    """A bold checkmark"""
    def draw(self):
        self.canv.setStrokeColor(colors.black)
        self.canv.setLineWidth(2.5)
        self.canv.setLineCap(1)  # Round line caps
        path = self.canv.beginPath()
        path.moveTo(self.width * 0.2, self.height * 0.5)
        path.lineTo(self.width * 0.4, self.height * 0.25)
        path.lineTo(self.width * 0.75, self.height * 0.7)
        self.canv.drawPath(path, stroke=1, fill=0)

class FancyCheck(BallotMark):
    """Checkmark in a circle - elegant"""
    def draw(self):
        # Light circle background
        self.canv.setStrokeColor(colors.grey)
        self.canv.setLineWidth(1)
        self.canv.circle(self.width/2, self.height/2, self.width/2.2, stroke=1, fill=0)
        # Bold checkmark
        self.canv.setStrokeColor(colors.HexColor('#2E7D32'))  # Dark green
        self.canv.setLineWidth(2)
        self.canv.setLineCap(1)
        path = self.canv.beginPath()
        path.moveTo(self.width * 0.25, self.height * 0.5)
        path.lineTo(self.width * 0.4, self.height * 0.35)
        path.lineTo(self.width * 0.7, self.height * 0.62)
        self.canv.drawPath(path, stroke=1, fill=0)

class FilledSquare(BallotMark):
    """A filled square with rounded corners"""
    def draw(self):
        self.canv.setFillColor(colors.black)
        # Draw rounded rectangle
        self.canv.roundRect(self.width * 0.15, self.height * 0.15, 
                           self.width * 0.7, self.height * 0.7,
                           radius=2, stroke=0, fill=1)

class Diamond(BallotMark):
    """A filled diamond shape"""
    def draw(self):
        self.canv.setFillColor(colors.black)
        path = self.canv.beginPath()
        path.moveTo(self.width/2, self.height * 0.1)
        path.lineTo(self.width * 0.9, self.height/2)
        path.lineTo(self.width/2, self.height * 0.9)
        path.lineTo(self.width * 0.1, self.height/2)
        path.close()
        self.canv.drawPath(path, stroke=0, fill=1)

class Star(BallotMark):
    """A filled 5-point star"""
    def draw(self):
        self.canv.setFillColor(colors.black)
        cx, cy = self.width/2, self.height/2
        r_outer = self.width/2.3
        r_inner = r_outer * 0.38
        
        # Create star path with 5 points
        path = self.canv.beginPath()
        for i in range(10):
            angle = (i * math.pi / 5) - math.pi/2
            r = r_outer if i % 2 == 0 else r_inner
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.close()
        self.canv.drawPath(path, stroke=0, fill=1)

class CrossMark(BallotMark):
    """A bold X mark with rounded ends"""
    def draw(self):
        self.canv.setStrokeColor(colors.black)
        self.canv.setLineWidth(2.5)
        self.canv.setLineCap(1)  # Round caps
        # First diagonal
        self.canv.line(self.width * 0.2, self.height * 0.2,
                      self.width * 0.8, self.height * 0.8)
        # Second diagonal
        self.canv.line(self.width * 0.8, self.height * 0.2,
                      self.width * 0.2, self.height * 0.8)

# ========== CONFIGURATION ==========
# Choose your preferred ballot mark style here:
BALLOT_MARK_STYLE = FilledCircle  # Change this to any class above
BALLOT_MARK_SIZE = 12  # Size in points (10-16 recommended)

# Available styles:
# - FilledCircle: Classic filled circle (recommended)
# - CircleWithDot: Radio button style
# - CheckMark: Simple checkmark
# - FancyCheck: Checkmark in circle
# - FilledSquare: Rounded square
# - Diamond: Diamond shape
# - Star: 5-point star
# - CrossMark: Stylized X

# =========================================

def register_custom_fonts():
    """
    Register Montserrat and Gloock fonts for the PDF.
    """
    fonts_registered = False
    
    try:
        # Get the fonts directory path
        fonts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "fonts")
        
        # Register Montserrat (your main sans-serif font)
        try:
            pdfmetrics.registerFont(TTFont('Montserrat', os.path.join(fonts_dir, 'Montserrat-Regular.ttf')))
            pdfmetrics.registerFont(TTFont('Montserrat-Medium', os.path.join(fonts_dir, 'Montserrat-Medium.ttf')))
            pdfmetrics.registerFont(TTFont('Montserrat-SemiBold', os.path.join(fonts_dir, 'Montserrat-SemiBold.ttf')))
            print("✓ Montserrat fonts registered successfully")
        except:
            print("✗ Montserrat fonts not found, using fallback")
        
        # Register Gloock (your display serif font)
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

# Font configuration matching your website
FONT_CONFIG = {
    'primary_font': 'Montserrat',
    'primary_font_medium': 'Montserrat-Medium',
    'primary_font_bold': 'Montserrat-SemiBold',
    'heading_font': 'Gloock',
    'fallback_font': 'Helvetica',
    'fallback_font_bold': 'Helvetica-Bold',
}

def get_font_name(font_type='normal', use_bold=False):
    """Get the appropriate font name with fallback support."""
    try:
        if font_type == 'heading':
            try:
                pdfmetrics.getFont('Gloock')
                return 'Gloock'
            except:
                return FONT_CONFIG['fallback_font_bold']
        elif use_bold:
            try:
                pdfmetrics.getFont('Montserrat-SemiBold')
                return 'Montserrat-SemiBold'
            except:
                return FONT_CONFIG['fallback_font_bold']
        else:
            try:
                pdfmetrics.getFont('Montserrat')
                return 'Montserrat'
            except:
                return FONT_CONFIG['fallback_font']
    except:
        return FONT_CONFIG['fallback_font']

def generate_ballot_pdf(ballot: Any, poll: Any) -> bytes:
    """
    Generate a professional PDF representation of a ballot.
    
    Args:
        ballot: Ballot object with rankings and write_ins
        poll: Poll object with title, candidates, etc.
    
    Returns:
        PDF content as bytes
    """
    
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("PDF generation requires reportlab library")
    
    # Register custom fonts if available
    register_custom_fonts()
    
    # Get timezone for this ballot
    ballot_timezone = getattr(ballot, 'timezone', None)
    if not ballot_timezone:
        ballot_timezone = 'UTC'
    
    # Create a BytesIO buffer
    buffer = BytesIO()
    
    # Create the PDF WITHOUT the footer callback first
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=50,
        bottomMargin=72  # Standard bottom margin
    )
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Custom styles with your website's fonts - COMPACT VERSION
    header_style = ParagraphStyle(
        'Header',
        parent=styles['Normal'],
        fontSize=9,  # Reduced from 10
        textColor=colors.blue,
        fontName=get_font_name('normal'),
        alignment=TA_LEFT
    )
    
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=20,  # Reduced from 24
        textColor=colors.black,
        spaceAfter=15,  # Reduced from 25
        alignment=TA_CENTER,
        fontName=get_font_name('heading')
    )
    
    heading_style = ParagraphStyle(
        'Heading',
        parent=styles['Heading2'],
        fontSize=14,  # Reduced from 16
        textColor=colors.HexColor('#2C3E50'),
        spaceAfter=8,  # Reduced from 12
        fontName=get_font_name('heading')
    )
    
    normal_style = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=9,  # Reduced from 10
        fontName=get_font_name('normal')
    )
    
    bold_style = ParagraphStyle(
        'Bold',
        parent=styles['Normal'],
        fontSize=9,  # Reduced from 10
        fontName=get_font_name('normal', use_bold=True)
    )
    
    # Build the document content
    story = []
    
    # Header with logo - using correct dimensions but smaller for one-page fit
    header_elements = []
    
    # Try to load the logo with proper constraints
    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images", "betterchoices-full-logo.png")
    
    # Alternative paths
    if not os.path.exists(logo_path):
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "betterchoices-full-logo.png")
    
    logo_added = False
    if os.path.exists(logo_path):
        try:
            # Slightly smaller logo for one-page layout
            logo_width = 2.2 * inch  # Reduced from 2.5
            logo_height = 0.84 * inch  # Maintains 2.62:1 aspect ratio
            
            logo = Image(logo_path, width=logo_width, height=logo_height)
            logo.hAlign = 'LEFT'
            header_elements.append(logo)
            logo_added = True
        except Exception as e:
            print(f"Failed to load logo: {e}")
    
    if not logo_added:
        # Text fallback if no logo
        header_elements.append(Paragraph("BetterChoices - Better Democracy Through Better Voting", 
                                        ParagraphStyle('LogoText', parent=heading_style, fontSize=14)))
    
    # Add header elements to story
    for element in header_elements:
        story.append(element)
    
    story.append(Spacer(1, 12))  # Reduced from 20
    
    # Main title
    story.append(Paragraph("Ballot Confirmation", title_style))
    
    # Poll Information
    story.append(Paragraph("Poll Information", heading_style))
    
    poll_info_data = [
        ["Poll Title:", poll.title],
        ["Poll ID:", poll.short_id],
        ["Submitted:", format_datetime_with_timezone(ballot.submitted_at, ballot_timezone)],
        ["Ballot ID:", str(ballot.id)]
    ]
    
    if poll.description:
        poll_info_data.insert(1, ["Description:", poll.description])
    
    poll_info_table = Table(poll_info_data, colWidths=[1.5*inch, 4.5*inch])
    poll_info_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 0), (0, -1), get_font_name('normal', use_bold=True)),
        ('FONTNAME', (1, 0), (1, -1), get_font_name('normal')),
        ('FONTSIZE', (0, 0), (-1, -1), 9),  # Reduced from 10
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),  # Reduced from 8
        ('TOPPADDING', (0, 0), (-1, -1), 2),  # Reduced from 4
    ]))
    
    story.append(poll_info_table)
    story.append(Spacer(1, 15))  # Reduced from 25
    
    # Your Ballot section
    story.append(Paragraph("Your Ballot", heading_style))
    
    if ballot.rankings and len(ballot.rankings) > 0:
        # CRITICAL FIX: Handle candidates with proper IDs
        
        candidate_lookup = {}
        all_candidates = []
        
        # Process poll candidates
        for idx, c in enumerate(poll.candidates):
            if isinstance(c, dict):
                # Check if candidate has an ID field
                cid = c.get('id') or c.get('candidate_id')
                cname = c.get('name') or c.get('candidate_name') or f"Candidate {idx+1}"
                
                if cid:
                    # Candidate has an ID - use it
                    candidate_lookup[str(cid)] = {'name': cname, 'is_write_in': False, 'index': idx}
                else:
                    # NO ID field - use index-based ID (candidate-0, candidate-1, etc.)
                    index_id = f"candidate-{idx}"
                    candidate_lookup[index_id] = {'name': cname, 'is_write_in': False, 'index': idx}
                    # Also store just the index as a string for flexibility
                    candidate_lookup[str(idx)] = {'name': cname, 'is_write_in': False, 'index': idx}
                
                # Store candidate with its effective ID
                all_candidates.append({
                    'id': cid or f"candidate-{idx}",
                    'name': cname,
                    'is_write_in': False,
                    'index': idx
                })
            else:
                # Handle non-dict candidates
                index_id = f"candidate-{idx}"
                candidate_lookup[index_id] = {'name': str(c), 'is_write_in': False, 'index': idx}
                all_candidates.append({
                    'id': index_id,
                    'name': str(c),
                    'is_write_in': False,
                    'index': idx
                })
        
        # Add write-ins
        if ballot.write_ins:
            for write_in_idx, write_in in enumerate(ballot.write_ins):
                if isinstance(write_in, dict):
                    wid = write_in.get('id') or write_in.get('candidate_id')
                    wname = write_in.get('name') or write_in.get('candidate_name')
                    if wid and wname:
                        candidate_lookup[str(wid)] = {'name': wname, 'is_write_in': True}
                        all_candidates.append({
                            'id': wid,
                            'name': wname,
                            'is_write_in': True,
                            'index': len(poll.candidates) + write_in_idx
                        })
        
        # Create rank lookup
        rank_lookup = {}
        for ranking in ballot.rankings:
            cid = ranking.get('candidate_id')
            rank = ranking.get('rank')
            
            if cid is not None and rank is not None:
                # Store the rank for this candidate ID
                rank_lookup[str(cid)] = rank
                
                # Also extract index from candidate-N format if present
                match = re.match(r'candidate-(\d+)', str(cid))
                if match:
                    idx = match.group(1)
                    rank_lookup[idx] = rank
        
        # Create ballot table data
        num_candidates = len(all_candidates)
        ballot_table_data = []
        
        # Header row
        header_row = [Paragraph("<b>Candidate</b>", bold_style)]
        for i in range(num_candidates):
            ordinal = "st" if i == 0 else "nd" if i == 1 else "rd" if i == 2 else "th"
            header_text = f"<b>{i+1}{ordinal}</b>"
            header_row.append(Paragraph(header_text, ParagraphStyle('CenterBold', parent=bold_style, alignment=TA_CENTER)))
        ballot_table_data.append(header_row)
        
        # Data rows for each candidate
        for candidate_info in all_candidates:
            row = []
            
            cid = candidate_info['id']
            cname = candidate_info['name']
            is_write_in = candidate_info.get('is_write_in', False)
            
            # Candidate name with write-in indicator
            display_name = cname
            if is_write_in:
                display_name += " <i>(write-in)</i>"
            
            name_paragraph = Paragraph(display_name, normal_style)
            row.append(name_paragraph)
            
            # Find this candidate's rank
            candidate_rank = rank_lookup.get(str(cid))
            
            # Rank columns - use beautiful custom ballot marks
            for rank_col in range(1, num_candidates + 1):
                if candidate_rank == rank_col:
                    # Use the configured beautiful ballot mark
                    row.append(BALLOT_MARK_STYLE(size=BALLOT_MARK_SIZE))
                else:
                    # Empty cell
                    row.append(Paragraph("", normal_style))
            
            ballot_table_data.append(row)
        
        # Create ballot table
        rank_col_width = 0.5*inch
        name_col_width = 6*inch - (num_candidates * rank_col_width)
        col_widths = [name_col_width] + [rank_col_width] * num_candidates
        
        ballot_table = Table(ballot_table_data, colWidths=col_widths)
        
        # Style the ballot table
        table_style = [
            # Header row styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), get_font_name('normal', use_bold=True)),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Data rows styling
            ('FONTNAME', (0, 1), (-1, -1), get_font_name('normal')),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Grid and padding - COMPACT VERSION
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 5),  # Reduced from 8
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),  # Reduced from 8
            ('LEFTPADDING', (0, 0), (-1, -1), 4),  # Reduced from 6
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),  # Reduced from 6
        ]
        
        # Add alternating row colors
        for i in range(2, len(ballot_table_data), 2):
            table_style.append(('BACKGROUND', (0, i), (-1, i), colors.lightgrey))
        
        ballot_table.setStyle(TableStyle(table_style))
        story.append(ballot_table)
    else:
        story.append(Paragraph("No rankings recorded.", normal_style))
    
    story.append(Spacer(1, 15))  # Reduced from 25
    
    # Results link and QR code section
    results_url = f"{os.getenv('BASE_URL', 'https://betterchoices.vote')}/results/{poll.short_id}"
    
    story.append(Paragraph("View Results", heading_style))
    
    qr_image_data = None
    if QRCODE_AVAILABLE:
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=3,
                border=2,
            )
            qr.add_data(results_url)
            qr.make(fit=True)
            
            qr_img = qr.make_image(fill_color="black", back_color="white")
            
            qr_buffer = BytesIO()
            qr_img.save(qr_buffer, format='PNG')
            qr_buffer.seek(0)
            qr_image_data = qr_buffer
        except Exception as e:
            print(f"QR code generation failed: {e}")
    
    # Results section layout
    if qr_image_data:
        qr_image = Image(qr_image_data, width=0.8*inch, height=0.8*inch)  # Reduced from 1 inch
        url_paragraph = Paragraph(f"<b>Results URL:</b><br/>{results_url}", normal_style)
        results_data = [[qr_image, url_paragraph]]
        
        results_table = Table(results_data, colWidths=[1.0*inch, 5.0*inch])
        results_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('ALIGN', (1, 0), (1, 0), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),  # Reduced from 6
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),  # Reduced from 6
            ('TOPPADDING', (0, 0), (-1, -1), 4),  # Reduced from 6
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),  # Reduced from 6
        ]))
        story.append(results_table)
    else:
        story.append(Paragraph(f"<b>Results URL:</b> {results_url}", normal_style))
    
    # OPTION 1: Footer follows content with fixed small spacing
    # This ALWAYS works regardless of ballot size
    story.append(Spacer(1, 20))
    
    # FOOTER
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.grey,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    footer_bold_style = ParagraphStyle(
        'FooterBold',
        parent=footer_style,
        fontSize=7,
        fontName='Helvetica-Bold'
    )
    
    # Footer content
    generated_time = format_datetime_with_timezone(datetime.now(), ballot_timezone)
    
    story.append(Paragraph(f"Generated on {generated_time}", footer_style))
    story.append(Paragraph(
        "This ballot confirmation is for your records. Your vote is anonymous and secure.",
        footer_style
    ))
    story.append(Paragraph(
        "Powered by BetterChoices - Better Democracy Through Better Voting",
        footer_bold_style
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

def generate_simple_text_pdf_fallback(ballot: Any, poll: Any) -> bytes:
    """
    Fallback PDF generator using simple text when reportlab is not available.
    """
    content = f"""
BALLOT CONFIRMATION
BetterChoices - betterchoices.vote

Poll: {poll.title}
Poll ID: {poll.short_id}
Submitted: {ballot.submitted_at.strftime('%Y-%m-%d %H:%M UTC') if ballot.submitted_at else 'Unknown'}

YOUR BALLOT:
"""
    
    if ballot.rankings:
        # Handle index-based candidate references
        candidate_names = []
        for idx, c in enumerate(poll.candidates):
            if isinstance(c, dict):
                name = c.get('name', f'Candidate {idx+1}')
            else:
                name = str(c)
            candidate_names.append(name)
        
        sorted_rankings = sorted(ballot.rankings, key=lambda x: x['rank'])
        
        for ranking in sorted_rankings:
            cid = ranking.get('candidate_id')
            
            # Extract index from candidate-N format
            if cid and 'candidate-' in str(cid):
                try:
                    idx = int(str(cid).replace('candidate-', ''))
                    if 0 <= idx < len(candidate_names):
                        candidate_name = candidate_names[idx]
                    else:
                        candidate_name = 'Unknown'
                except:
                    candidate_name = 'Unknown'
            else:
                candidate_name = 'Unknown'
            
            content += f"{ranking['rank']}. {candidate_name}\n"
    else:
        content += "No rankings recorded.\n"
    
    results_url = f"{os.getenv('BASE_URL', 'https://betterchoices.vote')}/results/{poll.short_id}"
    content += f"\nResults: {results_url}"
    content += f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}"
    content += "\n\nPowered by BetterChoices"
    content += "\nbetterchoices.vote"
    
    return content.encode('utf-8')