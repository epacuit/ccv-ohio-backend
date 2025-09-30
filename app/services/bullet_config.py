# Quick configuration section for ballot marking symbol
# Add this at the top of your pdf_generator.py after imports

# BALLOT MARKING CONFIGURATION
# Choose your preferred symbol and size:

BALLOT_MARK_CONFIG = {
    # Symbol options (uncomment the one you want):
    
    # DOTS/CIRCLES - Various sizes
    'symbol': '\u2B24',  # ⬤ LARGE BLACK CIRCLE (Recommended - most visible)
    # 'symbol': '\u25CF',  # ● Medium black circle  
    # 'symbol': '\u29BF',  # ⦿ Circled bullet (elegant)
    # 'symbol': '\u25C9',  # ◉ Fisheye (circle with center dot)
    
    # CHECK MARKS
    # 'symbol': '\u2714',  # ✔ Heavy check mark
    # 'symbol': '\u2713',  # ✓ Light check mark
    # 'symbol': '\u2611',  # ☑ Ballot box with check
    
    # X MARKS
    # 'symbol': '\u2718',  # ✘ Heavy ballot X
    # 'symbol': '\u2717',  # ✗ Light ballot X
    
    # SQUARES
    # 'symbol': '\u25A0',  # ■ Black square
    # 'symbol': '\u25AA',  # ▪ Small black square
    
    # Font size for the symbol (adjust as needed)
    'font_size': 20,  # Default: 18 (range: 12-24 recommended)
}

# Then in your ballot table code (around line 361), use:
"""
if candidate_rank == rank_col:
    circle_style = ParagraphStyle('Circle', 
                                 parent=normal_style, 
                                 alignment=TA_CENTER, 
                                 fontSize=BALLOT_MARK_CONFIG['font_size'],
                                 leading=14)
    row.append(Paragraph(BALLOT_MARK_CONFIG['symbol'], circle_style))
else:
    row.append(Paragraph("", normal_style))
"""

# VISUAL PREVIEW OF OPTIONS:
# Run this script to see all options printed:

if __name__ == "__main__":
    print("\nBALLOT MARKING SYMBOL OPTIONS:")
    print("=" * 50)
    
    symbols = {
        # Dots/Circles
        '\u2B24': 'LARGE BLACK CIRCLE (Best visibility)',
        '\u25CF': 'Medium black circle',
        '\u29BF': 'Circled bullet (elegant)',
        '\u25C9': 'Fisheye',
        '\u2299': 'Circled dot operator',
        
        # Checks
        '\u2714': 'Heavy check mark',
        '\u2713': 'Light check mark', 
        '\u2611': 'Ballot box with check',
        
        # X marks
        '\u2718': 'Heavy ballot X',
        '\u2717': 'Light ballot X',
        '\u2612': 'Ballot box with X',
        
        # Squares
        '\u25A0': 'Black square (medium)',
        '\u25AA': 'Black small square',
        '\u2588': 'Full block (large)',
    }
    
    for symbol, name in symbols.items():
        print(f"  {symbol}  {name:30} Unicode: {repr(symbol)}")
    
    print("\nRECOMMENDED:")
    print(f"  ⬤  Large black circle at size 18")
    print("=" * 50)




















