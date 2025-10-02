import random
import string
from datetime import datetime
from db import get_db
from config import load_config

def _generate_member_id():
    """Generate a unique member ID."""
    timestamp = int(datetime.utcnow().timestamp())
    random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"N{timestamp}-{random_suffix}"

def register_member(ref_code: str | None = None):
    """Register a new member and return (member_id, fee, parent_id, level)."""
    cfg = load_config()
    entry_fee = cfg["entry_fee"]
    max_levels = cfg["max_levels"]
    branching = cfg["branching"]
    market_cap = cfg["market_cap_limit"]

    # Capacity check
    with get_db() as con:
        total = con.execute("SELECT COUNT(*) FROM members").fetchone()[0]
        if total >= market_cap:
            raise RuntimeError("Market cap reached – no more registrations allowed.")

        # Decide parent / level
        parent_id = None
        level = 1
        
        if ref_code:
            # Validate referral code
            parent = con.execute(
                "SELECT id, level FROM members WHERE id = ?", 
                (ref_code,)
            ).fetchone()
            
            if parent:
                parent_id = ref_code
                level = parent["level"] + 1
                
                # Check if parent has reached branching limit
                child_count = con.execute(
                    "SELECT COUNT(*) FROM members WHERE parent = ?",
                    (parent_id,)
                ).fetchone()[0]
                
                if child_count >= branching:
                    raise RuntimeError(f"Referral code {ref_code} has reached maximum referrals.")
                
                if level > max_levels:
                    raise RuntimeError(f"Maximum level ({max_levels}) reached.")
            else:
                raise RuntimeError(f"Invalid referral code: {ref_code}")
        else:
            # Auto-assign to a parent with available slots
            if total > 0:
                available_parents = con.execute(
                    """
                    SELECT m.id, m.level, COUNT(c.id) as child_count
                    FROM members m
                    LEFT JOIN members c ON c.parent = m.id
                    WHERE m.level < ?
                    GROUP BY m.id, m.level
                    HAVING child_count < ?
                    ORDER BY m.level, m.joined_at
                    LIMIT 1
                    """,
                    (max_levels, branching)
                ).fetchone()
                
                if available_parents:
                    parent_id = available_parents["id"]
                    level = available_parents["level"] + 1

        # Generate unique member ID
        member_id = _generate_member_id()
        
        # Insert new member
        con.execute(
            "INSERT INTO members (id, level, parent, joined_at, paid, payout) "
            "VALUES (?,?,?,?,0,0)",
            (member_id, level, parent_id, int(datetime.utcnow().timestamp())),
        )
        con.commit()
    
    return member_id, entry_fee, parent_id, level

def distribute_payouts(new_member_id: str):
    """Distribute payouts to upline members."""
    cfg = load_config()
    ratio = cfg["payout_ratio"] / 100.0
    depth = cfg.get("payout_depth", 3)

    try:
        with get_db() as con:
            # Get inflow amount
            inflow_row = con.execute(
                "SELECT amount FROM transactions WHERE member_id = ? AND type='inflow' "
                "ORDER BY ts DESC LIMIT 1",
                (new_member_id,),
            ).fetchone()
            
            if not inflow_row:
                return
            
            inflow = inflow_row["amount"]
            pool = inflow * ratio
            
            # Distribution weights: 50%, 30%, 20%
            weights = [0.5, 0.3, 0.2]
            
            # Traverse upline
            current_id = new_member_id
            lvl = 0
            
            while lvl < depth:
                parent_row = con.execute(
                    "SELECT parent FROM members WHERE id = ?", 
                    (current_id,)
                ).fetchone()
                
                if not parent_row or not parent_row["parent"]:
                    break
                
                parent_id = parent_row["parent"]
                weight = weights[lvl] if lvl < len(weights) else 0.1
                share = pool * weight
                
                # Update parent payout
                con.execute(
                    "UPDATE members SET payout = payout + ? WHERE id = ?",
                    (share, parent_id),
                )
                
                # Record outflow transaction
                con.execute(
                    "INSERT INTO transactions (member_id, type, amount, ts) "
                    "VALUES (?,?,?,?)",
                    (parent_id, "outflow", int(share), 
                     int(datetime.utcnow().timestamp())),
                )
                
                current_id = parent_id
                lvl += 1
            
            con.commit()
    except Exception as e:
        print(f"Error distributing payouts: {e}")
        raise
