# app/api/v1/voters.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import Dict, Any, List
from datetime import datetime, timezone
from uuid import UUID
import secrets
import hashlib
import os
from fastapi import Query
from app.models import Voter

from app.db import get_db
from app.models import Poll, Ballot, Voter
from app.services.email import send_email

router = APIRouter()

def generate_voter_token() -> str:
    """Generate a secure voter token"""
    return secrets.token_urlsafe(32)

def hash_email(email: str) -> str:
    """Hash email for privacy"""
    return hashlib.sha256(email.lower().encode()).hexdigest()

@router.get("/polls/{poll_id}/voters")
async def get_poll_voters(
    poll_id: str,
    admin_token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get all voters for a private poll - admin only"""
    
    # Find poll
    poll = None
    try:
        poll_uuid = UUID(poll_id)
        stmt = select(Poll).where(Poll.id == poll_uuid)
    except ValueError:
        stmt = select(Poll).where(Poll.short_id == poll_id)
    
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as slug if still not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Verify admin token
    if poll.admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    if not poll.is_private:
        return {"voters": [], "message": "This is a public poll"}
    
    # Get all voters for this poll
    stmt = select(Voter).where(Voter.poll_id == poll.id).order_by(Voter.created_at)
    result = await db.execute(stmt)
    voters = result.scalars().all()
    
    # Check voting status for each voter
    voter_list = []
    for voter in voters:
        # Check if voter has submitted a ballot
        ballot_stmt = select(Ballot).where(
            Ballot.poll_id == poll.id,
            Ballot.voter_token == voter.token
        )
        ballot_result = await db.execute(ballot_stmt)
        ballot = ballot_result.scalar_one_or_none()
        
        voter_list.append({
            "email": voter.email,
            "token": voter.token,
            "invitation_sent": voter.invitation_sent,
            "invitation_sent_at": voter.invitation_sent_at.isoformat() if voter.invitation_sent_at else None,
            "has_voted": ballot is not None,
            "voted_at": ballot.submitted_at.isoformat() if ballot and ballot.submitted_at else None,
            "created_at": voter.created_at.isoformat() if voter.created_at else None
        })
    
    return {
        "voters": voter_list,
        "total": len(voter_list),
        "voted": sum(1 for v in voter_list if v['has_voted']),
        "invited": sum(1 for v in voter_list if v['invitation_sent'])
    }

@router.post("/polls/{poll_id}/voters")
async def add_poll_voters(
    poll_id: str,
    voter_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Add voters to a private poll - admin only"""
    
    admin_token = voter_data.get('admin_token')
    emails = voter_data.get('emails', [])
    send_invitations = voter_data.get('send_invitations', False)
    
    # Find poll
    poll = None
    try:
        poll_uuid = UUID(poll_id)
        stmt = select(Poll).where(Poll.id == poll_uuid)
    except ValueError:
        stmt = select(Poll).where(Poll.short_id == poll_id)
    
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as slug if still not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Verify admin token
    if poll.admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    if not poll.is_private:
        raise HTTPException(status_code=400, detail="Can only add voters to private polls")
    
    added = []
    duplicates = []
    
    for email in emails:
        email = email.lower().strip()
        
        # Check if voter already exists
        stmt = select(Voter).where(
            Voter.poll_id == poll.id,
            Voter.email == email
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            duplicates.append(email)
            continue  # CRITICAL: Skip to next email, don't try to add duplicate
        else:
            # Create new voter
            voter = Voter(
                poll_id=poll.id,
                email=email,
                email_hash=hash_email(email),
                token=generate_voter_token(),
                invitation_sent=False,
                created_at=datetime.now(timezone.utc)
            )
            db.add(voter)
            added.append({
                "email": email,
                "token": voter.token
            })
    
    await db.commit()
    
    # Send invitations if requested
    if send_invitations and added:
        # CRITICAL: Get frontend URL from environment - NO localhost default for production
        FRONTEND_URL = os.getenv("FRONTEND_URL")
        if not FRONTEND_URL:
            return {
                "success": False,
                "error": "FRONTEND_URL not configured - cannot send invitations",
                "added": [v['email'] for v in added],
                "duplicates": duplicates
            }

        sent_count = 0
        
        for voter_info in added:
            voting_link = f"{FRONTEND_URL}/vote/{poll.short_id}?token={voter_info['token']}"
            
            text_body = f"""You've been invited to vote in: {poll.title}

Click here to vote: {voting_link}

This is a private poll. Only invited voters can participate.

---
This email was sent because someone added you as a voter to a private poll.
If you believe this was sent in error, you can ignore this message.
"""
            
            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background-color: #f8f9fa; border-radius: 8px; padding: 30px; margin-bottom: 20px;">
        <h1 style="color: #333; margin-top: 0; font-size: 24px;">You're invited to vote!</h1>
        <p style="font-size: 16px; margin: 15px 0;"><strong>Poll:</strong> {poll.title}</p>
        {f'<p style="font-size: 14px; color: #666; margin: 15px 0;">{poll.description}</p>' if poll.description else ''}
        
        <div style="text-align: center; margin: 30px 0;">
            <a href="{voting_link}" style="background-color: #1976d2; color: white; padding: 12px 32px; text-decoration: none; border-radius: 4px; display: inline-block; font-weight: 500; font-size: 16px;">
                Cast Your Vote
            </a>
        </div>
        
        <div style="background-color: white; border-radius: 4px; padding: 15px; margin-top: 20px;">
            <p style="font-size: 13px; color: #666; margin: 5px 0;">Can't click the button? Copy this link:</p>
            <p style="font-size: 12px; word-break: break-all; background-color: #f5f5f5; padding: 10px; border-radius: 4px; margin: 10px 0;">
                {voting_link}
            </p>
        </div>
    </div>
    
    <div style="text-align: center; padding: 20px;">
        <p style="font-size: 12px; color: #999; margin: 5px 0;">
            This is a private poll. Only invited voters can participate.
        </p>
        <p style="font-size: 11px; color: #999; margin: 5px 0;">
            If you believe this was sent in error, you can ignore this message.
        </p>
    </div>
</body>
</html>
"""
            
            # Send email using centralized service
            email_result = await send_email(
                to_email=voter_info['email'],
                subject=f"You're invited to vote in: {poll.title}",
                text_body=text_body,
                html_body=html_body
            )
            
            if email_result["success"]:
                # Update invitation_sent flag
                stmt = select(Voter).where(
                    Voter.poll_id == poll.id,
                    Voter.email == voter_info['email']
                )
                result_db = await db.execute(stmt)
                voter = result_db.scalar_one()
                voter.invitation_sent = True
                voter.invitation_sent_at = datetime.now(timezone.utc)
                sent_count += 1
        
        await db.commit()
        
        # Build proper note based on email provider
        if sent_count > 0:
            # Get the provider from the last email result (they should all use same provider)
            provider = email_result.get("provider", "unknown")
            if provider == "postmark":
                note = f"Sent {sent_count} invitation email(s) via Postmark"
            else:
                note = f"Sent {sent_count} invitation email(s). Check MailHog at http://{os.getenv('MAILHOG_HOST', 'localhost')}:8025"
        else:
            note = None
    else:
        note = None
    
    return {
        "success": True,
        "added": [v['email'] for v in added],
        "duplicates": duplicates,
        "message": f"Added {len(added)} voter(s)",
        "note": note
    }

@router.delete("/polls/{poll_id}/voters/{email}")
async def remove_poll_voter(
    poll_id: str,
    email: str,
    admin_token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Remove a voter from a private poll - admin only"""
    
    # Find poll
    poll = None
    try:
        poll_uuid = UUID(poll_id)
        stmt = select(Poll).where(Poll.id == poll_uuid)
    except ValueError:
        stmt = select(Poll).where(Poll.short_id == poll_id)
    
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as slug if still not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Verify admin token
    if poll.admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    # Find voter
    email = email.lower().strip()
    stmt = select(Voter).where(
        Voter.poll_id == poll.id,
        Voter.email == email
    )
    result = await db.execute(stmt)
    voter = result.scalar_one_or_none()
    
    if not voter:
        raise HTTPException(status_code=404, detail="Voter not found")
    
    # Delete any ballot submitted by this voter
    stmt = select(Ballot).where(
        Ballot.poll_id == poll.id,
        Ballot.voter_token == voter.token
    )
    result = await db.execute(stmt)
    ballot = result.scalar_one_or_none()
    
    if ballot:
        await db.delete(ballot)
    
    # Delete the voter
    await db.delete(voter)
    await db.commit()
    
    return {
        "success": True,
        "message": f"Removed voter {email}",
        "ballot_deleted": ballot is not None
    }

@router.post("/polls/{poll_id}/voters/{email}/regenerate-token")
async def regenerate_voter_token(
    poll_id: str,
    email: str,
    request_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Regenerate a voter's token (invalidates old token and deletes any vote) - admin only"""
    
    admin_token = request_data.get('admin_token')
    
    # Find poll
    poll = None
    try:
        poll_uuid = UUID(poll_id)
        stmt = select(Poll).where(Poll.id == poll_uuid)
    except ValueError:
        stmt = select(Poll).where(Poll.short_id == poll_id)
    
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as slug if still not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Verify admin token
    if poll.admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    # Find voter
    email = email.lower().strip()
    stmt = select(Voter).where(
        Voter.poll_id == poll.id,
        Voter.email == email
    )
    result = await db.execute(stmt)
    voter = result.scalar_one_or_none()
    
    if not voter:
        raise HTTPException(status_code=404, detail="Voter not found")
    
    # Delete any ballot submitted with the old token
    stmt = select(Ballot).where(
        Ballot.poll_id == poll.id,
        Ballot.voter_token == voter.token
    )
    result = await db.execute(stmt)
    ballot = result.scalar_one_or_none()
    
    if ballot:
        await db.delete(ballot)
    
    # Generate new token
    new_token = generate_voter_token()
    voter.token = new_token
    voter.invitation_sent = False  # Reset invitation status
    voter.invitation_sent_at = None
    
    await db.commit()
    
    return {
        "success": True,
        "message": f"Regenerated token for {email}",
        "new_token": new_token,
        "ballot_deleted": ballot is not None
    }

@router.post("/polls/{poll_id}/send-invitations")
async def send_poll_invitations(
    poll_id: str,
    request_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Send or resend invitations to voters - admin only"""
    
    admin_token = request_data.get('admin_token')
    emails = request_data.get('emails', [])  # If empty, send to all unsent
    
    # Find poll
    poll = None
    try:
        poll_uuid = UUID(poll_id)
        stmt = select(Poll).where(Poll.id == poll_uuid)
    except ValueError:
        stmt = select(Poll).where(Poll.short_id == poll_id)
    
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as slug if still not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # Verify admin token
    if poll.admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    # Get voters to send to
    if emails:
        # Send to specific emails
        stmt = select(Voter).where(
            Voter.poll_id == poll.id,
            Voter.email.in_([e.lower().strip() for e in emails])
        )
    else:
        # Send to all who haven't been invited
        stmt = select(Voter).where(
            Voter.poll_id == poll.id,
            Voter.invitation_sent == False
        )
    
    result = await db.execute(stmt)
    voters = result.scalars().all()
    
    if not voters:
        return {
            "success": True,
            "sent_to": [],
            "failed": [],
            "message": "No voters to send invitations to",
        }
    
    sent_to = []
    failed = []
    
    # CRITICAL: Get frontend URL from environment - NO localhost default for production  
    FRONTEND_URL = os.getenv("FRONTEND_URL")
    if not FRONTEND_URL:
        raise HTTPException(
            status_code=500,
            detail="FRONTEND_URL environment variable not configured. Cannot send invitations."
        )
    
    for voter in voters:
        voting_link = f"{FRONTEND_URL}/vote/{poll.short_id}?token={voter.token}"
        
        # Plain text version
        text_body = f"""You've been invited to vote in: {poll.title}

Click here to vote: {voting_link}

This is a private poll. Only invited voters can participate.

---
This email was sent because someone added you as a voter to a private poll.
If you believe this was sent in error, you can ignore this message.
"""
        
        # HTML version - Professional design
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background-color: #f8f9fa; border-radius: 8px; padding: 30px; margin-bottom: 20px;">
        <h1 style="color: #333; margin-top: 0; font-size: 24px;">You're invited to vote!</h1>
        <p style="font-size: 16px; margin: 15px 0;"><strong>Poll:</strong> {poll.title}</p>
        {f'<p style="font-size: 14px; color: #666; margin: 15px 0;">{poll.description}</p>' if poll.description else ''}
        
        <div style="text-align: center; margin: 30px 0;">
            <a href="{voting_link}" style="background-color: #1976d2; color: white; padding: 12px 32px; text-decoration: none; border-radius: 4px; display: inline-block; font-weight: 500; font-size: 16px;">
                Cast Your Vote
            </a>
        </div>
        
        <div style="background-color: white; border-radius: 4px; padding: 15px; margin-top: 20px;">
            <p style="font-size: 13px; color: #666; margin: 5px 0;">Can't click the button? Copy this link:</p>
            <p style="font-size: 12px; word-break: break-all; background-color: #f5f5f5; padding: 10px; border-radius: 4px; margin: 10px 0;">
                {voting_link}
            </p>
        </div>
    </div>
    
    <div style="text-align: center; padding: 20px;">
        <p style="font-size: 12px; color: #999; margin: 5px 0;">
            This is a private poll. Only invited voters can participate.
        </p>
        <p style="font-size: 11px; color: #999; margin: 5px 0;">
            If you believe this was sent in error, you can ignore this message.
        </p>
    </div>
</body>
</html>
"""
        
        # Send email using centralized service
        email_result = await send_email(
            to_email=voter.email,
            subject=f"You're invited to vote in: {poll.title}",
            text_body=text_body,
            html_body=html_body
        )
        
        if email_result["success"]:
            # Mark as sent
            voter.invitation_sent = True
            voter.invitation_sent_at = datetime.now(timezone.utc)
            sent_to.append(voter.email)
        else:
            failed.append(voter.email)
            # Log the voting link even if email fails
            print(f"  Voting link for {voter.email}: {voting_link}")
    
    await db.commit()
    
    # Determine provider for response message
    provider = "unknown"
    if sent_to:
        # Get provider from environment (should match what email service is using)
        provider = os.getenv("EMAIL_PROVIDER", "mailhog")
    
    response_message = f"Sent {len(sent_to)} invitation(s)" + (f", {len(failed)} failed" if failed else "")
    if provider == "postmark":
        response_message += " via Postmark"
    elif provider == "mailhog":
        response_message += f". Check MailHog at http://{os.getenv('MAILHOG_HOST', 'localhost')}:8025"
    
    return {
        "success": True,
        "sent_to": sent_to,
        "failed": failed,
        "message": response_message,
        "provider": provider
    }

# Add these endpoints to your ballots.py file


@router.get("/check")
async def check_existing_ballot(
    poll_id: str = Query(...),
    voter_token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Check if a voter token has already been used to vote in a private poll"""
    
    # Find the poll
    poll = None
    try:
        poll_uuid = UUID(poll_id)
        stmt = select(Poll).where(Poll.id == poll_uuid)
    except ValueError:
        stmt = select(Poll).where(Poll.short_id == poll_id)
    
    result = await db.execute(stmt)
    poll = result.scalar_one_or_none()
    
    # Try as slug if still not found
    if not poll:
        stmt = select(Poll).where(Poll.slug == poll_id)
        result = await db.execute(stmt)
        poll = result.scalar_one_or_none()
    
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    # For private polls, verify the token is valid
    if poll.is_private:
        stmt = select(Voter).where(
            Voter.poll_id == poll.id,
            Voter.token == voter_token
        )
        result = await db.execute(stmt)
        voter = result.scalar_one_or_none()
        
        if not voter:
            raise HTTPException(status_code=403, detail="Invalid voting token")
    
    # Check if this token has voted
    stmt = select(Ballot).where(
        Ballot.poll_id == poll.id,
        Ballot.voter_token == voter_token
    )
    result = await db.execute(stmt)
    ballot = result.scalar_one_or_none()
    
    if ballot:
        # Return the ballot data
        return {
            "has_voted": True,
            "ballot": {
                "id": str(ballot.id),
                "submitted_at": ballot.submitted_at.isoformat() if ballot.submitted_at else None,
                "rankings": ballot.rankings,
                "write_ins": ballot.write_ins if hasattr(ballot, 'write_ins') else []
            }
        }
    else:
        return {
            "has_voted": False,
            "ballot": None
        }